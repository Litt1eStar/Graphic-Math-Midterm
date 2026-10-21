# Design: Realistic Shader Renderer (Fixed-Function Replacement)

## 1. Intent

The user wants the S13-30612 classroom to look as realistic as possible: light, shadow, texture, and movement. The fixed-function pipeline has a hard ceiling (lighting computed per vertex, no shadows, no HDR), so the user chose **Option B: replace the fixed-function renderer completely with a GLSL shader renderer**. No fixed-function fallback is kept.

Success means: in the FPV walk (preset 2) the room reads as a photographed space. The sun casts real shadows from desks, chairs and columns that change between Daylight and Sunset. Fluorescent lamps glow and bloom. Surfaces show bump detail and glossy highlights. Corners darken naturally. Walking feels physical. The demo stays smooth on the target laptop (Intel UHD Graphics, OpenGL 4.6).

## 2. Goals

1. Per-pixel physically based lighting: sun (directional) + 13 fluorescent fixtures (point lights at `Classroom.luminaire_positions`) + sky/ground hemisphere ambient.
2. HDR rendering, ACES tone mapping, exposure control, bloom, FXAA.
3. Sun shadow mapping with PCF soft edges, following the active preset's sun direction.
4. Material system: roughness, specular strength, and bump strength per surface; procedural bump detail; glossy floor/desk highlights.
5. Screen-space ambient occlusion (SSAO).
6. Atmosphere: shader-driven god rays with noise falloff and drifting dust particles in the beams.
7. Movement feel in FPV: acceleration/deceleration, head-bob, smoothed mouse look.
8. Quality setting Low/High so the demo stays smooth.
9. Existing features keep working: camera presets 1-4, FPV walk + collision, Tab cursor mode, tour, door animation, cutaway/ceiling toggles, T/L/G toggles, lighting sliders, F12 capture, `--verify`.

## 3. Non-Goals

- No fixed-function fallback renderer or "classic" comparison mode (user decision).
- No shadows from the fluorescent lamps (sun shadows only; lamps contribute via SSAO and falloff).
- No real-time global illumination or ray tracing.
- No macOS support (macOS lacks compatibility profiles; Windows is the delivery target).
- No changes to room geometry, dimensions, or furniture layout from `GEMINI.md` / `room_config.json`.

## 4. Anti-Goals (would be a failure even if it "works")

- Any external asset file: no `.obj/.gltf/.fbx`, no `.png/.jpg` textures, no separate `.glsl` files. Shaders are Python string constants.
- A demo that stutters below ~30 fps on Intel UHD at 1440x900 in High, or below ~60 fps in Low.
- Losing the measured-ground-truth geometry or breaking `--verify`.
- Overblown "game" look: crushed blacks, extreme bloom, oversaturated sunset. Default values must look like a real classroom photo.

## 5. Constraints

- Python 3.10+, PyOpenGL 3.1.10, glfw 2.10.2, Pillow >= 10. **No new dependencies** (no numpy). Matrix math in pure Python.
- OpenGL **3.3 compatibility profile** (`CONTEXT_VERSION 3.3`, default/any profile on Windows). Display lists, `glColor`, `glNormal`, `glTexCoord`, `glSecondaryColor` remain legal and are read by shaders through `gl_Vertex`, `gl_Normal`, `gl_Color`, `gl_SecondaryColor`, `gl_MultiTexCoord0`, `gl_ModelViewMatrix`.
- GLSL `#version 330 compatibility`.
- All textures procedural via Pillow in `surface_materials.py`.
- `classroom.py` and `surface_materials.py` stay compatible; the new renderer module ships alongside them.
- Verification: `python -m py_compile` on all modules, `python -m unittest discover tests`, `python classroom.py --hidden --verify previews` with `opengl_errors == 0` and zero shader compile/link errors.

## 6. Decisions Made With the User

| Decision | User's answer |
|---|---|
| Fixed-function vs shaders | Shaders (Option B) |
| Keep a fixed-function fallback / comparison toggle | No — replace completely |
| Plan first, trackable | Yes — written plan + task tracker |

## 7. Design

### 7.1 Module layout (builder's call, recorded)

- **New `realistic_renderer.py`**: GLSL sources as string constants, program compile/link helpers with error logs, `RenderTarget` (FBO wrapper), matrix helpers, the pass pipeline (`Renderer`), dust particle system. Keeps `classroom.py` (already ~1730 lines) from doubling.
- **`classroom.py`**: geometry, camera, HUD layout, input, app loop. Calls `Renderer`. All `glLight*`, `glMaterial*`, `GL_LIGHTING`, `GL_COLOR_MATERIAL` use is removed.
- **`surface_materials.py`**: upgraded procedural textures.
- The rule "must always accompany" now covers three files; `AGENTS.md`, `GEMINI.md`, `README_TH.md` updated accordingly, and the shader prohibition is replaced with "GLSL allowed only as embedded strings".

### 7.2 Keeping the existing geometry

Display lists stay. Two small changes make them shader-friendly:
- **Material tag via secondary colour.** Every compiled part emits `glSecondaryColor3f(roughness, specular, bump)` from a `MATERIALS` table keyed by the `COLORS` material name. Every `COLORS` key must have an entry.
- **Always-bound texture.** A 1x1 white texture is bound for untextured parts so the shader always samples unit 0; `draw_box` binds white when `texture == 0` (except the daylight backdrop, which is bound at draw time as today).

### 7.3 Frame pipeline

```
1. Shadow pass      depth-only, sun orthographic view → shadow map (2048² High / 1024² Low)
2. Scene pass       HDR RGBA16F colour + depth texture; opaque lists with PBR shader
                    then emissive (lamps, backdrop, luminaire glow) and
                    transparent (glass, god rays, dust) with depth-write off
3. SSAO pass        (High only) half-resolution AO from depth, bilateral blur
4. Bloom            bright-pass + 5-level downsample/upsample blur chain
5. Composite        AO multiply, bloom add, exposure, ACES tone map, sRGB gamma,
                    vignette (subtle) → LDR target
6. FXAA             → default framebuffer
7. HUD              textured-quad UI shader, unchanged layout
```
MSAA on the default framebuffer is no longer used (FXAA replaces it). Window resize reallocates all targets.

### 7.4 Lighting model

- Cook-Torrance GGX specular + Lambert diffuse, linear-space albedo (sRGB textures and vertex colours converted to linear).
- **Sun:** direction = normalize(preset light position − room centre). Daylight position `(1.5·W, 6.0, 14.0)`, colour `(0.85, 0.88, 0.90)`; Sunset position `(22.0, 4.0, 3.2)`, colour `(1.0, 0.58, 0.20)`. Base HDR intensity 3.0 (Daylight) / 4.0 (Sunset) × `sun_intensity` slider. Sun light only reaches the interior through the window wall; the shadow map handles occlusion by walls/columns.
- **Fluorescents:** 13 point lights at `luminaire_positions`, colour `(0.92, 0.97, 1.0)`, intensity 1.6 × `interior_intensity`, inverse-square falloff with smooth window to 0 at 7 m. Off when `interior_lights` is false. Lamp tubes render emissive (strength follows the same factor) so they bloom.
- **Ambient:** hemisphere sky/ground colours per preset × `ambient_brightness / 0.40`, multiplied by SSAO.
- These are starting values; the builder tunes them against the previews, keeping the anti-goal "looks like a real photo".

### 7.5 Shadows

- Orthographic light frustum fitted to the room + vestibule bounds `(0..W, 0..L+V, 0..H)` from the sun direction.
- Slope-scaled depth bias, front-face culling in the shadow pass.
- PCF: 16-tap Poisson; kernel radius from the `shadow_softness` slider.

### 7.6 Materials and textures

- `MATERIALS` table, e.g. floor terrazzo roughness 0.35 / specular 0.6 / bump 0.4; wood desk 0.45 / 0.5 / 0.3; chrome 0.15 / 1.0 / 0; walls 0.85 / 0.2 / 0.25; glass 0.05 / 1.0 / 0. Builder fills the rest.
- **Bump without tangents:** derivative-based bump mapping (screen-space `dFdx/dFdy` of a height value from albedo luminance), so no tangent attributes are needed.
- `surface_materials.py`: floor and wood up to 1024², plus new `"plaster"` wall texture (subtle noise, faint scuffs near the floor) and wear variation on the floor. Deterministic seeds; same function signature `make_surface_images()`.
- Glossy floor: GGX specular from sun + lamps, plus a blurred sky colour reflection term near grazing angles (Fresnel).

### 7.7 Atmosphere

- God rays keep their procedural frustum geometry, drawn with a volumetric shader: additive, noise-modulated, faded by depth and camera distance, alpha × `god_rays_opacity / 0.35`.
- Dust: ~400 (High) / 150 (Low) point sprites drifting slowly inside the god ray volumes, brighter where lit by the sun.
- Fake effects replaced: the old interior light-pool decals are removed (real point lights replace them). Contact-shadow decals are kept only in Low quality (where SSAO is off).

### 7.8 Movement feel (FPV only)

- Velocity with acceleration 12 m/s² and friction-style deceleration; walk 3.0 m/s, sprint 5.5 m/s (unchanged maxima).
- Head-bob: vertical amplitude 0.035 m, lateral 0.02 m, frequency tied to distance walked; fades out when stopping. Eye base stays 1.70 m; collision uses the un-bobbed position.
- Mouse smoothing: exponential, time constant ~30 ms.
- Tour and orbit presets are unaffected.

### 7.9 Controls

- Lighting panel grows to 7 sliders: Sunlight, Interior, God Rays, Ambient, **Exposure** (−2..+2 EV, default 0), **Bloom** (0..1, default 0.35), **Shadow Softness** (0..1, default 0.4).
- **F3** toggles quality Low/High (default High). Shown on the HUD.
- All other keys unchanged.

### 7.10 Verification

- Shader compile/link logs captured; any failure raises with the log and fails `--verify`.
- Every FBO checked with `glCheckFramebufferStatus`.
- New previews: `realistic_daylight.png`, `realistic_sunset_shadows.png`, `realistic_lamps_night.png` (sun 0, interior on), `realistic_low_quality.png`.
- Image assertions in `--verify`: shadowed floor patch under a desk is darker than an open sunlit patch in Sunset; a lamp pixel is brighter than the ceiling next to it.
- Frame-time sample (average of 60 frames) for Low and High recorded in `verification.json` as `frame_ms_low` / `frame_ms_high`. Recorded, not a hard failure (headless timing is noisy).

## 8. Left to the Builder

Exact light/ambient tuning, PCF kernel, SSAO sample count and radius, bloom thresholds, dust motion, texture detail, MATERIALS values beyond the examples, shader code structure.

