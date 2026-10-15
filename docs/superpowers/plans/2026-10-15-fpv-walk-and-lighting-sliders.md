# Authentic FPV Walk Mode & Adjustable Lighting Sliders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an authentic First-Person View (FPV) walk mode with direct mouse-look and wall collision, alongside an interactive 4-channel HUD lighting adjustment slider system for the S13-30612 OpenGL Classroom.

**Architecture:** Extend `Camera` with a grounded FPV walk mode ($Z = 1.70\text{ m}$) and room/vestibule boundary collision. Introduce a `LightingState` model driving `GL_LIGHT0..2`, `GL_LIGHT_MODEL_AMBIENT`, god ray opacity, and luminaire pools dynamically. Build an interactive `SliderWidget` HUD overlay for mouse drag and keyboard adjustment, coupled with a cursor state machine in `App` that toggles between direct mouselook and UI cursor manipulation via <kbd>Tab</kbd>.

**Tech Stack:** Python 3.10+, PyOpenGL 3.1.10 (fixed-function pipeline), GLFW 2.7+, Pillow (PIL).

**Spec:** [docs/superpowers/specs/2026-10-15-fpv-walk-and-lighting-sliders-design.md](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/docs/superpowers/specs/2026-10-15-fpv-walk-and-lighting-sliders-design.md)

## Global Constraints
- Pure procedural assets only: Zero external 3D models or bitmap image files; UI widgets and textures generated procedurally via Pillow.
- Standard OpenGL 2.1+ fixed-function pipeline; no external GLSL shaders.
- Pair synchronization: `classroom.py` and `surface_materials.py` must remain strictly compatible and side-by-side.
- Zero OpenGL errors in automated verification: `python classroom.py --hidden --verify previews`.
- Codebase style: Preserve all existing comments and docstrings.

## Review Focus
1. Player walks diagonally into a corner wall: Collision clamping must stop at wall threshold without clipping through exterior quads.
2. User toggles camera preset 1, 3, or 4: Cursor must immediately restore to `glfw.CURSOR_NORMAL` so drag-orbit functionality is never broken.
3. Sliders set to minimum ($0.0$): Zero division in light scaling must be guarded, turning off lights or setting alpha to zero gracefully without GL errors.
4. User clicks outside slider widget when cursor is unlocked in Preset 2: Must cleanly recapture cursor into `glfw.CURSOR_DISABLED` without jumping camera angle.
5. Headless test execution: Slider HUD rendering and FPV mode calculations must run without raising exceptions in off-screen/headless mode.

---

### Task 1: FPV Walk Camera Mechanics & Boundary Clamping

**Files:**
- Modify: `classroom.py:949-1010` (`Camera` class)
- Test: `tests/test_fpv_lighting.py`

**Interfaces:**
- Consumes: `room_config.json` room dimensions (`width`, `depth`, `vestibule_depth`).
- Produces: `Camera.clamp_bounds(pos: list[float]) -> list[float]`, `Camera.fpv_walk: bool`, `Camera.standing_eye_height: float = 1.70`.

- [ ] **Step 1: Write the failing unit tests for FPV walk mechanics and collision**

In `tests/test_fpv_lighting.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_fpv_lighting.py`
Expected: FAIL (missing `fpv_walk`, `move_vector`, `clamp_bounds`).

- [ ] **Step 3: Implement FPV walk mechanics and boundary clamping in `Camera`**

In `classroom.py:Camera`:
- Add attributes: `self.fpv_walk = False`, `self.standing_eye_height = 1.70`.
- In `preset(2)`: set `self.free = True`, `self.fpv_walk = True`, `self.position = [1.05, L - 1.30, 1.70]`.
- Add `move_vector(forward: float, strafe: float) -> tuple[float, float]`: computes $(dx, dy)$ using horizontal $\text{yaw}$ only:
  $dx = \cos(\theta) \cdot \text{forward} + \sin(\theta) \cdot \text{strafe}$
  $dy = \sin(\theta) \cdot \text{forward} - \cos(\theta) \cdot \text{strafe}$.
- Add `clamp_bounds(pos: list[float]) -> list[float]`:
  Main bounds: $X \in [0.45, W - 0.45]$, $Y \in [0.45, L - 0.45]$.
  Vestibule bounds: if $Y > L - 0.45$, clamp $X \in [0.45, 2.65]$ and $Y \in [0.45, L + V_{\text{depth}} - 0.45]$.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_fpv_lighting.py`
Expected: PASS.

---

### Task 2: Lighting State Model & Dynamic OpenGL Modulation

**Files:**
- Modify: `classroom.py:136-170, 720-760` (`Classroom.draw` and lighting state)
- Test: `tests/test_fpv_lighting.py`

**Interfaces:**
- Consumes: `room_config.json` lighting presets.
- Produces: `LightingState` dataclass with `sun_intensity`, `interior_intensity`, `god_rays_opacity`, `ambient_brightness`, and modulation helpers `get_sun_diffuse()`, `get_interior_diffuse()`, `get_ambient()`.

- [ ] **Step 1: Write the failing unit tests for `LightingState`**

In `tests/test_fpv_lighting.py`:
```python
from classroom import LightingState

class TestLightingState(unittest.TestCase):
    def test_default_values_and_clamping(self):
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
        state = LightingState()
        base_color = (0.8, 0.8, 0.8, 1.0)
        state.sun_intensity = 0.5
        scaled = state.scale_color(base_color, state.sun_intensity)
        self.assertAlmostEqual(scaled[0], 0.4)
        self.assertAlmostEqual(scaled[3], 1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_fpv_lighting.py`
Expected: FAIL (`LightingState` not found).

- [ ] **Step 3: Implement `LightingState` in `classroom.py`**

Define `@dataclass class LightingState`:
- Properties: `sun_intensity: float = 1.0`, `interior_intensity: float = 1.0`, `god_rays_opacity: float = 0.35`, `ambient_brightness: float = 0.40`.
- Mutators with clamping:
  - `set_sun(val: float)` clamped to $[0.0, 2.0]$
  - `set_interior(val: float)` clamped to $[0.0, 2.0]$
  - `set_god_rays(val: float)` clamped to $[0.0, 1.0]$
  - `set_ambient(val: float)` clamped to $[0.0, 1.0]$
  - `scale_color(base: tuple, factor: float) -> tuple`: scales RGB components by `factor` while preserving alpha.
- Integrate into `Classroom.draw`:
  - Pass `lighting_state: LightingState` to `draw()`.
  - Modulate `GL_LIGHT0` diffuse by `lighting_state.sun_intensity`.
  - Modulate `GL_LIGHT1` & `GL_LIGHT2` diffuse by `lighting_state.interior_intensity`.
  - Modulate `GL_LIGHT_MODEL_AMBIENT` by `lighting_state.ambient_brightness / 0.40`.
  - Modulate god rays alpha: if `lighting_state.god_rays_opacity <= 0.001`, skip drawing god rays.
  - Modulate interior light pools alpha: if `lighting_state.interior_intensity <= 0.001`, skip drawing light pools.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_fpv_lighting.py`
Expected: PASS.

---

### Task 3: Interactive HUD Sliders Widget

**Files:**
- Modify: `classroom.py:1020-1075` (`HUD` class)
- Test: `tests/test_fpv_lighting.py`

**Interfaces:**
- Consumes: `LightingState`.
- Produces: `HUD.draw_sliders(...)`, `HUD.hit_test_slider(x, y, w, h) -> int | None`, `HUD.drag_slider(index, norm_val, lighting_state)`.

- [ ] **Step 1: Write the failing unit tests for Slider interaction logic**

In `tests/test_fpv_lighting.py`:
```python
from classroom import HUD, LightingState

class TestHUDSliders(unittest.TestCase):
    def setUp(self):
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
        # Panel located at top-right
        is_hit = self.hud.is_point_in_panel(x=1300, y=100, window_w=1440, window_h=900)
        self.assertTrue(is_hit)
        outside_hit = self.hud.is_point_in_panel(x=200, y=500, window_w=1440, window_h=900)
        self.assertFalse(outside_hit)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_fpv_lighting.py`
Expected: FAIL (`apply_slider_value` / `is_point_in_panel` not defined).

- [ ] **Step 3: Implement Slider rendering and coordinate mapping in `HUD`**

In `classroom.py:HUD`:
- Define slider metadata:
  1. `("SUNLIGHT", 0.0, 2.0, "sun_intensity")`
  2. `("INTERIOR", 0.0, 2.0, "interior_intensity")`
  3. `("GOD RAYS", 0.0, 1.0, "god_rays_opacity")`
  4. `("AMBIENT", 0.0, 1.0, "ambient_brightness")`
- Add `apply_slider_value(index: int, norm_x: float, lighting_state: LightingState)`:
  Maps normalized value $[0.0, 1.0]$ to each slider's range $[min, max]$.
- Add `is_point_in_panel(x: float, y: float, window_w: int, window_h: int) -> bool`:
  Checks if mouse coordinate is inside the top-right slider box ($X \in [w - 350, w - 20]$, $Y \in [20, 230]$).
- Add `slider_hit_test(x: float, y: float, window_w: int, window_h: int) -> tuple[int, float] | None`:
  Determines which slider row is clicked and computes the normalized position along its rail.
- In `HUD.draw`:
  Render translucent rounded panel at top-right with labels, current numeric badges, rails, and glowing draggable thumbs.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_fpv_lighting.py`
Expected: PASS.

---

### Task 4: Cursor State Machine, Mouse-Look & Input Routing

**Files:**
- Modify: `classroom.py:1080-1230` (`App` class)
- Test: `tests/test_fpv_lighting.py`

**Interfaces:**
- Consumes: `Camera.fpv_walk`, `HUD.slider_hit_test`, `LightingState`.
- Produces: `App.cursor_locked: bool`, `App.active_slider: int`, `App.on_key`, `App.on_mouse`, `App.on_button`.

- [ ] **Step 1: Write unit tests for App input state routing**

In `tests/test_fpv_lighting.py`:
```python
class TestAppInputRouting(unittest.TestCase):
    def test_slider_keyboard_nudge(self):
        state = LightingState()
        # Active slider 0: Sun (step 0.05)
        state.set_sun(1.0)
        # Simulate [ (decrease) and ] (increase)
        state.nudge_slider(0, delta=-0.05)
        self.assertAlmostEqual(state.sun_intensity, 0.95, places=2)
        state.nudge_slider(0, delta=+0.10)
        self.assertAlmostEqual(state.sun_intensity, 1.05, places=2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_fpv_lighting.py`
Expected: FAIL (`nudge_slider` not defined).

- [ ] **Step 3: Implement cursor state management and event dispatching in `App`**

In `classroom.py:App`:
- Add `self.cursor_locked = False`, `self.active_slider = 0`, `self.dragging_slider = False`.
- In `App.preset(n)` / key handler for 1–4:
  - If $n == 2$: switch to FPV walk, set `cursor_locked = True`, `glfw.set_input_mode(self.window, glfw.CURSOR, glfw.CURSOR_DISABLED)`.
  - If $n \in \{1, 3, 4\}$: switch to Orbit, set `cursor_locked = False`, `glfw.set_input_mode(self.window, glfw.CURSOR, glfw.CURSOR_NORMAL)`.
- Key handler <kbd>Tab</kbd>:
  - If in Preset 2: toggle `cursor_locked = not cursor_locked`. Set GLFW cursor mode accordingly.
- Key handler <kbd>[</kbd> and <kbd>]</kbd>:
  - Nudge currently `active_slider` down/up.
- Key handler <kbd>Ctrl</kbd> + <kbd>1..4</kbd>:
  - Select active slider 0..3.
- Mouse button handler:
  - In `action == glfw.PRESS`:
    - If `not cursor_locked` and mouse clicked inside slider panel: start dragging active slider, update value.
    - If `not cursor_locked` and in Preset 2 and mouse clicked outside HUD: recapture cursor into FPV walk (`cursor_locked = True`, `CURSOR_DISABLED`).
    - If in Orbit view: standard drag-orbit behavior.
  - In `action == glfw.RELEASE`:
    - Stop dragging slider.
- Cursor movement handler:
  - If `cursor_locked` (FPV walk): apply $(\Delta X, \Delta Y)$ directly to `camera.rotate(dx, dy)`.
  - If dragging slider: compute rail fraction and update `lighting_state`.
- Update loop:
  - In FPV walk, WASD uses `camera.move_vector` and passes through `camera.clamp_bounds(camera.position)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_fpv_lighting.py`
Expected: PASS.

---

### Task 5: Verification Snapshots, Automated Pipeline & Documentation

**Files:**
- Modify: `classroom.py:1270-1350` (`verify` function)
- Modify: `README_TH.md:110-145`
- Test: automated render verification `python classroom.py --hidden --verify previews`

**Interfaces:**
- Produces: `previews/verification.json` with `fpv_walk_verified: true`, `lighting_sliders_verified: true`, and snapshots `previews/fpv_inside.png`, `previews/slider_hud.png`.

- [ ] **Step 1: Add verification assertions to `verify` routine in `classroom.py`**

In `classroom.py:verify()`:
- Test FPV walk camera view and capture `fpv_inside.png`.
- Test slider HUD rendering and value changes (e.g. `sun_intensity=1.8`, `god_rays_opacity=0.8`).
- Verify `lighting_sliders` status exported to `previews/verification.json`.

- [ ] **Step 2: Update Thai documentation in `README_TH.md`**

Add clear instructions in the Controls table for:
- <kbd>Tab</kbd>: สลับระหว่างโหมดเดิน FPV (ควบคุมมุมมองด้วยเมาส์โดยตรง) และโหมดเคอร์เซอร์ (คลิกปรับแถบเลื่อนแสง)
- Drag Sliders / <kbd>[</kbd> <kbd>]</kbd>: ปรับความสว่างแสงแดด (Sun), ไฟเพดาน (Interior), ลำแสง God Rays และแสงบรรยากาศ (Ambient)
- <kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd>: เดินในห้องตามทิศทางที่มอง พร้อมระบบป้องกันการเดินทะลุกำแพง

- [ ] **Step 3: Run compilation and verification suite**

Run:
1. `python -m py_compile classroom.py surface_materials.py` (Exit code 0).
2. `python -m unittest discover tests` (All tests pass).
3. `python classroom.py --hidden --verify previews` (All renders pass with `opengl_errors == 0`).

- [ ] **Step 4: Check verification output**

Inspect `previews/verification.json` to ensure `opengl_errors == 0` and all lighting parameters verify successfully.

