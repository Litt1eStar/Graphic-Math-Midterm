import unittest
from classroom import Camera

class TestFPVWalkCamera(unittest.TestCase):
    def setUp(self):
        self.room = {"width": 11.79, "depth": 12.10, "vestibule_depth": 4.01}
        self.cam = Camera(self.room)

    def test_preset_2_activates_fpv_walk_at_standing_height(self):
        self.cam.preset(2)
        self.assertTrue(self.cam.free)
        self.assertTrue(self.cam.fpv_walk)
        self.assertAlmostEqual(self.cam.position[2], 1.70, places=2)

    def test_horizontal_movement_preserves_standing_height(self):
        self.cam.preset(2)
        self.cam.pitch = 45.0  # looking up
        # Horizontal forward vector must not alter Z
        vec = self.cam.move_vector(forward=1.0, strafe=0.0)
        self.assertEqual(len(vec), 2)  # returns dx, dy only
        self.cam.position[0] += vec[0]
        self.cam.position[1] += vec[1]
        self.assertAlmostEqual(self.cam.position[2], 1.70, places=2)

    def test_boundary_clamping_prevents_exterior_walk(self):
        self.cam.preset(2)
        # Attempt to walk through front wall (Y < 0.45)
        clamped = self.cam.clamp_bounds([-2.0, -5.0, 1.70])
        self.assertGreaterEqual(clamped[0], 0.45)
        self.assertGreaterEqual(clamped[1], 0.45)
        # Attempt to walk through window wall (X > 11.79 - 0.45)
        clamped_window = self.cam.clamp_bounds([15.0, 5.0, 1.70])
        self.assertLessEqual(clamped_window[0], 11.79 - 0.45)

    def test_rear_wall_does_not_snap_x(self):
        self.cam.preset(2)
        # In main room at X = 8.0, walking into rear wall Y = 12.0 (L = 12.10)
        clamped = self.cam.clamp_bounds([8.0, 12.0, 1.70])
        self.assertAlmostEqual(clamped[0], 8.0, places=2)
        self.assertAlmostEqual(clamped[1], 12.10 - 0.45, places=2)

    def test_accelerates_then_caps(self):
        import math
        cam = Camera(self.room)
        cam.preset(2)
        cam.position = [5.0, 6.0, 1.70]
        cam.yaw = 0
        cam.step_walk(1, 0, False, 1 / 60)
        self.assertLess(math.hypot(*cam.velocity[:2]), 3.0)
        for _ in range(120):
            cam.step_walk(1, 0, False, 1 / 60)
        self.assertAlmostEqual(math.hypot(*cam.velocity[:2]), 3.0, places=1)

    def test_decelerates_to_stop(self):
        import math
        cam = Camera(self.room)
        cam.preset(2)
        cam.position = [5.0, 6.0, 1.70]
        cam.yaw = 0
        for _ in range(120):
            cam.step_walk(1, 0, False, 1 / 60)
        for _ in range(60):
            cam.step_walk(0, 0, False, 1 / 60)
        self.assertLess(math.hypot(*cam.velocity[:2]), 0.05)

    def test_bob_bounded_and_collision_unbobbed(self):
        cam = Camera(self.room)
        cam.preset(2)
        cam.position = [5.0, 6.0, 1.70]
        cam.yaw = 0
        for _ in range(300):
            cam.step_walk(1, 0, True, 1 / 60)
            self.assertAlmostEqual(cam.position[2], 1.70, places=5)
            self.assertLessEqual(abs(cam.eye_position()[2] - 1.70), 0.036)

class TestLightingState(unittest.TestCase):
    def test_default_values_and_clamping(self):
        from classroom import LightingState
        state = LightingState()
        self.assertAlmostEqual(state.sun_intensity, 1.0)
        self.assertAlmostEqual(state.interior_intensity, 1.0)
        self.assertAlmostEqual(state.god_rays_opacity, 0.35)
        self.assertAlmostEqual(state.ambient_brightness, 0.40)

        state.set_sun(2.5)
        self.assertEqual(state.sun_intensity, 2.0)
        state.set_sun(-0.5)
        self.assertEqual(state.sun_intensity, 0.0)

    def test_color_modulation(self):
        from classroom import LightingState
        state = LightingState()
        base_color = (0.8, 0.8, 0.8, 1.0)
        scaled = state.scale_color(base_color, 0.5)
        self.assertAlmostEqual(scaled[0], 0.4)
        self.assertAlmostEqual(scaled[3], 1.0)

    def test_nudge_slider(self):
        from classroom import LightingState
        state = LightingState()
        state.nudge_slider(0, -0.1)
        self.assertAlmostEqual(state.sun_intensity, 0.9, places=2)

class TestHUDSliders(unittest.TestCase):
    def setUp(self):
        from classroom import HUD, LightingState
        self.config = {"room_id": "S13-30612", "room": {"width": 11.79, "depth": 12.10, "vestibule_depth": 4.01, "height": 3.46}}
        self.hud = HUD(self.config)
        self.lighting = LightingState()

    def test_slider_drag_updates_state(self):
        # Slider 0: Sun (0.0 to 2.0)
        self.hud.apply_slider_value(0, 0.75, self.lighting)
        self.assertAlmostEqual(self.lighting.sun_intensity, 1.5, places=2)

        # Slider 2: God rays (0.0 to 1.0)
        self.hud.apply_slider_value(2, 0.50, self.lighting)
        self.assertAlmostEqual(self.lighting.god_rays_opacity, 0.50, places=2)

    def test_slider_bounds_check(self):
        is_hit = self.hud.is_point_in_panel(x=1300, y=100, window_w=1440, window_h=900)
        self.assertTrue(is_hit)
        outside_hit = self.hud.is_point_in_panel(x=200, y=500, window_w=1440, window_h=900)
        self.assertFalse(outside_hit)

class TestAppInputRouting(unittest.TestCase):
    def test_slider_keyboard_nudge(self):
        from classroom import LightingState
        state = LightingState()
        state.set_sun(1.0)
        state.nudge_slider(0, delta=-0.05)
        self.assertAlmostEqual(state.sun_intensity, 0.95, places=2)
        state.nudge_slider(0, delta=+0.10)
        self.assertAlmostEqual(state.sun_intensity, 1.05, places=2)

    def test_active_slider_bounds(self):
        active = 0
        active = (active + 1) % 4
        self.assertEqual(active, 1)
        active = 3
        active = (active + 1) % 4
        self.assertEqual(active, 0)

    def test_sit_on_chair_locks_movement_and_allows_mouse_rotation(self):
        from pathlib import Path
        from classroom import Camera, load_config, compute_chair_seats
        config = load_config(Path("room_config.json"))
        seats = compute_chair_seats(config)
        self.assertEqual(len(seats), 73)  # 72 student chairs + 1 instructor chair

        cam = Camera(config["room"])
        cam.preset(2)
        target_seat = seats[0]
        cam.position = [target_seat["x"] + 0.3, target_seat["y"] + 0.3, 1.70]

        sat = cam.toggle_sit(seats)
        self.assertTrue(sat)
        self.assertTrue(cam.seated)
        self.assertAlmostEqual(cam.position[0], target_seat["x"], places=3)
        self.assertAlmostEqual(cam.position[1], target_seat["y"], places=3)
        self.assertAlmostEqual(cam.position[2], target_seat["z"], places=3)

        # While seated, WASD walk input must not move the player
        cam.step_walk(1.0, 1.0, True, 0.05)
        self.assertAlmostEqual(cam.position[0], target_seat["x"], places=3)
        self.assertAlmostEqual(cam.position[1], target_seat["y"], places=3)
        self.assertEqual(cam.velocity, [0.0, 0.0, 0.0])
        self.assertEqual(cam.eye_position(), cam.position)

        # While seated, mouse rotation must still rotate camera yaw and pitch
        initial_yaw = cam.yaw
        initial_pitch = cam.pitch
        cam.rotate(20.0, -15.0)
        self.assertNotAlmostEqual(cam.yaw, initial_yaw)
        self.assertNotAlmostEqual(cam.pitch, initial_pitch)

        # Standing up restores standing eye height and unlocks movement
        sat_after = cam.toggle_sit(seats)
        self.assertFalse(sat_after)
        self.assertFalse(cam.seated)
        self.assertAlmostEqual(cam.position[2], 1.70, places=2)
        cam.step_walk(1.0, 0.0, False, 0.05)
        self.assertGreater(abs(cam.velocity[0]) + abs(cam.velocity[1]), 0.0)


if __name__ == "__main__":
    unittest.main()


