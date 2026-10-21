"""Realistic GLSL Shader Renderer for S13-30612 OpenGL Classroom.

Provides:
- Column-major 4x4 matrix helpers (pure Python, list[float] length 16)
- ShaderError & compile_program with detailed info log retrieval
- RenderTarget for color / depth FBOs with resize and zero-size safety
- FrameState dataclass
- sun_direction helper
- Renderer pipeline (PBR scene shader, emissive, transparent, HUD UI quad)
"""
import math
import random
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Any
from OpenGL.GL import *


# ---------------------------------------------------------------------------
# Shader compilation & errors
# ---------------------------------------------------------------------------

class ShaderError(RuntimeError):
    """Raised when GLSL shader compilation or program linking fails."""
    pass


def aces_tonemap(x: float) -> float:
    """Narkowicz ACES tonemapping curve fit mirror in Python: (x*(2.51*x + 0.03)) / (x*(2.43*x + 0.59) + 0.14)."""
    if x <= 0.0:
        return 0.0
    val = (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14)
    return max(0.0, min(1.0, val))


def compile_shader(source: str, shader_type: int, stage_name: str, program_name: str) -> int:
    shader = glCreateShader(shader_type)
    glShaderSource(shader, source)
    glCompileShader(shader)
    status = glGetShaderiv(shader, GL_COMPILE_STATUS)
    if not status:
        log = glGetShaderInfoLog(shader)
        if isinstance(log, bytes):
            log = log.decode("utf-8", errors="replace")
        glDeleteShader(shader)
        raise ShaderError(f"[{program_name}] {stage_name} shader compile error:\n{log}")
    return shader


def compile_program(vertex_src: str, fragment_src: str, name: str) -> int:
    """Compiles vertex and fragment shaders and links them into a program."""
    vs = compile_shader(vertex_src, GL_VERTEX_SHADER, "Vertex", name)
    fs = compile_shader(fragment_src, GL_FRAGMENT_SHADER, "Fragment", name)
    prog = glCreateProgram()
    glAttachShader(prog, vs)
    glAttachShader(prog, fs)
    glLinkProgram(prog)
    status = glGetProgramiv(prog, GL_LINK_STATUS)
    glDeleteShader(vs)
    glDeleteShader(fs)
    if not status:
        log = glGetProgramInfoLog(prog)
        if isinstance(log, bytes):
            log = log.decode("utf-8", errors="replace")
        glDeleteProgram(prog)
        raise ShaderError(f"[{name}] Program link error:\n{log}")
    return prog


# ---------------------------------------------------------------------------
# Pure-Python Column-Major 4x4 Matrix Mathematics
# ---------------------------------------------------------------------------

def mat_identity() -> List[float]:
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def mat_mul(a: List[float], b: List[float]) -> List[float]:
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            val = 0.0
            for k in range(4):
                val += a[k * 4 + row] * b[col * 4 + k]
            out[col * 4 + row] = val
    return out


def mat_perspective(fov_deg: float, aspect: float, near: float, far: float) -> List[float]:
    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    nf = 1.0 / (near - far)
    return [
        f / aspect, 0.0, 0.0, 0.0,
        0.0, f, 0.0, 0.0,
        0.0, 0.0, (far + near) * nf, -1.0,
        0.0, 0.0, (2.0 * far * near) * nf, 0.0,
    ]


def mat_ortho(left: float, right: float, bottom: float, top: float, near: float, far: float) -> List[float]:
    rl = 1.0 / (right - left)
    tb = 1.0 / (top - bottom)
    fn = 1.0 / (far - near)
    return [
        2.0 * rl, 0.0, 0.0, 0.0,
        0.0, 2.0 * tb, 0.0, 0.0,
        0.0, 0.0, -2.0 * fn, 0.0,
        -(right + left) * rl, -(top + bottom) * tb, -(far + near) * fn, 1.0,
    ]


def mat_look_at(eye: Tuple[float, float, float], target: Tuple[float, float, float], up: Tuple[float, float, float]) -> List[float]:
    fx = eye[0] - target[0]
    fy = eye[1] - target[1]
    fz = eye[2] - target[2]
    len_f = math.sqrt(fx * fx + fy * fy + fz * fz) or 1.0
    fx /= len_f
    fy /= len_f
    fz /= len_f

    rx = up[1] * fz - up[2] * fy
    ry = up[2] * fx - up[0] * fz
    rz = up[0] * fy - up[1] * fx
    len_r = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
    rx /= len_r
    ry /= len_r
    rz /= len_r

    ux = fy * rz - fz * ry
    uy = fz * rx - fx * rz
    uz = fx * ry - fy * rx

    dot_r = -(rx * eye[0] + ry * eye[1] + rz * eye[2])
    dot_u = -(ux * eye[0] + uy * eye[1] + uz * eye[2])
    dot_f = -(fx * eye[0] + fy * eye[1] + fz * eye[2])

    return [
        rx, ux, fx, 0.0,
        ry, uy, fy, 0.0,
        rz, uz, fz, 0.0,
        dot_r, dot_u, dot_f, 1.0,
    ]


def mat_inverse(m: List[float]) -> List[float]:
    inv = [0.0] * 16

    inv[0] = (
        m[5] * m[10] * m[15] - m[5] * m[11] * m[14] - m[9] * m[6] * m[15] +
        m[9] * m[7] * m[14] + m[13] * m[6] * m[11] - m[13] * m[7] * m[10]
    )
    inv[4] = (
        -m[4] * m[10] * m[15] + m[4] * m[11] * m[14] + m[8] * m[6] * m[15] -
        m[8] * m[7] * m[14] - m[12] * m[6] * m[11] + m[12] * m[7] * m[10]
    )
    inv[8] = (
        m[4] * m[9] * m[15] - m[4] * m[11] * m[13] - m[8] * m[5] * m[15] +
        m[8] * m[7] * m[13] + m[12] * m[5] * m[11] - m[12] * m[7] * m[9]
    )
    inv[12] = (
        -m[4] * m[9] * m[14] + m[4] * m[10] * m[13] + m[8] * m[5] * m[14] -
        m[8] * m[6] * m[13] - m[12] * m[5] * m[10] + m[12] * m[6] * m[9]
    )

    inv[1] = (
        -m[1] * m[10] * m[15] + m[1] * m[11] * m[14] + m[9] * m[2] * m[15] -
        m[9] * m[3] * m[14] - m[13] * m[2] * m[11] + m[13] * m[3] * m[10]
    )
    inv[5] = (
        m[0] * m[10] * m[15] - m[0] * m[11] * m[14] - m[8] * m[2] * m[15] +
        m[8] * m[3] * m[14] + m[12] * m[2] * m[11] - m[12] * m[3] * m[10]
    )
    inv[9] = (
        -m[0] * m[9] * m[15] + m[0] * m[11] * m[13] + m[8] * m[1] * m[15] -
        m[8] * m[3] * m[13] - m[12] * m[1] * m[11] + m[12] * m[3] * m[9]
    )
    inv[13] = (
        m[0] * m[9] * m[14] - m[0] * m[10] * m[13] - m[8] * m[1] * m[14] +
        m[8] * m[2] * m[13] + m[12] * m[1] * m[10] - m[12] * m[2] * m[9]
    )

    inv[2] = (
        m[1] * m[6] * m[15] - m[1] * m[7] * m[14] - m[5] * m[2] * m[15] +
        m[5] * m[3] * m[14] + m[13] * m[2] * m[7] - m[13] * m[3] * m[6]
    )
    inv[6] = (
        -m[0] * m[6] * m[15] + m[0] * m[7] * m[14] + m[4] * m[2] * m[15] -
        m[4] * m[3] * m[14] - m[12] * m[2] * m[7] + m[12] * m[3] * m[6]
    )
    inv[10] = (
        m[0] * m[5] * m[15] - m[0] * m[7] * m[13] - m[4] * m[1] * m[15] +
        m[4] * m[3] * m[13] + m[12] * m[1] * m[7] - m[12] * m[3] * m[5]
    )
    inv[14] = (
        -m[0] * m[5] * m[14] + m[0] * m[6] * m[13] + m[4] * m[1] * m[14] -
        m[4] * m[2] * m[13] - m[12] * m[1] * m[6] + m[12] * m[2] * m[5]
    )

    inv[3] = (
        -m[1] * m[6] * m[11] + m[1] * m[7] * m[10] + m[5] * m[2] * m[11] -
        m[5] * m[3] * m[10] - m[9] * m[2] * m[7] + m[9] * m[3] * m[6]
    )
    inv[7] = (
        m[0] * m[6] * m[11] - m[0] * m[7] * m[10] - m[4] * m[2] * m[11] +
        m[4] * m[3] * m[10] + m[8] * m[2] * m[7] - m[8] * m[3] * m[6]
    )
    inv[11] = (
        -m[0] * m[5] * m[11] + m[0] * m[7] * m[9] + m[4] * m[1] * m[11] -
        m[4] * m[3] * m[9] - m[8] * m[1] * m[7] + m[8] * m[3] * m[5]
    )
    inv[15] = (
        m[0] * m[5] * m[10] - m[0] * m[6] * m[9] - m[4] * m[1] * m[10] +
        m[4] * m[2] * m[9] + m[8] * m[1] * m[6] - m[8] * m[2] * m[5]
    )

    det = m[0] * inv[0] + m[1] * inv[4] + m[2] * inv[8] + m[3] * inv[12]
    if abs(det) < 1e-12:
        return mat_identity()

    inv_det = 1.0 / det
    return [x * inv_det for x in inv]


def transform_point(m: List[float], pt: Tuple[float, float, float]) -> Tuple[float, float, float]:
    x, y, z = pt
    rx = m[0] * x + m[4] * y + m[8] * z + m[12]
    ry = m[1] * x + m[5] * y + m[9] * z + m[13]
    rz = m[2] * x + m[6] * y + m[10] * z + m[14]
    rw = m[3] * x + m[7] * y + m[11] * z + m[15]
    if abs(rw) > 1e-12:
        inv_w = 1.0 / rw
        return (rx * inv_w, ry * inv_w, rz * inv_w)
    return (rx, ry, rz)


# ---------------------------------------------------------------------------
# Helper: sun direction vector
# ---------------------------------------------------------------------------

def sun_direction(preset: str, room: Dict[str, Any]) -> Tuple[float, float, float]:
    """Computes unit vector from room center toward the preset light position."""
    cx = room["width"] * 0.5
    cy = room["depth"] * 0.5
    cz = room["height"] * 0.5

    if preset == "sunset":
        lx, ly, lz = 22.0, 4.0, 3.2
    else:  # daylight
        lx, ly, lz = room["width"] * 1.5, 6.0, 14.0

    dx = lx - cx
    dy = ly - cy
    dz = lz - cz
    length = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    return (dx / length, dy / length, dz / length)


def sun_light_matrices(sun_dir: Tuple[float, float, float], bounds: Tuple[float, float, float, float, float, float]) -> Tuple[List[float], List[float]]:
    """Computes orthographic light view and projection matrices tightly fitting the bounding box.
    bounds: (min_x, max_x, min_y, max_y, min_z, max_z)
    Returns: (view_matrix, projection_matrix)
    """
    min_x, max_x, min_y, max_y, min_z, max_z = bounds
    cx = (min_x + max_x) * 0.5
    cy = (min_y + max_y) * 0.5
    cz = (min_z + max_z) * 0.5

    # Light direction points from sun toward the room center
    sdx, sdy, sdz = sun_dir
    len_s = math.sqrt(sdx * sdx + sdy * sdy + sdz * sdz) or 1.0
    sdx /= len_s
    sdy /= len_s
    sdz /= len_s

    # Choose up vector that is not parallel to light direction
    up = (0.0, 0.0, 1.0) if abs(sdz) < 0.95 else (0.0, 1.0, 0.0)

    # Temporary view matrix with eye at room center looking along -sun_dir
    # eye is cx + sdx * dist, looking at (cx, cy, cz)
    # Notice: fx in mat_look_at points from target to eye (eye - target)
    eye = (cx + sdx * 50.0, cy + sdy * 50.0, cz + sdz * 50.0)
    target = (cx, cy, cz)
    view = mat_look_at(eye, target, up)

    # Transform all 8 bounding box corners into light view space
    corners = [
        (min_x, min_y, min_z), (max_x, min_y, min_z),
        (min_x, max_y, min_z), (max_x, max_y, min_z),
        (min_x, min_y, max_z), (max_x, min_y, max_z),
        (min_x, max_y, max_z), (max_x, max_y, max_z),
    ]

    min_vx = float("inf")
    max_vx = float("-inf")
    min_vy = float("inf")
    max_vy = float("-inf")
    min_vz = float("inf")
    max_vz = float("-inf")

    for pt in corners:
        vx, vy, vz = transform_point(view, pt)
        if vx < min_vx: min_vx = vx
        if vx > max_vx: max_vx = vx
        if vy < min_vy: min_vy = vy
        if vy > max_vy: max_vy = vy
        if vz < min_vz: min_vz = vz
        if vz > max_vz: max_vz = vz

    # In OpenGL view space, forward is -Z, so near/far in ortho projection:
    # mat_ortho maps [left, right], [bottom, top], and maps near/far:
    # note: if vz is negative, near is -max_vz, far is -min_vz
    # Add a slight padding to avoid clipping exactly on the boundary
    pad_xy = 0.5
    pad_z = 2.0
    left = min_vx - pad_xy
    right = max_vx + pad_xy
    bottom = min_vy - pad_xy
    top = max_vy + pad_xy
    near = -max_vz - pad_z
    far = -min_vz + pad_z

    proj = mat_ortho(left, right, bottom, top, near, far)
    return (view, proj)


# ---------------------------------------------------------------------------
# Framebuffer Render Target
# ---------------------------------------------------------------------------

# Internal 3D render resolution relative to the window, per quality mode.
RENDER_SCALE = {"high": 1.0, "low": 0.67}


class RenderTarget:
    """Manages an OpenGL Framebuffer Object (FBO) with color and optional depth attachments."""
    def __init__(self, width: int, height: int, color_formats: Optional[List[int]] = None, depth_texture: bool = False, shadow_compare: bool = False):
        self.width = max(1, width)
        self.height = max(1, height)
        self.color_formats = list(color_formats) if color_formats else []
        self.has_depth = depth_texture
        self.shadow_compare = shadow_compare
        self.fbo = 0
        self.color_textures: List[int] = []
        self.depth_texture: Optional[int] = None
        self._allocate()

    def _allocate(self):
        self.fbo = glGenFramebuffers(1)
        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)

        self.color_textures = []
        draw_buffers = []
        for i, fmt in enumerate(self.color_formats):
            tex = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex)
            base_format = GL_RGBA
            data_type = GL_FLOAT if fmt in (GL_RGBA16F, GL_RGBA32F, GL_RGB16F) else GL_UNSIGNED_BYTE
            glTexImage2D(GL_TEXTURE_2D, 0, fmt, self.width, self.height, 0, base_format, data_type, None)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0 + i, GL_TEXTURE_2D, tex, 0)
            self.color_textures.append(tex)
            draw_buffers.append(GL_COLOR_ATTACHMENT0 + i)

        if draw_buffers:
            glDrawBuffers(len(draw_buffers), draw_buffers)
        else:
            glDrawBuffer(GL_NONE)
            glReadBuffer(GL_NONE)

        if self.has_depth:
            self.depth_texture = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.depth_texture)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT24, self.width, self.height, 0, GL_DEPTH_COMPONENT, GL_FLOAT, None)
            if self.shadow_compare:
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_MODE, GL_COMPARE_REF_TO_TEXTURE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_FUNC, GL_LEQUAL)
            else:
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, self.depth_texture, 0)

        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glBindTexture(GL_TEXTURE_2D, 0)
        if status != GL_FRAMEBUFFER_COMPLETE:
            self.delete()
            raise RuntimeError(f"Framebuffer incomplete: status 0x{status:04X}")

    def bind(self):
        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
        glViewport(0, 0, self.width, self.height)

    def resize(self, width: int, height: int):
        if width <= 0 or height <= 0:
            return
        if width == self.width and height == self.height:
            return
        self.delete()
        self.width = width
        self.height = height
        self._allocate()

    def delete(self):
        if self.color_textures:
            glDeleteTextures(len(self.color_textures), self.color_textures)
            self.color_textures = []
        if self.depth_texture is not None:
            glDeleteTextures(1, [self.depth_texture])
            self.depth_texture = None
        if self.fbo:
            glDeleteFramebuffers(1, [self.fbo])
            self.fbo = 0


# ---------------------------------------------------------------------------
# GLSL Shaders
# ---------------------------------------------------------------------------

SCENE_VS = """#version 330 compatibility
invariant gl_Position;
out vec3 v_world_pos;
out vec3 v_normal;
out vec4 v_color;
out vec3 v_mat;
out vec2 v_uv;
out vec4 v_light_space_pos;

uniform mat4 u_light_space_matrix;

void main() {
    v_world_pos = gl_Vertex.xyz;
    v_normal = normalize(gl_Normal);
    v_color = gl_Color;
    v_mat = gl_SecondaryColor.rgb;
    v_uv = gl_MultiTexCoord0.xy;
    v_light_space_pos = u_light_space_matrix * vec4(gl_Vertex.xyz, 1.0);
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
"""

SCENE_FS = """#version 330 compatibility
in vec3 v_world_pos;
in vec3 v_normal;
in vec4 v_color;
in vec3 v_mat;
in vec2 v_uv;
in vec4 v_light_space_pos;

uniform sampler2D u_texture;
uniform sampler2DShadow u_shadow_map;
uniform vec3 u_eye;
uniform vec3 u_sun_dir;
uniform vec3 u_sun_color;
uniform float u_sun_intensity;
uniform vec3 u_hemi_sky;
uniform vec3 u_hemi_ground;
uniform float u_ambient_scale;
uniform vec3 u_lamp_pos[13];
uniform vec3 u_lamp_color;
uniform float u_lamp_intensity;
uniform float u_emissive_factor;
uniform float u_shadow_softness;
uniform float u_shadow_map_size;
uniform int u_is_skybox;
uniform float u_time;

out vec4 fragColor;

const float PI = 3.14159265359;

// 16-tap Poisson disk distribution
const vec2 poisson_disk[16] = vec2[](
    vec2(-0.94201624, -0.39906216),
    vec2( 0.94558609, -0.76890725),
    vec2(-0.09418410, -0.92938870),
    vec2( 0.34495938,  0.29387760),
    vec2(-0.91588581,  0.45771432),
    vec2(-0.81544232, -0.87912464),
    vec2(-0.38277543,  0.27676845),
    vec2( 0.97484398,  0.75648379),
    vec2( 0.44323325, -0.97511554),
    vec2( 0.53742981, -0.47373420),
    vec2(-0.26496911, -0.41893023),
    vec2( 0.79197514,  0.19090188),
    vec2(-0.24188840,  0.99706507),
    vec2(-0.81409955,  0.91437590),
    vec2( 0.19984126,  0.78641367),
    vec2( 0.14383161, -0.14100790)
);

float sky_hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float sky_noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = sky_hash(i);
    float b = sky_hash(i + vec2(1.0, 0.0));
    float c = sky_hash(i + vec2(0.0, 1.0));
    float d = sky_hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float sky_fbm(vec2 p) {
    float v = 0.0;
    float amp = 0.5;
    mat2 rot = mat2(0.80, -0.60, 0.60, 0.80);
    for (int i = 0; i < 5; ++i) {
        v += amp * sky_noise(p);
        p = rot * p * 2.03 + vec2(17.1, 31.7);
        amp *= 0.5;
    }
    return v;
}

vec3 eval_procedural_sky(vec3 dir, float is_sunset) {
    vec3 sun_d = normalize(u_sun_dir);
    // 6th-floor optical horizon sits slightly below horizontal (dir.z = -0.14)
    float h = clamp((dir.z + 0.14) / 0.44, 0.0, 1.0);

    // Nostalgic warm daylight vs golden-hour sunset atmospheric Rayleigh gradient
    vec3 day_zenith  = vec3(0.08, 0.26, 0.68);
    vec3 day_mid     = vec3(0.24, 0.50, 0.86);
    vec3 day_horizon = vec3(0.84, 0.78, 0.66);

    vec3 sun_zenith  = vec3(0.06, 0.09, 0.26);
    vec3 sun_mid     = vec3(0.54, 0.23, 0.31);
    vec3 sun_horizon = vec3(0.92, 0.42, 0.15);

    vec3 zenith  = mix(day_zenith,  sun_zenith,  is_sunset);
    vec3 mid_sky = mix(day_mid,     sun_mid,     is_sunset);
    vec3 horizon = mix(day_horizon, sun_horizon, is_sunset);

    vec3 sky_col = mix(horizon, mid_sky, smoothstep(0.0, 0.32, h));
    sky_col = mix(sky_col, zenith, smoothstep(0.28, 0.92, h));

    // Mie forward-scattering solar glow & crisp sun corona
    float mu = max(dot(dir, sun_d), 0.0);
    vec3 mie_tint = mix(vec3(1.05, 0.90, 0.68), vec3(1.15, 0.50, 0.18), is_sunset);
    sky_col += mie_tint * (pow(mu, 6.0) * 0.24 + pow(mu, 28.0) * 0.38 + pow(mu, 180.0) * 1.10);

    // Cylindrical-dome projected 3D cumulus & cirrus clouds visible directly at window eye level
    if (dir.z > -0.13) {
        float az = atan(dir.y, dir.x);
        vec2 wind = vec2(u_time * 0.010, u_time * 0.004);
        vec2 uv_cumulus = vec2(az * 2.5, (dir.z + 0.12) * 5.2) / (1.0 + max(dir.z, 0.0) * 1.3) + wind;
        float n1 = sky_fbm(uv_cumulus);
        float n2 = sky_fbm(uv_cumulus * 2.15 - wind * 0.6);
        float cloud_val = n1 * 0.72 + n2 * 0.28;
        float density = smoothstep(0.46, 0.74, cloud_val);
        float horizon_fade = smoothstep(-0.13, -0.01, dir.z) * (1.0 - smoothstep(0.70, 0.96, dir.z) * 0.4);
        density *= horizon_fade;

        if (density > 0.001) {
            // Vertical & solar gradient for sculpted 3D cumulus tops and self-shadowed bases
            float n_top = sky_fbm(uv_cumulus + vec2(0.0, 0.16));
            float rim = clamp((n1 - n_top) * 2.9 + 0.58, 0.0, 1.0);
            float silver_lining = pow(mu, 7.0) * (1.0 - density * 0.5);

            vec3 cloud_lit = mix(vec3(0.98, 0.95, 0.88), vec3(1.10, 0.62, 0.28), is_sunset);
            vec3 cloud_shd = mix(vec3(0.36, 0.46, 0.64), vec3(0.24, 0.15, 0.26), is_sunset);
            vec3 cloud_col = mix(cloud_shd, cloud_lit, rim) + mie_tint * silver_lining * 0.40;
            sky_col = mix(sky_col, cloud_col, density * 0.88);
        }

        // High wispy nostalgic cirrus streaks
        vec2 uv_cirrus = vec2(az * 3.8, (dir.z + 0.08) * 3.2) - wind * 0.4;
        float cirrus = smoothstep(0.58, 0.80, sky_fbm(uv_cirrus)) * smoothstep(0.0, 0.25, dir.z) * 0.32;
        vec3 cirrus_col = mix(vec3(0.96, 0.92, 0.86), vec3(1.08, 0.54, 0.28), is_sunset);
        sky_col = mix(sky_col, cirrus_col, cirrus);
    }

    // Smooth atmospheric ground & distant parkland perspective below 6th-floor horizon
    float g_t = smoothstep(-0.12, -0.32, dir.z);
    vec3 dist_park = mix(vec3(0.22, 0.32, 0.24), vec3(0.14, 0.11, 0.14), is_sunset);
    vec3 hazed_ground = mix(horizon * 0.88, dist_park, smoothstep(-0.14, -0.30, dir.z));
    sky_col = mix(sky_col, hazed_ground, g_t);

    return sky_col;
}

float calculate_shadow(vec4 light_space_pos, vec3 normal, vec3 sun_dir) {
    // Perspective divide
    vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
    // Transform [-1, 1] to [0, 1]
    proj_coords = proj_coords * 0.5 + 0.5;

    // Check if outside shadow map frustum
    if (proj_coords.x < 0.0 || proj_coords.x > 1.0 ||
        proj_coords.y < 0.0 || proj_coords.y > 1.0 ||
        proj_coords.z < 0.0 || proj_coords.z > 1.0) {
        return 1.0;
    }

    // Slope-scaled depth bias to prevent shadow acne
    float cos_theta = clamp(dot(normal, sun_dir), 0.0, 1.0);
    float bias = max(0.003 * (1.0 - cos_theta), 0.0008);
    float current_depth = proj_coords.z - bias;

    // Radius in texture uv space from shadow_softness
    float filter_radius = (1.5 + u_shadow_softness * 4.5) / u_shadow_map_size;

    float shadow = 0.0;
    for (int i = 0; i < 16; ++i) {
        vec2 offset = poisson_disk[i] * filter_radius;
        shadow += texture(u_shadow_map, vec3(proj_coords.xy + offset, current_depth));
    }
    return shadow / 16.0;
}

vec3 srgb_to_linear(vec3 c) {
    return pow(c, vec3(2.2));
}

vec3 linear_to_srgb(vec3 c) {
    return pow(c, vec3(1.0 / 2.2));
}

float distribution_ggx(vec3 N, vec3 H, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float NdotH = max(dot(N, H), 0.0);
    float NdotH2 = NdotH * NdotH;
    float denom = (NdotH2 * (a2 - 1.0) + 1.0);
    return a2 / (PI * denom * denom + 1e-5);
}

float geometry_schlick_ggx(float NdotV, float roughness) {
    float r = (roughness + 1.0);
    float k = (r * r) / 8.0;
    return NdotV / (NdotV * (1.0 - k) + k + 1e-5);
}

float geometry_smith(vec3 N, vec3 V, vec3 L, float roughness) {
    float NdotV = max(dot(N, V), 0.0);
    float NdotL = max(dot(N, L), 0.0);
    return geometry_schlick_ggx(NdotV, roughness) * geometry_schlick_ggx(NdotL, roughness);
}

vec3 fresnel_schlick(float cosTheta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

vec3 eval_window_reflection(vec3 world_pos, vec3 N, vec3 V, vec3 F0, float roughness, float spec_strength, float is_sunset, float shadow_vis) {
    if (N.z < 0.75 || spec_strength < 0.20) return vec3(0.0);
    if (world_pos.x < 0.0 || world_pos.x > 11.79 || world_pos.y < 0.0 || world_pos.y > 12.10) return vec3(0.0);

    vec3 R = reflect(-V, N);
    if (R.x <= 0.04) return vec3(0.0);

    float t_w = (11.79 - world_pos.x) / R.x;
    float hit_y = world_pos.y + R.y * t_w;
    float hit_z = world_pos.z + R.z * t_w;

    float blur = 0.05 + roughness * 0.22;
    float in_y = smoothstep(0.48 - blur, 0.48 + blur, hit_y) * (1.0 - smoothstep(11.62 - blur, 11.62 + blur, hit_y));
    float in_z = smoothstep(0.94 - blur, 0.94 + blur, hit_z) * (1.0 - smoothstep(2.82 - blur, 2.82 + blur, hit_z));
    if (in_y * in_z <= 0.001) return vec3(0.0);

    float bay_u = fract((hit_y - 0.48) / 1.114);
    float mullion = smoothstep(0.025, 0.085, bay_u) * smoothstep(0.975, 0.915, bay_u);
    float transom = smoothstep(0.025, 0.085, abs(hit_z - 2.33));
    float win_mask = in_y * in_z * mix(1.0, mullion * transom, 1.0 - roughness * 0.80);

    vec3 sky_sample = eval_procedural_sky(normalize(vec3(R.x, R.y, max(R.z, 0.05))), is_sunset);
    vec3 F_win = fresnel_schlick(max(dot(N, V), 0.0), F0);
    float occ = shadow_vis * shadow_vis;
    return sky_sample * F_win * (win_mask * spec_strength * (1.0 - roughness * 0.60) * occ * 0.36);
}

void main() {
    float is_sunset = clamp((u_sun_color.r - u_sun_color.b) * 2.2, 0.0, 1.0);

    if (u_is_skybox == 1) {
        vec3 ray_dir = normalize(v_world_pos - u_eye);
        vec3 sky = eval_procedural_sky(ray_dir, is_sunset);
        fragColor = vec4(sky, 1.0);
        return;
    }

    vec4 tex_sample = texture(u_texture, v_uv);
    vec3 base_color = srgb_to_linear(v_color.rgb * tex_sample.rgb);
    float alpha = v_color.a * tex_sample.a;

    if (u_emissive_factor > 0.0) {
        vec3 emissive = base_color * u_emissive_factor;
        fragColor = vec4(emissive, alpha);
        return;
    }

    float roughness = clamp(v_mat.r, 0.04, 1.0);
    float spec_strength = v_mat.g;
    float bump_strength = v_mat.b;

    vec3 N = normalize(v_normal);
    vec3 to_eye = u_eye - v_world_pos;
    float view_dist = length(to_eye);
    vec3 V = to_eye / max(view_dist, 1e-4);

    bool is_exterior = (v_world_pos.x > 12.3 || v_world_pos.x < -0.6 || v_world_pos.y < -0.6 || v_world_pos.y > 16.6);
    vec3 ext_emissive = vec3(0.0);

    // Procedural architectural detailing on 3D exterior campus buildings & foliage
    if (is_exterior) {
        if (v_color.g > v_color.r + 0.03) {
            // Lush 3D tree canopy leaf clusters
            float leaf_n = sky_fbm(v_world_pos.xy * 0.85 + vec2(v_world_pos.z * 0.5));
            base_color *= (0.72 + 0.52 * leaf_n);
        } else if (abs(N.z) < 0.25 && v_color.b > v_color.r + 0.015) {
            // Exterior building glass window bands: aluminum mullions, sky reflection, & lit sunset rooms
            float cell_u = fract(v_world_pos.y / 1.25);
            float cell_v = fract(v_world_pos.z / 1.15);
            float mullion_frame = smoothstep(0.04, 0.09, cell_u) * smoothstep(0.96, 0.91, cell_u)
                                * smoothstep(0.05, 0.10, cell_v) * smoothstep(0.95, 0.90, cell_v);
            vec3 frame_col = vec3(0.05, 0.06, 0.08);
            vec3 ext_sky_ref = eval_procedural_sky(normalize(vec3(0.6, V.y, max(abs(V.z), 0.06))), is_sunset) * 0.35;
            float room_id = sky_hash(floor(vec2(v_world_pos.y / 2.5, v_world_pos.z / 3.2)));
            float room_lit = (is_sunset > 0.5 && room_id > 0.60) ? (0.65 + 0.35 * fract(room_id * 13.7)) : 0.0;
            vec3 warm_room = vec3(1.10, 0.65, 0.24) * room_lit;
            base_color = mix(frame_col, base_color * 0.55, mullion_frame);
            ext_emissive = (ext_sky_ref + warm_room) * mullion_frame;
        } else if (abs(N.z) < 0.25) {
            // Exterior concrete/masonry facade panel joints & warm vertical sun-bounce gradient
            float j_u = smoothstep(0.015, 0.04, fract(v_world_pos.y / 2.4));
            float j_v = smoothstep(0.015, 0.04, fract(v_world_pos.z / 3.2));
            float height_grad = clamp((v_world_pos.z + 14.0) / 26.0, 0.72, 1.12);
            base_color *= (0.90 + 0.10 * j_u * j_v) * height_grad;
        }
    }

    vec3 F0 = mix(vec3(0.04), base_color, spec_strength * 0.5);

    // Screen-space derivative bump mapping from albedo luminance
    if (bump_strength > 0.001) {
        float luma = dot(tex_sample.rgb, vec3(0.299, 0.587, 0.114));
        float dhx = dFdx(luma);
        float dhy = dFdy(luma);
        vec3 dpdx = dFdx(v_world_pos);
        vec3 dpdy = dFdy(v_world_pos);
        vec3 surf_grad = cross(dpdy, N) * dhx + cross(N, dpdx) * dhy;
        float det = dot(dpdx, cross(dpdy, N));
        if (abs(det) > 1e-4) {
            vec3 grad = surf_grad / det;
            float grad_len = length(grad);
            if (grad_len > 2.0) grad = (grad / grad_len) * 2.0;
            N = normalize(N - bump_strength * 0.025 * grad);
        }
    }

    float NdotV = max(dot(N, V), 0.001);

    vec3 Lo = vec3(0.0);
    float surface_shadow = 1.0;

    // Sun directional light with shadow factor
    if (u_sun_intensity > 0.0) {
        vec3 L = normalize(u_sun_dir);
        vec3 H = normalize(V + L);
        float NdotL = max(dot(N, L), 0.0);
        if (!is_exterior) {
            surface_shadow = calculate_shadow(v_light_space_pos, N, L);
        }
        if (NdotL > 0.0) {
            float shadow_factor = surface_shadow;
            if (shadow_factor > 0.001) {
                float D = distribution_ggx(N, H, roughness);
                float G = geometry_smith(N, V, L, roughness);
                vec3 F = fresnel_schlick(max(dot(H, V), 0.0), F0);
                vec3 kS = F;
                vec3 kD = (vec3(1.0) - kS);
                vec3 spec = (D * G * F) / max(4.0 * NdotV * NdotL, 0.001);
                vec3 radiance = u_sun_color * (u_sun_intensity * shadow_factor);
                Lo += (kD * base_color / PI + spec * spec_strength) * radiance * NdotL;
            }
        } else if (is_exterior) {
            // Warm courtyard & sky bounce light on west-facing exterior building facades
            float bounce_ndl = max(dot(N, normalize(vec3(-0.65, 0.35, 0.65))), 0.0);
            Lo += (base_color / PI) * u_sun_color * (u_sun_intensity * 0.34 * bounce_ndl);
        }
    }

    // 13 fluorescent point lights
    if (u_lamp_intensity > 0.0 && !is_exterior) {
        for (int i = 0; i < 13; ++i) {
            vec3 to_light = u_lamp_pos[i] - v_world_pos;
            float dist = length(to_light);
            if (dist < 8.0) {
                vec3 L = to_light / dist;
                vec3 H = normalize(V + L);
                float NdotL = max(dot(N, L), 0.0);
                if (NdotL > 0.0) {
                    float atten = 1.0 / (1.0 + 0.1 * dist + 0.25 * dist * dist);
                    float window = clamp(1.0 - pow(dist / 8.0, 4.0), 0.0, 1.0);
                    atten *= window * window;
                    vec3 radiance = u_lamp_color * (u_lamp_intensity * atten);
                    float D = distribution_ggx(N, H, roughness);
                    float G = geometry_smith(N, V, L, roughness);
                    vec3 F = fresnel_schlick(max(dot(H, V), 0.0), F0);
                    vec3 kS = F;
                    vec3 kD = (vec3(1.0) - kS);
                    vec3 spec = (D * G * F) / max(4.0 * NdotV * NdotL, 0.001);
                    Lo += (kD * base_color / PI + spec * spec_strength) * radiance * NdotL;
                }
            }
        }
    }

    // Hemisphere ambient
    float hemi = clamp(N.z * 0.5 + 0.5, 0.0, 1.0);
    vec3 ambient_light = mix(u_hemi_ground, u_hemi_sky, hemi) * u_ambient_scale;
    vec3 ambient = ambient_light * base_color;

    // Specular Fresnel sky & window-bay reflection for glossy surfaces (floors, oak desks)
    if (spec_strength > 0.1) {
        vec3 R = reflect(-V, N);
        float r_hemi = clamp(R.z * 0.5 + 0.5, 0.0, 1.0);
        vec3 sky_ref = mix(u_hemi_ground, u_hemi_sky, r_hemi) * u_ambient_scale;
        vec3 F_grazing = fresnel_schlick(NdotV, F0);
        Lo += sky_ref * F_grazing * (spec_strength * (1.0 - roughness * 0.5));
        Lo += eval_window_reflection(v_world_pos, N, V, F0, roughness, spec_strength, is_sunset, surface_shadow);
    }

    vec3 final_color = Lo + ambient + ext_emissive;

    // Subtle real-glass sky glint on transparent window & door glazing
    if (alpha < 0.85) {
        float f_glass = 0.03 + 0.18 * pow(1.0 - NdotV, 4.0);
        float glint_band = smoothstep(0.20, 0.80, sin(v_world_pos.y * 0.75 + v_world_pos.z * 1.20));
        vec3 glass_sky = eval_procedural_sky(normalize(vec3(0.75, -V.y * 0.4, 0.22)), is_sunset);
        final_color = mix(final_color, glass_sky * (0.75 + 0.25 * glint_band), 0.35);
        alpha = clamp(alpha + f_glass * 0.08, 0.0, 0.16);
    }

    // Distance-based aerial perspective haze on exterior 3D campus & skyline buildings
    if (is_exterior && view_dist > 16.0) {
        float aerial_haze = clamp((view_dist - 16.0) / 105.0, 0.0, 0.78);
        vec3 haze_col = mix(vec3(0.62, 0.72, 0.84), vec3(0.84, 0.42, 0.22), is_sunset) * max(u_ambient_scale, 0.55);
        final_color = mix(final_color, haze_col, aerial_haze);
    }

    fragColor = vec4(final_color, alpha);
}
"""

UI_VS = """#version 330 compatibility
out vec2 v_uv;
void main() {
    v_uv = gl_MultiTexCoord0.xy;
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
"""

UI_FS = """#version 330 compatibility
in vec2 v_uv;
uniform sampler2D u_texture;
uniform vec4 u_color;
out vec4 fragColor;
void main() {
    fragColor = u_color * texture(u_texture, v_uv);
}
"""

SHADOW_VS = """#version 330 compatibility
invariant gl_Position;
void main() {
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
"""

SHADOW_FS = """#version 330 compatibility
void main() {
    // Empty fragment shader; depth written automatically
}
"""

QUAD_VS = """#version 330 compatibility
out vec2 v_uv;
void main() {
    v_uv = gl_MultiTexCoord0.xy;
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
"""

BRIGHTPASS_FS = """#version 330 compatibility
in vec2 v_uv;
uniform sampler2D u_hdr_texture;
uniform float u_threshold;
uniform float u_knee;
out vec4 fragColor;

void main() {
    vec3 color = texture(u_hdr_texture, v_uv).rgb;
    float luma = dot(color, vec3(0.2126, 0.7152, 0.0722));
    // Soft knee curve
    float soft = clamp(luma - u_threshold + u_knee, 0.0, 2.0 * u_knee);
    soft = (soft * soft) / (4.0 * u_knee + 1e-5);
    float factor = max(soft, luma - u_threshold) / max(luma, 1e-4);
    factor = clamp(factor, 0.0, 1.0);
    fragColor = vec4(color * factor, 1.0);
}
"""

BLUR_FS = """#version 330 compatibility
in vec2 v_uv;
uniform sampler2D u_texture;
uniform vec2 u_direction;
out vec4 fragColor;

// 9-tap Gaussian weights (half symmetric: 0, 1, 2, 3, 4)
const float weights[5] = float[](0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);

void main() {
    // Zero direction = plain down/upsample copy. Weights sum to 1, so one fetch
    // gives the same result as nine.
    if (u_direction == vec2(0.0)) {
        fragColor = vec4(texture(u_texture, v_uv).rgb, 1.0);
        return;
    }
    vec3 result = texture(u_texture, v_uv).rgb * weights[0];
    for (int i = 1; i < 5; ++i) {
        vec2 offset = u_direction * float(i);
        result += texture(u_texture, v_uv + offset).rgb * weights[i];
        result += texture(u_texture, v_uv - offset).rgb * weights[i];
    }
    fragColor = vec4(result, 1.0);
}
"""

SSAO_FS = """#version 330 compatibility
in vec2 v_uv;
uniform sampler2D u_depth_texture;
uniform mat4 u_inv_proj;
uniform mat4 u_proj;
uniform vec2 u_resolution;
out vec4 fragColor;

// 16 pseudo-random hemispherical sample offsets
const vec3 ssao_kernel[16] = vec3[](
    vec3( 0.5381,  0.1856, -0.4319),
    vec3( 0.1379,  0.2486,  0.4430),
    vec3( 0.3371,  0.5679, -0.0057),
    vec3(-0.6999, -0.0451, -0.0019),
    vec3( 0.0689, -0.1598, -0.8547),
    vec3( 0.0560,  0.0069, -0.1843),
    vec3(-0.0146,  0.1402,  0.0762),
    vec3( 0.0100, -0.1924, -0.0344),
    vec3(-0.3577, -0.5301, -0.4358),
    vec3(-0.3169,  0.1063,  0.0158),
    vec3( 0.0103, -0.5869,  0.0046),
    vec3(-0.0897, -0.4940,  0.3287),
    vec3( 0.7119, -0.0154, -0.0918),
    vec3(-0.0533,  0.0596, -0.5411),
    vec3( 0.0352, -0.0631,  0.5460),
    vec3(-0.4776,  0.2847, -0.0271)
);

vec3 view_pos_from_depth(vec2 uv, float depth) {
    vec4 clip = vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    vec4 view = u_inv_proj * clip;
    return view.xyz / view.w;
}

void main() {
    float depth = texture(u_depth_texture, v_uv).r;
    if (depth >= 1.0) {
        fragColor = vec4(1.0);
        return;
    }

    vec3 pos = view_pos_from_depth(v_uv, depth);

    // Reconstruct view-space normal from depth derivatives
    vec3 dpos_dx = dFdx(pos);
    vec3 dpos_dy = dFdy(pos);
    vec3 normal = normalize(cross(dpos_dx, dpos_dy));

    // Simple pseudo-random rotation per pixel
    vec2 noise = fract(sin(gl_FragCoord.xy * vec2(12.9898, 78.233)) * 43758.5453);
    float angle = noise.x * 6.2831853;
    mat2 rot = mat2(cos(angle), -sin(angle), sin(angle), cos(angle));

    float occlusion = 0.0;
    float radius = 0.45; // 0.45 meter AO hemisphere radius
    float bias = 0.025;

    for (int i = 0; i < 16; ++i) {
        vec3 sample_dir = ssao_kernel[i];
        sample_dir.xy = rot * sample_dir.xy;
        if (dot(sample_dir, normal) < 0.0) {
            sample_dir = -sample_dir;
        }

        vec3 sample_pos = pos + sample_dir * radius;
        vec4 sample_clip = u_proj * vec4(sample_pos, 1.0);
        vec3 sample_ndc = sample_clip.xyz / sample_clip.w;
        vec2 sample_uv = sample_ndc.xy * 0.5 + 0.5;

        if (sample_uv.x >= 0.0 && sample_uv.x <= 1.0 && sample_uv.y >= 0.0 && sample_uv.y <= 1.0) {
            float sample_depth = texture(u_depth_texture, sample_uv).r;
            vec3 actual_pos = view_pos_from_depth(sample_uv, sample_depth);
            float dist = abs(pos.z - actual_pos.z);
            float range_check = (dist < radius) ? smoothstep(radius, 0.0, dist) : 0.0;
            if (actual_pos.z >= sample_pos.z + bias) {
                occlusion += range_check;
            }
        }
    }

    float ao = clamp(1.0 - (occlusion / 16.0) * 1.5, 0.0, 1.0);
    fragColor = vec4(vec3(ao), 1.0);
}
"""

SSAO_BLUR_FS = """#version 330 compatibility
in vec2 v_uv;
uniform sampler2D u_ssao_texture;
uniform vec2 u_texel_size;
out vec4 fragColor;

void main() {
    float result = 0.0;
    for (int x = -2; x <= 2; ++x) {
        for (int y = -2; y <= 2; ++y) {
            vec2 offset = vec2(float(x), float(y)) * u_texel_size;
            result += texture(u_ssao_texture, v_uv + offset).r;
        }
    }
    fragColor = vec4(vec3(result / 25.0), 1.0);
}
"""

COMPOSITE_FS = """#version 330 compatibility
in vec2 v_uv;
uniform sampler2D u_hdr_texture;
uniform sampler2D u_bloom_texture;
uniform sampler2D u_ao_texture;
uniform float u_exposure;
uniform float u_bloom_strength;
uniform float u_ao_strength;
out vec4 fragColor;

// Narkowicz ACES tone mapping curve
vec3 aces_film(vec3 x) {
    float a = 2.51;
    float b = 0.03;
    float c = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

void main() {
    vec3 hdr = texture(u_hdr_texture, v_uv).rgb;
    vec3 bloom = texture(u_bloom_texture, v_uv).rgb;
    float ao = texture(u_ao_texture, v_uv).r;
    float ao_factor = mix(1.0, ao, u_ao_strength);

    // Apply SSAO darkening to HDR color
    hdr *= ao_factor;

    // Exposure scale: 2^exposure_ev
    vec3 color = hdr * exp2(u_exposure);
    color += bloom * u_bloom_strength;

    // ACES Tone mapping
    vec3 ldr = aces_film(color);

    // Subtle nostalgic heartwarming film color grade (purely multiplicative so shadow depth is preserved)
    vec3 warm_tint = ldr * vec3(1.022, 1.000, 0.965);
    vec3 film_grade = clamp(mix(ldr, warm_tint, 0.40), 0.0, 1.0);
    ldr = film_grade;

    // Gentle optical vignette
    vec2 coord = (v_uv - 0.5) * 2.0;
    float dist = dot(coord, coord);
    float vignette = clamp(1.0 - dist * 0.18, 0.0, 1.0);
    ldr *= vignette;

    // Linear to sRGB gamma
    ldr = pow(ldr, vec3(1.0 / 2.2));

    fragColor = vec4(ldr, 1.0);
}
"""

FXAA_FS = """#version 330 compatibility
in vec2 v_uv;
uniform sampler2D u_texture;
uniform vec2 u_texel_size;
out vec4 fragColor;

float rgb2luma(vec3 rgb) {
    return dot(rgb, vec3(0.299, 0.587, 0.114));
}

void main() {
    vec2 tc = v_uv;
    vec3 rgbM = texture(u_texture, tc).rgb;
    float lumaM = rgb2luma(rgbM);

    float lumaNW = rgb2luma(texture(u_texture, tc + vec2(-1.0, -1.0) * u_texel_size).rgb);
    float lumaNE = rgb2luma(texture(u_texture, tc + vec2( 1.0, -1.0) * u_texel_size).rgb);
    float lumaSW = rgb2luma(texture(u_texture, tc + vec2(-1.0,  1.0) * u_texel_size).rgb);
    float lumaSE = rgb2luma(texture(u_texture, tc + vec2( 1.0,  1.0) * u_texel_size).rgb);

    float lumaMin = min(lumaM, min(min(lumaNW, lumaNE), min(lumaSW, lumaSE)));
    float lumaMax = max(lumaM, max(max(lumaNW, lumaNE), max(lumaSW, lumaSE)));

    float range = lumaMax - lumaMin;
    if (range < max(0.05, lumaMax * 0.125)) {
        fragColor = vec4(rgbM, 1.0);
        return;
    }

    vec2 dir;
    dir.x = -((lumaNW + lumaNE) - (lumaSW + lumaSE));
    dir.y =  ((lumaNW + lumaSW) - (lumaNE + lumaSE));

    float dirReduce = max((lumaNW + lumaNE + lumaSW + lumaSE) * 0.03125, 0.0078125);
    float rcpDirMin = 1.0 / (min(abs(dir.x), abs(dir.y)) + dirReduce);
    dir = min(vec2(8.0), max(vec2(-8.0), dir * rcpDirMin)) * u_texel_size;

    vec3 rgbA = 0.5 * (
        texture(u_texture, tc + dir * (1.0 / 3.0 - 0.5)).rgb +
        texture(u_texture, tc + dir * (2.0 / 3.0 - 0.5)).rgb
    );
    vec3 rgbB = rgbA * 0.5 + 0.25 * (
        texture(u_texture, tc + dir * (0.0 / 3.0 - 0.5)).rgb +
        texture(u_texture, tc + dir * (3.0 / 3.0 - 0.5)).rgb
    );

    float lumaB = rgb2luma(rgbB);
    if ((lumaB < lumaMin) || (lumaB > lumaMax)) {
        fragColor = vec4(rgbA, 1.0);
    } else {
        fragColor = vec4(rgbB, 1.0);
    }
}
"""


# ---------------------------------------------------------------------------
# Volumetric God Rays & Dust Shaders
# ---------------------------------------------------------------------------

GODRAY_VS = """#version 330 compatibility

uniform mat4 u_light_space_matrix;

out vec3 v_world_pos;
out vec2 v_uv;
out vec3 v_normal;
out float v_layer_weight;
out vec4 v_light_space_pos;

void main() {
    v_world_pos = gl_Vertex.xyz;
    v_uv = gl_MultiTexCoord0.xy;
    v_normal = gl_Normal;
    v_layer_weight = gl_Color.a;
    v_light_space_pos = u_light_space_matrix * vec4(gl_Vertex.xyz, 1.0);
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
"""

GODRAY_FS = """#version 330 compatibility

uniform vec3 u_color;
uniform float u_opacity;
uniform vec3 u_eye;
uniform float u_time;
uniform vec3 u_sun_dir;
uniform sampler2DShadow u_shadow_map;

in vec3 v_world_pos;
in vec2 v_uv;
in vec3 v_normal;
in float v_layer_weight;
in vec4 v_light_space_pos;

out vec4 fragColor;

float hash(vec3 p) {
    p = fract(p * 0.3183099 + 0.1);
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float noise(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash(i + vec3(0,0,0)), hash(i + vec3(1,0,0)), f.x),
                   mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
               mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x),
                   mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z);
}

float sample_volumetric_shadow(vec4 light_space_pos) {
    vec3 proj = light_space_pos.xyz / max(light_space_pos.w, 0.0001);
    proj = proj * 0.5 + 0.5;
    if (proj.x < 0.0 || proj.x > 1.0 || proj.y < 0.0 || proj.y > 1.0 || proj.z > 1.0) {
        return 1.0;
    }
    float z_ref = proj.z - 0.003;
    float s = texture(u_shadow_map, vec3(proj.xy, z_ref));
    s += texture(u_shadow_map, vec3(proj.xy + vec2( 0.0018,  0.0018), z_ref));
    s += texture(u_shadow_map, vec3(proj.xy + vec2(-0.0018,  0.0018), z_ref));
    s += texture(u_shadow_map, vec3(proj.xy + vec2( 0.0018, -0.0018), z_ref));
    s += texture(u_shadow_map, vec3(proj.xy + vec2(-0.0018, -0.0018), z_ref));
    return s * 0.2;
}

void main() {
    float ray_t = clamp(v_uv.x, 0.0, 1.0);
    float edge_u = clamp(v_uv.y, 0.0, 1.0);

    // Smooth entry at window glass + exponential atmospheric decay along shaft
    float entry_feather = smoothstep(0.0, 0.06, ray_t);
    float ray_fade = entry_feather * pow(1.0 - ray_t, 1.55);

    // Sinusoidal transverse edge feathering eliminates hard polygon edges
    float edge_feather = pow(sin(edge_u * 3.14159265), 1.55) * clamp(v_layer_weight, 0.0, 1.0);

    // Soft fade near floor and camera lens
    float floor_fade = smoothstep(0.08, 0.45, v_world_pos.z);
    vec3 view_vec = u_eye - v_world_pos;
    float dist = length(view_vec);
    vec3 V = view_vec / max(dist, 0.001);
    float near_fade = smoothstep(0.18, 0.90, dist);

    // Grazing view-angle fade so edge-on slices never form bright lines
    float ndotv = abs(dot(normalize(v_normal), V));
    float view_fade = smoothstep(0.03, 0.28, ndotv);

    // Anti-washout lengthwise overlap compensation when viewing down the row of window bays
    float overlap_comp = mix(1.0, 0.38, smoothstep(0.48, 0.88, abs(V.y)));
    float dist_damping = 1.0 / (1.0 + 0.045 * max(dist - 4.0, 0.0));

    // Henyey-Greenstein / Mie forward-scattering phase boost toward sun
    float cos_theta = clamp(dot(-V, normalize(u_sun_dir)), -1.0, 1.0);
    float phase = 0.82 + 0.42 * pow(max(cos_theta, 0.0), 2.0);

    // 2-octave animated convection air-current FBM
    vec3 npos1 = v_world_pos * 0.55 + vec3(u_time * 0.025, u_time * 0.015, -u_time * 0.018);
    vec3 npos2 = v_world_pos * 1.25 + vec3(-u_time * 0.018, u_time * 0.028, u_time * 0.012);
    float air_fbm = 0.72 + 0.20 * noise(npos1) + 0.12 * noise(npos2);

    // Shadow-mapped occlusion from window mullions and furniture with crisp crepuscular contrast
    float shadow_raw = sample_volumetric_shadow(v_light_space_pos);
    float shadow_vis = mix(0.06, 1.0, shadow_raw);

    float alpha = u_opacity * ray_fade * edge_feather * floor_fade * near_fade * view_fade * overlap_comp * dist_damping * phase * air_fbm * shadow_vis * 0.24;
    if (alpha <= 0.0004) discard;

    // Warm golden-white core near the window transitioning to nostalgic amber-gold deeper in the room
    vec3 warm_core = mix(u_color, vec3(1.0, 0.96, 0.86), 0.30 * (1.0 - ray_t));
    fragColor = vec4(warm_core * 2.50, alpha);
}
"""

DUST_VS = """#version 330 compatibility

uniform vec3 u_eye;
uniform mat4 u_light_space_matrix;

out float v_alpha;
out vec4 v_light_space_pos;

void main() {
    v_alpha = gl_Color.a;
    v_light_space_pos = u_light_space_matrix * vec4(gl_Vertex.xyz, 1.0);
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
    float dist = length(gl_Vertex.xyz - u_eye);
    gl_PointSize = clamp(3.6 * (14.0 / max(dist, 1.0)), 1.8, 6.2);
}
"""

DUST_FS = """#version 330 compatibility

uniform vec3 u_color;
uniform float u_opacity;
uniform sampler2DShadow u_shadow_map;

in float v_alpha;
in vec4 v_light_space_pos;
out vec4 fragColor;

void main() {
    vec2 coord = gl_PointCoord - vec2(0.5);
    float dist = length(coord);
    if (dist > 0.5) discard;

    // Soft out-of-focus bokeh core + golden halo
    float core = smoothstep(0.24, 0.0, dist);
    float halo = smoothstep(0.50, 0.10, dist) * 0.48;
    float bokeh = core + halo;

    vec3 proj = v_light_space_pos.xyz / max(v_light_space_pos.w, 0.0001);
    proj = proj * 0.5 + 0.5;
    float lit = 1.0;
    if (proj.x >= 0.0 && proj.x <= 1.0 && proj.y >= 0.0 && proj.y <= 1.0 && proj.z <= 1.0) {
        lit = mix(0.30, 1.25, texture(u_shadow_map, vec3(proj.xy, proj.z - 0.003)));
    }

    float alpha = u_opacity * v_alpha * bokeh * lit * 0.72;
    if (alpha <= 0.001) discard;

    vec3 mote_color = mix(u_color, vec3(1.0, 0.96, 0.84), 0.45 * core);
    fragColor = vec4(mote_color * 3.1, alpha);
}
"""


# ---------------------------------------------------------------------------
# Physical Dust System
# ---------------------------------------------------------------------------

class DustParticle:
    __slots__ = ("x", "y", "z", "vx", "vy", "vz", "vol_idx", "size", "alpha_factor")

    def __init__(self, x: float, y: float, z: float, vx: float, vy: float, vz: float, vol_idx: int, size: float, alpha_factor: float):
        self.x = x
        self.y = y
        self.z = z
        self.vx = vx
        self.vy = vy
        self.vz = vz
        self.vol_idx = vol_idx
        self.size = size
        self.alpha_factor = alpha_factor


class DustSystem:
    """Drifting physical dust particles constrained inside volumetric light shafts."""

    def __init__(self, count: int, volumes: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]], seed: int = 612):
        self.count = max(0, int(count))
        self.volumes = [v for v in volumes] if volumes else [((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))]
        self.seed = seed
        self.particles: List[DustParticle] = []
        self._init_particles()

    def _init_particles(self):
        rng = random.Random(self.seed)
        n_vols = len(self.volumes)
        self.particles.clear()
        for i in range(self.count):
            vol_idx = i % n_vols
            (min_x, min_y, min_z), (max_x, max_y, max_z) = self.volumes[vol_idx]
            x = rng.uniform(min_x, max_x)
            y = rng.uniform(min_y, max_y)
            z = rng.uniform(min_z, max_z)
            vx = rng.uniform(-0.035, 0.035)
            vy = rng.uniform(-0.035, 0.035)
            vz = rng.uniform(-0.012, 0.022)
            size = rng.uniform(1.8, 3.5)
            alpha_factor = rng.uniform(0.4, 1.0)
            self.particles.append(DustParticle(x, y, z, vx, vy, vz, vol_idx, size, alpha_factor))

    def set_volumes(self, volumes: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]):
        if not volumes:
            return
        self.volumes = [v for v in volumes]
        n_vols = len(self.volumes)
        for i, p in enumerate(self.particles):
            p.vol_idx = i % n_vols
            (min_x, min_y, min_z), (max_x, max_y, max_z) = self.volumes[p.vol_idx]
            dx = max_x - min_x
            dy = max_y - min_y
            dz = max_z - min_z
            if dx > 1e-6: p.x = min_x + (p.x - min_x) % dx
            if dy > 1e-6: p.y = min_y + (p.y - min_y) % dy
            if dz > 1e-6: p.z = min_z + (p.z - min_z) % dz

    @property
    def positions(self) -> List[Tuple[float, float, float]]:
        return [(p.x, p.y, p.z) for p in self.particles]

    def update(self, dt: float) -> None:
        dt = max(0.0, min(0.2, float(dt)))
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.z += p.vz * dt
            (min_x, min_y, min_z), (max_x, max_y, max_z) = self.volumes[p.vol_idx]
            dx = max_x - min_x
            dy = max_y - min_y
            dz = max_z - min_z
            if dx > 1e-6:
                p.x = min_x + (p.x - min_x) % dx
            if dy > 1e-6:
                p.y = min_y + (p.y - min_y) % dy
            if dz > 1e-6:
                p.z = min_z + (p.z - min_z) % dz

    def draw(self, frame: Any) -> None:
        if not self.particles:
            return
        glEnable(GL_PROGRAM_POINT_SIZE)
        glEnable(GL_POINT_SMOOTH)
        glBegin(GL_POINTS)
        for p in self.particles:
            glColor4f(1.0, 1.0, 1.0, p.alpha_factor)
            glVertex3f(p.x, p.y, p.z)
        glEnd()
        glDisable(GL_POINT_SMOOTH)


# ---------------------------------------------------------------------------
# FrameState dataclass
# ---------------------------------------------------------------------------

@dataclass
class FrameState:
    eye: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    target: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    fov: float = 52.0
    width: int = 1440
    height: int = 900
    cutaway: bool = False
    ceiling: bool = True
    door_angle: float = 0.0
    lighting_preset: str = "daylight"
    interior_lights: bool = True
    god_rays: bool = True
    lighting: Any = None
    time: float = 0.0
    quality: str = "high"


# ---------------------------------------------------------------------------
# Renderer pipeline
# ---------------------------------------------------------------------------

class Renderer:
    """Shader-driven OpenGL renderer replacing fixed-function lighting."""
    def __init__(self, scene: Any, quality: str = "high"):
        if quality not in ("low", "high"):
            raise ValueError(f"Invalid quality mode: '{quality}'. Must be 'low' or 'high'.")
        self.scene = scene
        self.quality = quality
        self.depth_prepass = True
        self.shadow_prog = compile_program(SHADOW_VS, SHADOW_FS, "Shadow_Depth")
        self.scene_prog = compile_program(SCENE_VS, SCENE_FS, "PBR_Scene")
        self.ssao_prog = compile_program(QUAD_VS, SSAO_FS, "SSAO")
        self.ssao_blur_prog = compile_program(QUAD_VS, SSAO_BLUR_FS, "SSAO_Blur")
        self.brightpass_prog = compile_program(QUAD_VS, BRIGHTPASS_FS, "BrightPass")
        self.blur_prog = compile_program(QUAD_VS, BLUR_FS, "GaussianBlur")
        self.composite_prog = compile_program(QUAD_VS, COMPOSITE_FS, "Composite")
        self.fxaa_prog = compile_program(QUAD_VS, FXAA_FS, "FXAA")
        self.ui_prog = compile_program(UI_VS, UI_FS, "UI_Quad")
        self.godray_prog = compile_program(GODRAY_VS, GODRAY_FS, "GodRays")
        self.dust_prog = compile_program(DUST_VS, DUST_FS, "Dust")

        # Dust system
        dust_count = 400 if quality == "high" else 150
        init_vols = getattr(scene, "god_ray_volumes", {}).get("daylight", [])
        self.dust_system = DustSystem(dust_count, init_vols)
        self.last_time = 0.0

        # Framebuffers (allocated lazily / resized in _ensure_targets)
        self.width = 1
        self.height = 1
        self.shadow_size = 2048 if quality == "high" else 1024
        self.shadow_target: Optional[RenderTarget] = None
        self.hdr_target: Optional[RenderTarget] = None
        self.ssao_target: Optional[RenderTarget] = None
        self.ssao_blur_target: Optional[RenderTarget] = None
        self.bloom_targets_a: List[RenderTarget] = []
        self.bloom_targets_b: List[RenderTarget] = []
        self.ldr_target: Optional[RenderTarget] = None

        self._cache_uniforms()

    def _cache_uniforms(self):
        p = self.scene_prog
        self.u_texture = glGetUniformLocation(p, "u_texture")
        self.u_shadow_map = glGetUniformLocation(p, "u_shadow_map")
        self.u_light_space_matrix = glGetUniformLocation(p, "u_light_space_matrix")
        self.u_shadow_softness = glGetUniformLocation(p, "u_shadow_softness")
        self.u_shadow_map_size = glGetUniformLocation(p, "u_shadow_map_size")
        self.u_eye = glGetUniformLocation(p, "u_eye")
        self.u_sun_dir = glGetUniformLocation(p, "u_sun_dir")
        self.u_sun_color = glGetUniformLocation(p, "u_sun_color")
        self.u_sun_intensity = glGetUniformLocation(p, "u_sun_intensity")
        self.u_hemi_sky = glGetUniformLocation(p, "u_hemi_sky")
        self.u_hemi_ground = glGetUniformLocation(p, "u_hemi_ground")
        self.u_ambient_scale = glGetUniformLocation(p, "u_ambient_scale")
        self.u_lamp_color = glGetUniformLocation(p, "u_lamp_color")
        self.u_lamp_intensity = glGetUniformLocation(p, "u_lamp_intensity")
        self.u_emissive_factor = glGetUniformLocation(p, "u_emissive_factor")
        self.u_is_skybox = glGetUniformLocation(p, "u_is_skybox")
        self.u_time = glGetUniformLocation(p, "u_time")
        self.u_lamp_pos = [glGetUniformLocation(p, f"u_lamp_pos[{i}]") for i in range(13)]

        gr = self.godray_prog
        self.gr_u_color = glGetUniformLocation(gr, "u_color")
        self.gr_u_opacity = glGetUniformLocation(gr, "u_opacity")
        self.gr_u_eye = glGetUniformLocation(gr, "u_eye")
        self.gr_u_time = glGetUniformLocation(gr, "u_time")
        self.gr_u_sun_dir = glGetUniformLocation(gr, "u_sun_dir")
        self.gr_u_shadow_map = glGetUniformLocation(gr, "u_shadow_map")
        self.gr_u_light_space_matrix = glGetUniformLocation(gr, "u_light_space_matrix")

        dp = self.dust_prog
        self.dust_u_color = glGetUniformLocation(dp, "u_color")
        self.dust_u_opacity = glGetUniformLocation(dp, "u_opacity")
        self.dust_u_eye = glGetUniformLocation(dp, "u_eye")
        self.dust_u_shadow_map = glGetUniformLocation(dp, "u_shadow_map")
        self.dust_u_light_space_matrix = glGetUniformLocation(dp, "u_light_space_matrix")

        s = self.ssao_prog
        self.ssao_u_depth = glGetUniformLocation(s, "u_depth_texture")
        self.ssao_u_inv_proj = glGetUniformLocation(s, "u_inv_proj")
        self.ssao_u_proj = glGetUniformLocation(s, "u_proj")
        self.ssao_u_resolution = glGetUniformLocation(s, "u_resolution")

        sb = self.ssao_blur_prog
        self.sb_u_ssao = glGetUniformLocation(sb, "u_ssao_texture")
        self.sb_u_texel_size = glGetUniformLocation(sb, "u_texel_size")

        bp = self.brightpass_prog
        self.bp_u_hdr = glGetUniformLocation(bp, "u_hdr_texture")
        self.bp_u_threshold = glGetUniformLocation(bp, "u_threshold")
        self.bp_u_knee = glGetUniformLocation(bp, "u_knee")

        bl = self.blur_prog
        self.bl_u_texture = glGetUniformLocation(bl, "u_texture")
        self.bl_u_direction = glGetUniformLocation(bl, "u_direction")

        cp = self.composite_prog
        self.cp_u_hdr = glGetUniformLocation(cp, "u_hdr_texture")
        self.cp_u_bloom = glGetUniformLocation(cp, "u_bloom_texture")
        self.cp_u_ao = glGetUniformLocation(cp, "u_ao_texture")
        self.cp_u_exposure = glGetUniformLocation(cp, "u_exposure")
        self.cp_u_bloom_strength = glGetUniformLocation(cp, "u_bloom_strength")
        self.cp_u_ao_strength = glGetUniformLocation(cp, "u_ao_strength")

        fx = self.fxaa_prog
        self.fx_u_texture = glGetUniformLocation(fx, "u_texture")
        self.fx_u_texel_size = glGetUniformLocation(fx, "u_texel_size")

        u = self.ui_prog
        self.ui_u_texture = glGetUniformLocation(u, "u_texture")
        self.ui_u_color = glGetUniformLocation(u, "u_color")

    def _ensure_targets(self, width: int, height: int):
        expected_shadow = 2048 if self.quality == "high" else 1024
        if self.shadow_target is None or self.shadow_size != expected_shadow:
            if self.shadow_target:
                self.shadow_target.delete()
            self.shadow_size = expected_shadow
            self.shadow_target = RenderTarget(expected_shadow, expected_shadow, [], depth_texture=True, shadow_compare=True)

        if width <= 0 or height <= 0:
            return
        # Low quality renders the 3D scene at a reduced internal resolution and the
        # final FXAA pass upscales it to the window. Pixel shading dominates frame time.
        scale = RENDER_SCALE.get(self.quality, 1.0)
        internal = (max(1, int(width * scale)), max(1, int(height * scale)))
        if self.hdr_target and self.width == width and self.height == height and                 getattr(self, "internal_size", None) == internal:
            return

        self.width = width
        self.height = height
        self.internal_size = internal
        width, height = internal

        # Clean old targets
        if self.hdr_target:
            self.hdr_target.delete()
        if self.ssao_target:
            self.ssao_target.delete()
        if self.ssao_blur_target:
            self.ssao_blur_target.delete()
        for t in self.bloom_targets_a + self.bloom_targets_b:
            t.delete()
        self.bloom_targets_a = []
        self.bloom_targets_b = []
        if self.ldr_target:
            self.ldr_target.delete()

        # 1. Main HDR target (RGBA16F with depth texture)
        self.hdr_target = RenderTarget(width, height, [GL_RGBA16F], depth_texture=True)

        # 2. SSAO half-resolution targets (R8)
        sw = max(1, width // 2)
        sh = max(1, height // 2)
        self.ssao_target = RenderTarget(sw, sh, [GL_RGBA8], depth_texture=False)
        self.ssao_blur_target = RenderTarget(sw, sh, [GL_RGBA8], depth_texture=False)

        # 3. Bloom 5-level half-resolution downsample chain
        bw = max(1, width // 2)
        bh = max(1, height // 2)
        for i in range(5):
            w = max(1, bw >> i)
            h = max(1, bh >> i)
            self.bloom_targets_a.append(RenderTarget(w, h, [GL_RGBA16F], depth_texture=False))
            self.bloom_targets_b.append(RenderTarget(w, h, [GL_RGBA16F], depth_texture=False))

        # 4. LDR target for ACES composite output
        self.ldr_target = RenderTarget(width, height, [GL_RGBA8], depth_texture=False)

    def resize(self, width: int, height: int):
        if width > 0 and height > 0:
            self._ensure_targets(width, height)

    def set_quality(self, quality: str):
        if quality not in ("low", "high"):
            raise ValueError(f"Invalid quality mode: '{quality}'. Must be 'low' or 'high'.")
        if quality != self.quality:
            self.quality = quality
            expected_shadow = 2048 if self.quality == "high" else 1024
            if self.shadow_target and self.shadow_size != expected_shadow:
                self.shadow_target.delete()
                self.shadow_target = None
                self.shadow_size = expected_shadow
            dust_count = 400 if self.quality == "high" else 150
            if hasattr(self, "dust_system") and self.dust_system:
                self.dust_system = DustSystem(dust_count, self.dust_system.volumes)

    def diagnostics(self) -> Dict[str, Any]:
        count = 0
        if self.shadow_target and self.shadow_target.depth_texture: count += 1
        if self.hdr_target:
            count += len(self.hdr_target.color_textures)
            if self.hdr_target.depth_texture: count += 1
        if self.ssao_target: count += len(self.ssao_target.color_textures)
        if self.ssao_blur_target: count += len(self.ssao_blur_target.color_textures)
        for t in self.bloom_targets_a + self.bloom_targets_b:
            count += len(t.color_textures)
        if self.ldr_target: count += len(self.ldr_target.color_textures)

        return {
            "quality": self.quality,
            "scene_program": self.scene_prog,
            "shadow_program": self.shadow_prog,
            "ssao_program": self.ssao_prog,
            "brightpass_program": self.brightpass_prog,
            "blur_program": self.blur_prog,
            "composite_program": self.composite_prog,
            "fxaa_program": self.fxaa_prog,
            "ui_program": self.ui_prog,
            "godray_program": self.godray_prog,
            "dust_program": self.dust_prog,
            "dust_particles": len(self.dust_system.particles) if hasattr(self, "dust_system") else 0,
            "fbo_complete": bool(self.hdr_target and self.hdr_target.fbo and self.shadow_target and self.shadow_target.fbo),
            "shadow_map_size": self.shadow_size,
            "texture_count": count,
        }

    def _draw_fullscreen_quad(self):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        ortho = mat_ortho(0.0, 1.0, 0.0, 1.0, -1.0, 1.0)
        glLoadMatrixf(ortho)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glBegin(GL_QUADS)
        glTexCoord2f(0.0, 0.0)
        glVertex2f(0.0, 0.0)
        glTexCoord2f(1.0, 0.0)
        glVertex2f(1.0, 0.0)
        glTexCoord2f(1.0, 1.0)
        glVertex2f(1.0, 1.0)
        glTexCoord2f(0.0, 1.0)
        glVertex2f(0.0, 1.0)
        glEnd()

        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def render(self, frame: FrameState) -> None:
        if frame.width <= 0 or frame.height <= 0:
            return

        self._ensure_targets(frame.width, frame.height)

        room = self.scene.r
        sun_dir = sun_direction(frame.lighting_preset, room)
        W, L, H = room["width"], room["depth"], room["height"]
        V = room.get("vestibule_depth", 4.01)
        light_view, light_proj = sun_light_matrices(sun_dir, (0.0, W, 0.0, L + V, 0.0, H))
        light_space_matrix = mat_mul(light_proj, light_view)

        # -------------------------------------------------------------
        # 0. Shadow Pass -> Sun Depth Map (Front-Face Culling)
        # -------------------------------------------------------------
        self.shadow_target.bind()
        glClear(GL_DEPTH_BUFFER_BIT)
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)

        # Front-face culling eliminates shadow acne on backfaces
        glEnable(GL_CULL_FACE)
        glCullFace(GL_FRONT)

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glLoadMatrixf(light_proj)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glLoadMatrixf(light_view)

        glUseProgram(self.shadow_prog)
        self.scene.draw_opaque(frame)
        glUseProgram(0)

        glCullFace(GL_BACK)
        glDisable(GL_CULL_FACE)

        # -------------------------------------------------------------
        # 1. Scene Pass -> HDR Framebuffer
        # -------------------------------------------------------------
        self.hdr_target.bind()
        glClearColor(0.20, 0.27, 0.32, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        proj = mat_perspective(frame.fov, frame.width / frame.height, 0.08, 280.0)
        glLoadMatrixf(proj)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        view = mat_look_at(frame.eye, frame.target, (0.0, 0.0, 1.0))
        glLoadMatrixf(view)

        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # Depth pre-pass: lay down opaque depth with a trivial shader so the costly
        # lighting shader below runs only once per visible pixel (no overdraw).
        if self.depth_prepass:
            glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_FALSE)
            glUseProgram(self.shadow_prog)
            self.scene.draw_opaque(frame)
            glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE)

        glUseProgram(self.scene_prog)
        glActiveTexture(GL_TEXTURE0)
        glUniform1i(self.u_texture, 0)

        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self.shadow_target.depth_texture)
        glUniform1i(self.u_shadow_map, 1)
        glActiveTexture(GL_TEXTURE0)

        glUniformMatrix4fv(self.u_light_space_matrix, 1, GL_FALSE, light_space_matrix)
        glUniform1f(self.u_shadow_map_size, float(self.shadow_size))

        l_state = frame.lighting
        softness = l_state.shadow_softness if l_state else 0.40
        glUniform1f(self.u_shadow_softness, softness)

        glUniform3f(self.u_eye, *frame.eye)
        glUniform3f(self.u_sun_dir, *sun_dir)
        glUniform1i(self.u_is_skybox, 0)
        glUniform1f(self.u_time, float(getattr(frame, "time", 0.0)))

        l_state = frame.lighting
        sun_factor = l_state.sun_intensity if l_state else 1.0
        int_factor = l_state.interior_intensity if (l_state and frame.interior_lights) else (1.0 if frame.interior_lights else 0.0)
        amb_val = l_state.ambient_brightness if l_state else 0.40
        exposure_ev = l_state.exposure_ev if l_state else 0.0
        bloom_str = l_state.bloom_strength if l_state else 0.35

        is_sunset = (frame.lighting_preset == "sunset")
        if is_sunset:
            glUniform3f(self.u_sun_color, 1.0, 0.56, 0.22)
            glUniform1f(self.u_sun_intensity, 3.2 * sun_factor)
            glUniform3f(self.u_hemi_sky, 0.34, 0.26, 0.30)
            glUniform3f(self.u_hemi_ground, 0.24, 0.19, 0.17)
        else:
            # Heartwarming nostalgic golden-ivory morning/afternoon sun
            glUniform3f(self.u_sun_color, 0.98, 0.91, 0.78)
            glUniform1f(self.u_sun_intensity, 2.6 * sun_factor)
            glUniform3f(self.u_hemi_sky, 0.46, 0.50, 0.54)
            glUniform3f(self.u_hemi_ground, 0.31, 0.29, 0.26)

        ambient_scale = (amb_val / 0.40) * (0.85 if is_sunset else 0.95)
        glUniform1f(self.u_ambient_scale, ambient_scale)

        lamp_positions = self.scene.luminaire_positions
        for i in range(13):
            if i < len(lamp_positions):
                pos = lamp_positions[i]
                glUniform3f(self.u_lamp_pos[i], pos[0], pos[1], pos[2] - 0.12)
            else:
                glUniform3f(self.u_lamp_pos[i], 0.0, 0.0, -100.0)

        glUniform3f(self.u_lamp_color, 0.95, 0.97, 0.99)
        glUniform1f(self.u_lamp_intensity, 1.6 * int_factor)

        # 1.1 Opaque geometry pass
        glUniform1f(self.u_emissive_factor, 0.0)
        self.scene.draw_opaque(frame)

        # 1.2 Emissive geometry pass (fluorescents, glows)
        glUniform1f(self.u_emissive_factor, 2.5 * int_factor if frame.interior_lights else 0.0)
        self.scene.draw_emissive(frame)

        # 1.3 Transparent geometry pass
        glUniform1f(self.u_emissive_factor, 0.0)
        self.scene.draw_transparent(frame)

        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)
        glUseProgram(0)

        # 1.4 Atmosphere pass (Volumetric god rays & drifting dust particles)
        self._draw_atmosphere(frame)

        # -------------------------------------------------------------
        # 1.5 SSAO Pass (High quality only)
        # -------------------------------------------------------------
        if self.quality == "high":
            # SSAO generation
            self.ssao_target.bind()
            glClearColor(1.0, 1.0, 1.0, 1.0)
            glClear(GL_COLOR_BUFFER_BIT)
            glUseProgram(self.ssao_prog)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.hdr_target.depth_texture)
            glUniform1i(self.ssao_u_depth, 0)
            inv_proj = mat_inverse(proj)
            glUniformMatrix4fv(self.ssao_u_inv_proj, 1, GL_FALSE, inv_proj)
            glUniformMatrix4fv(self.ssao_u_proj, 1, GL_FALSE, proj)
            glUniform2f(self.ssao_u_resolution, float(self.ssao_target.width), float(self.ssao_target.height))
            self._draw_fullscreen_quad()

            # SSAO 5x5 blur
            self.ssao_blur_target.bind()
            glClearColor(1.0, 1.0, 1.0, 1.0)
            glClear(GL_COLOR_BUFFER_BIT)
            glUseProgram(self.ssao_blur_prog)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.ssao_target.color_textures[0])
            glUniform1i(self.sb_u_ssao, 0)
            glUniform2f(self.sb_u_texel_size, 1.0 / self.ssao_target.width, 1.0 / self.ssao_target.height)
            self._draw_fullscreen_quad()

        # -------------------------------------------------------------
        # 2. Bloom Chain Pass
        # -------------------------------------------------------------
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)

        # 2.1 Bright-pass extraction: HDR -> Bloom A[0]
        self.bloom_targets_a[0].bind()
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)
        glUseProgram(self.brightpass_prog)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.hdr_target.color_textures[0])
        glUniform1i(self.bp_u_hdr, 0)
        glUniform1f(self.bp_u_threshold, 1.0)
        glUniform1f(self.bp_u_knee, 0.5)
        self._draw_fullscreen_quad()

        # 2.2 Downsample cascade across bloom levels (High: 5 levels, Low: 3 levels)
        levels = 5 if self.quality == "high" else 3
        for i in range(1, levels):
            self.bloom_targets_a[i].bind()
            glClearColor(0.0, 0.0, 0.0, 1.0)
            glClear(GL_COLOR_BUFFER_BIT)
            # Use blur shader with zero offset to downsample
            glUseProgram(self.blur_prog)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.bloom_targets_a[i - 1].color_textures[0])
            glUniform1i(self.bl_u_texture, 0)
            glUniform2f(self.bl_u_direction, 0.0, 0.0)
            self._draw_fullscreen_quad()

        # 2.3 Two-pass separable Gaussian blur per level (A -> B horizontal, B -> A vertical)
        glUseProgram(self.blur_prog)
        for i in range(levels):
            target_a = self.bloom_targets_a[i]
            target_b = self.bloom_targets_b[i]

            # Horizontal pass: A -> B
            target_b.bind()
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, target_a.color_textures[0])
            glUniform1i(self.bl_u_texture, 0)
            glUniform2f(self.bl_u_direction, 1.2 / target_a.width, 0.0)
            self._draw_fullscreen_quad()

            # Vertical pass: B -> A
            target_a.bind()
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, target_b.color_textures[0])
            glUniform1i(self.bl_u_texture, 0)
            glUniform2f(self.bl_u_direction, 0.0, 1.2 / target_a.height)
            self._draw_fullscreen_quad()

        # 2.4 Upsample and accumulate from coarsest level back up to level 0
        glEnable(GL_BLEND)
        glBlendFunc(GL_ONE, GL_ONE)
        for i in range(levels - 1, 0, -1):
            self.bloom_targets_a[i - 1].bind()
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.bloom_targets_a[i].color_textures[0])
            glUniform1i(self.bl_u_texture, 0)
            glUniform2f(self.bl_u_direction, 0.0, 0.0)
            self._draw_fullscreen_quad()
        glDisable(GL_BLEND)

        # -------------------------------------------------------------
        # 3. Composite Pass -> LDR Framebuffer
        # -------------------------------------------------------------
        self.ldr_target.bind()
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)
        glUseProgram(self.composite_prog)

        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.hdr_target.color_textures[0])
        glUniform1i(self.cp_u_hdr, 0)

        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self.bloom_targets_a[0].color_textures[0])
        glUniform1i(self.cp_u_bloom, 1)

        glActiveTexture(GL_TEXTURE2)
        if self.quality == "high":
            glBindTexture(GL_TEXTURE_2D, self.ssao_blur_target.color_textures[0])
            glUniform1f(self.cp_u_ao_strength, 1.0)
        else:
            glBindTexture(GL_TEXTURE_2D, 0)
            glUniform1f(self.cp_u_ao_strength, 0.0)
        glUniform1i(self.cp_u_ao, 2)

        glUniform1f(self.cp_u_exposure, exposure_ev)
        glUniform1f(self.cp_u_bloom_strength, bloom_str)
        self._draw_fullscreen_quad()

        glActiveTexture(GL_TEXTURE2)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)

        # -------------------------------------------------------------
        # 4. FXAA Pass -> Default Framebuffer (FBO 0)
        # -------------------------------------------------------------
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glViewport(0, 0, frame.width, frame.height)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glUseProgram(self.fxaa_prog)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.ldr_target.color_textures[0])
        glUniform1i(self.fx_u_texture, 0)
        glUniform2f(self.fx_u_texel_size, 1.0 / self.ldr_target.width, 1.0 / self.ldr_target.height)
        self._draw_fullscreen_quad()

        glBindTexture(GL_TEXTURE_2D, 0)
        glUseProgram(0)

    def draw_ui_quad(self, texture: int, x: float, y: float, w: float, h: float, screen_w: int, screen_h: int) -> None:
        """Draws a textured 2D HUD rectangle using the UI shader."""
        if screen_w <= 0 or screen_h <= 0 or w <= 0 or h <= 0:
            return

        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glUseProgram(self.ui_prog)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, texture)
        glUniform1i(self.ui_u_texture, 0)
        glUniform4f(self.ui_u_color, 1.0, 1.0, 1.0, 1.0)

        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        ortho = mat_ortho(0.0, float(screen_w), float(screen_h), 0.0, -1.0, 1.0)
        glLoadMatrixf(ortho)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glBegin(GL_QUADS)
        glTexCoord2f(0.0, 0.0)
        glVertex2f(x, y)
        glTexCoord2f(1.0, 0.0)
        glVertex2f(x + w, y)
        glTexCoord2f(1.0, 1.0)
        glVertex2f(x + w, y + h)
        glTexCoord2f(0.0, 1.0)
        glVertex2f(x, y + h)
        glEnd()

        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

        glBindTexture(GL_TEXTURE_2D, 0)
        glUseProgram(0)
        glEnable(GL_DEPTH_TEST)

    def _draw_atmosphere(self, frame: FrameState) -> None:
        l_state = frame.lighting
        opacity = l_state.god_rays_opacity if l_state else 0.35
        if opacity <= 0.005 or not frame.god_rays:
            return

        preset = frame.lighting_preset
        if not hasattr(self.scene, "god_rays_lists") or preset not in self.scene.god_rays_lists:
            return

        # Synchronize dust volumes with active preset
        if hasattr(self.scene, "god_ray_volumes") and preset in self.scene.god_ray_volumes:
            vols = self.scene.god_ray_volumes[preset]
            if vols and self.dust_system.volumes != vols:
                self.dust_system.set_volumes(vols)

        dt = frame.time - self.last_time if self.last_time > 0.0 else 0.016
        self.last_time = frame.time
        self.dust_system.update(dt)

        if preset == "sunset":
            beam_color = (1.0, 0.62, 0.24)
        else:
            # Nostalgic heartwarming golden-ivory morning/afternoon sunbeams
            beam_color = (1.0, 0.90, 0.70)

        room = self.scene.r
        sun_dir = sun_direction(preset, room)
        W, L, H = room["width"], room["depth"], room["height"]
        V = room.get("vestibule_depth", 4.01)
        light_view, light_proj = sun_light_matrices(sun_dir, (0.0, W, 0.0, L + V, 0.0, H))
        light_space_matrix = mat_mul(light_proj, light_view)

        glDepthMask(GL_FALSE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)

        if self.shadow_target and self.shadow_target.depth_texture:
            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, self.shadow_target.depth_texture)
            glActiveTexture(GL_TEXTURE0)

        # 1. Volumetric God Rays
        glUseProgram(self.godray_prog)
        glUniform3f(self.gr_u_color, *beam_color)
        glUniform1f(self.gr_u_opacity, opacity)
        glUniform3f(self.gr_u_eye, *frame.eye)
        glUniform1f(self.gr_u_time, frame.time)
        glUniform3f(self.gr_u_sun_dir, *sun_dir)
        glUniform1i(self.gr_u_shadow_map, 1)
        glUniformMatrix4fv(self.gr_u_light_space_matrix, 1, GL_FALSE, light_space_matrix)

        glCallList(self.scene.god_rays_lists[preset])

        # 2. Drifting Dust Particles
        glUseProgram(self.dust_prog)
        glUniform3f(self.dust_u_color, *beam_color)
        glUniform1f(self.dust_u_opacity, opacity)
        glUniform3f(self.dust_u_eye, *frame.eye)
        glUniform1i(self.dust_u_shadow_map, 1)
        glUniformMatrix4fv(self.dust_u_light_space_matrix, 1, GL_FALSE, light_space_matrix)

        self.dust_system.draw(frame)

        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)
        glUseProgram(0)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_TRUE)

