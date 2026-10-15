import unittest
from pathlib import Path
from classroom import load_config

class TestLightingConfig(unittest.TestCase):
    def test_lighting_config_present(self):
        cfg = load_config(Path("room_config.json"))
        self.assertIn("lighting", cfg, "lighting config section required")
        lighting = cfg["lighting"]
        self.assertIn(lighting["default_preset"], ("daylight", "sunset"))
        self.assertIn("god_rays", lighting)
        self.assertIn("interior_lights", lighting)
        self.assertIn("daylight", lighting)
        self.assertIn("sunset", lighting)

if __name__ == "__main__":
    unittest.main()

