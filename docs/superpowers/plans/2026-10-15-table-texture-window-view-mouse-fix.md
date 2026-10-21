# Table Texture, Window View & Mouse Invert Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

This plan addresses three specific user requests for the S13-30612 OpenGL digital twin:
1. **Table Texture**: Preserve the original geometric shape of the tables exactly, but upgrade the texture to an authentic warm Oak wood grain with visible growth rings and pores (resolving the white/washed-out appearance).
2. **Looking Through Window**: Eliminate the opaque/white window block by creating an expansive outdoor sky and city panorama (15–20m away) with self-luminous daylight/sunset textures, plus high-transparency glass.
3. **Inverted FPV Mouse Control**: Fix horizontal mouse look in FPV and Freecam so moving the mouse left turns left, and moving right turns right.

---

## File Structure

- [classroom.py](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/classroom.py):
  - Invert horizontal mouse look delta in `Camera.add_look()` and `Camera.rotate()`.
  - Invert arrow keys in `App.update()`.
  - Update `COLORS["wood"]` and `MATERIALS["wood"]` to preserve warm oak tones without PBR saturation.
  - Expand outdoor backdrop geometry from 45cm to 18m distance spanning wide view angles.
  - Ensure texture binding for wood and outdoor panorama is properly preserved in display lists and shader passes.
  - Update window glass transparency.
- [surface_materials.py](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/surface_materials.py):
  - Generate high-contrast, authentic Oak wood texture `_oak_wood()` with growth rings, grain arches, and medullary pores.
  - Generate high-resolution, vibrant outdoor sky and city panoramas for `daylight` and `sunset`.
- [realistic_renderer.py](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/realistic_renderer.py):
  - Support self-luminous emissive rendering for outdoor sky/city panorama so daylight is bright and visible through glass.
- `tests/test_mouse_and_view.py`:
  - Unit tests verifying mouse yaw delta direction and outdoor backdrop visibility.

---

## Tasks

### Task 1: Fix FPV and Freecam Mouse Look Inversion

- [ ] **Step 1.1: Write failing unit test for camera mouse look**
  Create `tests/test_mouse_and_view.py` testing that moving mouse left ($dx < 0$) causes camera yaw to turn left towards $+X$ (increasing yaw), and moving mouse right ($dx > 0$) turns right (decreasing yaw).
- [ ] **Step 1.2: Run test to confirm failure**
  Run `python -m unittest tests/test_mouse_and_view.py`.
- [ ] **Step 1.3: Update camera look logic in `classroom.py`**
  - In `Camera.add_look(dx, dy, dt)`: `self.target_yaw -= dx * 0.22`
  - In `Camera.rotate(dx, dy)` for `self.free`: `self.yaw -= dx * 0.22`
  - In `App.update(dt)`:
    - `if pressed(glfw.KEY_LEFT): cam.rotate(-140*dt, 0)` -> ensure left arrow turns left.
    - `if pressed(glfw.KEY_RIGHT): cam.rotate(140*dt, 0)` -> ensure right arrow turns right.
- [ ] **Step 1.4: Run test to verify pass**
  Run `python -m unittest tests/test_mouse_and_view.py`.

---

### Task 2: Synthesize Oak Wood Texture & Preserve Table Model Shape

- [ ] **Step 2.1: Write unit test for oak wood texture in `tests/test_mouse_and_view.py`**
  Verify `make_surface_images()["wood"]` returns image with warm golden-oak palette and distinct grain contrast.
- [ ] **Step 2.2: Implement `_oak_wood()` in `surface_materials.py`**
  - Synthesize authentic Oak wood grain (1024x512):
    - Warm honey-amber oak base `(198, 156, 110)`.
    - Annual growth rings with undulating sinusoidal grain arches.
    - Fine medullary rays and earlywood/latewood pore structure with visible contrast ($\pm 25-35$).
- [ ] **Step 2.3: Update wood color and texture binding in `classroom.py`**
  - Set `COLORS["wood"] = (.90, .82, .70)` (natural oak tint, avoiding blown-out white).
  - Set `MATERIALS["wood"] = (0.38, 0.40, 0.25)` (satin finish, natural wood specularity).
  - Ensure `table()` geometry remains 100% original (no shape changes).
  - Ensure texture `self.textures["wood"]` is properly bound during drawing of student and teacher desks.
- [ ] **Step 2.4: Run unit test to confirm pass**
  Run `python -m unittest tests/test_mouse_and_view.py`.

---

### Task 3: Expansive Outdoor Sky & City Window View

- [ ] **Step 3.1: Upgrade outdoor panoramas in `surface_materials.py`**
  - `_daylight()`: Bright daytime blue sky gradient, cumulus clouds, distant city skyline/campus architecture with windows and roofs, green trees and ground level.
  - `_sunset()`: Dramatic golden hour twilight gradient, backlit skyline silhouette with warm lit windows, glowing clouds.
- [ ] **Step 3.2: Rebuild outdoor backdrop geometry in `classroom.py`**
  - Replace the 45cm flat board with an expansive outdoor panorama placed 15-20m away:
    - Window wall backdrop at $X = W + 16.0$, spanning $Y = -6 \dots L + 10$, $Z = -3 \dots +18$.
    - Corridor/transom window backdrop at $X = -16.0$, spanning $Y = -6 \dots L/2$, $Z = -3 \dots +18$.
  - Group as `"daylight"` and ensure it renders self-luminous so it doesn't attenuate like an interior wall.
  - Adjust glass transparency in `COLORS["glass"] = (.82, .88, .92, .08)` for crystal clear transparency.
- [ ] **Step 3.3: Update `realistic_renderer.py` and `classroom.py` rendering pass**
  - When rendering `"daylight"` backdrop in `draw_opaque`, bind `self.textures["daylight"]` (or `"sunset"`) and set `u_emissive_factor = 1.0` so it radiates outdoor sky brightness.
- [ ] **Step 3.4: Verify outdoor rendering via test**
  Run `python -m unittest tests/test_mouse_and_view.py`.

---

### Task 4: Comprehensive Verification & Visual Check

- [ ] **Step 4.1: Run `py_compile` across all files**
  `python -m py_compile classroom.py surface_materials.py realistic_renderer.py`
- [ ] **Step 4.2: Run entire test suite**
  `python -m unittest discover -s tests -p "test_*.py"`
- [ ] **Step 4.3: Generate headless verification previews**
  `python classroom.py --hidden --verify previews`
- [ ] **Step 4.4: Inspect previews and verification.json**
  Confirm:
  - `previews/side_window.png` and `previews/inside.png` clearly show outdoor city/sky through the window.
  - Tables display rich warm Oak wood grain.
  - `opengl_errors == 0`, `shader_errors == []`, `fbo_complete == true`.

