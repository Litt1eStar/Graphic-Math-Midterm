import unittest
from classroom import Classroom

class TestInteriorLighting(unittest.TestCase):
    def test_interior_methods_exist(self):
        self.assertTrue(hasattr(Classroom, "build_interior_light_pools"), "Classroom must have build_interior_light_pools method")

if __name__ == "__main__":
    unittest.main()

