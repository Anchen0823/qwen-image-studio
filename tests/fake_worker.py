"""Deterministic queue integration fixture; never used by production UI/CLI."""
import json
import sys
import time
from pathlib import Path
from PIL import Image

spec = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
active = Path(spec['output']).parent / 'active-worker'
active.mkdir()  # Fails if two workers overlap in the same test workspace.
try:
    for i in range(5):
        print('@workbench ' + json.dumps(dict(kind='progress', step=i, total=5)), flush=True)
        time.sleep(.15 if spec['prompt'] != 'slow' else .5)
    if spec['prompt'] == 'fail':
        print('@workbench ' + json.dumps(dict(kind='error', text='Intentional fixture failure')), flush=True)
        sys.exit(3)
    Image.new('RGB', (spec['width'], spec['height']), '#b5a2ff').save(spec['output'])
finally:
    active.rmdir()
