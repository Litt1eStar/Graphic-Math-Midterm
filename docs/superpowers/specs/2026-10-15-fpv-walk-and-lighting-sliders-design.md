# Specification: Authentic FPV Walk Mode & Adjustable Lighting Sliders

## 1. Overview & Objectives
This feature delivers an immersive First-Person View (FPV) walk mode and an interactive, real-time lighting adjustment panel for the S13-30612 OpenGL Classroom:
1. **Authentic FPV Walk Mode**:
   - Direct mouse-look navigation (cursor captured/locked in walk mode; mouse movement steers yaw and pitch directly without holding down a mouse button).
   - Grounded walking with **WASD** keys moving forward, backward, and strafing left/right relative to the horizontal facing direction.
   - Fixed realistic human standing eye height ($Z = 1.70\text{ m}$) with boundary collision against classroom walls and entry vestibule.
   - Seamless cursor toggle with <kbd>Tab</kbd> to switch between FPV Walk Mode and Cursor/HUD Mode.
2. **Interactive Lighting Sliders**:
   - Real-time adjustable sliders on the HUD for fine-grained visual tuning:
     - **Sunlight Intensity**: Controls directional sun illumination through the window wall ($0.0 \dots 2.0$, default $1.0$).
     - **Interior Fluorescent Intensity**: Controls ceiling luminaire brightness and downward light pools on desks and the floor ($0.0 \dots 2.0$, default $1.0$).
     - **God Rays Opacity**: Controls volumetric light shaft alpha/visibility ($0.0 \dots 1.0$, default $0.35$).
     - **Ambient Brightness**: Controls base shadow illumination and overall room visibility ($0.0 \dots 1.0$, default $0.40$).
   - Dynamic real-time response: Adjusting any slider immediately updates OpenGL fixed-function lights (`GL_LIGHT0`, `GL_LIGHT1`, `GL_LIGHT2`, `GL_LIGHT_MODEL_AMBIENT`), god ray transparency, and luminaire glow.

---

## 2. Technical Constraints & Principles
- **OpenGL Pipeline**: Standard OpenGL 2.1+ fixed-function pipeline (`PyOpenGL`) with GLFW windowing. Zero external GLSL shader dependencies.
- **Pure Procedural Assets**: Zero external textures, fonts, or 3D models.
  - Slider UI elements (tracks, knobs, labels, values) generated procedurally via Pillow and rendered via dynamic OpenGL HUD textures/quads.
- **Pair Synchronization**: `classroom.py` and `surface_materials.py` remain side-by-side and fully compatible.
- **Backward Compatibility**: Existing camera presets (1: Overview, 3: Exterior, 4: Top View) and automated tour (<kbd>P</kbd>) remain fully operational. Preset 2 ("Inside") launches directly into FPV Walk Mode.
- **Verification Integrity**: Must pass `python -m py_compile classroom.py surface_materials.py` and automated verification `python classroom.py --hidden --verify previews` with zero OpenGL errors.

---

## 3. Detailed Technical Design & Builder Resolution

### 3.1. FPV Walk Camera & Input Handling
- **Eye Height & Grounding**:
  - In FPV Walk Mode (Preset 2), camera eye height is locked to standing eye-level ($Z = 1.70\text{ m}$).
  - Movement plane is strictly horizontal ($XY$), decoupled from camera pitch angle.
- **Movement Vectors**:
  - Let $\theta$ be `camera.yaw` in radians.
  - Forward vector: $(\cos\theta, \sin\theta, 0)$
  - Right strafe vector: $(\sin\theta, -\cos\theta, 0)$
  - Speed: $3.0\text{ m/s}$ (normal walk), $5.5\text{ m/s}$ (holding <kbd>Shift</kbd> to sprint).
- **Collision Detection & Boundaries**:
  - Clamps player $(X, Y)$ within valid walking areas:
    - Main classroom area: $X \in [0.45\text{ m}, W - 0.45\text{ m}]$, $Y \in [0.45\text{ m}, L - 0.45\text{ m}]$.
    - Entry hallway extension: $X \in [0.45\text{ m}, 2.65\text{ m}]$, $Y \in [L - 0.45\text{ m}, L + V_{\text{depth}} - 0.45\text{ m}]$.
  - Prevents the user from walking out through solid walls or disappearing into the void.
- **Mouse Look & Cursor Management (Builder Call)**:
  - Cursor lock (`glfw.CURSOR_DISABLED`) is scoped **strictly to Preset 2 (FPV Walk)**.
  - In Orbit views (Presets 1, 3, 4), the cursor is **always normal** (`glfw.CURSOR_NORMAL`), and clicking/dragging rotates the orbit camera normally.
  - In Preset 2, the cursor starts disabled (direct mouselook). Pressing <kbd>Tab</kbd> unlocks the cursor to `glfw.CURSOR_NORMAL` for dragging HUD sliders.
  - When in Preset 2 with cursor unlocked, clicking anywhere in the 3D viewport outside HUD widgets recaptures the cursor back into FPV Walk Mode.

### 3.2. Key Bindings & Input Priority (Builder Call)
- Unmodified keys <kbd>1</kbd>–<kbd>4</kbd> **always** switch camera presets globally (1: Overview, 2: Inside/FPV, 3: Exterior, 4: Top View).
- Slider interaction is primarily driven by direct mouse click and drag on the HUD slider tracks/knobs.
- In addition, keys <kbd>[</kbd> and <kbd>]</kbd> decrease and increase the actively selected slider.
- Keys <kbd>Ctrl</kbd> + <kbd>1</kbd>–<kbd>4</kbd> (or clicking on a slider) select which of the 4 sliders is active for keyboard adjustment.
- Legacy freecam toggle (<kbd>F</kbd>): In Preset 2, pressing <kbd>F</kbd> toggles between grounded FPV walking ($Z = 1.70\text{ m}$) and free flight mode (allowing <kbd>Q</kbd>/<kbd>E</kbd> vertical elevation).

### 3.3. Adjustable Lighting System Architecture
- **Lighting State Model**:
  Stored in `App` and passed to `Classroom.draw`:
  - `sun_intensity`: Float $[0.0, 2.0]$, default $1.0$.
  - `interior_intensity`: Float $[0.0, 2.0]$, default $1.0$.
  - `god_rays_opacity`: Float $[0.0, 1.0]$, default $0.35$.
  - `ambient_brightness`: Float $[0.0, 1.0]$, default $0.40$.
- **OpenGL Lighting Modulation**:
  - `GL_LIGHT0` (Sun / Window Key Light): Base preset color scaled by `sun_intensity`.
  - `GL_LIGHT1` & `GL_LIGHT2` (Interior Downward Fill): Base color scaled by `interior_intensity`. If `interior_intensity == 0.0` or `not interior_lights`, interior lights are disabled.
  - `GL_LIGHT_MODEL_AMBIENT`: Base ambient RGB scaled by `ambient_brightness / 0.40`.
  - **God Rays**: Rendered with vertex alpha multiplied by `god_rays_opacity / 0.35`. If `god_rays_opacity == 0.0` or `not god_rays`, god rays draw call is skipped.
  - **Downward Light Pools & Luminaire Glow**: Rendered with alpha multiplied by `interior_intensity`. If `interior_intensity == 0.0`, rendering is skipped.

### 3.4. Interactive HUD Sliders
- **Visual Design**:
  - Translucent glassmorphism HUD panel located at top-right ($X = \text{width} - 350$, $Y = 20$, $W = 330$, $H = 210$).
  - 4 horizontal slider rows:
    1. **SUNLIGHT**: $[0.0 \dots 2.0]$, step $0.05$
    2. **INTERIOR**: $[0.0 \dots 2.0]$, step $0.05$
    3. **GOD RAYS**: $[0.0 \dots 1.0]$, step $0.02$
    4. **AMBIENT**: $[0.0 \dots 1.0]$, step $0.02$
  - Each row displays: Label, numerical value badge (e.g. `1.00x` or `35%`), slider rail, and glowing draggable thumb/knob.
- **Interactions**:
  - Hover highlights knob.
  - Mouse click/drag anywhere on rail or knob smoothly maps mouse $X$ coordinate to slider parameter value.
- **HUD Help Bar Update**:
  - Updated help strip: `WASD Move | Tab Cursor/Walk | Drag Sliders | [ ] Adjust | T Sun | L Lights | G Rays | P Tour | Esc Exit`.

---

## 4. Verification & Testing Strategy
1. **Compilation Check**: `python -m py_compile classroom.py surface_materials.py` exits code 0.
2. **Headless Render Verification**: `python classroom.py --hidden --verify previews` runs all snapshot sequences including:
   - Verification of lighting slider ranges (minimum, nominal, maximum).
   - Zero OpenGL errors in `previews/verification.json`.
3. **Automated Unit Tests**: Add tests in `tests/test_fpv_lighting.py` validating:
   - Camera FPV walk mode vectors, grounding at $Z = 1.70\text{ m}$, and boundary clamping.
   - Slider value clamping, normalization, and light state synchronization.
