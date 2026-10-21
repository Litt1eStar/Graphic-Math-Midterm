"""Unit tests for Task 5: Materials, procedural textures, bump, and specular gloss."""
import unittest
from surface_materials import make_surface_images
from tests.gl_helpers import render_view


class TestSurfaceMaterials(unittest.TestCase):
    def test_texture_set_and_sizes(self):
        imgs = make_surface_images()
        self.assertEqual(set(imgs), {"floor", "wood", "panel", "plaster", "daylight", "sunset"})
        self.assertEqual(max(imgs["floor"].size), 1024)
        self.assertEqual(max(imgs["wood"].size), 1024)
        self.assertEqual(imgs["plaster"].size, (512, 512))

    def test_textures_deterministic(self):
        a = make_surface_images()
        b = make_surface_images()
        self.assertEqual(a["plaster"].tobytes(), b["plaster"].tobytes())
        self.assertEqual(a["floor"].tobytes(), b["floor"].tobytes())

    def test_floor_has_specular_highlight(self):
        # In side_window view, floor specular highlights from sunlight/lamps create clear contrast
        img = render_view("side_window")
        # Crop floor region in lower third of image
        w, h = img.size
        floor_crop = img.crop((int(w * 0.1), int(h * 0.7), int(w * 0.9), int(h * 0.95))).convert("L")
        lo, hi = floor_crop.getextrema()
        # Contrast ratio between brightest highlight and base floor
        self.assertGreater(hi, lo * 1.15)


if __name__ == "__main__":
    unittest.main()
