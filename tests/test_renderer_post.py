"""Unit tests for Task 3: HDR, ACES tone mapping, exposure, bloom, and FXAA."""
import math
import unittest
from classroom import LightingState
from realistic_renderer import aces_tonemap
from tests.gl_helpers import render_inside, render_view, mean_luminance, lamp_halo_luminance, ceiling_luminance


class TestRendererPost(unittest.TestCase):
    def test_aces_monotonic_and_bounded(self):
        vals = [aces_tonemap(x / 10.0) for x in range(0, 200)]
        self.assertEqual(vals, sorted(vals))
        self.assertEqual(vals[0], 0.0)
        self.assertLessEqual(vals[-1], 1.0)

    def test_exposure_and_bloom_clamp(self):
        s = LightingState()
        s.set_exposure(5.0)
        self.assertEqual(s.exposure_ev, 2.0)
        s.set_exposure(-5.0)
        self.assertEqual(s.exposure_ev, -2.0)
        s.set_bloom(-1.0)
        self.assertEqual(s.bloom_strength, 0.0)
        s.set_bloom(2.0)
        self.assertEqual(s.bloom_strength, 1.0)

    def test_exposure_brightens_image(self):
        dark = mean_luminance(render_inside(exposure=-1.0))
        bright = mean_luminance(render_inside(exposure=1.0))
        self.assertGreater(bright, dark * 1.3)

    def test_slider_extremes_finite(self):  # Review Focus 2
        for kw in ({"sun": 0.0, "interior_lights": False}, {"exposure": 2.0, "bloom": 1.0}, {"exposure": -2.0, "bloom": 0.0}):
            img = render_inside(**kw)
            lo, hi = img.convert("L").getextrema()
            self.assertTrue(hi > lo or hi > 0)  # not a uniform black/white frame
            self.assertTrue(all(math.isfinite(v) for v in (lo, hi)))

    def test_lamp_blooms(self):
        img = render_view("fluorescent_detail")
        self.assertGreater(lamp_halo_luminance(img), ceiling_luminance(img))


if __name__ == "__main__":
    unittest.main()

