"""Unit tests for Task 4: Sun shadow maps (PCF) and shadow softness slider."""
import itertools
import unittest
from pathlib import Path
from classroom import LightingState, load_config
from realistic_renderer import (
    sun_direction,
    sun_light_matrices,
    mat_mul,
    transform_point,
)
from tests.gl_helpers import render_view, patch_luminance


class TestRendererShadows(unittest.TestCase):
    def test_shadow_softness_clamp_and_nudge(self):
        s = LightingState()
        self.assertAlmostEqual(s.shadow_softness, 0.4)
        s.set_shadow_softness(1.5)
        self.assertEqual(s.shadow_softness, 1.0)
        s.set_shadow_softness(-0.5)
        self.assertEqual(s.shadow_softness, 0.0)

        s.set_shadow_softness(0.5)
        s.nudge_slider(6, 0.05)
        self.assertAlmostEqual(s.shadow_softness, 0.55, places=2)

    def test_light_frustum_contains_room(self):
        room = load_config(Path("room_config.json"))["room"]
        W, L, H, V = room["width"], room["depth"], room["height"], room["vestibule_depth"]
        for preset in ("daylight", "sunset"):
            sun_dir = sun_direction(preset, room)
            view, proj = sun_light_matrices(sun_dir, (0.0, W, 0.0, L + V, 0.0, H))
            vp = mat_mul(proj, view)
            for corner in itertools.product((0.0, W), (0.0, L + V), (0.0, H)):
                ndc = transform_point(vp, corner)
                for coord in ndc:
                    self.assertTrue(-1.001 <= coord <= 1.001, f"Corner {corner} outside NDC: {ndc}")

    def test_sunset_desk_casts_shadow(self):
        # In sunset view from sunset_god_rays camera, probe shadow under desk vs lit open floor
        img = render_view("sunset_god_rays", interior_lights=False)
        # Probe on the floor in the shadow cast by a desk block
        shadow_probe = (6.0, 7.0, 0.05)
        # Probe on the open floor receiving direct low-angle sunset rays
        lit_probe = (8.0, 7.0, 0.05)
        shadow = patch_luminance(img, world_point=shadow_probe)
        lit = patch_luminance(img, world_point=lit_probe)
        self.assertLess(shadow, lit * 0.5)


if __name__ == "__main__":
    unittest.main()
