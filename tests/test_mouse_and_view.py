import unittest
from classroom import Camera
from surface_materials import make_surface_images

class TestMouseAndView(unittest.TestCase):
    def setUp(self):
        self.room = {
            "width": 11.79,
            "depth": 12.10,
            "height": 3.46,
            "vestibule_width": 2.90,
            "vestibule_depth": 4.01,
        }
        self.cam = Camera(self.room)

    def test_fpv_mouse_look_direction(self):
        self.cam.preset(2)  # FPV mode
        initial_yaw = self.cam.target_yaw

        # Moving mouse LEFT (dx < 0) should turn camera LEFT (increasing yaw towards +X)
        self.cam.add_look(-10.0, 0.0)
        self.assertGreater(self.cam.target_yaw, initial_yaw,
                           "Moving mouse left (dx < 0) must increase yaw to turn left")

        # Moving mouse RIGHT (dx > 0) should turn camera RIGHT (decreasing yaw towards X=0)
        self.cam.add_look(20.0, 0.0)
        self.assertLess(self.cam.target_yaw, initial_yaw,
                        "Moving mouse right (dx > 0) must decrease yaw to turn right")

    def test_freecam_mouse_look_direction(self):
        self.cam.free = True
        self.cam.fpv_walk = False
        initial_yaw = self.cam.yaw

        # In freecam, moving mouse left (dx < 0) should turn camera left (increasing yaw)
        self.cam.rotate(-10.0, 0.0)
        self.assertGreater(self.cam.yaw, initial_yaw,
                           "Freecam moving mouse left must turn left (increasing yaw)")

    def test_oak_wood_texture_contrast(self):
        images = make_surface_images()
        wood = images["wood"]
        self.assertIsNotNone(wood)
        self.assertEqual(wood.size, (1024, 512))
        
        # Check that wood has warm golden oak tones
        extrema = wood.getextrema()
        r_min, r_max = extrema[0]
        # Should have distinct visible grain contrast (spread > 40)
        self.assertGreater(r_max - r_min, 40, "Oak wood grain must have visible growth ring contrast")

    def test_outdoor_panoramas(self):
        images = make_surface_images()
        self.assertIn("daylight", images)
        self.assertIn("sunset", images)
        daylight = images["daylight"]
        sunset = images["sunset"]
        self.assertEqual(daylight.size, (1024, 512))
        self.assertEqual(sunset.size, (1024, 512))

if __name__ == "__main__":
    unittest.main()
