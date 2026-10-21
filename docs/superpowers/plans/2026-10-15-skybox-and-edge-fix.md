# 360° Skybox & Surface Edge Artifact Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

This plan resolves:
1. **Edge Black Color & Texture Stretching**: Replaces fixed $(0, 0) \to (1, 1)$ UV mapping with metric world-space UV tiling on boxes/walls, clamps screen-space derivative bump mapping in `SCENE_FS`, and adds edge-aware depth rejection in `SSAO_FS` to eliminate black halos on edges.
2. **True 360° Skybox System**: Replaces the flat billboard image with an enclosed 360-degree panoramic skybox that wraps around the entire world in all directions, so when walking close to the window, the sky, city, and horizon surround the view seamlessly with no image borders.

---

## File Structure

- [surface_materials.py](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/surface_materials.py):
  - Seamless 360° panoramic skybox texture synthesis for `daylight` and `sunset` (2048x1024 or 1024x512 wrap-around continuity).
- [classroom.py](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/classroom.py):
  - Proportional / metric UV mapping in `draw_box()` based on physical face dimensions (meters) to eliminate texture stretching on edges and trims.
  - Build 360° Skybox geometry (cylindrical or dome enclosure) with outward/inward facing normals and seamless spherical coordinates.
  - Update `draw_opaque()` to render the 360° skybox with emissive factor.
- [realistic_renderer.py](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/realistic_renderer.py):
  - Clamp normal derivative bump gradients in `SCENE_FS` to prevent normal inversion and pitch-black edge artifacts.
  - Add edge-aware depth discontinuity check in `SSAO_FS` to prevent dark halos along silhouette edges.
- `tests/test_skybox_and_edges.py`:
  - Unit tests verifying seamless panorama wrap, metric UV computation, and shader compilation.

---

## Tasks

### Task 1: Fix Edge Black Artifacts & Texture Stretching

- [ ] **Step 1.1: Write failing unit test in `tests/test_skybox_and_edges.py`**
  Verify that metric UV mapping produces proportional aspect ratios and that shader compilation passes without warnings.
- [ ] **Step 1.2: Implement metric / proportional UV mapping in `draw_box` in `classroom.py`**
  - Compute face UVs proportional to face length and width (e.g. for plaster walls, 1 meter = 1 repeat; for wooden tabletop edges, keep edge UVs proportional to height rather than stretching a full texture unit across 28mm).
- [ ] **Step 1.3: Update `SCENE_FS` in `realistic_renderer.py`**
  - Clamp bump mapping gradient: `grad = clamp(surf_grad / det, vec3(-2.5), vec3(2.5));` and ensure `abs(det) > 1e-4`.
- [ ] **Step 1.4: Update `SSAO_FS` in `realistic_renderer.py`**
  - Add depth discontinuity rejection in normal reconstruction and sample loop so silhouette boundaries do not produce pitch-black halos.
- [ ] **Step 1.5: Run unit tests to confirm pass**

---

### Task 2: Seamless 360° Skybox Texture Synthesis

- [ ] **Step 2.1: Write unit test for 360° seamless wrap in `tests/test_skybox_and_edges.py`**
  Verify that column $X=0$ and column $X=width-1$ in `daylight` and `sunset` panoramas match within a small delta for seamless wrapping.
- [ ] **Step 2.2: Implement 360° seamless wrap in `surface_materials.py`**
  - Update `_daylight()` and `_sunset()` to use continuous angular coordinates ($2\pi \cdot x / \text{width}$) so the city skyline, clouds, and sky gradient wrap seamlessly at the $360^\circ$ seam.
- [ ] **Step 2.3: Run unit tests to verify seamless wrap**

---

### Task 3: 360° Skybox Geometry & Rendering

- [ ] **Step 3.1: Build 360° Skybox geometry in `classroom.py`**
  - Create `self.build_skybox()`: a large 32-segment panoramic cylinder/dome surrounding the classroom (radius 45m, height 36m, covering $Z=-8 \dots +28$).
  - Correct cylindrical UV mapping mapping $U \in [0, 1]$ around $360^\circ$ and $V \in [0, 1]$ from ground to zenith.
- [ ] **Step 3.2: Render Skybox with self-illumination in `classroom.py`**
  - Render with `u_emissive_factor = 1.1` and `glDepthMask(GL_FALSE)` so skybox is always at infinity and radiates natural outdoor illumination.
- [ ] **Step 3.3: Verify via unit test and headless render check**

---

### Task 4: Verification, Visual Previews & Documentation

- [ ] **Step 4.1: Run `py_compile` across all files**
- [ ] **Step 4.2: Run entire test suite**
- [ ] **Step 4.3: Generate headless verification previews with `python classroom.py --hidden --verify previews`**
- [ ] **Step 4.4: Inspect `side_window.png` and `inside.png`**
  - Confirm: No black edge borders or stretched textures on walls/furniture.
  - Confirm: Looking through the window shows a continuous 360° skybox view with no billboard borders.

