import unittest
from pathlib import Path
from classroom import App, load_config
import glfw

class TestAppState(unittest.TestCase):
    def test_app_lighting_state_toggles(self):
        cfg = load_config(Path("room_config.json"))
        app = App(cfg, width=640, height=480, hidden=True)
        try:
            self.assertEqual(app.lighting_preset, "daylight")
            self.assertTrue(app.interior_lights)
            self.assertTrue(app.god_rays)

            app.toggle_lighting_preset()
            self.assertEqual(app.lighting_preset, "sunset")

            app.toggle_interior_lights()
            self.assertFalse(app.interior_lights)

            app.toggle_god_rays()
            self.assertFalse(app.god_rays)
        finally:
            glfw.destroy_window(app.window)
            glfw.terminate()

if __name__ == "__main__":
    unittest.main()

