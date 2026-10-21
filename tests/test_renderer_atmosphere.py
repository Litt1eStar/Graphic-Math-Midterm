"""Unit tests for Task 7: Volumetric god rays and dust particles."""
import unittest
from realistic_renderer import DustSystem
from tests.gl_helpers import render_view, mean_luminance


class TestRendererAtmosphere(unittest.TestCase):
    def test_dust_stays_in_volumes(self):
        vols = [((10.0, 1.0, 0.9), (11.79, 3.0, 2.8))]
        dust = DustSystem(200, vols)
        for _ in range(600):
            dust.update(1 / 60)
        for x, y, z in dust.positions:
            self.assertTrue(10.0 <= x <= 11.79 and 1.0 <= y <= 3.0 and 0.9 <= z <= 2.8)

    def test_dust_deterministic(self):
        a = DustSystem(50, [((0, 0, 0), (1, 1, 1))])
        b = DustSystem(50, [((0, 0, 0), (1, 1, 1))])
        self.assertEqual(a.positions, b.positions)

    def test_god_ray_slider_changes_beams(self):
        off = mean_luminance(render_view("sunset_god_rays", god_rays_opacity=0.0))
        on = mean_luminance(render_view("sunset_god_rays", god_rays_opacity=1.0))
        self.assertGreater(on, off + 3)

    def test_godray_shader_uses_shadow_map_and_soft_edge_feathering(self):
        import realistic_renderer
        self.assertIn("u_shadow_map", realistic_renderer.GODRAY_FS)
        self.assertIn("v_light_space_pos", realistic_renderer.GODRAY_FS)
        self.assertIn("edge_feather", realistic_renderer.GODRAY_FS)
        self.assertIn("u_sun_dir", realistic_renderer.GODRAY_FS)
        self.assertIn("overlap_comp", realistic_renderer.GODRAY_FS)
        self.assertIn("halo", realistic_renderer.DUST_FS)
        self.assertIn("film_grade", realistic_renderer.COMPOSITE_FS)


if __name__ == "__main__":
    unittest.main()



