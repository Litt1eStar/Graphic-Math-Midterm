# Project Guidelines & Memory: S13-30612 OpenGL Classroom

## 1. Project Identity & Purpose
- **Project**: S13-30612 — Python + OpenGL Interactive Classroom Digital Twin (Version 14).
- **Academic Context**: Midterm assignment "Room in 6th floor modeling" (Computer Graphics).
- **Core Directive**: 100% of the 3D geometry and surface textures must be synthesized procedurally in Python code. **Do not use external 3D model files (`.obj`, `.gltf`, `.fbx`) or external image files for textures**.
- **Delivery Target**: Standalone executable (`S13-30612.exe`), clean source scripts (`classroom.py`, `surface_materials.py`, `realistic_renderer.py`), JSON config (`room_config.json`), and comprehensive documentation (`README_TH.md`, `PRESENTATION_TH.md`).

---

## 2. File Responsibilities & Architecture
- **[classroom.py](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/classroom.py)**: Main engine. Houses scene geometry, display lists compilation, camera subsystem (orbit & FPV physical walk with bob/acceleration/smoothing), 7-channel HUD sliders, input callbacks, and headless verification.
- **[surface_materials.py](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/surface_materials.py)**: Procedural texture generator. Uses PIL to generate wood grain, terrazzo aggregate, plaster wall, and daylight/sunset backdrops. **Must always accompany `classroom.py`**.
- **[realistic_renderer.py](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/realistic_renderer.py)**: Full GLSL 3.3 shader pipeline (Option B). Houses per-pixel Cook-Torrance GGX/Lambert PBR, PCF sun shadow mapping, HDR RGBA16F FBO, 5-level bloom, ACES tonemapping, FXAA 3.11, SSAO, volumetric god rays, and drifting dust particle system. All shaders embedded as pure Python string constants (no external `.glsl` files). **Must always accompany `classroom.py`**.
- **[room_config.json](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/room_config.json)**: External configuration file defining dimensions for the room, vestibule, columns, and seating layout.
- **[data/](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/data/)**: Ground-truth architectural plans (`floor6_plan.pdf`), tape/laser measurement photos (`measurement_01..06.jpg`), reference photos, and revision history manifest (`sources.json`).
- **[previews/](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/previews/)**: Automated render verification captures and JSON status reports (`verification.json`, `controls_verification.json`).
- **[PRESENTATION_TH.md](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/PRESENTATION_TH.md)**: 5-minute timed presentation script and cue sheet for demonstrations.
- **[README_TH.md](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/README_TH.md)**: Full Thai technical manual and coordinate guide.

---

## 3. Spatial & Geometric Ground Truth (V14 Approved)
- **Coordinate System**: Metric units ($m$). $Z$ is up ($+Z$). Origin $(0, 0, 0)$ is at the front-right floor corner when facing the front screen.
  - Front wall / Screen: $Y = 0$.
  - Window wall: $X = \text{width} = 11.79\text{ m}$.
  - Right wall (opposite window): $X = 0$.
  - Rear wall: $Y = \text{depth} = 12.10\text{ m}$.
- **Confirmed Room Dimensions**:
  - Height: $3.46\text{ m}$ (Explicitly confirmed by user measurement).
  - Main width ($X$): $11.79\text{ m}$ (Visible in measurements).
  - Main depth ($Y$): $12.10\text{ m}$ (Matches photo measurements).
- **Entrance Vestibule & Door**:
  - Position: Rear RIGHT when standing inside facing the screen ($X = 0 \dots 2.90\text{ m}$, $Y = 12.10 \dots 16.11\text{ m}$, depth $4.01\text{ m}$).
  - Double glass door: Width $2.30\text{ m}$, Height $2.75\text{ m}$. Right door jamb is flush with the return wall.
  - Left entrance column projection: $0.25\text{ m}$ (thinned per user correction).
  - No standalone table in the entry hallway.
- **Furniture & Equipment Layout**:
  - **Student Desks & Chairs**: 3 longitudinal blocks $\times$ 6 rows = 36 tables, 72 seats. Each transverse pair seats 4 students on 2 touching tables.
  - **Chairs**: Black padded cushions, chrome trapezoid frame with bent floor runners, and manufacturer badge.
  - **Instructor Station**: $3.20\text{ m}$ long desk touching the front-left student pair. Equipped with silver iMac, keyboard, and mouse; screen faces the front wall (instructor sits behind desk facing classroom). No separate computer case. High-back ergonomic swivel chair.
  - **Displays**: 1 large front-right TV on a floor stand; 2 overhead TVs mounted to the middle ceiling beam with angled tilt; 1 large front projection screen. No front upper wall TVs, wooden podium, or wall speakers.
  - **A/C & Electrical**: 4 under-ceiling air conditioners (2 on left wall, 2 on right wall) with underside return grilles. Circuit breaker and single remote on $X=0$ wall at $Y=7.00\text{ m}$ (raised $+0.40\text{ m}$ from V12), connected via vertical PVC conduits.
  - **Ceiling & Roof**: Exposed cross-beams, fluorescent dual-lamp fixtures, PVC conduits wrapping columns, two ceiling access hatches in hallway, and turret CCTV camera under rear beam.

---

## 4. Engineering Standards & Workflows
- **Display List Compilation**: All static geometry must be compiled into display lists (`glGenLists`, `glNewList`, `glCallList`) grouped by material and boundary, emitting secondary color material attributes.
- **Outward Normals**: All custom polygon faces and cuboids must supply normalized outward normals (`glNormal3f`) for Cook-Torrance GGX/Lambert PBR lighting and shadow map projection.
- **Alpha Blending**: Transparent surfaces (glass doors, window glazing, contact shadows, god rays, dust) must be drawn with `glDepthMask(GL_FALSE)` and appropriate blending modes (`GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA` or additive `GL_SRC_ALPHA, GL_ONE`).
- **Validation**:
  - Compile check: `python -m py_compile classroom.py surface_materials.py realistic_renderer.py`
  - Automated render test: `python classroom.py --hidden --verify previews`
  - Unit tests: `python -m unittest discover -s tests -p "test_*.py"`
  - Check `verification.json` for `opengl_errors == 0`, `shader_errors == []`, `fbo_complete == true`, and shadow/bloom validation passes.

---

## 5. Superpowers Skill Integration
This workspace is equipped with the **Superpowers** development framework (`.agents/skills/`).
When executing engineering tasks:
1. Always invoke `using-superpowers` at conversation start.
2. Follow the disciplined workflow: **Brainstorming** $\rightarrow$ **Writing Plans** $\rightarrow$ **Test-Driven Development (TDD)** $\rightarrow$ **Systematic Debugging** $\rightarrow$ **Verification Before Completion**.
3. Do not jump into code modifications without understanding specifications and planning verified steps.

