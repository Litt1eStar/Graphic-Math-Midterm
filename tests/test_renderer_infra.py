"""Unit tests for realistic_renderer infrastructure: matrices, shaders, and RenderTarget."""
import unittest
from OpenGL.GL import *
from tests.gl_helpers import hidden_context
from realistic_renderer import (
    ShaderError,
    compile_program,
    RenderTarget,
    mat_perspective,
    mat_look_at,
    mat_ortho,
    mat_mul,
    mat_inverse,
)


class TestRendererInfra(unittest.TestCase):
    def test_matrix_inverse_roundtrip(self):
        m = mat_mul(
            mat_perspective(52, 1.6, 0.08, 180),
            mat_look_at((1, 2, 1.7), (5, 6, 1.7), (0, 0, 1)),
        )
        inv = mat_inverse(m)
        ident = mat_mul(m, inv)
        for i in range(16):
            expected = 1.0 if i % 5 == 0 else 0.0
            self.assertAlmostEqual(ident[i], expected, places=4)

    def test_context_is_33_or_newer(self):
        with hidden_context():
            major = glGetIntegerv(GL_MAJOR_VERSION)
            minor = glGetIntegerv(GL_MINOR_VERSION)
            self.assertGreaterEqual((major, minor), (3, 3))

    def test_bad_shader_raises_with_log(self):
        with hidden_context():
            with self.assertRaises(ShaderError) as ctx:
                compile_program(
                    "#version 330 compatibility\nvoid main(){ gl_Position = oops; }",
                    "#version 330 compatibility\nvoid main(){}",
                    "broken",
                )
            self.assertIn("broken", str(ctx.exception))

    def test_render_target_complete_and_resizable(self):
        with hidden_context():
            rt = RenderTarget(320, 200, [GL_RGBA16F], depth_texture=True)
            self.assertEqual((rt.width, rt.height), (320, 200))
            rt.resize(640, 400)
            self.assertEqual((rt.width, rt.height), (640, 400))
            rt.resize(0, 0)  # minimised window: must be a no-op, no GL error
            self.assertEqual(glGetError(), GL_NO_ERROR)
            rt.delete()


if __name__ == "__main__":
    unittest.main()

