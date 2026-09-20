"""Durable, process-safe queue shared by the desktop and agent CLI."""
import json
import os
import re
import secrets
import sqlite3
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL = Path(os.environ.get('QWEN_MODEL_DIR', r'D:\AI\Qwen-Image-2.1'))
TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}


def split_prompts(text):
    return [part.strip() for part in re.split(r'(?m)^\s*---\s*$', text) if part.strip()]


def validate(prompt, width=512, height=512, steps=40, seed=-1, edit=''):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError('请输入画面描述。')
    w, h, n, s = int(width), int(height), int(steps), int(seed)
    if any(v < 256 or v > 1536 or v % 16 for v in (w, h)):
        raise ValueError('宽高必须为 256–1536 之间的 16 的倍数。')
    if not 1 <= n <= 100:
        raise ValueError('步数必须为 1–100。')
    if s == -1:
        s = secrets.randbelow(2**32)
    if not 0 <= s < 2**32:
        raise ValueError('种子必须为 0–4294967295，或 -1 随机。')
    if edit:
        edit = str(Path(edit).resolve())
        if not Path(edit).is_file():
            raise ValueError(f'参考图不存在：{edit}')
        from PIL import Image
        with Image.open(edit) as im:
            im.verify()
    return dict(prompt=prompt.strip(), width=w, height=h, steps=n, seed=s, edit=edit)


class Store:
    def __init__(self, root=ROOT, model=MODEL):
        self.root, self.model = Path(root).resolve(), Path(model).resolve()
        self.state = self.root / '.state'
        self.state.mkdir(parents=True, exist_ok=True)
        self.outputs = self.root / 'outputs'
        self.outputs.mkdir(exist_ok=True)
        self.db = self.state / 'queue.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, spec TEXT NOT NULL, status TEXT NOT NULL,
                  created REAL NOT NULL, started REAL, finished REAL,
                  progress INTEGER DEFAULT 0, phase TEXT DEFAULT '',
                  error TEXT DEFAULT '', cancel INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
                INSERT OR IGNORE INTO settings VALUES ('paused', '0');
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, specs):
        # Validate the whole batch before inserting anything.
        prepared = []
        if not specs or len(specs) > 200:
            raise ValueError('一次请输入 1–200 个任务。')
        for spec in specs:
            value = validate(**spec)
            key = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(4)
            value.update(model_base=str(self.model), output=str(self.outputs / f'{key}.png'))
            prepared.append((key, json.dumps(value, ensure_ascii=False), 'queued', time.time()))
        with self.connect() as db:
            db.executemany('INSERT INTO jobs (id,spec,status,created) VALUES (?,?,?,?)', prepared)
        return [row[0] for row in prepared]

    @staticmethod
    def decode(row):
        value = dict(row)
        value['spec'] = json.loads(value['spec'])
        return value

    def list(self):
        with self.connect() as db:
            return [self.decode(row) for row in db.execute('SELECT * FROM jobs ORDER BY rowid')]

    def get(self, key):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()
        if row is None:
            raise ValueError(f'任务不存在：{key}')
        return self.decode(row)

    def update(self, key, **values):
        allowed = {'status', 'started', 'finished', 'progress', 'phase', 'error', 'cancel'}
        if not values or not set(values) <= allowed:
            raise ValueError('Invalid queue fields')
        with self.connect() as db:
            db.execute('UPDATE jobs SET ' + ','.join(f'{k}=?' for k in values) + ' WHERE id=?',
                       [*values.values(), key])

    @property
    def paused(self):
        with self.connect() as db:
            return db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0] == '1'

    def pause(self, enabled=True):
        with self.connect() as db:
            db.execute("UPDATE settings SET value=? WHERE key='paused'", ('1' if enabled else '0',))

    def cancel(self, key):
        with self.connect() as db:
            if db.execute('SELECT id FROM jobs WHERE id=?', (key,)).fetchone() is None:
                raise ValueError(f'任务不存在：{key}')
            db.execute("UPDATE jobs SET cancel=1 WHERE id=? AND status='running'", (key,))
            db.execute("UPDATE jobs SET status='cancelled',finished=? WHERE id=? AND status='queued'", (time.time(), key))

    def retry(self, key):
        with self.connect() as db:
            result = db.execute("UPDATE jobs SET status='queued',cancel=0,progress=0,error='',phase='',started=NULL,finished=NULL WHERE id=? AND status IN ('failed','cancelled','interrupted')", (key,))
        if result.rowcount == 0:
            raise ValueError('只能重试失败、已取消或中断的任务。')


class Runner:
    """One OS lock owns all GPU work, including GUI/CLI contention."""
    def __init__(self, store, command=None):
        self.store = store
        self.command = command
        self.stop_event = threading.Event()
        self.thread = None
        self.last_error = ''

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.drain, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    @contextmanager
    def lock(self):
        path = self.store.state / 'runner.lock'
        stream = path.open('a+b')
        acquired = False
        try:
            if path.stat().st_size == 0:
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                except OSError:
                    pass
            else:
                import fcntl
                try:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError:
                    pass
            yield acquired
        finally:
            if acquired and os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            stream.close()

    def drain(self):
        self.last_error = ''
        try:
            with self.lock() as acquired:
                if not acquired:
                    return False
                # Only the OS-lock owner may recover abandoned running jobs.
                for job in self.store.list():
                    if job['status'] == 'running':
                        output = Path(job['spec']['output'])
                        if output.exists():
                            self.store.update(job['id'], status='completed', finished=time.time(), progress=100,
                                              phase='已恢复保存的作品')
                        else:
                            self.store.update(job['id'], status='interrupted', finished=time.time(),
                                              error='上次运行中断，可选中任务重试。')
                        self.snapshot(job['id'])
                while not self.stop_event.is_set() and not self.store.paused:
                    jobs = [j for j in self.store.list() if j['status'] == 'queued']
                    if not jobs:
                        break
                    job = jobs[0]
                    with self.store.connect() as db:
                        claimed = db.execute("UPDATE jobs SET status='running',started=?,phase='正在启动' WHERE id=? AND status='queued'", (time.time(), job['id'])).rowcount
                    if claimed:
                        self.execute(job)
                return True
        except Exception as error:
            self.last_error = str(error)
            return False

    def snapshot(self, key):
        job = self.store.get(key)
        metadata = dict(job['spec'], status=job['status'], id=key,
                        created=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(job['created'])),
                        error=job['error'], seconds=round((job['finished'] or time.time()) - (job['started'] or time.time()), 1))
        path = Path(job['spec']['output']).with_suffix('.json')
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(path)
        return path

    def execute(self, job):
        key, proc = job['id'], None
        interrupted = False
        try:
            spec_path = self.snapshot(key)
            command = self.command or [str(self.store.model / '.venv/Scripts/python.exe'), '-u', str(ROOT / 'worker.py')]
            env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
            proc = subprocess.Popen([*command, str(spec_path)], cwd=ROOT, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            def read():
                with proc.stdout as lines, Path(job['spec']['output']).with_suffix('.log').open('w', encoding='utf-8') as log:
                    for line in lines:
                        log.write(line)
                        log.flush()
                        if line.startswith('@workbench '):
                            try:
                                event = json.loads(line[11:])
                                if event['kind'] == 'progress':
                                    self.store.update(key, progress=int(event['step'] / event['total'] * 100),
                                                      phase=f"采样 {event['step']} / {event['total']}")
                                elif event['kind'] == 'status':
                                    self.store.update(key, phase=event['text'])
                                elif event['kind'] == 'error':
                                    self.store.update(key, error=event['text'])
                            except (ValueError, KeyError, ZeroDivisionError):
                                pass
            reader = threading.Thread(target=read, daemon=True)
            reader.start()
            while proc.poll() is None:
                if self.stop_event.is_set() or self.store.get(key)['cancel']:
                    interrupted = self.stop_event.is_set()
                    self.terminate(proc)
                    break
                time.sleep(.15)
            proc.wait()
            reader.join()
            if Path(job['spec']['output']).exists() and proc.returncode == 0:
                state = 'completed'
            elif interrupted:
                state = 'interrupted'
            elif self.store.get(key)['cancel']:
                state = 'cancelled'
            else:
                state = 'failed'
            error = self.store.get(key)['error']
            if state == 'failed' and not error:
                error = f'推理进程退出码 {proc.returncode}，请查看任务日志。'
            self.store.update(key, status=state, finished=time.time(), error=error,
                              progress=100 if state == 'completed' else self.store.get(key)['progress'])
        except KeyboardInterrupt:
            if proc is not None and proc.poll() is None:
                self.terminate(proc)
            self.store.update(key, status='interrupted', finished=time.time(), error='命令行运行被中断。')
            raise
        except Exception as error:
            if proc is not None and proc.poll() is None:
                self.terminate(proc)
            self.store.update(key, status='failed', finished=time.time(), error=str(error))
        finally:
            self.snapshot(key)

    @staticmethod
    def terminate(proc):
        if proc.poll() is not None:
            return
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
