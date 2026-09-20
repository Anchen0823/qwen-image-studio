"""Machine-readable interface. stdout is JSON; model logs stay on disk."""
import argparse
import json
import sys
import time
from pathlib import Path
from engine import Store, Runner, ROOT, MODEL, TERMINAL, split_prompts


def main(argv=None):
    parser = argparse.ArgumentParser(description='Qwen Image local persistent queue')
    parser.add_argument('--workspace', type=Path, default=ROOT)
    parser.add_argument('--model-dir', type=Path, default=MODEL)
    sub = parser.add_subparsers(dest='command', required=True)
    add = sub.add_parser('submit')
    group = add.add_mutually_exclusive_group(required=True)
    group.add_argument('--prompt')
    group.add_argument('--prompt-file', type=Path, help='UTF-8 prompts separated by a line containing ---')
    group.add_argument('--batch', type=Path, help='UTF-8 JSON array of task parameter objects')
    for name, default in [('width', 512), ('height', 512), ('steps', 40), ('seed', -1)]:
        add.add_argument('--' + name, type=int, default=default)
    add.add_argument('--edit', default='')
    status = sub.add_parser('status')
    status.add_argument('--id')
    for name in ['cancel', 'retry']:
        sub.add_parser(name).add_argument('id')
    for name in ['run', 'pause', 'resume']:
        sub.add_parser(name)
    wait = sub.add_parser('wait')
    wait.add_argument('ids', nargs='+')
    wait.add_argument('--timeout', type=float, default=60)
    args = parser.parse_args(argv)
    store = Store(args.workspace, args.model_dir)
    if args.command == 'submit':
        if args.batch:
            specs = json.loads(args.batch.read_text(encoding='utf-8-sig'))
            if not isinstance(specs, list) or not all(isinstance(x, dict) for x in specs):
                raise ValueError('Batch must be a JSON array of task objects')
        else:
            prompts = split_prompts(args.prompt_file.read_text(encoding='utf-8-sig')) if args.prompt_file else [args.prompt]
            specs = [dict(prompt=p, width=args.width, height=args.height, steps=args.steps, seed=args.seed, edit=args.edit) for p in prompts]
        result = dict(ids=store.add(specs), paused=store.paused)
    elif args.command == 'status':
        result = store.get(args.id) if args.id else dict(paused=store.paused, jobs=store.list())
    elif args.command == 'run':
        runner = Runner(store)
        try:
            acquired = runner.drain()
        except KeyboardInterrupt:
            runner.stop()
            raise
        if runner.last_error:
            raise RuntimeError(runner.last_error)
        jobs = store.list()
        result = dict(runner_acquired=acquired, paused=store.paused, jobs=jobs)
    elif args.command == 'wait':
        deadline = time.monotonic() + max(0, args.timeout)
        while True:
            jobs = [store.get(key) for key in args.ids]
            if all(j['status'] in TERMINAL for j in jobs) or time.monotonic() >= deadline:
                break
            time.sleep(.3)
        result = dict(done=all(j['status'] in TERMINAL for j in jobs), jobs=jobs)
    elif args.command in ('cancel', 'retry'):
        getattr(store, args.command)(args.id)
        result = store.get(args.id)
    else:
        store.pause(args.command == 'pause')
        result = dict(paused=store.paused)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps(dict(error=str(error)), ensure_ascii=False))
        sys.exit(1)
