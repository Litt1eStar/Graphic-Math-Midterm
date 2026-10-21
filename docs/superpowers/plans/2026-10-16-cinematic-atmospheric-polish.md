# Cinematic & Atmospheric Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Elevate the classroom's nostalgic, heartwarming visual realism with four targeted shader and geometry upgrades: (1) high-contrast cerulean-to-gold sky dome with 3D self-shadowed cumulus clouds and detailed exterior building facades (mullions + warm lit rooms at sunset), (2) anti-washout volumetric grazing control so sunset god rays form distinct crepuscular shafts without blowing out the far-left wall, (3) physical window-bay Fresnel reflections on the polished terrazzo floor and varnished oak desks, and (4) subtle window glass sky glint with nostalgic film grading and soft optical vignette.

**Architecture:**
1. **`realistic_renderer.py` (`SCENE_FS`)**:
   - Upgrade `eval_procedural_sky` with faster horizon-to-cerulean elevation ramp and 3D self-shadowed cloud bases (`cloud_grad`).
   - Add procedural exterior building facade detailing (concrete panel joints, vertical window mullions, sky reflection gradient, and warm lit office windows in sunset mode).
   - Add analytical ray-plane window-bay Fresnel reflections (`eval_window_reflection`) on smooth upward-facing interior surfaces (terrazzo floor and oak tabletops).
   - Add subtle Fresnel sky glint on transparent window glass (`v_alpha < 0.85`).
2. **`realistic_renderer.py` (`GODRAY_FS` & `COMPOSITE_FS`)**:
   - In `GODRAY_FS`, add longitudinal overlap compensation (`overlap_comp`) when viewing lengthwise down the window wall (`abs(V.y)` high), distance damping (`dist_damping`), and stronger mullion shadow contrast (`mix(0.18, 1.0, shadow_raw)`).
   - In `COMPOSITE_FS`, add subtle warm nostalgic film grading and a gentle 8% optical lens vignette.

**Tech Stack:** Python 3, PyOpenGL (GLSL 3.30 compatibility profile), `unittest`.

---

### Task 1: Crisp Sky Gradient, Sculpted 3D Clouds & Exterior Building Facade Detail

**Files:**
- Modify: `realistic_renderer.py` (`SCENE_FS`)
- Modify: `classroom.py` (`draw_opaque`)
- Modify: `tests/test_skybox_and_edges.py`

- [ ] **Step 1: Add unit test in `tests/test_skybox_and_edges.py` checking for sculpted cloud shading, exterior facade mullions, and window Fresnel reflection function in `SCENE_FS`**
- [ ] **Step 2: Implement upgraded `eval_procedural_sky`, exterior facade mullion/lit-window shader logic, and `eval_window_reflection` in `SCENE_FS` (`realistic_renderer.py`) and tune skybox emissive factor in `classroom.py`**
- [ ] **Step 3: Run `python -m unittest tests/test_skybox_and_edges.py`**

### Task 2: Anti-Washout Volumetric Grazing Control & Cinematic Composite Polish

**Files:**
- Modify: `realistic_renderer.py` (`GODRAY_FS`, `COMPOSITE_FS`)
- Modify: `tests/test_renderer_atmosphere.py`

- [ ] **Step 1: Add unit test in `tests/test_renderer_atmosphere.py` checking for `overlap_comp` in `GODRAY_FS` and `vignette` in `COMPOSITE_FS`**
- [ ] **Step 2: Update `GODRAY_FS` and `COMPOSITE_FS` in `realistic_renderer.py`**
- [ ] **Step 3: Run `python -m unittest tests/test_renderer_atmosphere.py`**

### Task 3: Full Verification & Visual Inspection

**Files:**
- Verify: `previews/verification.json`, `previews/side_window.png`, `previews/sunset_god_rays.png`, `previews/realistic_daylight.png`, `previews/inside.png`

- [ ] **Step 1: Run `python -m py_compile classroom.py surface_materials.py realistic_renderer.py`**
- [ ] **Step 2: Run `python classroom.py --hidden --verify previews` and inspect rendered images**
- [ ] **Step 3: Run `python -m unittest discover -s tests -p "test_*.py"`**

