import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vae_decode import decode_with_context, install_context_decoder


class ContextDecodeTests(unittest.TestCase):
    def test_matches_full_local_decoder_on_rectangles_and_partial_tiles(self):
        torch.manual_seed(31)
        def decoder(z, *, tiled):
            self.assertFalse(tiled)
            return F.interpolate(F.avg_pool2d(z, 3, stride=1, padding=1),
                                 scale_factor=2, mode='nearest')
        # Includes alpha, multiple batches, edge tiles, and images below one tile.
        for shape in [(2, 4, 13, 19), (1, 4, 1, 3), (1, 4, 16, 16)]:
            z = torch.randn(shape)
            expected = decoder(z, tiled=False)
            result = decode_with_context(decoder, z, core_size=8, context=4, scale=2)
            self.assertTrue(torch.equal(result, expected))
            self.assertEqual(result.device.type, 'cpu')
        z = torch.randn(1, 4, 7, 11)
        self.assertTrue(torch.equal(decode_with_context(decoder, z, core_size=8, context=4, scale=2),
                                    decoder(z, tiled=False)))

    def test_rejects_invalid_dimensions_and_decode_scale(self):
        z = torch.zeros(1, 4, 3, 3)
        for kwargs in [dict(core_size=0),dict(context=0),dict(core_size=15),dict(scale=0)]:
            with self.assertRaises(ValueError):
                decode_with_context(lambda z, **k:z, z, **kwargs)
        with self.assertRaises(ValueError):
            decode_with_context(lambda z, **k:z, z, core_size=32, context=16, scale=16)
        with self.assertRaises(ValueError):
            decode_with_context(lambda z, **k:z, z.unsqueeze(2))

    def test_oom_retries_same_latent_and_non_oom_errors_propagate(self):
        class VAE:
            scale_factor_spatial = 8  # Stale upstream metadata must be ignored.
            spatial_compression_ratio = 16
            patch_size = None
            decode = staticmethod(lambda z, **k:z)
            clear_cache = staticmethod(lambda:None)
        vae, z, messages = VAE(), torch.zeros(1,64,8,8), []
        install_context_decoder(vae,messages.append)
        with patch('vae_decode.decode_with_context',side_effect=[torch.OutOfMemoryError(), z]) as call, patch('vae_decode.torch.cuda.empty_cache'):
            self.assertIs(vae.decode(z,tiled=True),z)
            self.assertEqual(call.call_count,2)
            self.assertIs(call.call_args_list[0].args[1],z)
            self.assertIs(call.call_args_list[1].args[1],z)
            self.assertEqual(call.call_args.kwargs['context'],128)
            self.assertEqual(call.call_args.kwargs['scale'],16)
        with patch('vae_decode.decode_with_context',side_effect=ValueError('bad model')) as call:
            with self.assertRaisesRegex(ValueError,'bad model'):
                vae.decode(z)
            self.assertEqual(call.call_count,1)


if __name__ == '__main__':
    unittest.main()
