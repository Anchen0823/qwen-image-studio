import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ROOT, Runner, Store, split_prompts, validate


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def runner(self):
        return Runner(self.store, [sys.executable, str(ROOT / 'tests/fake_worker.py')])

    def until(self, condition, timeout=10):
        end = time.monotonic() + timeout
        while not condition() and time.monotonic() < end:
            time.sleep(.04)
        self.assertTrue(condition())

    def test_multiline_and_atomic_validation(self):
        self.assertEqual(split_prompts('第一行\n第二行\n---\n另一任务\n\n---\n'), ['第一行\n第二行', '另一任务'])
        self.assertEqual(split_prompts('a---b'), ['a---b'])
        with self.assertRaises(ValueError):
            self.store.add([dict(prompt='valid'), dict(prompt='bad', width=513)])
        self.assertEqual(self.store.list(), [])
        self.assertEqual(validate('ok', seed=42)['seed'], 42)
        with self.assertRaises(ValueError):
            validate('ok', steps=0)

    def test_sequential_failure_continuation_and_snapshots(self):
        keys = self.store.add([dict(prompt=p, steps=1) for p in ['one', 'fail', 'three']])
        self.assertTrue(self.runner().drain())
        jobs = [self.store.get(k) for k in keys]
        self.assertEqual([j['status'] for j in jobs], ['completed', 'failed', 'completed'])
        self.assertLessEqual(jobs[0]['finished'], jobs[1]['started'])
        self.assertLessEqual(jobs[1]['finished'], jobs[2]['started'])
        self.assertIn('Intentional', jobs[1]['error'])
        for job in jobs:
            meta = json.loads(Path(job['spec']['output']).with_suffix('.json').read_text(encoding='utf-8'))
            self.assertEqual(meta['status'], job['status'])

    def test_pause_persists_and_queued_cancellation(self):
        keys = self.store.add([dict(prompt='one'), dict(prompt='two')])
        self.store.pause()
        self.store.cancel(keys[0])
        self.runner().drain()
        reopened = Store(self.temp.name)
        self.assertTrue(reopened.paused)
        self.assertEqual(reopened.get(keys[0])['status'], 'cancelled')
        self.assertEqual(reopened.get(keys[1])['status'], 'queued')
        reopened.pause(False)
        self.runner().drain()
        self.assertEqual(reopened.get(keys[1])['status'], 'completed')

    def test_only_one_runner(self):
        self.store.add([dict(prompt='one'), dict(prompt='two')])
        first, second = self.runner(), self.runner()
        first.start()
        self.until(lambda: any(j['status']=='running' for j in self.store.list()))
        self.assertFalse(second.drain())
        first.thread.join(10)
        self.assertFalse(first.thread.is_alive())
        self.assertTrue(all(j['status']=='completed' for j in self.store.list()))

    def test_running_cancel_and_retry(self):
        key = self.store.add([dict(prompt='slow')])[0]
        runner = self.runner()
        runner.start()
        self.until(lambda: self.store.get(key)['progress'] > 0)
        self.store.cancel(key)
        runner.thread.join(10)
        self.assertFalse(runner.thread.is_alive())
        self.assertEqual(self.store.get(key)['status'], 'cancelled')
        # A killed fixture cannot execute its finally cleanup.
        active = self.store.outputs / 'active-worker'
        if active.exists():
            active.rmdir()
        self.store.retry(key)
        self.runner().drain()
        self.assertEqual(self.store.get(key)['status'], 'completed')

    def test_pause_during_work_and_interrupted_recovery(self):
        keys = self.store.add([dict(prompt='one'), dict(prompt='two')])
        runner = self.runner()
        runner.start()
        self.until(lambda: self.store.get(keys[0])['status']=='running')
        self.store.pause()
        runner.thread.join(10)
        self.assertEqual(self.store.get(keys[0])['status'], 'completed')
        self.assertEqual(self.store.get(keys[1])['status'], 'queued')
        self.store.update(keys[1], status='running', started=time.time())
        self.runner().drain()
        self.assertEqual(self.store.get(keys[1])['status'], 'interrupted')

    def test_cli_json_protocol(self):
        command = [sys.executable, str(ROOT/'qwen_cli.py'), '--workspace', self.temp.name]
        result = subprocess.run([*command, 'submit', '--prompt', '多行\n任务'], capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        key = json.loads(result.stdout)['ids'][0]
        result = subprocess.run([*command, 'status', '--id', key], capture_output=True, encoding='utf-8')
        self.assertEqual(json.loads(result.stdout)['spec']['prompt'], '多行\n任务')
        result = subprocess.run([*command, 'status', '--id', 'missing'], capture_output=True, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('error', json.loads(result.stdout))


if __name__=='__main__':
    unittest.main(verbosity=2)
