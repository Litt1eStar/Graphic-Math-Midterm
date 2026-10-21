import unittest
import math
from surface_materials import make_surface_images

class TestSkyboxAndEdges(unittest.TestCase):
    def test_skybox_seamless_wrap(self):
        images = make_surface_images()
        for name in ("daylight", "sunset"):
            img = images[name]
            w, h = img.size
            total_diff = 0
            samples = 0
            for y in range(int(h * 0.1), int(h * 0.9), 10):
                p_left = img.getpixel((0, y))
                p_right = img.getpixel((w - 1, y))
                diff = sum(abs(a - b) for a, b in zip(p_left, p_right)) / 3.0
                total_diff += diff
                samples += 1
            avg_diff = total_diff / max(1, samples)
            self.assertLess(avg_diff, 20.0, f"{name} skybox must wrap seamlessly at 360-degree boundary")

    def test_table_wood_edge_uv_proportions(self):
        from classroom import compute_box_face_uvs
        # Table top: 1.2m x 0.6m x 0.028m
        uvs = compute_box_face_uvs(1.2, 0.6, 0.028, texture_name="wood")
        top_uv, bot_uv, front_uv, back_uv, left_uv, right_uv = uvs
        # Front edge height in UV space should match thickness ratio (h/d = 0.028/0.6 = ~0.0467)
        front_v_span = max(uv[1] for uv in front_uv) - min(uv[1] for uv in front_uv)
        self.assertAlmostEqual(front_v_span, 0.028 / 0.6, places=3)
        self.assertLess(front_v_span, 0.1, "Table edge UV should not span full unit height to prevent stretching")

    def test_wall_plaster_metric_uv(self):
        from classroom import compute_box_face_uvs
        # Wall: 12.1m x 0.18m x 3.46m
        uvs = compute_box_face_uvs(12.1, 0.18, 3.46, texture_name="plaster")
        top_uv, bot_uv, front_uv, back_uv, left_uv, right_uv = uvs
        # Top edge width in UV should scale with 12.1m, and depth with 0.18m
        top_u_span = max(uv[0] for uv in top_uv) - min(uv[0] for uv in top_uv)
        top_v_span = max(uv[1] for uv in top_uv) - min(uv[1] for uv in top_uv)
        self.assertAlmostEqual(top_u_span, 12.1 * 0.8, places=3)
        self.assertAlmostEqual(top_v_span, 0.18 * 0.8, places=3)

    def test_scene_fs_bump_gradient_clamp(self):
        import realistic_renderer
        # SCENE_FS must clamp the bump gradient to prevent infinite normal spikes on edges
        self.assertIn("grad_len", realistic_renderer.SCENE_FS, "SCENE_FS must clamp bump gradient length")

    def test_ssao_fs_depth_rejection(self):
        import realistic_renderer
        # SSAO_FS must check depth difference to avoid false occlusion across silhouettes
        self.assertIn("dist < radius", realistic_renderer.SSAO_FS, "SSAO_FS must check dist < radius")

    def test_procedural_sky_dome_and_aerial_perspective(self):
        import realistic_renderer
        self.assertIn("u_is_skybox", realistic_renderer.SCENE_FS,
                      "SCENE_FS must support per-pixel procedural skybox dome via u_is_skybox")
        self.assertIn("eval_procedural_sky", realistic_renderer.SCENE_FS,
                      "SCENE_FS must evaluate procedural sky gradient, sun corona, and FBM clouds")
        self.assertIn("aerial_haze", realistic_renderer.SCENE_FS,
                      "SCENE_FS must apply distance-based aerial perspective haze to exterior 3D buildings")

    def test_3d_layered_exterior_scenery(self):
        from classroom import generate_exterior_scenery_boxes
        boxes = generate_exterior_scenery_boxes(11.79, 12.10, 4.01, 3.46)
        self.assertGreater(len(boxes), 25, "Must generate rich 3D multi-layer exterior campus & skyline boxes")
        # Verify multi-depth layers outside +X window wall: midground (18..52m) and distant skyline (>60m)
        midground = [b for b in boxes if 18.0 <= b[0] <= 52.0]
        distant = [b for b in boxes if b[0] >= 60.0]
        below_6th_floor = [b for b in boxes if b[2] < -2.0]
        self.assertGreater(len(midground), 5, "Must have midground 3D campus buildings/trees for parallax")
        self.assertGreater(len(distant), 5, "Must have distant 3D skyline towers for horizon depth")
        self.assertGreater(len(below_6th_floor), 5, "Must have 3D rooftops/trees below 6th floor level (Z < -2m)")

    def test_sky_clouds_exterior_mullions_and_floor_reflections(self):
        import realistic_renderer
        self.assertIn("eval_window_reflection", realistic_renderer.SCENE_FS,
                      "SCENE_FS must compute analytical window-bay Fresnel reflections on floor and oak desks")
        self.assertIn("mullion", realistic_renderer.SCENE_FS,
                      "SCENE_FS must render procedural mullions on exterior buildings and window reflections")


if __name__ == "__main__":
    unittest.main()


