import unittest
from surface_materials import make_surface_images

class TestSurfaceMaterials(unittest.TestCase):
    def test_make_surface_images_contains_sunset(self):
        images = make_surface_images()
        self.assertIn("sunset", images, "sunset texture must be generated")
        self.assertEqual(images["sunset"].mode, "RGB")
        self.assertEqual(images["sunset"].size, (512, 512))

if __name__ == "__main__":
    unittest.main()

