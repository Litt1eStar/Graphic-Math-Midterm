# Dual-Config Lighting, Volumetric God Rays, and Interior Glow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement dual lighting presets (Daylight and dramatic low-angle Sunset) with procedural volumetric god rays streaming through windows, accompanied by toggleable interior fluorescent luminaire glow and downward light pools.

**Architecture:** Extend `surface_materials.py` with an algorithmic sunset horizon generator (`_sunset()`). In `classroom.py`, introduce a dynamic lighting state machine (`lighting_preset`, `interior_lights`, `god_rays`) driving OpenGL fixed-function lights (`GL_LIGHT0`, `GL_LIGHT1`, `GL_LIGHT2`, ambient model), compile procedural alpha-blended god ray shafts and downward luminaire light pool discs into dedicated display lists, and expose runtime toggles via keyboard callbacks (`T`, `L`, `G`) and HUD status displays.

**Tech Stack:** Python 3.10+, PyOpenGL 3.1.10, GLFW 2.10.2, Pillow >= 10.0, standard OpenGL fixed-function compatibility profile.

**Spec:** `docs/superpowers/specs/2026-10-15-lighting-and-godrays.md`

## Global Constraints
- Must remain 100% procedurally generated; zero external image files or 3D model formats.
- Must remain strictly compatible with standard OpenGL fixed-function pipeline (no GLSL shaders).
- `surface_materials.py` and `classroom.py` must maintain mutual backward compatibility and side-by-side execution.
- Automated verification (`python classroom.py --hidden --verify previews`) must exit with 0 OpenGL errors.
- Both scripts must compile cleanly with `python -m py_compile classroom.py surface_materials.py`.

## Review Focus
1. **Alpha blending order & depth mask**: God rays and translucent light pools must disable `glDepthMask` and enable alpha blending so they never occlude furniture or solid walls behind them.
2. **Window boundary alignment**: Light shafts must anchor exactly to actual window aperture geometry on the window wall ($X = 11.79\text{ m}$) rather than arbitrary space.
3. **Smooth visual transitions**: Toggling between daylight, sunset, and interior lights must cleanly switch `GL_LIGHT` parameters and textures without texture leaking or display list corruptions.
4. **Performance impact**: Volumetric shafts and light pools must be compiled into static display lists to maintain high frame rates.
5. **Headless test safety**: The headless `--verify previews` pipeline must run non-interactively without requiring GLFW display window focus.

---

### Task 1: Procedural Sunset Texture Synthesis

**Files:**
- Modify: `surface_materials.py:80-120`
- Create: `tests/test_materials.py`

**Interfaces:**
- Consumes: `PIL.Image`, `PIL.ImageDraw`, `PIL.ImageFilter`
- Produces: `make_surface_images() -> dict[str, Image.Image]` containing key `"sunset"` in addition to `"daylight"`, `"floor"`, `"wood"`, `"panel"`

- [ ] **Step 1: Write the failing unit test for `surface_materials`**

Create `tests/test_materials.py`:
```python
from surface_materials import make_surface_images

def test_make_surface_images_contains_sunset():
    images = make_surface_images()
    assert "sunset" in images, "sunset texture must be generated"
    assert images["sunset"].mode == "RGB"
    assert images["sunset"].size == (512, 512)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_materials.py`
Expected: FAIL with `AssertionError: sunset texture must be generated`

- [ ] **Step 3: Implement `_sunset()` in `surface_materials.py`**

Add `_sunset()` to `surface_materials.py`:
- Generate a 512x512 RGB image with a twilight sky gradient: deep twilight violet-blue at top `(58, 48, 88)` fading to vibrant amber-orange `(245, 142, 60)` near horizon ($Y \approx 360$) and deep warm crimson `(175, 62, 45)` at the bottom edge.
- Render low-contrast distant building silhouettes in dark silhouette tone `(72, 54, 62)` and blurred tree masses with `ImageFilter.GaussianBlur(2.0)`.
- Register `"sunset": _sunset()` in `make_surface_images()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_materials.py`
Expected: PASS

- [ ] **Step 5: Verify compilation**

Run: `python -m py_compile surface_materials.py`
Expected: Exit code 0

---

### Task 2: Lighting Configuration Schema in `room_config.json`

**Files:**
- Modify: `room_config.json:25-35`
- Modify: `classroom.py:33-56` (Config loader validation)
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: JSON config structure from `room_config.json`
- Produces: `load_config(path)["lighting"]` dictionary defining default preset, sun trajectories, and intensities

- [ ] **Step 1: Write the failing test for lighting config**

Create `tests/test_config.py`:
```python
from classroom import load_config
from pathlib import Path

def test_lighting_config_present():
    cfg = load_config(Path("room_config.json"))
    assert "lighting" in cfg, "lighting config section required"
    assert cfg["lighting"]["default_preset"] in ("daylight", "sunset")
    assert "god_rays" in cfg["lighting"]
    assert "interior_lights" in cfg["lighting"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_config.py`
Expected: FAIL with `AssertionError: lighting config section required`

- [ ] **Step 3: Update `room_config.json` and `load_config()` in `classroom.py`**

In `room_config.json`, add:
```json
  "lighting": {
    "default_preset": "daylight",
    "god_rays": true,
    "interior_lights": true,
    "daylight": {
      "sun_position": [18.0, 6.0, 14.0],
      "sun_diffuse": [0.85, 0.88, 0.90],
      "ambient": [0.42, 0.42, 0.42]
    },
    "sunset": {
      "sun_position": [22.0, 4.0, 3.2],
      "sun_diffuse": [1.0, 0.58, 0.20],
      "ambient": [0.18, 0.16, 0.16]
    }
  }
```
Update `load_config(path)` in `classroom.py` to accept optional `lighting` with valid defaults if omitted.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_config.py`
Expected: PASS

---

### Task 3: Volumetric God Rays Generator in `classroom.py`

**Files:**
- Modify: `classroom.py` (Add `build_god_rays()`, display list compilation, and rendering calls)
- Create: `tests/test_god_rays.py`

**Interfaces:**
- Consumes: Window bay dimensions ($X = 11.79\text{ m}$, $Y = 0.48 \dots 11.14\text{ m}$, $Z = 0.94 \dots 2.82\text{ m}$)
- Produces: `Classroom.build_god_rays(preset: str)` generating display lists `god_rays_daylight` and `god_rays_sunset`

- [ ] **Step 1: Write test for god rays geometry compilation**

Create `tests/test_god_rays.py`:
```python
from classroom import Classroom, load_config
from pathlib import Path

def test_god_rays_lists_compiled():
    # Will check that god ray display lists or parts are registered
    cfg = load_config(Path("room_config.json"))
    # In headless testing, verify ray frustum count matches window bays (10 bays)
    assert hasattr(Classroom, "build_god_rays")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_god_rays.py`
Expected: FAIL with `AttributeError: type object 'Classroom' has no attribute 'build_god_rays'`

- [ ] **Step 3: Implement `build_god_rays()` in `classroom.py`**

In `classroom.py`:
- Define `build_god_rays()`:
  - For each window bay along $X = W$ ($Y \in [0.48, L-0.48]$):
    - Compute window sill and header coordinates: $(W, y_0, z_0)$ to $(W, y_1, z_1)$.
    - For **Daylight**: Cast frustum vector $\vec{d} = (-4.8, 0.4, -1.8)$. Top/bottom vertices project into the room.
    - For **Sunset**: Cast dramatic low-angle rake vector $\vec{d} = (-9.8, -0.6, -1.2)$, reaching across the student desks toward $X = 1.0\text{ m}$.
    - Construct quad faces for the volumetric beam envelope.
    - Assign vertex colors with alpha: sill vertices at $\alpha = 0.30$ (daylight) or $\alpha = 0.40$ (sunset golden), terminus vertices at $\alpha = 0.0$.
  - Compile into `self.god_rays_lists = {"daylight": lid_day, "sunset": lid_set}` using `glBlendFunc(GL_SRC_ALPHA, GL_ONE)` and `glDepthMask(GL_FALSE)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_god_rays.py`
Expected: PASS

---

### Task 4: Interior Fluorescent Glow & Downward Light Pools

**Files:**
- Modify: `classroom.py` (Add `build_interior_light_pools()`, luminaire glow geometry, and toggling logic)
- Create: `tests/test_interior_lighting.py`

**Interfaces:**
- Consumes: Ceiling luminaire coordinates $(x, y, H)$
- Produces: `Classroom.interior_light_list` (radial light pool decals on desks/floor) and dynamic luminaire glow display

- [ ] **Step 1: Write test for interior lighting methods**

Create `tests/test_interior_lighting.py`:
```python
from classroom import Classroom
def test_interior_methods_exist():
    assert hasattr(Classroom, "build_interior_light_pools")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_interior_lighting.py`
Expected: FAIL with `AttributeError: type object 'Classroom' has no attribute 'build_interior_light_pools'`

- [ ] **Step 3: Implement `build_interior_light_pools()` and emissive glow**

In `classroom.py`:
- In `build_interior_light_pools()`:
  - For each luminaire position $(x, y)$:
    - Create a floor light pool at $Z = 0.015\text{ m}$: `GL_TRIANGLE_FAN` centered at $(x, y)$ with radius $R = 1.25\text{ m}$. Center color: soft warm-white `(0.95, 0.98, 1.0, 0.22)`, perimeter color: `(0.95, 0.98, 1.0, 0.0)`.
    - If student tables overlap $(x, y)$, also project a desk light pool at desk height $Z = f["table_height"] + 0.002\text{ m}$.
  - Compile into `self.interior_pool_list`.
- In `fluorescent()`:
  - Add translucent luminaire glow envelope around the dual tube lamps (`COLORS["light"]` with alpha $0.35$).
  - When `interior_lights` is OFF, luminaire glow and light pools are suppressed, and interior ambient/fill lights `GL_LIGHT1` and `GL_LIGHT2` are dimmed to near-zero.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_interior_lighting.py`
Expected: PASS

---

### Task 5: Dynamic Preset Switching, Key Handlers, and HUD Integration

**Files:**
- Modify: `classroom.py:940-1065` (Light model setup, `on_key()`, `update()`, HUD panel)

**Interfaces:**
- Consumes: User keyboard inputs (`T`, `L`, `G`)
- Produces: Dynamic state transitions in `App`:
  - `T`: Toggles `lighting_preset` between `"daylight"` and `"sunset"`
  - `L`: Toggles `interior_lights` between `True` and `False`
  - `G`: Toggles `god_rays` between `True` and `False`
  - Backdrop plane switches between `textures["daylight"]` and `textures["sunset"]`
  - HUD overlay displays active preset and toggle states

- [ ] **Step 1: Write test for state transitions**

Create `tests/test_app_state.py`:
```python
from classroom import App, load_config
from pathlib import Path

def test_app_lighting_state_toggles():
    cfg = load_config(Path("room_config.json"))
    app = App(cfg, width=640, height=480, hidden=True)
    try:
        assert app.lighting_preset == "daylight"
        app.toggle_lighting_preset()
        assert app.lighting_preset == "sunset"
        app.toggle_interior_lights()
        assert app.interior_lights is False
        app.toggle_god_rays()
        assert app.god_rays is False
    finally:
        import glfw
        glfw.destroy_window(app.window)
        glfw.terminate()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_app_state.py`
Expected: FAIL with `AttributeError: 'App' object has no attribute 'toggle_lighting_preset'`

- [ ] **Step 3: Implement key handlers, dynamic OpenGL light update, and HUD**

In `classroom.py`:
- In `App.__init__()`:
  - Initialize `self.lighting_preset = "daylight"`, `self.interior_lights = True`, `self.god_rays = True`.
- Implement:
  - `toggle_lighting_preset()`: Alternates between `"daylight"` and `"sunset"`. Updates `GL_LIGHT0` position/diffuse and ambient model.
  - `toggle_interior_lights()`: Toggles boolean. Adjusts `GL_LIGHT1`/`GL_LIGHT2` diffuse levels.
  - `toggle_god_rays()`: Toggles boolean.
- In `on_key()`:
  - Map `glfw.KEY_T` $\rightarrow$ `self.toggle_lighting_preset()`
  - Map `glfw.KEY_L` $\rightarrow$ `self.toggle_interior_lights()`
  - Map `glfw.KEY_G` $\rightarrow$ `self.toggle_god_rays()`
- In `HUD`:
  - Add status badge: `PRESET: [DAYLIGHT|SUNSET] (T) | LIGHTS: [ON|OFF] (L) | RAYS: [ON|OFF] (G)`
  - Update help panel text to mention keys `T`, `L`, `G`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_app_state.py`
Expected: PASS

---

### Task 6: Headless Verification & Render Snapshot Pipeline

**Files:**
- Modify: `classroom.py:1074-1199` (`verify()`)
- Output: `previews/sunset_inside.png`, `previews/sunset_god_rays.png`, `previews/daylight_inside.png`, `previews/verification.json`

**Interfaces:**
- Consumes: `App.verify(folder)`
- Produces: Comprehensive capture verification suite ensuring both lighting modes render without OpenGL errors

- [ ] **Step 1: Update `verify()` method in `classroom.py`**

Add verification captures to `App.verify()`:
1. Capture `daylight_inside.png` with interior lights ON and god rays ON.
2. Toggle to sunset (`lighting_preset = "sunset"`), lights ON $\rightarrow$ capture `sunset_inside.png`.
3. Set sunset with interior lights OFF (`interior_lights = False`), camera angled toward window rays $\rightarrow$ capture `sunset_god_rays.png` showing dramatic golden light sweeping across desks.
4. Verify `glGetError() == GL_NO_ERROR` at every phase.
5. Record lighting status in `verification.json`.

- [ ] **Step 2: Run verification command**

Run: `python classroom.py --hidden --verify previews`
Expected: Exits with code 0, all snapshot files created in `previews/`, and `opengl_errors == 0`.

- [ ] **Step 3: Run py_compile check**

Run: `python -m py_compile classroom.py surface_materials.py`
Expected: Exit code 0

