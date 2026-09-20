"""Visible layout, Chinese wrapping, batch snapshot, and UI queue integration."""
import sys
import tempfile
import time
from pathlib import Path
from PIL import ImageGrab
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ROOT, Store, Runner
from workbench import Studio

with tempfile.TemporaryDirectory() as folder:
    app = Studio(Store(folder), autorun=False)
    app.runner = Runner(app.store, [sys.executable, str(ROOT/'tests/fake_worker.py')])
    app.update()
    long_prompt = '雨后黄昏的江南街巷，暖色灯光倒映在青石板上，远处有人撑着纸伞走过。电影摄影，自然光，细腻质感，画面应安静而有故事感。'
    app.set_mode(True)
    app.set_prompt(long_prompt + '\n保留自然的光影与细节。\n---\n一只橘猫坐在窗边看星空，温暖灯光，精致绘本插画。')
    app.update()
    before = app.prompt.get('1.0','end-1c')
    ids = app.submit()
    assert len(ids)==2
    assert app.store.get(ids[0])['spec']['prompt'].endswith('保留自然的光影与细节。')
    app.width_var.set('768')
    assert app.store.get(ids[0])['spec']['width']==512
    app.width_var.set('512')
    real_images = list((ROOT/'outputs').glob('*.png'))
    if real_images:
        app.show_image(real_images[0])
    target = ROOT/'verification'
    target.mkdir(exist_ok=True)
    for w,h in [(1180,820),(1440,940)]:
        app.geometry(f'{w}x{h}')
        app.update()
        assert app.prompt.count('1.0','1.end','displaylines')[0] >= 2, 'Long Chinese prompt did not wrap'
        assert app.prompt.winfo_width() < 430
        assert app.prompt.winfo_height() >= 145, 'Prompt editor was squeezed too short'
        assert app.generate_button.winfo_height() > 35
        assert app.generate_button.winfo_rooty()+app.generate_button.winfo_height() < app.winfo_rooty()+h
        assert app.prompt.get('1.0','end-1c')==before
        ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+w,app.winfo_rooty()+h)).save(target/f'studio-{w}.png')
    app.jobs.selection_set(ids[0])
    app.details()
    app.update()
    for child in app.winfo_children():
        if child.winfo_class()=='Toplevel':
            child.destroy()
    app.runner.start()
    end = time.monotonic()+15
    while app.runner.thread.is_alive() and time.monotonic()<end:
        app.update()
        time.sleep(.05)
    assert not app.runner.thread.is_alive()
    app.refresh_jobs()
    assert all(app.store.get(key)['status']=='completed' for key in ids)
    assert len(app.history_paths)==2
    app.destroy()
print('PASS: Chinese wrapping, small/large layout, immutable batch parameters, task details, two sequential UI jobs, preview/history.')
