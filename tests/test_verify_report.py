"""Unit test for Task 9: Verify report fields and preview outputs."""
import json
import subprocess
import sys
import unittest
from pathlib import Path


class TestVerifyReport(unittest.TestCase):
    def test_report_has_renderer_fields(self):
        subprocess.run([sys.executable, "classroom.py", "--hidden", "--verify", "previews"], check=True)
        rep = json.loads(Path("previews/verification.json").read_text(encoding="utf-8"))
        self.assertEqual(rep["opengl_errors"], 0)
        self.assertEqual(rep["shader_errors"], [])
        self.assertTrue(rep["fbo_complete"])
        self.assertTrue(rep["shadow_check"]["pass"])
        for name in ("realistic_daylight", "realistic_sunset_shadows", "realistic_lamps_night", "realistic_low_quality"):
            self.assertTrue(Path(f"previews/{name}.png").exists(), f"Missing preview: previews/{name}.png")
        self.assertGreater(rep["frame_ms_high"], 0)
        self.assertGreater(rep["frame_ms_low"], 0)


if __name__ == "__main__":
    unittest.main()

