# Agent Operating Guidelines: S13-30612 OpenGL Workspace

## 1. Operating Philosophy
Every AI agent working in this repository operates as a disciplined, senior graphics engineer paired with the user.

You MUST adhere to the **Superpowers** methodology:
- **Spec First**: Always clarify requirements and design before proposing or executing code changes (use `brainstorming`).
- **Plan First**: Structure multi-step work into clear, bite-sized tasks (use `writing-plans`).
- **Verify Always**: Run compilation and render verification before declaring any task complete (use `verification-before-completion`).
- **Traceability**: Respect the ground-truth measurements documented in `GEMINI.md`, `room_config.json`, and `data/sources.json`.

---

## 2. Antigravity Tool Mapping & Execution Rules
When executing skills from `.agents/skills/`:
- **Subagents**: Use `invoke_subagent` (`TypeName: "self"` for full tool access, `TypeName: "research"` for read-only exploration).
- **Task Tracking**: Antigravity uses task artifacts in the brain directory (`IsArtifact: true`, `ArtifactMetadata.ArtifactType: "task"`), updated via `replace_file_content` or `write_to_file`. **Do not use `manage_task` for task tracking** (`manage_task` is strictly for background OS processes).
- **File Edits**: Use `replace_file_content` for targeted contiguous edits and `write_to_file` for new files. Preserve existing comments and docstrings.
- **Commands**: Execute commands via `run_command` in PowerShell.

---

## 3. OpenGL Codebase Conventions
- **GLSL 3.3 Shader Pipeline (Option B)**: The project runs on a custom GLSL 3.3 Compatibility Profile shader pipeline (`realistic_renderer.py`) replacing legacy fixed-function lighting with per-pixel GGX/Lambert PBR, PCF sun shadows, HDR, ACES tonemapping, bloom, FXAA, SSAO, and volumetric atmosphere.
- **Pure Procedural Asset Rule**:
  - Never import external 3D models (`.obj`, `.gltf`, `.stl`, `.fbx`).
  - Never load external texture bitmaps (`.png`, `.jpg`).
  - Never load external `.glsl` files; all shader sources must remain embedded Python string constants in `realistic_renderer.py`.
  - Textures must be procedurally generated via Pillow in [surface_materials.py](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/surface_materials.py).
- **Trio Synchronization**:
  - [classroom.py](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/classroom.py), [surface_materials.py](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/surface_materials.py), and [realistic_renderer.py](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/realistic_renderer.py) must always remain compatible and side-by-side.
- **Validation Checklist**:
  Before finishing a change:
  1. `python -m py_compile classroom.py surface_materials.py realistic_renderer.py` (Must exit code 0).
  2. `python -m unittest discover -s tests -p "test_*.py"` (All unit tests must pass).
  3. `python classroom.py --hidden --verify previews` (All view renders must complete without OpenGL or shader errors).
  4. Inspect [previews/verification.json](file:///c:/Users/krittin%20pragopdee/Downloads/New%20folder%20%2823%29/S13-30612_OpenGL/previews/verification.json) to ensure `opengl_errors == 0`, `shader_errors == []`, and `fbo_complete == true`.

