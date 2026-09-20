"""Explicit real GPU test: two 512px tasks through the new shared queue."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ROOT, Store, Runner
from PIL import Image

store = Store(ROOT/'verification/gpu-queue')
ids = store.add([dict(prompt='一只橘猫坐在窗边，温暖阳光，精致插画。', steps=2, seed=42),
                 dict(prompt='一只陶瓷咖啡杯，奶油色背景，柔和光线，静物摄影。', steps=2, seed=43)])
store.pause(False)
runner = Runner(store)
assert runner.drain(), runner.last_error
for key in ids:
    job = store.get(key)
    assert job['status']=='completed', job
    with Image.open(job['spec']['output']) as im:
        assert im.size==(512,512)
    print(f"{key}: completed in {job['finished']-job['started']:.1f}s", flush=True)
