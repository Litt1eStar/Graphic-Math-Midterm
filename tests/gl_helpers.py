"""OpenGL test helpers for hidden context creation and headless rendering."""
import contextlib
import glfw
from OpenGL.GL import *


@contextlib.contextmanager
def hidden_context(width=320, height=240):
    """Context manager yielding with an active hidden OpenGL 3.3 context."""
    if not glfw.init():
        raise RuntimeError("GLFW initialization failed in hidden_context")
    glfw.default_window_hints()
    glfw.window_hint(glfw.VISIBLE, False)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_COMPAT_PROFILE)
    window = glfw.create_window(width, height, "test_context", None, None)
    if not window:
        # Fallback without explicit version hints
        glfw.default_window_hints()
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_COMPAT_PROFILE)
        glfw.window_hint(glfw.VISIBLE, False)
        window = glfw.create_window(width, height, "test_context", None, None)
    if not window:
        glfw.terminate()
        raise RuntimeError("Failed to create hidden GLFW window")
    glfw.make_context_current(window)
    try:
        yield window
    finally:
        glfw.destroy_window(window)
        glfw.terminate()


def render_inside(preset="daylight", interior_lights=True, sun=1.0, exposure=0.0, bloom=0.35, width=640, height=400, show_hud=False):
    """Renders the scene from preset 2 (inside) using a hidden App, returning a PIL Image."""
    import tempfile
    from pathlib import Path
    from PIL import Image
    from classroom import App, load_config

    cfg = load_config(Path("room_config.json"))
    app = App(cfg, width=width, height=height, hidden=True)
    try:
        app.lighting_preset = preset
        app.interior_lights = interior_lights
        app.show_hud = show_hud
        app.lighting_state.set_sun(sun)
        if hasattr(app.lighting_state, "set_exposure"):
            app.lighting_state.set_exposure(exposure)
        if hasattr(app.lighting_state, "set_bloom"):
            app.lighting_state.set_bloom(bloom)
        app.camera.preset(2)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            app.capture(tmp_path)
            im = Image.open(tmp_path).copy()
            return im
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
    finally:
        glfw.destroy_window(app.window)
        glfw.terminate()


@contextlib.contextmanager
def hidden_app(width=640, height=400):
    """Context manager yielding a running hidden App instance with cleanup."""
    from pathlib import Path
    from classroom import App, load_config
    cfg = load_config(Path("room_config.json"))
    app = App(cfg, width=width, height=height, hidden=True)
    try:
        yield app
    finally:
        glfw.destroy_window(app.window)
        glfw.terminate()


def render_view(view_name, preset="daylight", interior_lights=True, width=640, height=400, quality="high", god_rays_opacity=0.35):
    """Renders a named view corresponding to verify poses."""
    import tempfile
    from pathlib import Path
    from PIL import Image
    from classroom import App, load_config

    cfg = load_config(Path("room_config.json"))
    app = App(cfg, width=width, height=height, hidden=True)
    try:
        app.renderer.set_quality(quality)
        app.lighting_preset = preset
        app.interior_lights = interior_lights
        app.lighting_state.set_god_rays(god_rays_opacity)
        app.show_hud = False
        if view_name == "fluorescent_detail":
            app.camera.preset(2)
            app.camera.position = [4.3, 5.2, 1.70]
            app.camera.yaw, app.camera.pitch = -153, 34
        elif view_name == "sunset_god_rays":
            app.lighting_preset = "sunset"
            app.camera.preset(2)
            app.camera.position = [4.5, 7.5, 1.45]
            app.camera.yaw, app.camera.pitch = -35, -8
        elif view_name == "rear_wall":
            app.camera.preset(2)
            app.camera.position = [7.0, 8.0, 1.9]
            app.camera.yaw, app.camera.pitch = 106, 0
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            app.capture(tmp_path)
            im = Image.open(tmp_path).copy()
            return im
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
    finally:
        glfw.destroy_window(app.window)
        glfw.terminate()


def corner_luminance(image):
    """Measures luminance in wall/ceiling corner crease."""
    rgb = image.convert("RGB")
    w, h = rgb.size
    # Upper wall junction in rear_wall view
    box = (int(w * 0.15), int(h * 0.12), int(w * 0.28), int(h * 0.22))
    return mean_luminance(rgb.crop(box))


def mean_luminance(image):
    """Calculates mean relative luminance (0-255 scale) of an RGB/RGBA PIL Image."""
    rgb = image.convert("RGB")
    data = rgb.tobytes()
    total = 0.0
    count = len(data) // 3
    for i in range(0, len(data), 3):
        r, g, b = data[i], data[i+1], data[i+2]
        total += 0.2126 * r + 0.7152 * g + 0.0722 * b
    return total / max(1, count)


def lamp_halo_luminance(image):
    """Sample luminance in the lamp region (center area of fluorescent_detail)."""
    rgb = image.convert("RGB")
    w, h = rgb.size
    # Lamp fixture is roughly centered
    box = (int(w * 0.45), int(h * 0.45), int(w * 0.55), int(h * 0.55))
    crop = rgb.crop(box)
    return mean_luminance(crop)


def ceiling_luminance(image):
    """Sample luminance on the ceiling away from the lamp fixture."""
    rgb = image.convert("RGB")
    w, h = rgb.size
    box = (int(w * 0.05), int(h * 0.05), int(w * 0.20), int(h * 0.20))
    crop = rgb.crop(box)
    return mean_luminance(crop)


def patch_luminance(image, world_point=(0.0, 0.0, 0.0), patch_size=9):
    """Computes luminance around projected screen coordinate or fallback central pixel patch."""
    import math
    from realistic_renderer import mat_perspective, mat_look_at, mat_mul, transform_point

    rgb = image.convert("RGB")
    w, h = rgb.size

    # sunset_god_rays camera settings:
    # position = [4.5, 7.5, 1.45], yaw = -35, pitch = -8, fov = 52
    cam_pos = [4.5, 7.5, 1.45]
    yaw_rad = math.radians(-35)
    pitch_rad = math.radians(-8)
    cos_p = math.cos(pitch_rad)
    sin_p = math.sin(pitch_rad)
    cos_y = math.cos(yaw_rad)
    sin_y = math.sin(yaw_rad)
    forward = (cos_p * cos_y, cos_p * sin_y, sin_p)
    target = (cam_pos[0] + forward[0] * 5.0, cam_pos[1] + forward[1] * 5.0, cam_pos[2] + forward[2] * 5.0)

    proj = mat_perspective(52.0, w / float(h), 0.08, 180.0)
    view = mat_look_at(tuple(cam_pos), target, (0.0, 0.0, 1.0))
    vp = mat_mul(proj, view)

    ndc = transform_point(vp, world_point)
    # NDC (-1..1) to screen pixels (0..w, 0..h)
    sx = int((ndc[0] * 0.5 + 0.5) * w)
    sy = int((1.0 - (ndc[1] * 0.5 + 0.5)) * h)

    half = patch_size // 2
    x0 = max(0, min(w - patch_size, sx - half))
    y0 = max(0, min(h - patch_size, sy - half))
    crop = rgb.crop((x0, y0, x0 + patch_size, y0 + patch_size))
    return mean_luminance(crop)


