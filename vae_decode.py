"""Decode image latents with context, excluding artificial tile boundaries."""
import gc

import torch


@torch.no_grad()
def decode_with_context(decode, latents, *, core_size=256, context=256, scale=16):
    """Keep only each tile's center; preserve the real outer image boundaries.

    Sizes are output pixels. The default maximum decoded tile is 768px.
    Assemble on CPU so decoded tiles and the canvas do not accumulate on GPU.
    This is image-only and retains every decoded channel, including alpha.
    """
    if latents.ndim != 4 or min(latents.shape) <= 0:
        raise ValueError('Context decoding requires non-empty BCHW image latents')
    if (scale <= 0 or core_size <= 0 or context <= 0
            or core_size % scale or context % scale):
        raise ValueError('Tile sizes must be positive multiples of the VAE scale')
    height, width = latents.shape[-2:]
    step, margin = core_size // scale, context // scale
    canvas = None
    for y in range(0, height, step):
        for x in range(0, width, step):
            end_y, end_x = min(y + step, height), min(x + step, width)
            start_y, start_x = max(0, y - margin), max(0, x - margin)
            stop_y, stop_x = min(height, end_y + margin), min(width, end_x + margin)
            tile = decode(latents[..., start_y:stop_y, start_x:stop_x], tiled=False)
            expected = ((stop_y - start_y) * scale, (stop_x - start_x) * scale)
            if tile.ndim != 4 or tile.shape[0] != latents.shape[0] or tile.shape[-2:] != expected:
                raise ValueError('Unexpected VAE output shape or spatial scale')
            if canvas is None:
                canvas = torch.empty((*tile.shape[:-2], height * scale, width * scale),
                                     dtype=tile.dtype, device='cpu')
            elif tile.shape[1] != canvas.shape[1] or tile.dtype != canvas.dtype:
                raise ValueError('Inconsistent VAE output channels or dtype')
            canvas[..., y*scale:end_y*scale, x*scale:end_x*scale] = tile[
                ..., (y-start_y)*scale:(end_y-start_y)*scale,
                (x-start_x)*scale:(end_x-start_x)*scale].cpu()
            del tile
    return canvas


def install_context_decoder(vae, status):
    """Replace only image decoding; reference-image encoding stays unchanged."""
    native_decode = vae.decode
    # DiffSynth's informational scale_factor_spatial may retain its default
    # value (8) even when the loaded decoder actually upsamples by 16.
    scale = vae.spatial_compression_ratio * (vae.patch_size or 1)

    def decode(latents, **_options):
        status('正在解码图片 · 上下文分块')
        try:
            return decode_with_context(native_decode, latents, scale=scale)
        except torch.OutOfMemoryError:
            # Retry only decoding, with the same latent and a smaller halo.
            vae.clear_cache()
            gc.collect()
            torch.cuda.empty_cache()
        status('显存紧张 · 使用较小上下文解码')
        return decode_with_context(native_decode, latents, context=128, scale=scale)

    vae.decode = decode
