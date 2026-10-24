import struct
import unittest
from studio_core.loop_regions import encode


class LoopRegionTests(unittest.TestCase):
    def test_combined_models_share_identical_clock(self):
        data=encode([(1798,10367,3400),(1798,10367,3400)])
        self.assertEqual(data[:8],b'WDSLOOP1')
        self.assertEqual(struct.unpack('<IIII',data[8:]),(1,1798,10367,3400))

    def test_conflicting_model_clocks_are_blocked(self):
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            encode([(1798,10367,3400),(1798,10368,3400)])

    def test_invalid_or_stock_regions_are_blocked(self):
        for row in [(69,10367,3400),(65536,10367,3400),(1798,0,0),(1798,10,10),(1798,10,-1)]:
            with self.assertRaises(ValueError):encode([row])


if __name__=='__main__':unittest.main()
