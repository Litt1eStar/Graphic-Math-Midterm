"""Unit tests for Task 2: PBR scene shader, MATERIALS table, and fixed-function lighting removal."""
import math
import unittest
from pathlib import Path
from classroom import COLORS, MATERIALS, load_config
from realistic_renderer import sun_direction
from tests.gl_helpers import render_inside, mean_luminance


class TestRendererScene(unittest.TestCase):
    def test_every_colour_has_material(self):
        self.assertEqual(set(MATERIALS), set(COLORS))
        for rough, spec, bump in MATERIALS.values():
            for v in (rough, spec, bump):
                self.assertTrue(0.0 <= v <= 1.0)

    def test_sun_direction_points_from_window_side(self):
        room = load_config(Path("room_config.json"))["room"]
        for preset in ("daylight", "sunset"):
            d = sun_direction(preset, room)
            self.assertAlmostEqual(sum(c * c for c in d), 1.0, places=5)
            self.assertGreater(d[0], 0)  # sun outside the X = width window wall
        self.assertGreater(
            sun_direction("daylight", room)[2],
            sun_direction("sunset", room)[2],
        )  # sunset is lower

    def test_no_fixed_function_lighting_left(self):
        src = Path("classroom.py").read_text(encoding="utf-8")
        for token in ("glLightfv", "glMaterial", "GL_LIGHTING", "GL_COLOR_MATERIAL", "glLightModel"):
            self.assertNotIn(token, src)

    def test_dark_sunset_is_not_black(self):  # Review Focus 4
        img = render_inside(preset="sunset", interior_lights=False, sun=0.0)
        self.assertGreater(mean_luminance(img), 6)  # 0-255 scale
        self.assertTrue(all(math.isfinite(v) for v in img.getextrema()[0]))


if __name__ == "__main__":
    unittest.main()

