# Specification: Dual-Config Lighting, Volumetric God Rays, and Interior Glow

## 1. Overview & Objectives
Enhance the S13-30612 classroom visualization with atmospheric lighting:
1. **Two External Lighting Presets**:
   - **Daylight**: Crisp, bright daylight streaming at a high angle from the window wall ($X = 11.79\text{ m}$) with subtle light shafts.
   - **Sunset (Golden Hour)**: Dramatic, low-angled golden-amber sunlight penetrating deep into the room, sweeping across desks toward the far wall, with dimmed interior ambient light.
2. **Volumetric God Rays**:
   - Distinct, visible light shafts beaming through window openings into the classroom interior.
   - Built with pure procedural OpenGL geometry and alpha/additive blending.
3. **Interior Lighting System**:
   - Toggleable fluorescent luminaires with emissive glow geometry.
   - Soft downward light pools projected on desks and floor directly beneath luminaires.
   - When interior lights are switched off during sunset, the room dims dramatically to showcase the golden rays.

---

## 2. Technical Constraints & Principles
- **OpenGL Pipeline**: Standard OpenGL 2.1+ fixed-function / compatibility profile (`PyOpenGL`). Zero external GLSL shader dependencies to maintain classroom compatibility.
- **Pure Procedural Assets**: Zero external textures or 3D models.
  - Backdrop textures synthesized procedurally via Pillow in `surface_materials.py` (new `_sunset()` texture added).
  - God ray frustums and light pool meshes generated procedurally in `classroom.py`.
- **Performance & Batching**: God rays and interior light pools compiled into optimized display lists with smooth real-time toggling.
- **Verification Integrity**: Must pass `python -m py_compile classroom.py surface_materials.py` and headless `--verify previews` with 0 OpenGL errors.

---

## 3. Detailed Technical Design

### 3.1. External Lighting Presets
The sun originates from the window wall ($X = 11.79\text{ m}$):
- **Daylight Mode**:
  - `GL_LIGHT0` Position: `(18.0, 6.0, 14.0, 1.0)`
  - `GL_LIGHT0` Diffuse: `(0.85, 0.88, 0.90, 1.0)` (cool bright white)
  - Ambient Model: `(0.42, 0.42, 0.42, 1.0)`
  - Backdrop: `textures["daylight"]`
  - Ray Color: Cool pale white `(0.85, 0.92, 0.98, 0.14)`
- **Sunset Mode**:
  - `GL_LIGHT0` Position: `(22.0, 4.0, 3.2, 1.0)` (low horizontal trajectory)
  - `GL_LIGHT0` Diffuse: `(1.0, 0.58, 0.20, 1.0)` (rich golden amber)
  - Ambient Model: `(0.18, 0.16, 0.16, 1.0)` (dimmed twilight)
  - Backdrop: `textures["sunset"]` (procedural golden/magenta horizon gradient)
  - Ray Color: Deep golden amber `(1.0, 0.65, 0.22, 0.28)`

### 3.2. Volumetric God Rays
- Window bays along $X = 11.79\text{ m}$ span $Y = 0.48\text{ m}$ to $L - 0.48\text{ m}$, between height $Z = 0.94\text{ m}$ (sill) and $2.82\text{ m}$ (top).
- For each bay, a 3D polygonal volumetric frustum is projected inwards into the classroom.
- Ray angles:
  - In Daylight: Extends inwards $\Delta X \approx -4.5\text{ m}$, dropping $\Delta Z \approx -1.8\text{ m}$.
  - In Sunset: Extends across the entire room $\Delta X \approx -9.5\text{ m}$, angling shallowly $\Delta Z \approx -1.2\text{ m}$, dramatically raking across the student desks.
- Blending & Normals:
  - Rendered with `glDepthMask(GL_FALSE)` and `glBlendFunc(GL_SRC_ALPHA, GL_ONE)` (additive) or `(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)`.
  - Vertex colors fade from opacity $\alpha = 0.35$ at window glazing to $\alpha = 0.0$ at beam terminus.

### 3.3. Interior Lighting & Downward Light Pools
- **Fluorescent Luminaires Glow**:
  - A subtle translucent glow quad/box surrounding each of the 13 fluorescent ceiling fixtures when active (`COLORS["light"]` with alpha $\approx 0.25$).
- **Downward Light Pools**:
  - Rendered onto the floor and desk tops directly below each luminaire ($X \in \{W \cdot 0.18, W \cdot 0.50, W \cdot 0.82\}$, $Y \in \{1.55, 4.1, 6.7, 9.3\}$).
  - Built as radial alpha-gradient fans (`GL_TRIANGLE_FAN`), bright at center ($\alpha \approx 0.22$), fading to $\alpha = 0.0$ at radius $R \approx 1.2\text{ m}$.
- **Switching State**:
  - Toggled independently via key `L`. When off, `GL_LIGHT1` and `GL_LIGHT2` (interior fill lights) are disabled, darkening the room and highlighting the window god rays.

### 3.4. User Interaction & Keybindings
| Key | Function |
|---|---|
| `T` | Toggle Time of Day Preset: **Daylight** $\leftrightarrow$ **Sunset** |
| `L` | Toggle Interior Fluorescent Lights: **ON** $\leftrightarrow$ **OFF** |
| `G` | Toggle Volumetric God Rays: **ON** $\leftrightarrow$ **OFF** |

- HUD updated to display: `PRESET: SUNSET [T] | LIGHTS: ON [L] | RAYS: ON [G]`.

