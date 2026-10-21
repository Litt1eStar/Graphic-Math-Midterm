# Nostalgic Volumetric God Rays & 3D Layered Sky View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the classroom's artificial box-like god rays and flat skybox image into heartwarming, shadow-mapped volumetric sunbeams and a true 3D multi-layer exterior campus & procedural sky dome.

**Architecture:**
1. Replace the hollow 4-sided box god rays with a multi-slice volumetric light field that samples the real-time sun shadow map (`u_shadow_map`), performs soft-depth fade against `u_depth_texture`, applies transverse Gaussian edge feathering, and uses Henyey-Greenstein forward scattering in warm nostalgic tones.
2. Replace the flat-looking zoomed-in cylinder image with a per-pixel procedural atmospheric sky shader (Rayleigh/Mie scattering, sun corona, drifting FBM clouds at eye-level horizon) paired with real 3D multi-layer exterior campus buildings, rooftops, and tree canopies below the 6th floor for genuine 3D parallax.

**Tech Stack:** Python 3, PyOpenGL (GLSL 3.30 compatibility profile), GLFW, Pillow.

**Spec:** Approved inline in conversation (2026-10-16).

## Global Constraints
- 100% procedural geometry and textures in Python/GLSL: zero external 3D models (`.obj`, `.gltf`) or external image files (`.png`, `.jpg`) or external `.glsl` files.
- Keep `classroom.py`, `surface_materials.py`, and `realistic_renderer.py` synchronized.
- All 53 existing unit tests plus new tests must pass; `python classroom.py --hidden --verify previews` must report `opengl_errors == 0`, `shader_errors == []`, and `fbo_complete == true`.

## Review Focus
- Looking straight out or down from the 6th-floor window must show eye-level horizon, crisp sky/clouds above, and 3D buildings/treetops below with real parallax when moving the camera.
- God rays must not exhibit hard diagonal polygon edges or wash out desks into opaque milky white triangles.
- God rays must naturally split around window mullions via shadow-map sampling and fade softly where they intersect desks and the floor.
- Far clip plane in perspective matrix must encompass the 3D exterior skyline and sky dome without clipping (`far >= 260.0`).

---

### Task 1: Per-Pixel Procedural Sky Dome & Aerial Perspective in `realistic_renderer.py`

**Files:**
- Modify: `realistic_renderer.py` (`SCENE_FS`, `RealisticRenderer._init_gl`, `RealisticRenderer.render_frame`)
- Modify: `surface_materials.py` (`_daylight`, `_sunset` horizon alignment)
- Test: `tests/test_skybox_and_edges.py`

**Interfaces:**
- Produces:
  - `u_is_skybox` uniform (`int`) in `SCENE_FS`: when `1`, evaluates per-pixel procedural sky dome (Rayleigh/Mie gradient, sun disk & corona, animated 2-layer FBM clouds, and eye-level horizon at `dir.z == 0`).
  - `u_time` uniform (`float`) in `SCENE_FS` for subtle cloud drift.
  - Aerial perspective haze in `SCENE_FS` for exterior 3D buildings (`dist > 20.0` outside the classroom bounds).

- [ ] **Step 1.1: Write failing unit tests in `tests/test_skybox_and_edges.py`**
  Verify that `SCENE_FS` includes procedural sky evaluation (`u_is_skybox`) and aerial perspective haze, and that `surface_materials` places the horizon near vertical center (`0.48..0.55`).
- [ ] **Step 1.2: Run unit test to verify it fails**
  Run: `python -m unittest tests/test_skybox_and_edges.py`
- [ ] **Step 1.3: Implement procedural sky shader and aerial perspective in `realistic_renderer.py` and horizon fix in `surface_materials.py`**
  - Increase camera far clip plane from `180.0` to `280.0` in `realistic_renderer.py`.
  - Add `u_is_skybox` and `u_time` uniforms to `SCENE_FS` and `RealisticRenderer`.
  - Implement heartwarming nostalgic daylight & golden-hour sunset sky gradients, Mie sun glow, and procedural FBM cloud layers in `SCENE_FS`.
  - Add distance-based aerial haze for exterior 3D architecture (`v_world_pos.x > 13.0 || v_world_pos.x < -1.0 || v_world_pos.y < -1.0 || v_world_pos.y > 17.0`).
- [ ] **Step 1.4: Run unit tests to verify pass**
  Run: `python -m unittest tests/test_skybox_and_edges.py`

---

### Task 2: True 3D Multi-Layer Campus & Cityscape Exterior in `classroom.py`

**Files:**
- Modify: `classroom.py` (`Classroom.build`, `Classroom.build_skybox_list`, `Classroom.draw_opaque`)
- Test: `tests/test_skybox_and_edges.py`

**Interfaces:**
- Consumes: `u_is_skybox` uniform in `SCENE_FS`
- Produces:
  - `Classroom.build_exterior_scenery(W, L, H)` in `classroom.py`: builds 3D layered exterior group `"exterior_3d"` containing:
    - Lower street/courtyard ground plane and 3D lush tree canopies below the 6th floor ($Z = -12\text{ m} \dots -2.5\text{ m}$).
    - Mid-ground 3D campus buildings ($X = 24\text{ m} \dots 46\text{ m}$) with architectural ledges, window bays, and rooftop structures below/near eye level.
    - Distant 3D city skyline towers ($X = 68\text{ m} \dots 115\text{ m}$) spanning the horizon for multi-depth parallax.

- [ ] **Step 2.1: Write failing unit test in `tests/test_skybox_and_edges.py`**
  Verify that `Classroom` builds `"exterior_3d"` parts at multiple depth layers ($X \in [20, 50]$ and $X > 60$) providing 3D parallax outside the window wall.
- [ ] **Step 2.2: Run unit test to verify it fails**
  Run: `python -m unittest tests/test_skybox_and_edges.py`
- [ ] **Step 2.3: Implement `build_exterior_scenery` and `u_is_skybox` binding in `classroom.py`**
  - Enlarge skybox cylinder radius to `R = 160.0` (`z_bot = -45.0, z_top = 95.0`) and set `u_is_skybox = 1` when drawing `self.skybox_list`.
  - Build 3D mid-ground campus buildings, tree canopies, and distant skyline towers in `build_exterior_scenery()`, excluded from the sun shadow pass so they don't block classroom sunlight.
- [ ] **Step 2.4: Run unit tests to verify pass**
  Run: `python -m unittest tests/test_skybox_and_edges.py`

---

### Task 3: Shadow-Mapped, Soft-Depth Nostalgic Volumetric God Rays & Sunlit Dust

**Files:**
- Modify: `classroom.py` (`Classroom.build_god_rays`)
- Modify: `realistic_renderer.py` (`GODRAY_VS`, `GODRAY_FS`, `DUST_VS`, `DUST_FS`, `RealisticRenderer._init_gl`, `RealisticRenderer.render_frame`)
- Test: `tests/test_renderer_atmosphere.py`

**Interfaces:**
- Produces:
  - Feathered volumetric slice lattice in `Classroom.build_god_rays` with `(ray_t, edge_u)` UV coordinates and zero hard box corners.
  - Shadow-map-aware (`u_shadow_map` + `u_light_space_matrix`) and soft-depth-aware (`u_depth_texture` + `u_viewport`) `GODRAY_FS` with Henyey-Greenstein phase and warm nostalgic golden-ivory / sunset-amber scattering.
  - Bokeh dust motes in `DUST_FS` that softly glow when illuminated by the sunbeams.

- [ ] **Step 3.1: Write failing unit tests in `tests/test_renderer_atmosphere.py`**
  Verify that `GODRAY_FS` samples `u_shadow_map` and `u_depth_texture` for soft volumetric occlusion and that rendered god rays produce smooth, non-saturated warm luminance without hard edge artifacts.
- [ ] **Step 3.2: Run unit test to verify it fails**
  Run: `python -m unittest tests/test_renderer_atmosphere.py`
- [ ] **Step 3.3: Implement shadow-mapped soft volumetric god rays and bokeh dust**
  - Update `build_god_rays()` in `classroom.py` to generate a smooth 3D volumetric slice lattice across the window bays instead of hollow 4-sided boxes.
  - Update `GODRAY_FS` in `realistic_renderer.py` to sample `u_shadow_map` (carving real window mullion shadows in mid-air), compare against `u_depth_texture` for soft surface fade on desks/floor, apply `sin(v_uv.y * PI)` transverse feathering, and compute Henyey-Greenstein forward scattering with warm nostalgic colors.
  - Update `DUST_VS` / `DUST_FS` for soft warm bokeh dust particles.
- [ ] **Step 3.4: Run unit tests to verify pass**
  Run: `python -m unittest tests/test_renderer_atmosphere.py`

---

### Task 4: Full Verification & Visual Inspection

**Files:**
- Verify: `classroom.py`, `surface_materials.py`, `realistic_renderer.py`, `previews/verification.json`

- [ ] **Step 4.1: Run `python -m py_compile classroom.py surface_materials.py realistic_renderer.py`**
- [ ] **Step 4.2: Run full unit test suite `python -m unittest discover -s tests -p "test_*.py"`**
- [ ] **Step 4.3: Run headless verification `python classroom.py --hidden --verify previews`**
- [ ] **Step 4.4: Visually inspect `previews/side_window.png`, `previews/inside.png`, `previews/realistic_daylight.png`, and `previews/sunset_god_rays.png`**

