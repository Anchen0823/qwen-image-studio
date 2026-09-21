"""Isolated GPU worker. The desktop process never imports torch."""
import json
import os
import sys
import time
from pathlib import Path


def emit(kind, **data):
    print('@workbench ' + json.dumps(dict(kind=kind, **data), ensure_ascii=False), flush=True)


def run(spec):
    base = Path(spec['model_base'])
    os.environ.update(HF_HUB_OFFLINE='1', HF_HOME=str(base / 'cache/huggingface'),
                      MODELSCOPE_CACHE=str(base / 'cache/modelscope'))
    import torch
    from PIL import Image, ImageOps
    from diffsynth.pipelines.qwen_image_21 import QwenImage21Pipeline, ModelConfig
    from vae_decode import install_context_decoder
    if not torch.cuda.is_available():
        raise RuntimeError('未检测到可用的 NVIDIA CUDA 显卡。')
    root = base / 'models/Qwen/Qwen-Image-2.1'
    free, total = torch.cuda.mem_get_info()
    limit = min(total / 1024**3 - .8, free / 1024**3 - .5)
    if limit < 2:
        raise RuntimeError('可用显存不足 2GB，请关闭其他占用显卡的软件后重试。')
    emit('status', text=f'正在加载模型 · 显存预算 {limit:.1f} GB')
    config = dict(offload_dtype='disk', offload_device='disk', onload_dtype='disk',
                  onload_device='disk', preparing_dtype=torch.bfloat16,
                  preparing_device='cuda', computation_dtype=torch.bfloat16,
                  computation_device='cuda')
    configs = []
    for pattern in ['transformer/diffusion_pytorch_model*.safetensors',
                    'text_encoder/model*.safetensors', 'vae/diffusion_pytorch_model*.safetensors']:
        files = sorted(str(p) for p in root.glob(pattern))
        if not files:
            raise FileNotFoundError(f'模型文件缺失：{root / pattern}')
        configs.append(ModelConfig(path=files, **config))
    pipe = QwenImage21Pipeline.from_pretrained(torch_dtype=torch.bfloat16, device='cuda',
        model_configs=configs, processor_config=ModelConfig(path=str(root / 'processor')), vram_limit=limit)
    install_context_decoder(pipe.vae, lambda text: emit('status', text=text))
    emit('status', text='正在编码提示词 / 参考图')
    def progress(items):
        count = len(items)
        for i, item in enumerate(items):
            emit('progress', step=i, total=count)
            yield item
        emit('progress', step=count, total=count)
    reference = None
    if spec.get('edit'):
        with Image.open(spec['edit']) as source:
            reference = ImageOps.exif_transpose(source).convert('RGB')
    image = pipe(prompt=spec['prompt'], width=spec['width'], height=spec['height'],
                 num_inference_steps=spec['steps'], seed=spec['seed'], tiled=True,
                 # These settings apply to reference encoding. Output decoding
                 # uses context tiles and excludes their artificial boundaries.
                 tile_size=512, tile_stride=384,
                 edit_image=reference, progress_bar_cmd=progress)
    emit('status', text='正在保存图片')
    output = Path(spec['output'])
    temporary = output.with_suffix('.png.tmp')
    image.save(temporary, format='PNG')
    temporary.replace(output)
    emit('done', output=spec['output'])


if __name__ == '__main__':
    try:
        run(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
    except Exception as error:
        import traceback
        traceback.print_exc()
        emit('error', text=str(error))
        sys.exit(1)
