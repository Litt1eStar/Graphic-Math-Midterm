import unittest
from classroom import Classroom

class TestGodRays(unittest.TestCase):
    def test_build_god_rays_method_exists(self):
        self.assertTrue(hasattr(Classroom, "build_god_rays"), "Classroom must have build_god_rays method")

if __name__ == "__main__":
    unittest.main()

