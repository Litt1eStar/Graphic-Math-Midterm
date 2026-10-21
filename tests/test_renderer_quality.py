"""Unit tests for Task 6: SSAO and Low/High quality toggle."""
import unittest
from OpenGL.GL import *
from tests.gl_helpers import hidden_app, render_view, corner_luminance


class TestRendererQuality(unittest.TestCase):
    def test_quality_toggle_no_leak(self):
        with hidden_app() as app:
            app.render()
            diag_before = app.renderer.diagnostics()
            before_count = diag_before.get("texture_count", 0)
            for q in ("low", "high", "low", "high"):
                app.renderer.set_quality(q)
                app.render()
            self.assertEqual(app.renderer.diagnostics().get("texture_count", 0), before_count)
            self.assertEqual(glGetError(), GL_NO_ERROR)

    def test_invalid_quality(self):
        with hidden_app() as app:
            with self.assertRaises(ValueError):
                app.renderer.set_quality("ultra")

    def test_ssao_darkens_corners(self):
        high = render_view("rear_wall", quality="high")
        low = render_view("rear_wall", quality="low")
        self.assertLess(corner_luminance(high), corner_luminance(low))


if __name__ == "__main__":
    unittest.main()

