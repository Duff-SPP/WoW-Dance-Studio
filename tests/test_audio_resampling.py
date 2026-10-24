import array
import random
import unittest
from unittest.mock import patch
from studio_core.client_audio import resample,resample_reference


class PCMFastTests(unittest.TestCase):
    def test_reference_fallback_without_numpy(self):
        data=array.array('h',[0,32767,-32768,17])
        with patch.dict('sys.modules',{'numpy':None}):
            self.assertEqual(resample(data,2,48000,2),resample_reference(data,2,48000,2))
    def test_exact_pcm_for_rates_channels_and_chunk_boundaries(self):
        rng=random.Random(731)
        for rate in (8000,22050,44100,48000,96000):
            for channels in (1,2):
                for frames in (1,137,72001):
                    data=array.array('h',(rng.randint(-32768,32767) for _ in range(frames*channels)))
                    with self.subTest(rate=rate,channels=channels,frames=frames):
                        self.assertEqual(resample(data,channels,rate,frames),resample_reference(data,channels,rate,frames))
