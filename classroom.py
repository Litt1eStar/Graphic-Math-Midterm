"""S13-30612: a photograph/plan-based classroom rendered with real OpenGL.

Run: python classroom.py
The fixed-function OpenGL renderer uses PyOpenGL; GLFW only creates the window
and handles input. Units are meters; Z is up. All geometry is built in code.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path

try:
    import glfw
    from OpenGL.GL import *
    from OpenGL.GLU import gluLookAt, gluPerspective, gluNewQuadric, gluSphere, gluCylinder, gluDisk
    from PIL import Image, ImageDraw, ImageFont
    from surface_materials import make_surface_images
except ImportError as exc:
    print("Missing dependency:", exc)
    print("Install with: python -m pip install -r requirements.txt")
    raise SystemExit(1)

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    r, f = config["room"], config["furniture"]
    for key, value in r.items():
        if not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"room.{key} must be a positive finite number")
    for key in ("rows", "blocks", "tables_per_block", "seats_per_table"):
        if not isinstance(f[key], int) or not 1 <= f[key] <= 20:
            raise ValueError(f"furniture.{key} must be an integer from 1 to 20")
    for key in ("table_width", "table_depth", "table_height", "wall_clearance", "first_row_y", "row_spacing"):
        if not isinstance(f[key], (float, int)) or not math.isfinite(f[key]) or f[key] <= 0:
            raise ValueError(f"furniture.{key} must be a positive finite number")
    if r["vestibule_width"] >= r["width"] or r["door_height"] >= r["height"]:
        raise ValueError("Vestibule width and door height must fit the room")
    if r["door_width"] + .25 >= r["vestibule_width"]:
        raise ValueError("Door width must fit the vestibule end wall")
    if f["blocks"] * f["tables_per_block"] * f["table_width"] >= r["width"] - 2*f["wall_clearance"]:
        raise ValueError("Table blocks do not fit the room width")
    last_y = f["first_row_y"] + (f["rows"] - 1) * f["row_spacing"]
    if last_y + f["table_depth"] / 2 + .8 >= r["depth"]:
        raise ValueError("Last seating row does not fit inside the room")
    lighting = config.setdefault("lighting", {})
    lighting.setdefault("default_preset", "daylight")
    lighting.setdefault("god_rays", True)
    lighting.setdefault("interior_lights", True)
    lighting.setdefault("daylight", {
        "sun_position": [18.0, 6.0, 14.0],
        "sun_diffuse": [0.85, 0.88, 0.90],
        "ambient": [0.42, 0.42, 0.42]
    })
    lighting.setdefault("sunset", {
        "sun_position": [22.0, 4.0, 3.2],
        "sun_diffuse": [1.0, 0.58, 0.20],
        "ambient": [0.18, 0.16, 0.16]
    })
    return config



COLORS = {
    "wall": (.89, .89, .865), "ceiling": (.93, .935, .92),
    "trim": (.22, .26, .27), "metal": (.12, .15, .16),
    "steel": (.48, .52, .54), "chair": (.075, .10, .11),
    "chrome": (.64, .67, .69),
    "wood": (.98, .98, .98), "panel": (.94, .94, .92),
    "wood_edge": (.69, .59, .43), "joint": (.73, .74, .71),
    "screen": (.93, .94, .89), "black": (.035, .055, .065),
    "glass": (.79, .86, .87, .14), "light": (.92, .97, 1.0),
    "door_glass": (.82, .86, .85, .10), "door_metal": (.09, .11, .11),
    "noticeboard": (.38, .055, .065),
    "pipe": (.72, .74, .69), "floor": (.78, .79, .75),
    "ground": (.30, .36, .40), "green": (.25, .42, .30),
    "imac_silver": (.70, .72, .74), "monitor_display": (.16, .24, .28),
    "luminaire_glow": (.92, .97, 1.0, .28),
}


def make_texture(image, repeat=False):
    image = image.convert("RGBA")
    tid = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tid)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT if repeat else GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT if repeat else GL_CLAMP_TO_EDGE)
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, image.width, image.height, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, image.tobytes())
    glGenerateMipmap(GL_TEXTURE_2D)
    return tid


def procedural_textures():
    return {name: make_texture(im.transpose(Image.Transpose.FLIP_TOP_BOTTOM), name not in ("daylight", "sunset"))
            for name, im in make_surface_images().items()}


def draw_box(x, y, z, w, d, h, color, texture=0):
    """Box origin is its minimum corner; outward face normals provide lighting."""
    glColor4f(*color) if len(color) == 4 else glColor3f(*color)
    if texture:
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, texture)
    a, b, c = x + w, y + d, z + h
    faces = [
        ((0, 0, 1), ((x, y, c), (a, y, c), (a, b, c), (x, b, c))),
        ((0, 0, -1), ((x, b, z), (a, b, z), (a, y, z), (x, y, z))),
        ((0, -1, 0), ((x, y, z), (a, y, z), (a, y, c), (x, y, c))),
        ((0, 1, 0), ((a, b, z), (x, b, z), (x, b, c), (a, b, c))),
        ((-1, 0, 0), ((x, b, z), (x, y, z), (x, y, c), (x, b, c))),
        ((1, 0, 0), ((a, y, z), (a, b, z), (a, b, c), (a, y, c))),
    ]
    glBegin(GL_QUADS)
    for normal, verts in faces:
        glNormal3f(*normal)
        for uv, vertex in zip(((0, 0), (1, 0), (1, 1), (0, 1)), verts):
            glTexCoord2f(*uv)
            glVertex3f(*vertex)
    glEnd()
    if texture:
        glDisable(GL_TEXTURE_2D)


@dataclass
class LightingState:
    sun_intensity: float = 1.0
    interior_intensity: float = 1.0
    god_rays_opacity: float = 0.35
    ambient_brightness: float = 0.40

    def set_sun(self, val: float):
        self.sun_intensity = max(0.0, min(2.0, float(val)))

    def set_interior(self, val: float):
        self.interior_intensity = max(0.0, min(2.0, float(val)))

    def set_god_rays(self, val: float):
        self.god_rays_opacity = max(0.0, min(1.0, float(val)))

    def set_ambient(self, val: float):
        self.ambient_brightness = max(0.0, min(1.0, float(val)))

    def scale_color(self, base: tuple, factor: float) -> tuple:
        f = max(0.0, float(factor))
        r = max(0.0, min(1.0, base[0] * f))
        g = max(0.0, min(1.0, base[1] * f))
        b = max(0.0, min(1.0, base[2] * f))
        a = base[3] if len(base) > 3 else 1.0
        return (r, g, b, a)

    def nudge_slider(self, index: int, delta: float):
        if index == 0:
            self.set_sun(self.sun_intensity + delta)
        elif index == 1:
            self.set_interior(self.interior_intensity + delta)
        elif index == 2:
            self.set_god_rays(self.god_rays_opacity + delta)
        elif index == 3:
            self.set_ambient(self.ambient_brightness + delta)


@dataclass
class Part:
    group: str
    dims: tuple
    color: tuple
    texture: str = ""
    boundary: str = ""
    tilt_x: float = 0
    angle_z: float = 0
    pivot: tuple | None = None
    mesh: tuple = ()


class Classroom:
    def __init__(self, config):
        self.config = config
        self.r = config["room"]
        self.parts = []
        self.lists = {}
        self.textures = procedural_textures()
        self.quadric = gluNewQuadric()
        self.luminaire_positions = []
        self.build()
        self.compile()


    def box(self, group, x, y, z, w, d, h, material="wall", texture="", boundary="", tilt_x=0, angle_z=0, pivot=None):
        if min(w, d, h) <= 0:
            raise ValueError(f"Invalid box dimensions in {group}: {(w, d, h)}")
        self.parts.append(Part(group, (x, y, z, w, d, h), COLORS[material], texture, boundary, tilt_x, angle_z, pivot))

    def mesh_part(self, group, faces, material, boundary=""):
        """Store normals and polygon vertices, with bounds for layout checks."""
        vertices = [v for _, face in faces for v in face]
        low = tuple(min(v[i] for v in vertices) for i in range(3))
        high = tuple(max(v[i] for v in vertices) for i in range(3))
        self.parts.append(Part(group, low+tuple(high[i]-low[i] for i in range(3)),
                               COLORS[material], boundary=boundary, mesh=tuple(faces)))

    def tube(self, group, points, radius=.012, material="chrome", boundary=""):
        """Round steel tubing following a bent centerline; no square chair legs."""
        # Round each bend with a quadratic arc before sweeping a circular section.
        path = [points[0]]
        for a, b, c in zip(points, points[1:], points[2:]):
            trim = min(.055, math.dist(a, b)*.24, math.dist(b, c)*.24)
            u, v = normalize(tuple(a[i]-b[i] for i in range(3))), normalize(tuple(c[i]-b[i] for i in range(3)))
            entry = tuple(b[i]+u[i]*trim for i in range(3))
            leave = tuple(b[i]+v[i]*trim for i in range(3))
            for j in range(7):
                t = j/6
                path.append(tuple((1-t)**2*entry[i]+2*(1-t)*t*b[i]+t*t*leave[i] for i in range(3)))
        path.append(points[-1])
        rings = []
        for j, p in enumerate(path):
            before, after = path[max(0, j-1)], path[min(len(path)-1, j+1)]
            tangent = normalize(tuple(after[i]-before[i] for i in range(3)))
            ref = (1, 0, 0) if abs(tangent[0]) < .9 else (0, 1, 0)
            u = normalize((tangent[1]*ref[2]-tangent[2]*ref[1], tangent[2]*ref[0]-tangent[0]*ref[2], tangent[0]*ref[1]-tangent[1]*ref[0]))
            v = (tangent[1]*u[2]-tangent[2]*u[1], tangent[2]*u[0]-tangent[0]*u[2], tangent[0]*u[1]-tangent[1]*u[0])
            rings.append([tuple(p[i]+radius*(math.cos(k*math.tau/12)*u[i]+math.sin(k*math.tau/12)*v[i]) for i in range(3)) for k in range(12)])
        faces = []
        for j in range(len(rings)-1):
            for k in range(12):
                verts = (rings[j][k], rings[j][(k+1)%12], rings[j+1][(k+1)%12], rings[j+1][k])
                normal = normalize(tuple((verts[0][i]+verts[1][i])/2-path[j][i] for i in range(3)))
                faces.append((normal, verts))
        self.mesh_part(group, faces, material, boundary)

    def cushion(self, group, x, y, z, width, length, thickness, vertical=False):
        """Rounded padded panel with a bevelled rim; back leans away from sitter."""
        radius = .055
        perimeter = []
        for cx, cy, start in ((width/2-radius, length/2-radius, 0),
                              (-width/2+radius, length/2-radius, 90),
                              (-width/2+radius, -length/2+radius, 180),
                              (width/2-radius, -length/2+radius, 270)):
            for j in range(7):
                a = math.radians(start+j*15)
                perimeter.append((cx+radius*math.cos(a), cy+radius*math.sin(a)))
        def transform(u, v, depth):
            if vertical:
                return (x+u, y+.13*v-depth, z+v)
            return (x+u, y+v, z+depth)
        rings = [[transform(u*scale, v*scale, depth) for u,v in perimeter]
                 for scale,depth in ((.95, 0), (1, thickness*.3), (1, thickness*.7), (.95, thickness))]
        faces = []
        def face(vertices):
            a,b,c = vertices[:3]
            u,v = tuple(b[i]-a[i] for i in range(3)), tuple(c[i]-a[i] for i in range(3))
            normal = normalize((u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]))
            faces.append((normal, tuple(vertices)))
        face(list(reversed(rings[0])))
        face(rings[-1])
        for lower, upper in zip(rings, rings[1:]):
            for k in range(len(perimeter)):
                n = (k+1)%len(perimeter)
                face((lower[k], lower[n], upper[n], upper[k]))
        self.mesh_part(group, faces, "chair")

    def build(self):
        r, f = self.r, self.config["furniture"]
        W, L, H, t = r["width"], r["depth"], r["height"], r["wall_thickness"]
        V, D = r["vestibule_width"], r["vestibule_depth"]
        # Right is defined while standing inside and facing the screen at Y=0.
        # In this coordinate system that side is X=0, opposite the window wall.
        X, T = 0, L + D
        B = X + V
        self.vestibule_x = X
        self.vestibule_right = B
        self.box("ground", -5, -5, -.34, W + 10, T + 10, .12, "ground")
        self.box("floor", 0, 0, -.20, W, L, .20, "floor")
        self.box("floor", X, L, -.20, V, D, .20, "floor")
        # The entry hall is BEHIND the classroom, as clarified by the user.
        # Its X range stays inside the classroom width; it extends only in +Y.
        self.box("walls", -t, -t, 0, W + 2*t, t, H, boundary="front")
        # User-marked front bay on X=0 is a window, not a solid wall.
        bay_end = L/2-r["column_width"]/2
        self.box("walls", -t, 0, 0, t, L, .94, boundary="left")
        self.box("walls", -t, 0, 2.82, t, L, H-2.82, boundary="left")
        self.box("walls", -t, 0, .94, t, .48, 1.88, boundary="left")
        self.box("walls", -t, bay_end, .94, t, L-bay_end, 1.88, boundary="left")
        for z, height in ((.94, .08), (2.33, .045), (2.76, .06)):
            self.box("windows", -.045, .45, z, .10, bay_end-.45, height, "trim", boundary="left")
        for i in range(6):
            self.box("windows", -.045, .48+i*(bay_end-.48)/5-.022, .94, .10, .045, 1.88, "trim", boundary="left")
        self.box("glass", -.022, .48, 1.02, .016, bay_end-.48, 1.74, "glass", boundary="left")
        self.box("walls", B, L, 0, W-B+t, t, H, boundary="back")
        self.box("walls", X-t, L, 0, t, D+t, H, boundary="vestleft")
        self.box("walls", B, L, 0, t, D+t, H, boundary="vestright")
        dw, dh = r["door_width"], r["door_height"]
        self.door_x = B-dw  # Right jamb meets the return wall in the reference.
        self.door_y = T
        self.box("walls", X, T, 0, self.door_x-X, t, H, boundary="entry")
        self.box("walls", self.door_x, T, dh, dw, t, H-dh, boundary="entry")
        # Continuous window band on the exterior wall, as in the photographs.
        sill, win_top = .94, 2.82
        self.box("walls", W, 0, 0, t, L, sill, boundary="right")
        self.box("walls", W, 0, win_top, t, L, H-win_top, boundary="right")
        self.box("walls", W, 0, sill, t, .48, win_top-sill, boundary="right")
        self.box("walls", W, L-.48, sill, t, .48, win_top-sill, boundary="right")
        self.box("windows", W-.055, .45, sill, .10, L-.9, .08, "trim", boundary="right")
        self.box("windows", W-.055, .45, win_top-.06, .10, L-.9, .06, "trim", boundary="right")
        self.box("windows", W-.055, .45, 2.33, .10, L-.9, .045, "trim", boundary="right")
        for i in range(11):
            y = .48 + i*(L-.96)/10
            self.box("windows", W-.05, y-.022, sill, .10, .045, win_top-sill,
                     "trim", boundary="right")
        self.box("glass", W+.006, .48, sill+.08, .016, L-.96, win_top-sill-.14,
                 "glass", boundary="right")
        # Skirting follows every wall, including the vestibule.
        self.box("walls", 0, 0, .01, W, .055, .11, "trim", boundary="front")
        self.box("walls", 0, 0, .01, .055, L, .11, "trim", boundary="left")
        self.box("walls", W-.055, 0, .01, .055, L, .11, "trim", boundary="right")
        self.box("walls", B, L-.055, .01, W-B, .055, .11, "trim", boundary="back")
        self.box("walls", X, L, .01, .055, D, .11, "trim", boundary="vestleft")
        self.box("walls", B-.055, L, .01, .055, D, .11, "trim", boundary="vestright")
        self.box("walls", X, T-.055, .01, self.door_x-X, .055, .11, "trim", boundary="entry")
        # Concrete columns and exposed beams. 0.60 m is a provisional column size.
        c = r["column_width"]
        for x in (0, W-c):
            for y in (0, L/2-c/2, L-c):
                projection = r.get("entry_column_projection", c) if x == 0 and y == L-c else c
                self.box("structure", x, y, 0, projection, c, H)
        # No center column against the rear wall (user's circled correction).
        for y in (0, L/2-.20, L-.40):
            beam_drop = .90 if abs(y-(L/2-.20)) < .01 else .52
            self.box("beams", 0, y, H-beam_drop, W, .40, beam_drop)
        self.box("beams", X, T-.4, H-.52, V, .4, .52)
        self.box("ceiling", 0, 0, H, W, L, .12, "ceiling")
        self.box("ceiling", X, L, H, V, D, .12, "ceiling")
        # Tile grid, fluorescent fixtures and ceiling air conditioning.
        for i in range(1, math.ceil(W/1.2)):
            self.box("ceiling", i*1.2, 0, H-.004, .006, L, .005, "joint")
        for i in range(1, math.ceil(L/.6)):
            self.box("ceiling", 0, i*.6, H-.004, W, .006, .005, "joint")
        for x in (W*.18, W*.50, W*.82):
            for y in (1.55, 4.1, 6.7, 9.3):
                self.fluorescent(x, y, H)
        self.fluorescent(X+V/2, L+D/2, H)
        # Four air conditioners: two on each side wall, as specified by user.
        # Units remain visible when the ceiling is hidden in the overview.
        self.aircon_locations = []
        for side, x in (("right", .07), ("left", W-.85)):
            for cy in (4.1, 9.1):
                self.aircon_locations.append({"side": side, "position": [x, cy-.85, H-.34]})
                group = "aircon_"+side
                # Broad under-ceiling cabinet: underside return grille and a
                # slim supply slot on the room-facing edge, as photographed.
                self.box(group,x,cy-.85,H-.34,.78,1.70,.26,"ceiling")
                self.box(group,x+.06,cy-.76,H-.352,.48,1.52,.014,"trim")
                for i in range(32):
                    self.box(group,x+.065,cy-.75+i*.047,H-.36,.47,.014,.013,"pipe")
                inner_x=x+.78 if side == "right" else x-.012
                self.box(group,inner_x,cy-.76,H-.30,.012,1.52,.10,"trim")
                for zz in (H-.28,H-.245):
                    self.box(group,inner_x-.002,cy-.75,zz,.016,1.50,.010,"steel")
                for yy in (cy-.66,cy+.66):
                    self.box(group,x+.15,yy,H-.08,.42,.07,.08,"steel")
                self.box(group,x+.59,cy+.54,H-.353,.10,.09,.015,"pipe")
        # Front wood panel, projection screen and teaching displays.
        self.box("fixtures", .75, .025, .2, W-1.5, .07, 2.18, "panel", "panel", "front")
        for x in (2.1, 4.2, 6.3, 8.4):
            self.box("fixtures", x, .098, .2, .012, .009, 2.18, "wood_edge", boundary="front")
        sx = W*.49
        self.box("fixtures", sx-1.53, .14, 1.07, 3.06, .09, 1.85, "black", boundary="front")
        self.box("fixtures", sx-1.45, .238, 1.14, 2.90, .012, 1.69, "screen", boundary="front")
        self.box("fixtures", sx-1.60, .12, 2.92, 3.20, .16, .10, "steel", boundary="front")
        # Large RIGHT front TV on a floor stand, facing the student seating.
        self.front_tv_positions = [[.85, .74, .83]]
        self.front_tv_dimensions = [2.50, .16, 1.44]
        for x, y, z in self.front_tv_positions:
            tw, td, th = self.front_tv_dimensions
            self.box("front_tv", x, y, z, tw, td, th, "trim")
            self.box("front_tv", x+.055, y+td+.003, z+.055, tw-.11, .01, th-.11, "black")
            for support_x in (x+tw*.25, x+tw*.75):
                self.box("front_tv_stand", support_x-.12, y-.30, .012, .24, .78, .055, "metal")
                self.box("front_tv_stand", support_x-.038, y+.012, .067, .076, .076, 1.10, "steel")
            self.box("front_tv_stand", x+tw*.25, y+.012, .45, tw*.50, .076, .075, "metal")
        # Beam-mounted screens visible in the reference photograph. Their
        # brackets anchor to real beam faces, and the screens tilt downwards.
        self.overhead_tv_locations = [
            {"x": 2.55, "y": L/2+.24, "z": 2.45, "width": 1.30, "height": .74, "beam_y": L/2-.20},
            {"x": W-3.85, "y": L/2+.24, "z": 2.45, "width": 1.30, "height": .74, "beam_y": L/2-.20},
        ]
        for tv in self.overhead_tv_locations:
            tx, ty, tz, tw, th = (tv[k] for k in ("x", "y", "z", "width", "height"))
            pivot = (tx+tw/2, ty+.05, tz+th/2)
            self.box("overhead_tv", tx, ty, tz, tw, .10, th, "trim", tilt_x=-10, pivot=pivot)
            self.box("overhead_tv", tx+.04, ty+.103, tz+.04, tw-.08, .008, th-.08, "black", tilt_x=-10, pivot=pivot)
            # Wall plate overlaps the deepened beam; arms reach the TV's back
            # at its rotation pivot, with vertical VESA rails on the cabinet.
            mount_z = tz+th/2
            for bx in (tx+tw*.32, tx+tw*.68):
                self.box("overhead_tv_mount", bx-.055, tv["beam_y"]+.37, mount_z-.19, .11, .07, .42, "steel")
                self.box("overhead_tv_mount", bx-.028, tv["beam_y"]+.40, mount_z-.028, .056, ty-tv["beam_y"]-.35, .056, "metal")
                self.box("overhead_tv_mount", bx-.038, ty-.028, mount_z-.22, .076, .05, .44, "steel", tilt_x=-10, pivot=pivot)
        # Projector and surface-mounted cable conduits; the speakers are removed.
        self.box("ceiling", W*.50-.03, 4.8, H-.58, .06, .06, .58, "metal")
        self.box("ceiling", W*.50-.22, 4.6, H-.72, .44, .35, .18, "ceiling")
        self.electrical_details(W, L, H, c)
        self.tube("conduits", [(X+.045,L+.12,3.03),(X+.045,T-.12,3.03),
                              (self.door_x-.18,T-.12,3.03),(self.door_x-.18,T-.12,1.70),
                              (self.door_x-.18,T-.055,1.70)],
                  .013, "pipe", "vestleft")
        # Student desk blocks; every table and chair is explicit OpenGL geometry.
        block_width = f["tables_per_block"]*f["table_width"]
        self.seating_layout = []
        for row in range(f["rows"]):
            y = f["first_row_y"] + row*f["row_spacing"]
            # Bring outer blocks to the wall/skirting. Where a column overlaps
            # the table-and-chair footprint, place that row against its face.
            margin = f["wall_clearance"]
            row_front, row_back = y-f["table_depth"]/2, y+f["table_depth"]/2+.59
            if any(row_front < cy+c and row_back > cy for cy in (0, L/2-c/2, L-c)):
                margin = max(margin, c+.025)
            for block in range(f["blocks"]):
                x = (W-block_width)/2 if f["blocks"] == 1 else margin+block*(W-2*margin-block_width)/(f["blocks"]-1)
                layout = {"row": row, "block": block, "tables": [], "chairs": []}
                for table in range(f["tables_per_block"]):
                    tx = x+table*f["table_width"]
                    self.table(tx, y-f["table_depth"]/2, f["table_width"], f["table_depth"], f["table_height"], "student_tables")
                    layout["tables"].append([tx, y-f["table_depth"]/2, f["table_width"], f["table_depth"]])
                    for seat in range(f["seats_per_table"]):
                        cx = tx+(seat+.5)*f["table_width"]/f["seats_per_table"]
                        self.chair(cx, y+f["table_depth"]/2+.37, "student_chairs")
                        layout["chairs"].append([cx, y+f["table_depth"]/2+.37])
                    if table > 0:
                        # A thin joint makes the two flush table tops distinguishable.
                        self.box("student_tables", tx-.003, y-f["table_depth"]/2, f["table_height"]+.001,
                                 .004, f["table_depth"], .002, "wood_edge")
                self.seating_layout.append(layout)
        # Longer computer desk at the front-left spot shown by the user.
        # The previously invented wooden podium is removed.
        dw, dd, dh = 3.20, .75, f["table_height"]
        dx = W-f["wall_clearance"]-dw
        dy = f["first_row_y"]-f["table_depth"]/2-dd
        self.instructor_desk = [dx, dy, dw, dd, dh]
        self.table(dx, dy, dw, dd, dh, "instructor")
        cx, my = dx+dw/2, dy+.53
        chair_y = dy-.44
        self.instructor_chair_position = [cx, chair_y]
        self.office_chair(cx, chair_y)
        # Silver all-in-one iMac: face points toward the wall (-Y), so the
        # instructor sits behind the desk and faces the classroom (+Y).
        self.monitor_face_normal = [0, -1, 0]
        self.imac_position = [cx, my, dh+.18]
        self.box("imac_base", cx-.17, my-.05, dh+.008, .34, .26, .022, "imac_silver")
        self.box("imac_base", cx-.027, my+.045, dh+.03, .054, .065, .20, "imac_silver")
        self.box("imac_base", cx-.075, my-.012, dh+.20, .15, .12, .03, "imac_silver")
        self.box("imac_body", cx-.37, my-.04, dh+.18, .74, .07, .51, "imac_silver")
        self.box("imac_bezel", cx-.355, my-.051, dh+.28, .71, .011, .395, "black")
        self.box("imac_screen", cx-.325, my-.058, dh+.305, .65, .006, .345, "monitor_display")
        # Magic Keyboard and mouse on the operator's edge; no separate case.
        self.keyboard_position = [cx-.30, dy+.10, dh+.008]
        self.mouse_position = [cx+.40, dy+.13, dh+.008]
        self.box("keyboard", *self.keyboard_position, .60, .17, .018, "imac_silver")
        for kr in range(4):
            for kc in range(16):
                self.box("keyboard", cx-.28+kc*.035, dy+.113+kr*.036, dh+.027,
                         .029, .028, .003, "screen")
        self.box("mouse", *self.mouse_position, .060, .10, .025, "screen")
        # Entry kept clear: the user removed the standalone rear table.
        for z in (1.35,1.57):
            self.box("entry_switches", self.door_x-.26,T-.07,z,.16,.07,.14,"pipe",boundary="entry")
            for offset in (.02,.086):
                self.box("entry_switches",self.door_x-.26+offset,T-.078,z+.026,.052,.013,.085,"ceiling",boundary="entry")
        # Double glazed door: frame is fixed, door leaves rotate with the O key.
        # Read room dimensions here: desk width/height must never size the jambs.
        dw, dh = r["door_width"], r["door_height"]
        for x in (self.door_x, self.door_x+dw-.045):
            self.box("doorframe", x, T-.055, 0, .045, .11, dh, "door_metal")
        for z in (.0, dh-.045, 2.30):
            self.box("doorframe", self.door_x, T-.055, z, dw, .11, .045, "door_metal")
        self.box("doorframe", self.door_x+.045,T-.045,2.16,dw-.09,.09,.14,"pipe")
        self.box("doorframe", self.door_x+dw/2-.022,T-.055,2.345,.044,.11,dh-2.39,"door_metal")
        self.transom_fan(self.door_x+dw*.25,T-.065,(2.345+dh-.045)/2)
        self.reference_details(W,L,H,V,D)

    def reference_details(self,w,length,h,hall_w,hall_d):
        end=length+hall_d
        # Shallow plaster joint at waist height, visible in the hall photos.
        for x,boundary in ((.002,"vestleft"),(hall_w-.008,"vestright")):
            self.box("walls",x,length,1.05,.006,hall_d,.006,"joint",boundary=boundary)
        self.box("walls",hall_w,length-.008,1.05,w-hall_w,.006,.006,"joint",boundary="back")
        # Two flush ceiling access panels on the left of the entry passage.
        for yy,depth in ((length+1.30,1.05),(length+2.55,.65)):
            self.box("ceiling",.25,yy,h-.022,.75,depth,.018,"ceiling")
            for xx in (.25,.99):
                self.box("ceiling",xx,yy,h-.025,.010,depth,.008,"steel")
            for y in (yy,yy+depth-.010):
                self.box("ceiling",.25,y,h-.025,.75,.010,.008,"steel")
            self.box("ceiling",.90,yy+.09,h-.028,.032,.050,.008,"trim")
        # Three exposed PVC routes continue along the passage wall.
        for z in (3.00,3.08,3.16):
            self.tube("conduits",[(.29,length-.10,z),(.045,length+.15,z),
                                  (.045,end-.50,z),(.29,end-.50,z)],.012,"pipe","vestleft")
            for yy in (length+.8,length+2.2,end-.6):
                self.box("conduits",.047,yy-.025,z-.021,.024,.05,.042,"pipe",boundary="vestleft")
        # Thin cable bends over the entry beam and reaches the CCTV mounting base.
        self.tube("ceiling",[(.045,end-.62,h-.04),(.28,end-.62,h-.04),
                              (.28,end-.43,h-.04),(.28,end-.43,h-.55),
                              (.28,end-.27,h-.55)],.009,"pipe")
        # Light exterior context makes the glazing read as clear glass. These
        # backdrop planes are illustrative scenery, not measured architecture.
        for x,y,depth,boundary in ((w+.45,.48,length-.96,"right"),
                                    (-.48,.48,length/2-.78,"left")):
            self.box("daylight",x,y,.90,.015,depth,2.05,"wood","daylight",boundary)
        self.box("outside_entry",0,end+.10,-.025,hall_w,2.45,.025,"floor","floor","entry")
        self.box("outside_entry",0,end+2.55,0,hall_w,.10,h,"wall",boundary="entry")
        self.box("outside_entry",.35,end+2.51,1.10,1.75,.035,1.0,"noticeboard",boundary="entry")
        for row in range(3):
            for col in range(5):
                self.box("outside_entry",.58+col*.26,end+2.495,1.28+row*.23,.14,.012,.13,"screen",boundary="entry")

    def fluorescent(self, x, y, h):
        self.luminaire_positions.append((x, y, h))
        self.box("ceiling",x-.105,y-.66,h-.075,.21,1.32,.055,"ceiling")
        for side in (-1,1):
            self.box("ceiling",x+side*.10-.012,y-.65,h-.10,.024,1.30,.05,"steel")
        for dx in (-.055,.055):
            self.tube("lamps",[(x+dx,y-.59,h-.122),(x+dx,y+.59,h-.122)],.014,"light")
            for yy in (-.615,.615):
                self.box("ceiling",x+dx-.023,y+yy-.022,h-.145,.046,.044,.060,"ceiling")
        self.box("ceiling",x-.033,y-.06,h-.10,.066,.12,.035,"pipe")
        self.tube("ceiling",[(x+.11,y,h-.04),(x+.20,y,h-.04),
                             (x+.20,y+.74,h-.04)],.008,"pipe")
        self.box("luminaire_glow",x-.115,y-.63,h-.138,.23,1.26,.065,"luminaire_glow")


    def electrical_details(self, w, length, h, column):
        for side in (0,1):
            boundary = "left" if side == 0 else "right"
            def wall_x(value): return value if side == 0 else w-value
            rear_projection = self.r.get("entry_column_projection", column) if side == 0 else column
            # Three PVC conduits wrap around the projecting concrete columns.
            for z in (3.00,3.08,3.16):
                points=[(wall_x(column+.045),.045,z),(wall_x(column+.045),column+.10,z),
                        (wall_x(.045),column+.10,z),(wall_x(.045),length/2-column/2-.10,z),
                        (wall_x(column+.045),length/2-column/2-.10,z),
                        (wall_x(column+.045),length/2+column/2+.10,z),
                        (wall_x(.045),length/2+column/2+.10,z),
                        (wall_x(.045),length-column-.10,z),(wall_x(rear_projection+.045),length-column-.10,z),
                        (wall_x(rear_projection+.045),length-.08,z)]
                self.tube("conduits",points,.012,"pipe",boundary)
                for yy in (1.2,2.6,4.7,7.1,8.3,10.5):
                    self.box("conduits",wall_x(.065)-.007,yy-.023,z-.021,.014,.046,.042,"steel",boundary=boundary)
            # Marked right-side control group moves from the middle column to
            # the solid rear wall bay, with one remote centered below the breaker.
            cy=length/2+.95 if side == 0 else length/2
            lift=.40 if side == 0 else 0
            inset=0 if side == 0 else column
            face=wall_x(inset)
            def device(group, yy, zz, width, height, depth, material, offset=0):
                xx=face+offset if side == 0 else face-offset-depth
                self.box(group,xx,yy,zz+lift,depth,width,height,material)
            device("breaker",cy-.13,1.52,.26,.30,.085,"pipe",.006)
            device("breaker",cy-.105,1.55,.21,.24,.013,"ceiling",.092)
            device("breaker",cy-.055,1.62,.11,.11,.009,"trim",.106)
            device("breaker",cy-.018,1.65,.036,.065,.025,"black",.116)
            self.tube("conduits",[(wall_x(inset+.045),cy,3.00),(wall_x(inset+.045),cy,1.82+lift)],.013,"pipe")
            for zz in ((2.35,2.60,2.85) if side == 0 else (1.98,2.40,2.82)):
                device("conduits",cy-.024,zz-lift,.048,.028,.018,"steel",.04)
            for yy in ((cy-.05,) if side == 0 else (cy-.16,cy+.04)):
                device("remote_holder",yy,1.18,.10,.19,.025,"pipe",.01)
                device("remote",yy+.012,1.21,.076,.20,.022,"ceiling",.035)
                device("remote_display",yy+.025,1.34,.05,.05,.004,"monitor_display",.058)
                for row in range(3):
                    for col in range(2):
                        device("remote_buttons",yy+.026+col*.027,1.27-row*.018,.014,.010,.005,"trim",.058)
                device("remote_holder",yy,1.18,.10,.065,.027,"pipe",.060)
            # Keep the existing low outlet at the column, separate from controls.
            cy,face=length/2,wall_x(column)
            lift=0
            device("outlets",cy-.075,.34,.15,.09,.025,"pipe",.008)
            for yy in (cy-.040,cy+.015):
                device("outlets",yy,.365,.008,.032,.003,"black",.035)
        # Ceiling branches with a drop around the deep middle beam.
        for x in (w*.18,w*.50,w*.82):
            self.tube("ceiling",[(x+.20,.7,h-.035),(x+.20,length/2-.30,h-.035),
                                 (x+.20,length/2-.30,h-.94),(x+.20,length/2+.30,h-.94),
                                 (x+.20,length/2+.30,h-.035),(x+.20,10.3,h-.035)],.009,"pipe")
        for z in (3.00,3.08,3.16):
            self.tube("conduits",[(column+.04,.045,z),(w-column-.04,.045,z)],.012,"pipe","front")

    def transom_fan(self, x, y, z):
        faces=[]
        for k in range(40):
            a,b=k*math.tau/40,(k+1)*math.tau/40
            faces.append(((0,-1,0),tuple((x+r*math.cos(t),y,z+r*math.sin(t)) for r,t in ((.135,a),(.135,b),(.108,b),(.108,a)))))
        for k in range(5):
            a=k*math.tau/5
            faces.append(((0,-1,0),tuple((x+r*math.cos(a+t),y-.012,z+r*math.sin(a+t)) for r,t in ((.018,0),(.10,.10),(.10,.58),(.035,.80)))))
        self.mesh_part("door_fan",faces,"door_metal")
        self.box("door_fan",x-.023,y-.027,z-.023,.046,.035,.046,"steel")
        self.tube("door_fan",[(x,y,z-.12),(x,y,z-.22),(x+.3,y,z-.29)],.003,"black")

    def table(self, x, y, w, d, h, group="furniture"):
        self.box(group, x, y, h-.028, w, d, .028, "wood", "wood")
        self.box(group, x+.035, y+.035, h-.078, w-.07, .035, .05, "metal")
        self.box(group, x+.035, y+d-.07, h-.078, w-.07, .035, .05, "metal")
        for dx in (.06, w-.105):
            for dy in (.045, d-.085):
                self.box(group, x+dx, y+dy, .02, .045, .045, h-.07, "metal")
        for dx in (.06, w-.105):
            self.box(group, x+dx, y+.065, .17, .042, d-.13, .042, "metal")

    def chair(self, x, y, group="furniture"):
        # Side profile from the close-up: near-vertical front leg, sloping rear
        # leg and rounded floor runner form a closed trapezoid under the seat.
        self.cushion(group, x, y-.025, .425, .45, .43, .052)
        for sx in (-1, 1):
            for sy in (-1, 1):
                self.cushion(group, x+sx*.109, y-.025+sy*.104, .470,
                             .216, .205, .017)
        self.cushion(group, x, y+.175, .725, .445, .31, .038, vertical=True)
        for side in (-1, 1):
            xx, foot_x = x+side*.235, x+side*.25
            # One bent tube descends from the back, curves around the rear
            # floor corner and runs forward, then rises beneath the seat FRONT.
            self.tube(group, [(xx,y+.213,.865), (xx,y+.19,.70),
                             (xx,y+.13,.425), (foot_x,y+.32,.028),
                             (foot_x,y-.27,.028), (xx,y-.235,.425),
                             (xx,y+.145,.425)], .010)
            for yy in (-.23, .28):
                self.box(group, foot_x-.016, y+yy-.023, .009, .032, .046, .014, "black")
        # Curved chrome top follows the padded back with a narrow edge reveal.
        self.tube(group, [(x-.235,y+.203,.81),(x-.235,y+.216,.894),
                         (x+.235,y+.216,.894),(x+.235,y+.203,.81)], .010)
        for yy in (-.17, .13):
            self.tube(group, [(x-.235,y+yy,.413),(x+.235,y+yy,.413)], .009)
        # Small silver manufacturer badge visible from behind in the photo.
        self.box(group, x-.027, y+.187, .790, .054, .006, .020, "chrome")
        self.box(group, x-.019, y+.194, .796, .038, .0015, .006, "trim")

    def office_chair(self, x, y):
        """High-back instructor chair facing +Y, with five caster spokes."""
        group = "instructor_chair"
        for angle in range(0, 360, 72):
            a = math.radians(angle)
            bx, by = x+.17*math.cos(a), y+.17*math.sin(a)
            self.box(group, bx-.17, by-.03, .065, .34, .06, .045, "metal", angle_z=angle)
            self.box(group, x+.31*math.cos(a)-.045, y+.31*math.sin(a)-.045, .012,
                     .09, .09, .055, "black")
        self.box(group, x-.035, y-.035, .11, .07, .07, .35, "steel")
        self.cushion(group,x,y,.46,.52,.50,.06)
        self.cushion(group,x,y-.17,.925,.49,.67,.08,vertical=True)
        self.cushion(group,x,y-.175,1.275,.36,.13,.08,vertical=True)
        for side in (-1, 1):
            self.box(group, x+side*.28-.017, y-.04, .52, .034, .034, .14, "steel")
            self.box(group, x+side*.28-.033, y-.20, .65, .066, .43, .035, "chair")

    def compile(self):
        batches = {}
        for p in self.parts:
            batches.setdefault((p.group, p.boundary), []).append(p)
        for key, batch in batches.items():
            lid = glGenLists(1)
            glNewList(lid, GL_COMPILE)
            for part in batch:
                if part.mesh:
                    glColor3f(*part.color)
                    if part.color == COLORS["chrome"]:
                        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (.75, .75, .75, 1))
                        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 72)
                    for normal, vertices in part.mesh:
                        glBegin(GL_POLYGON)
                        glNormal3f(*normal)
                        for vertex in vertices:
                            glVertex3f(*vertex)
                        glEnd()
                    if part.color == COLORS["chrome"]:
                        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (0, 0, 0, 1))
                        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 0)
                elif part.tilt_x or part.angle_z:
                    x, y, z, w, d, h = part.dims
                    px, py, pz = part.pivot or (x+w/2, y+d/2, z+h/2)
                    glPushMatrix(); glTranslatef(px, py, pz)
                    glRotatef(part.angle_z, 0, 0, 1); glRotatef(part.tilt_x, 1, 0, 0)
                    draw_box(x-px, y-py, z-pz, w, d, h, part.color, self.textures.get(part.texture, 0))
                    glPopMatrix()
                else:
                    tex = 0 if part.group == "daylight" else self.textures.get(part.texture, 0)
                    draw_box(*part.dims, part.color, tex)
            glEndList()
            self.lists[key] = lid
        self.floor_list = glGenLists(1)
        glNewList(self.floor_list, GL_COMPILE)
        W, L = self.r["width"], self.r["depth"]
        V, D = self.r["vestibule_width"], self.r["vestibule_depth"]
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.textures["floor"])
        glColor3f(.94, .95, .93)
        glBegin(GL_QUADS)
        glNormal3f(0, 0, 1)
        X, T = self.vestibule_x, L+D
        B = self.vestibule_right
        for x0, y0, x1, y1 in ((0, 0, W, L), (X, L, B, T)):
            for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                glTexCoord2f(x*1.5, y*1.5)
                glVertex3f(x, y, .003)
        glEnd()
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_LIGHTING)
        glColor3f(.67, .69, .67)
        glBegin(GL_LINES)
        for x in range(math.ceil(W)):
            glVertex3f(x, 0, .009); glVertex3f(x, L, .009)
        for y in range(math.ceil(L)):
            glVertex3f(0, y, .009); glVertex3f(W, y, .009)
        for x in range(math.ceil(X), math.ceil(B)):
            glVertex3f(x, L, .009); glVertex3f(x, T, .009)
        for y in range(math.ceil(L), math.ceil(T)):
            glVertex3f(X, y, .009); glVertex3f(B, y, .009)
        glEnd()
        glEnable(GL_LIGHTING)
        glEndList()
        self.contact_list=glGenLists(1)
        glNewList(self.contact_list,GL_COMPILE)
        glDisable(GL_LIGHTING); glDepthMask(GL_FALSE)
        def contact(x,y,rx,ry,opacity):
            glBegin(GL_TRIANGLE_FAN)
            glColor4f(.13,.14,.14,opacity); glVertex3f(x,y,.014)
            for i in range(25):
                a=i*math.tau/24
                glColor4f(.13,.14,.14,0); glVertex3f(x+rx*math.cos(a),y+ry*math.sin(a),.014)
            glEnd()
        for block in self.seating_layout:
            for x,y,w,d in block["tables"]:
                contact(x+w/2,y+d/2,w*.57,d*.85,.15)
                for xx in (x+.08,x+w-.08):
                    for yy in (y+.065,y+d-.065): contact(xx,yy,.065,.065,.27)
            for x,y in block["chairs"]:
                contact(x,y,.34,.39,.15)
                for xx in (x-.25,x+.25): contact(xx,y,.06,.34,.23)
        x,y,w,d,_=self.instructor_desk
        contact(x+w/2,y+d/2,w*.55,d*.75,.16)
        glDepthMask(GL_TRUE); glEnable(GL_LIGHTING)
        glEndList()
        self.god_rays_lists = {
            "daylight": self.build_god_rays("daylight"),
            "sunset": self.build_god_rays("sunset")
        }
        self.interior_pool_list = self.build_interior_light_pools()

    def build_interior_light_pools(self):
        lid = glGenLists(1)
        glNewList(lid, GL_COMPILE)
        glDisable(GL_LIGHTING)
        glDepthMask(GL_FALSE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        for x, y, _ in self.luminaire_positions:
            # Soft radial downward pool on floor
            glBegin(GL_TRIANGLE_FAN)
            glColor4f(0.95, 0.98, 1.0, 0.16)
            glVertex3f(x, y, 0.012)
            for i in range(25):
                a = i * math.tau / 24
                glColor4f(0.95, 0.98, 1.0, 0.0)
                glVertex3f(x + 1.20 * math.cos(a), y + 1.50 * math.sin(a), 0.012)
            glEnd()
            # Also illuminate desk height if overlapping tables
            for block in self.seating_layout:
                for tx, ty, tw, td in block["tables"]:
                    if abs((tx + tw / 2) - x) < tw / 2 + 0.5 and abs((ty + td / 2) - y) < td / 2 + 0.5:
                        glBegin(GL_TRIANGLE_FAN)
                        glColor4f(0.97, 0.99, 1.0, 0.14)
                        glVertex3f(x, y, self.config["furniture"]["table_height"] + 0.002)
                        for i in range(25):
                            a = i * math.tau / 24
                            glColor4f(0.97, 0.99, 1.0, 0.0)
                            glVertex3f(x + 0.80 * math.cos(a), y + 0.80 * math.sin(a), self.config["furniture"]["table_height"] + 0.002)
                        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_TRUE)
        glEnable(GL_LIGHTING)
        glEndList()
        return lid

    def build_god_rays(self, preset="daylight"):
        W, L = self.r["width"], self.r["depth"]
        sill, win_top = .94, 2.82
        lid = glGenLists(1)
        glNewList(lid, GL_COMPILE)
        glDisable(GL_LIGHTING)
        glDepthMask(GL_FALSE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)

        is_sunset = (preset == "sunset")
        # Daylight: steeper, cooler, extends 4.8m into room
        # Sunset: low dramatic angle, warm golden, extends 9.6m across desks
        dx = -9.6 if is_sunset else -4.8
        dy = -0.55 if is_sunset else 0.35
        dz = -1.15 if is_sunset else -1.65

        c_origin = (1.0, 0.65, 0.22, 0.26) if is_sunset else (0.85, 0.94, 1.0, 0.12)
        c_term = (1.0, 0.50, 0.15, 0.0) if is_sunset else (0.85, 0.94, 1.0, 0.0)

        glBegin(GL_QUADS)
        for i in range(10):
            y0 = 0.48 + i * (L - 0.96) / 10 + 0.03
            y1 = 0.48 + (i + 1) * (L - 0.96) / 10 - 0.03
            z0 = sill + 0.08
            z1 = win_top - 0.06

            p0 = (W, y0, z0)
            p1 = (W, y1, z0)
            p2 = (W, y1, z1)
            p3 = (W, y0, z1)

            q0 = (W + dx, y0 + dy, max(0.015, z0 + dz))
            q1 = (W + dx, y1 + dy, max(0.015, z0 + dz))
            q2 = (W + dx, y1 + dy, max(0.75, z1 + dz))
            q3 = (W + dx, y0 + dy, max(0.75, z1 + dz))

            # Bottom face
            glColor4f(*c_origin); glVertex3f(*p0); glVertex3f(*p1)
            glColor4f(*c_term); glVertex3f(*q1); glVertex3f(*q0)
            # Top face
            glColor4f(*c_origin); glVertex3f(*p2); glVertex3f(*p3)
            glColor4f(*c_term); glVertex3f(*q3); glVertex3f(*q2)
            # Left face
            glColor4f(*c_origin); glVertex3f(*p3); glVertex3f(*p0)
            glColor4f(*c_term); glVertex3f(*q0); glVertex3f(*q3)
            # Right face
            glColor4f(*c_origin); glVertex3f(*p1); glVertex3f(*p2)
            glColor4f(*c_term); glVertex3f(*q2); glVertex3f(*q1)
            # Interior cross-slice for enhanced density
            mid_z = (z0 + z1) / 2
            mid_qz = (q0[2] + q2[2]) / 2
            glColor4f(*c_origin); glVertex3f(W, y0, mid_z); glVertex3f(W, y1, mid_z)
            glColor4f(*c_term); glVertex3f(W + dx, y1 + dy, mid_qz); glVertex3f(W + dx, y0 + dy, mid_qz)
        glEnd()

        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_TRUE)
        glEnable(GL_LIGHTING)
        glEndList()
        return lid

    def boundary_visible(self, boundary, eye, cutaway):
        if not boundary or not cutaway:
            return True
        x, y, _ = eye
        return {"front": y >= 0, "back": y <= self.r["depth"],
                "left": x >= 0, "right": x <= self.r["width"],
                "entry": y <= self.r["depth"]+self.r["vestibule_depth"],
                "vestleft": x >= self.vestibule_x,
                "vestright": x <= self.vestibule_right}[boundary]

    def draw_door(self, angle):
        r = self.r
        dw, dh = r["door_width"], r["door_height"]
        leaf_width=(dw-.09)/2-.003
        for sign in (1, -1):
            hinge_x = self.door_x+.045 if sign == 1 else self.door_x+dw-.045
            glPushMatrix()
            glTranslatef(hinge_x, self.door_y, 0)
            glRotatef(-sign*angle, 0, 0, 1)
            x = 0 if sign == 1 else -leaf_width
            for z,height in ((.035,.07),(1.08,.075),(2.09,.055)):
                draw_box(x,-.034,z,leaf_width,.068,height,COLORS["door_metal"])
            for dx in (x,x+leaf_width-.043):
                draw_box(dx,-.034,.035,.043,.068,2.11,COLORS["door_metal"])
            handle_x=x+leaf_width*(.89 if sign==1 else .11)
            for z in (.95,1.19):
                draw_box(handle_x,-.073,z,.020,.045,.020,COLORS["steel"])
            draw_box(handle_x,-.088,.95,.024,.022,.26,COLORS["steel"])
            # Door closer body and jointed arm at the top of each leaf.
            draw_box(x+leaf_width*.18,-.063,2.035,leaf_width*.32,.045,.045,COLORS["steel"])
            draw_box(x+leaf_width*.35,-.077,2.071,leaf_width*.30,.018,.015,COLORS["door_metal"])
            for z in (.30,1.78):
                hx=x if sign==1 else x+leaf_width-.025
                draw_box(hx,-.044,z,.025,.088,.085,COLORS["steel"])
            glDepthMask(GL_FALSE)
            for z,height in ((.105,.975),(1.155,.935)):
                draw_box(x+.044,-.006,z,leaf_width-.088,.012,height,COLORS["door_glass"])
            glDepthMask(GL_TRUE)
            glPopMatrix()
        glDepthMask(GL_FALSE)
        for i in (0,1):
            draw_box(self.door_x+.045+i*(dw/2),self.door_y-.006,2.345,dw/2-.067,.012,dh-2.39,COLORS["door_glass"])
        glDepthMask(GL_TRUE)

    def draw(self, eye, cutaway, ceiling, door_angle, lighting_preset="daylight", interior_lights=True, god_rays=True, lighting_state=None):
        if lighting_state is None:
            lighting_state = LightingState()

        is_sunset = (lighting_preset == "sunset")
        if is_sunset:
            glLightfv(GL_LIGHT0, GL_POSITION, (22.0, 4.0, 3.2, 1.0))
            sun_color = lighting_state.scale_color((1.0, 0.58, 0.20, 1.0), lighting_state.sun_intensity)
            base_ambient = (0.24, 0.21, 0.19, 1.0) if interior_lights else (0.16, 0.14, 0.14, 1.0)
        else:
            glLightfv(GL_LIGHT0, GL_POSITION, (self.r["width"] * 1.5, 6.0, 14.0, 1.0))
            sun_color = lighting_state.scale_color((0.85, 0.88, 0.90, 1.0), lighting_state.sun_intensity)
            base_ambient = (0.44, 0.44, 0.44, 1.0) if interior_lights else (0.26, 0.26, 0.26, 1.0)
        glLightfv(GL_LIGHT0, GL_DIFFUSE, sun_color)

        ambient = lighting_state.scale_color(base_ambient, lighting_state.ambient_brightness / 0.40)
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, ambient)

        if interior_lights and lighting_state.interior_intensity > 0.001:
            l1 = lighting_state.scale_color((.20, .21, .22, 1), lighting_state.interior_intensity)
            l2 = lighting_state.scale_color((.35, .35, .34, 1), lighting_state.interior_intensity)
            glLightfv(GL_LIGHT1, GL_DIFFUSE, l1)
            glLightfv(GL_LIGHT2, GL_DIFFUSE, l2)
        else:
            glLightfv(GL_LIGHT1, GL_DIFFUSE, (.0, .0, .0, 1))
            glLightfv(GL_LIGHT2, GL_DIFFUSE, (.0, .0, .0, 1))

        for (group, boundary), lid in self.lists.items():
            if group in ("glass", "lamps", "luminaire_glow"):
                continue
            if (group in ("ceiling", "beams") or group.startswith("overhead_tv")) and not ceiling:
                continue
            if group in ("daylight","outside_entry") and (cutaway or not
                    (0 <= eye[0] <= self.r["width"] and 0 <= eye[1] <= self.door_y)):
                continue
            if self.boundary_visible(boundary, eye, cutaway):
                if group == "daylight":
                    glDisable(GL_LIGHTING)
                    glEnable(GL_TEXTURE_2D)
                    glBindTexture(GL_TEXTURE_2D, self.textures["sunset" if is_sunset else "daylight"])
                glCallList(lid)
                if group == "daylight":
                    glDisable(GL_TEXTURE_2D)
                    glEnable(GL_LIGHTING)
        glCallList(self.floor_list)
        glCallList(self.contact_list)
        if interior_lights and lighting_state.interior_intensity > 0.01:
            glCallList(self.interior_pool_list)
        if god_rays and lighting_state.god_rays_opacity > 0.01 and lighting_preset in self.god_rays_lists:
            glCallList(self.god_rays_lists[lighting_preset])
        # White turret camera attached beneath the beam, with lens + IR window.
        if ceiling:
            glPushMatrix()
            glTranslatef(self.vestibule_x+.28,self.door_y-.27,self.r["height"]-.58)
            glColor3f(.86,.87,.83)
            gluCylinder(self.quadric,.115,.115,.06,24,1)
            gluDisk(self.quadric,0,.115,24,1)
            glTranslatef(0,0,-.055)
            gluSphere(self.quadric,.092,24,16)
            for dx,radius in ((-.036,.027),(.036,.024)):
                glPushMatrix(); glTranslatef(dx,-.068,-.032)
                glColor3f(.025,.03,.035); gluSphere(self.quadric,radius,16,10)
                glTranslatef(-.004,-.015,.005); glColor3f(.12,.18,.20)
                gluSphere(self.quadric,radius*.47,12,8); glPopMatrix()
            glPopMatrix()
        if ceiling and interior_lights and lighting_state.interior_intensity > 0.01:
            glDepthMask(GL_FALSE)
            for (group, _), lid in self.lists.items():
                if group == "luminaire_glow":
                    glCallList(lid)
            glDepthMask(GL_TRUE)
        glDisable(GL_LIGHTING)
        if ceiling:
            for (group, _), lid in self.lists.items():
                if group == "lamps":
                    if interior_lights and lighting_state.interior_intensity > 0.05:
                        lamp_col = lighting_state.scale_color(COLORS["light"], lighting_state.interior_intensity)[:3]
                        glColor3f(*lamp_col)
                    else:
                        glColor3f(.28, .30, .32)
                    glCallList(lid)
        glEnable(GL_LIGHTING)
        glDepthMask(GL_FALSE)
        for (group, boundary), lid in self.lists.items():
            if group == "glass" and self.boundary_visible(boundary, eye, cutaway):
                glCallList(lid)
        glDepthMask(GL_TRUE)
        # Keep the door visible in cutaway views so its rear position is clear.
        self.draw_door(door_angle)



def normalize(v):
    size = math.sqrt(sum(x*x for x in v)) or 1
    return tuple(x/size for x in v)


class Camera:
    def __init__(self, room):
        self.r = room
        self.fpv_walk = False
        self.standing_eye_height = 1.70
        self.preset(1)

    def preset(self, n):
        W, L = self.r["width"], self.r["depth"]
        self.view = n
        full_depth = L+self.r["vestibule_depth"]
        self.target = [W/2, full_depth/2, 1.10]
        self.azimuth, self.elevation, self.distance = 137, 38, max(W, full_depth)*1.80
        self.cutaway, self.ceiling, self.free, self.fpv_walk = True, False, False, False
        if n == 2:
            self.free, self.cutaway, self.ceiling, self.fpv_walk = True, False, True, True
            self.position = [1.05, L-1.30, 1.70]
            self.yaw, self.pitch = -66, -1
        elif n == 3:
            self.azimuth, self.elevation, self.distance = 137, 21, max(W, full_depth)*1.95
            self.cutaway, self.ceiling = False, True
        elif n == 4:
            self.azimuth, self.elevation, self.distance = 90, 89.8, max(W, full_depth)*1.9

    def vectors(self):
        if self.free:
            yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
            direction = (math.cos(yaw)*math.cos(pitch), math.sin(yaw)*math.cos(pitch), math.sin(pitch))
            eye = self.position[:]
            target = [eye[i]+direction[i] for i in range(3)]
        else:
            az, el = math.radians(self.azimuth), math.radians(self.elevation)
            direction = (math.cos(az)*math.cos(el), math.sin(az)*math.cos(el), math.sin(el))
            target = self.target
            eye = [target[i]+self.distance*direction[i] for i in range(3)]
        return eye, target

    def rotate(self, dx, dy):
        if self.free:
            self.yaw += dx*.22
            self.pitch = max(-85, min(85, self.pitch-dy*.20))
        else:
            self.azimuth += dx*.28
            self.elevation = max(-15, min(89.8, self.elevation+dy*.23))

    def zoom(self, amount):
        if self.free:
            eye, target = self.vectors()
            direction = normalize([target[i]-eye[i] for i in range(3)])
            self.position = [eye[i]+amount*.5*direction[i] for i in range(3)]
        else:
            self.distance = max(2, min(65, self.distance*math.exp(-amount*.10)))

    def move_vector(self, forward: float, strafe: float) -> tuple:
        yaw = math.radians(self.yaw)
        dx = math.cos(yaw) * forward + math.sin(yaw) * strafe
        dy = math.sin(yaw) * forward - math.cos(yaw) * strafe
        return (dx, dy)

    def clamp_bounds(self, pos: list) -> list:
        W, L = self.r["width"], self.r["depth"]
        V = self.r.get("vestibule_depth", 4.01)
        margin = 0.45
        x, y, z = pos[0], pos[1], pos[2]

        # Front wall collision
        y = max(margin, y)

        if x > 2.65:
            # Main room: strictly bounded by solid rear classroom wall
            x = max(margin, min(W - margin, x))
            y = min(L - margin, y)
        else:
            # Vestibule doorway / hallway column:
            x = max(margin, min(W - margin, x))
            if y > L - margin:
                x = min(2.65, x)
                y = min(L + V - margin, y)

        if self.fpv_walk:
            z = self.standing_eye_height
        return [x, y, z]

    def toggle_free(self):
        if self.free:
            self.free = False
            self.fpv_walk = False
        else:
            eye, target = self.vectors()
            d = normalize([target[i]-eye[i] for i in range(3)])
            self.position = list(eye)
            self.yaw = math.degrees(math.atan2(d[1], d[0]))
            self.pitch = math.degrees(math.asin(d[2]))
            self.free = True


@lru_cache(maxsize=16)
def font(size, bold=False):
    filenames = ["C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for filename in filenames:
        if Path(filename).exists():
            return ImageFont.truetype(filename, size)
    return ImageFont.load_default()


class HUD:
    def __init__(self, config):
        self.config = config
        self.cache = {}
        self.help_image = Image.new("RGBA", (1080, 84), (16, 28, 38, 231))
        d = ImageDraw.Draw(self.help_image)
        d.text((22, 12), "1 Overview   2 Inside/FPV   3 Exterior   4 Top   |   Drag: look/orbit   Wheel: zoom", font=font(18), fill=(242, 244, 235))
        d.text((22, 44), "WASD Walk  Tab Cursor/FPV  Sliders Drag/[ ]  T Sun  L Lights  G Rays  O Door  P Tour  Esc Exit", font=font(15), fill=(180, 205, 208))

    def apply_slider_value(self, index: int, norm_x: float, lighting_state):
        nx = max(0.0, min(1.0, float(norm_x)))
        if index == 0:
            lighting_state.set_sun(nx * 2.0)
        elif index == 1:
            lighting_state.set_interior(nx * 2.0)
        elif index == 2:
            lighting_state.set_god_rays(nx * 1.0)
        elif index == 3:
            lighting_state.set_ambient(nx * 1.0)

    def is_point_in_panel(self, x: float, y: float, window_w: int, window_h: int) -> bool:
        pw, ph = 340, 210
        px = window_w - pw - 20
        py = 18
        return (px <= x <= px + pw) and (py <= y <= py + ph)

    def slider_hit_test(self, x: float, y: float, window_w: int, window_h: int) -> tuple | None:
        if not self.is_point_in_panel(x, y, window_w, window_h):
            return None
        pw, ph = 340, 210
        px = window_w - pw - 20
        py = 18
        rel_x = x - px
        rel_y = y - py
        start_y = 42
        rail_x0 = 105
        rail_x1 = 275
        rail_w = rail_x1 - rail_x0
        for idx in range(4):
            row_y = start_y + idx * 40
            if row_y <= rel_y <= row_y + 38:
                norm_val = max(0.0, min(1.0, (rel_x - rail_x0) / rail_w))
                return (idx, norm_val)
        return None

    def slider_panel_image(self, lighting_state, active_slider=0):
        pw, ph = 340, 210
        im = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, pw, ph), 14, fill=(16, 28, 38, 235), outline=(50, 80, 100), width=1)
        d.text((18, 12), "LIGHTING CONTROLS", font=font(15, True), fill=(245, 247, 239))
        d.text((225, 14), "[Tab] cursor", font=font(12), fill=(140, 180, 195))

        sliders = [
            ("SUNLIGHT", lighting_state.sun_intensity, 2.0, (255, 205, 110)),
            ("INTERIOR", lighting_state.interior_intensity, 2.0, (140, 220, 240)),
            ("GOD RAYS", lighting_state.god_rays_opacity, 1.0, (240, 230, 160)),
            ("AMBIENT", lighting_state.ambient_brightness, 1.0, (180, 200, 210)),
        ]
        start_y = 42
        rail_x0 = 105
        rail_x1 = 275
        rail_w = rail_x1 - rail_x0

        for idx, (name, val, max_val, col) in enumerate(sliders):
            y_offset = start_y + idx * 40
            is_active = (idx == active_slider)
            label_col = (255, 255, 255) if is_active else (180, 205, 215)
            d.text((18, y_offset + 8), name, font=font(12, is_active), fill=label_col)

            # Rail background
            d.rounded_rectangle((rail_x0, y_offset + 14, rail_x1, y_offset + 20), 3, fill=(35, 50, 65))
            norm = max(0.0, min(1.0, val / max_val))
            fill_x = rail_x0 + norm * rail_w
            if fill_x > rail_x0 + 2:
                d.rounded_rectangle((rail_x0, y_offset + 14, fill_x, y_offset + 20), 3, fill=col)
            # Knob
            kx = int(fill_x)
            ky = y_offset + 17
            knob_r = 8 if is_active else 6
            d.ellipse((kx - knob_r, ky - knob_r, kx + knob_r, ky + knob_r), fill=(255, 255, 255), outline=col, width=2)
            # Numeric value
            d.text((rail_x1 + 8, y_offset + 8), f"{val:.2f}", font=font(12), fill=(225, 235, 240))

        return im

    def panel(self, key, image, x, y, w, h):
        if key not in self.cache:
            self.cache[key] = make_texture(image)
        glBindTexture(GL_TEXTURE_2D, self.cache[key])
        glColor4f(1, 1, 1, 1)
        glBegin(GL_QUADS)
        for uv, pos in zip(((0, 0), (1, 0), (1, 1), (0, 1)), ((x, y), (x+w, y), (x+w, y+h), (x, y+h))):
            glTexCoord2f(*uv); glVertex2f(*pos)
        glEnd()

    def image(self, camera, tour, lighting_preset="daylight", interior_lights=True, god_rays=True):
        key = (camera.view, camera.free, camera.cutaway, camera.ceiling, tour, lighting_preset, interior_lights, god_rays)
        im = Image.new("RGBA", (1080, 140), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, 1080, 140), 17, fill=(16, 28, 38, 235))
        d.rectangle((23, 24, 28, 116), fill=(120, 206, 199))
        d.text((45, 16), self.config["room_id"], font=font(36, True), fill=(245, 247, 239))
        d.text((47, 65), "6TH FLOOR / OPENGL CLASSROOM", font=font(16), fill=(167, 196, 201))
        r = self.config["room"]
        d.text((47, 93), f"{r['width']:.2f} x {r['depth']:.2f} m  |  H {r['height']:.2f} m", font=font(17), fill=(238, 222, 181))
        l_color = (255, 200, 110) if lighting_preset == "sunset" else (160, 220, 240)
        d.text((47, 117), f"LIGHT: {lighting_preset.upper()} (T) | INT: {'ON' if interior_lights else 'OFF'} (L) | RAYS: {'ON' if god_rays else 'OFF'} (G)", font=font(13, True), fill=l_color)
        names = {1: "OVERVIEW", 2: "INSIDE (FPV)", 3: "EXTERIOR", 4: "TOP VIEW"}
        d.text((700, 23), names[camera.view], font=font(24, True), fill=(233, 244, 244))
        info = "FPV WALK" if getattr(camera, "fpv_walk", False) else ("FREE CAM" if camera.free else "ORBIT CAMERA")
        d.text((700, 61), info, font=font(15), fill=(167, 196, 201))
        d.text((700, 91), "AUTO TOUR" if tour else "DIMENSION MAPPING: DRAFT", font=font(15), fill=(238, 222, 181))
        return key, im

    def draw(self, width, height, camera, tour, lighting_preset="daylight", interior_lights=True, god_rays=True, lighting_state=None, active_slider=0):
        if lighting_state is None:
            lighting_state = LightingState()
        glDisable(GL_DEPTH_TEST); glDisable(GL_LIGHTING)
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity()
        glOrtho(0, width, height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
        glEnable(GL_TEXTURE_2D)
        scale = min(1, (width-40)/1080)
        key = (camera.view, camera.free, camera.cutaway, camera.ceiling, tour, lighting_preset, interior_lights, god_rays)
        im = self.image(camera, tour, lighting_preset, interior_lights, god_rays)[1] if key not in self.cache else None
        self.panel(key, im, 20, 18, 1080*scale, 140*scale)
        self.panel("help", self.help_image, 20, height-84*scale-18, 1080*scale, 84*scale)

        # Draw lighting sliders panel at top-right
        pw, ph = 340, 210
        px = width - pw - 20
        py = 18
        s_key = ("sliders", round(lighting_state.sun_intensity, 2), round(lighting_state.interior_intensity, 2),
                 round(lighting_state.god_rays_opacity, 2), round(lighting_state.ambient_brightness, 2), active_slider)
        if s_key not in self.cache:
            if len(self.cache) > 40:
                for k in list(self.cache.keys()):
                    if isinstance(k, tuple) and len(k) > 0 and k[0] == "sliders":
                        glDeleteTextures([self.cache.pop(k)])
            sim = self.slider_panel_image(lighting_state, active_slider)
            self.cache[s_key] = make_texture(sim)
        self.panel(s_key, None, px, py, pw, ph)

        glDisable(GL_TEXTURE_2D)
        glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)
        glEnable(GL_LIGHTING); glEnable(GL_DEPTH_TEST)



class App:
    def __init__(self, config, width=1440, height=900, hidden=False):
        self.config = config
        self.errors = []
        glfw.set_error_callback(lambda code, desc: self.errors.append((code, desc.decode(errors="replace"))))
        if not glfw.init():
            raise RuntimeError("GLFW initialization failed. Check the display and graphics driver.")
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 2)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 1)
        glfw.window_hint(glfw.SAMPLES, 4)
        glfw.window_hint(glfw.VISIBLE, not hidden)
        self.window = glfw.create_window(width, height, "S13-30612 | OpenGL Classroom", None, None)
        if not self.window:
            glfw.default_window_hints()
            glfw.window_hint(glfw.VISIBLE, not hidden)
            self.window = glfw.create_window(width, height, "S13-30612 | OpenGL Classroom", None, None)
        if not self.window:
            glfw.terminate()
            raise RuntimeError(f"Cannot create an OpenGL window: {self.errors}")
        glfw.make_context_current(self.window)
        glfw.swap_interval(1)
        print("OpenGL:", glGetString(GL_VERSION).decode())
        print("Renderer:", glGetString(GL_RENDERER).decode())
        glEnable(GL_DEPTH_TEST); glEnable(GL_MULTISAMPLE)
        glEnable(GL_NORMALIZE); glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glEnable(GL_LIGHTING); glEnable(GL_LIGHT0); glEnable(GL_LIGHT1); glEnable(GL_LIGHT2)
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, (.46, .46, .46, 1))
        glLightfv(GL_LIGHT0, GL_DIFFUSE, (.45, .45, .44, 1))
        glLightfv(GL_LIGHT1, GL_DIFFUSE, (.18, .19, .20, 1))
        glLightfv(GL_LIGHT2, GL_DIFFUSE, (.38, .38, .37, 1))
        glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        self.camera = Camera(config["room"])
        self.scene = Classroom(config)
        self.hud = HUD(config)
        self.show_hud, self.tour, self.door_open = True, False, False
        self.door_angle = 0.0
        self.dragging, self.last_mouse = False, None
        self.tour_start = time.perf_counter()
        l_cfg = config.get("lighting", {})
        self.lighting_preset = l_cfg.get("default_preset", "daylight")
        self.interior_lights = l_cfg.get("interior_lights", True)
        self.god_rays = l_cfg.get("god_rays", True)
        self.lighting_state = LightingState()
        self.cursor_locked = False
        self.active_slider = 0
        self.dragging_slider = False
        glfw.set_key_callback(self.window, self.on_key)
        glfw.set_scroll_callback(self.window, lambda _w, _x, y: self.camera.zoom(y))
        glfw.set_mouse_button_callback(self.window, self.on_button)
        glfw.set_cursor_pos_callback(self.window, self.on_mouse)

    def set_cursor_mode(self, locked: bool):
        self.cursor_locked = locked
        glfw.set_input_mode(self.window, glfw.CURSOR,
                            glfw.CURSOR_DISABLED if locked else glfw.CURSOR_NORMAL)
        if locked:
            self.last_mouse = glfw.get_cursor_pos(self.window)

    def toggle_lighting_preset(self):
        self.lighting_preset = "sunset" if self.lighting_preset == "daylight" else "daylight"

    def toggle_interior_lights(self):
        self.interior_lights = not self.interior_lights

    def toggle_god_rays(self):
        self.god_rays = not self.god_rays

    def on_key(self, _window, key, _scancode, action, _mods):
        if action != glfw.PRESS:
            return
        if _mods & glfw.MOD_CONTROL and glfw.KEY_1 <= key <= glfw.KEY_4:
            self.active_slider = key - glfw.KEY_1
            return
        if glfw.KEY_1 <= key <= glfw.KEY_4:
            n = key - glfw.KEY_1 + 1
            self.camera.preset(n)
            self.tour = False
            self.set_cursor_mode(n == 2)
        elif key == glfw.KEY_TAB:
            if self.camera.view == 2 or getattr(self.camera, "fpv_walk", False):
                self.set_cursor_mode(not self.cursor_locked)
        elif key == glfw.KEY_LEFT_BRACKET:
            step = -0.05 if self.active_slider in (0, 1) else -0.02
            self.lighting_state.nudge_slider(self.active_slider, step)
        elif key == glfw.KEY_RIGHT_BRACKET:
            step = 0.05 if self.active_slider in (0, 1) else 0.02
            self.lighting_state.nudge_slider(self.active_slider, step)
        elif key == glfw.KEY_F:
            self.camera.toggle_free()
            self.tour = False
            if self.camera.free and not self.camera.fpv_walk:
                self.set_cursor_mode(False)
        elif key == glfw.KEY_C:
            self.camera.ceiling = not self.camera.ceiling
        elif key == glfw.KEY_V:
            self.camera.cutaway = not self.camera.cutaway
        elif key == glfw.KEY_O:
            self.door_open = not self.door_open
        elif key == glfw.KEY_T:
            self.toggle_lighting_preset()
        elif key == glfw.KEY_L:
            self.toggle_interior_lights()
        elif key == glfw.KEY_G:
            self.toggle_god_rays()
        elif key == glfw.KEY_H:
            self.show_hud = not self.show_hud
        elif key == glfw.KEY_P:
            self.tour = not self.tour
            self.tour_start = time.perf_counter()
            if self.tour:
                self.set_cursor_mode(False)
        elif key in (glfw.KEY_R, glfw.KEY_HOME):
            self.camera.preset(1)
            self.tour = False
            self.set_cursor_mode(False)
        elif key == glfw.KEY_ESCAPE:
            glfw.set_window_should_close(self.window, True)
        elif key == glfw.KEY_F12:
            self.capture(BASE/"screenshots"/f"room_{time.strftime('%Y%m%d_%H%M%S')}.png")

    def on_button(self, _window, button, action, _mods):
        if button == glfw.MOUSE_BUTTON_LEFT:
            w, h = glfw.get_framebuffer_size(self.window)
            if action == glfw.PRESS:
                pos = glfw.get_cursor_pos(self.window)
                self.last_mouse = pos
                if not self.cursor_locked and self.hud.is_point_in_panel(pos[0], pos[1], w, h):
                    hit = self.hud.slider_hit_test(pos[0], pos[1], w, h)
                    if hit:
                        self.active_slider, norm_val = hit
                        self.hud.apply_slider_value(self.active_slider, norm_val, self.lighting_state)
                        self.dragging_slider = True
                elif not self.cursor_locked and (self.camera.view == 2 or getattr(self.camera, "fpv_walk", False)):
                    self.set_cursor_mode(True)
                else:
                    self.dragging = True
            elif action == glfw.RELEASE:
                self.dragging = False
                self.dragging_slider = False

    def on_mouse(self, _window, x, y):
        if self.cursor_locked:
            if self.last_mouse:
                dx, dy = x - self.last_mouse[0], y - self.last_mouse[1]
                self.camera.rotate(dx, dy)
                self.tour = False
            self.last_mouse = (x, y)
        elif self.dragging_slider:
            w, h = glfw.get_framebuffer_size(self.window)
            pw = 340
            px = w - pw - 20
            rel_x = x - px
            rail_x0 = 105
            rail_w = 170
            norm_val = max(0.0, min(1.0, (rel_x - rail_x0) / rail_w))
            self.hud.apply_slider_value(self.active_slider, norm_val, self.lighting_state)
        elif self.dragging and self.last_mouse:
            dx, dy = x - self.last_mouse[0], y - self.last_mouse[1]
            self.camera.rotate(dx, dy)
            self.tour = False
            self.last_mouse = (x, y)
        else:
            self.last_mouse = (x, y)

    def update(self, dt):
        cam = self.camera
        self.door_angle += max(-dt*100, min(dt*100, (85 if self.door_open else 0)-self.door_angle))
        if self.tour:
            self.update_tour(time.perf_counter()-self.tour_start)
            return
        pressed = lambda key: glfw.get_key(self.window, key) == glfw.PRESS
        if getattr(cam, "fpv_walk", False):
            speed = (5.5 if pressed(glfw.KEY_LEFT_SHIFT) else 3.0) * dt
            forward = 0.0
            strafe = 0.0
            if pressed(glfw.KEY_W): forward += 1.0
            if pressed(glfw.KEY_S): forward -= 1.0
            if pressed(glfw.KEY_D): strafe += 1.0
            if pressed(glfw.KEY_A): strafe -= 1.0
            if forward != 0.0 or strafe != 0.0:
                dx, dy = cam.move_vector(forward, strafe)
                norm = math.sqrt(dx*dx + dy*dy) or 1.0
                cam.position[0] += (dx / norm) * speed
                cam.position[1] += (dy / norm) * speed
            cam.position = cam.clamp_bounds(cam.position)
        elif cam.free:
            speed = (8 if pressed(glfw.KEY_LEFT_SHIFT) else 3.5)*dt
            yaw = math.radians(cam.yaw)
            forward = (math.cos(yaw), math.sin(yaw))
            right = (math.sin(yaw), -math.cos(yaw))
            for key, direction, sign in ((glfw.KEY_W, forward, 1), (glfw.KEY_S, forward, -1),
                                         (glfw.KEY_D, right, 1), (glfw.KEY_A, right, -1)):
                if pressed(key):
                    for i in range(2): cam.position[i] += sign*direction[i]*speed
            if pressed(glfw.KEY_Q): cam.position[2] -= speed
            if pressed(glfw.KEY_E): cam.position[2] += speed
            cam.position[2] = max(.25, min(30, cam.position[2]))
        else:
            speed = (8 if pressed(glfw.KEY_LEFT_SHIFT) else 3.5)*dt
            if pressed(glfw.KEY_A): cam.target[0] -= speed
            if pressed(glfw.KEY_D): cam.target[0] += speed
            if pressed(glfw.KEY_W): cam.target[1] -= speed
            if pressed(glfw.KEY_S): cam.target[1] += speed
            if pressed(glfw.KEY_Q): cam.target[2] -= speed
            if pressed(glfw.KEY_E): cam.target[2] += speed
        if pressed(glfw.KEY_LEFT): cam.rotate(-140*dt, 0)
        if pressed(glfw.KEY_RIGHT): cam.rotate(140*dt, 0)
        if pressed(glfw.KEY_UP): cam.rotate(0, -110*dt)
        if pressed(glfw.KEY_DOWN): cam.rotate(0, 110*dt)

    def update_tour(self, elapsed):
        # A 60-second loop: exterior -> cutaway -> inside -> overhead.
        phase = elapsed % 60
        W, L = self.config["room"]["width"], self.config["room"]["depth"]
        if phase < 15:
            self.camera.preset(3)
            self.camera.azimuth = 125 + phase*6
        elif phase < 32:
            self.camera.preset(1)
            self.camera.azimuth = 130 + (phase-15)*4
            self.camera.elevation = 33
        elif phase < 48:
            self.camera.preset(2)
            p = (phase-32)/16
            self.camera.position = [1.1 + p*(W*.32), L-1.2-p*3, 1.7]
            self.camera.yaw = -63-p*18
        else:
            self.camera.preset(4)
            self.camera.elevation = 72
            self.camera.azimuth = 90+(phase-48)*3

    def render(self):
        width, height = glfw.get_framebuffer_size(self.window)
        if not width or not height:
            return
        glViewport(0, 0, width, height)
        glClearColor(.20, .27, .32, 1)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glMatrixMode(GL_PROJECTION); glLoadIdentity()
        gluPerspective(getattr(self,"capture_fov",52), width/height, .08, 180)
        glMatrixMode(GL_MODELVIEW); glLoadIdentity()
        eye, target = self.camera.vectors()
        gluLookAt(*eye, *target, 0, 0, 1)
        self.scene.draw(eye, self.camera.cutaway, self.camera.ceiling, self.door_angle,
                        self.lighting_preset, self.interior_lights, self.god_rays, self.lighting_state)
        if self.show_hud:
            self.hud.draw(width, height, self.camera, self.tour,
                          self.lighting_preset, self.interior_lights, self.god_rays,
                          self.lighting_state, self.active_slider)

    def capture(self, path):
        self.render()
        glFinish()
        width, height = glfw.get_framebuffer_size(self.window)
        glReadBuffer(GL_BACK)
        glPixelStorei(GL_PACK_ALIGNMENT, 1)
        pixels = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
        im = Image.frombytes("RGB", (width, height), pixels).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        im.save(path)
        print("Saved:", path)

    def verify(self, folder):
        folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
        shots = []
        for n, name in ((1, "overview"), (2, "inside"), (3, "exterior"), (4, "top")):
            self.camera.preset(n)
            for _ in range(3): self.render(); glfw.swap_buffers(self.window); glfw.poll_events()
            path = folder/f"{name}.png"
            self.capture(path)
            err = glGetError()
            if err != GL_NO_ERROR:
                raise RuntimeError(f"OpenGL error in view {n}: {err}")
            shots.append(str(path.name))
        # Exercise the animated doors and every tour phase using the same renderer.
        self.camera.preset(3); self.door_angle = 85; self.capture(folder/"door_open.png")
        self.camera.preset(2)
        self.camera.position = [self.scene.door_x+self.config["room"]["door_width"]/2,
                                self.config["room"]["depth"]-.65, 1.70]
        self.camera.yaw, self.camera.pitch = 90, 0
        self.door_angle = 0
        self.capture(folder/"rear_entry.png")
        self.camera.preset(2)
        self.camera.position = [4.2, 4.0, 1.65]
        self.camera.yaw, self.camera.pitch = -124, -10
        previous_hud = self.show_hud
        self.show_hud = False
        self.capture(folder/"floor_standing_tv.png")
        self.camera.position = [7.3, 4.2, 2.55]
        self.camera.yaw, self.camera.pitch = -43, -31
        self.capture(folder/"instructor_workstation.png")
        self.camera.position = [8.9, .20, 1.90]
        self.camera.yaw, self.camera.pitch = 64, -23
        self.capture(folder/"instructor_operator_view.png")
        self.camera.position = [self.config["room"]["width"]/2, self.config["room"]["depth"]-1, 1.65]
        self.camera.yaw, self.camera.pitch = -90, 5
        self.capture(folder/"overhead_tvs.png")
        self.camera.position = [6.1, 6.0, 1.9]
        self.camera.yaw, self.camera.pitch = -144, -5
        self.capture(folder/"side_window.png")
        self.camera.position = [7.0, 8.0, 1.9]
        self.camera.yaw, self.camera.pitch = 106, 0
        self.capture(folder/"rear_wall.png")
        self.camera.position = [8.1, 5.9, 1.3]
        self.camera.yaw, self.camera.pitch = -132, -24
        self.capture(folder/"student_chairs.png")
        self.camera.position = [9.75, 6.48, 2.65]
        self.camera.yaw, self.camera.pitch = -164, 6
        self.capture(folder/"tv_mount.png")
        self.camera.position = [5.9, 4.5, 1.65]
        self.camera.yaw, self.camera.pitch = -90, 4
        self.capture(folder/"front_projection.png")
        self.camera.position = [self.config["room"]["vestibule_width"]*.40,
                                self.config["room"]["depth"]-.45,1.75]
        self.camera.yaw, self.camera.pitch = 87, -8
        self.capture(folder/"entry_clear.png")
        self.camera.position = [2.20,self.config["room"]["depth"]-3.0,2.05]
        self.camera.yaw,self.camera.pitch=100,-5
        self.capture(folder/"entry_widened.png")
        self.camera.position = [self.config["room"]["vestibule_width"]*.43,
                                self.config["room"]["depth"]+.90,1.65]
        self.camera.yaw,self.camera.pitch=90,-7
        self.capture(folder/"entry_proportions.png")
        self.camera.preset(4)
        self.camera.target=[self.config["room"]["vestibule_width"]/2,
                            self.config["room"]["depth"]+self.config["room"]["vestibule_depth"]/2,0]
        self.camera.distance=10
        self.camera.azimuth,self.camera.elevation=125,65
        self.capture(folder/"entry_layout.png")
        self.camera.preset(2)
        self.camera.position = [self.scene.door_x+.58, self.scene.door_y-3.30,1.40]
        self.camera.yaw,self.camera.pitch=90,0
        self.capture(folder/"door_detail.png")
        self.door_angle=70
        self.capture(folder/"door_detail_open.png")
        self.door_angle=0
        self.camera.position = [3.8,8.2,1.9]
        self.camera.yaw,self.camera.pitch=180,4
        self.capture(folder/"electrical_controls.png")
        self.camera.position = [3.0,7.8,1.90]
        self.camera.yaw,self.camera.pitch=-135,22
        self.capture(folder/"conduits_lighting.png")
        self.camera.position = [4.3,5.2,1.70]
        self.camera.yaw,self.camera.pitch=-153,34
        self.capture(folder/"fluorescent_detail.png")
        self.camera.position = [.95,self.config["room"]["depth"]-1.05,1.68]
        self.camera.yaw,self.camera.pitch=-57,6
        self.capture_fov=72
        self.capture(folder/"reference_interior.png")
        self.capture_fov=52
        self.camera.position=[1.6,self.scene.door_y-2.2,2.05]
        self.camera.yaw,self.camera.pitch=126,25
        self.capture(folder/"entry_ceiling_details.png")

        # Lighting feature validation snapshots
        self.camera.preset(2)
        self.lighting_preset = "daylight"
        self.interior_lights = True
        self.god_rays = True
        self.capture(folder/"daylight_inside.png")

        self.lighting_preset = "sunset"
        self.interior_lights = True
        self.god_rays = True
        self.capture(folder/"sunset_inside.png")

        self.lighting_preset = "sunset"
        self.interior_lights = False
        self.god_rays = True
        self.camera.position = [4.5, 7.5, 1.45]
        self.camera.yaw, self.camera.pitch = -35, -8
        self.capture(folder/"sunset_god_rays.png")

        # FPV walk and slider HUD validation snapshots
        self.camera.preset(2)
        self.lighting_preset = "daylight"
        self.interior_lights = True
        self.god_rays = True
        self.show_hud = True
        self.capture(folder/"fpv_inside.png")

        self.lighting_state.set_sun(1.8)
        self.lighting_state.set_interior(0.5)
        self.lighting_state.set_god_rays(0.85)
        self.lighting_state.set_ambient(0.60)
        self.capture(folder/"slider_hud.png")

        # Reset nominal state
        self.lighting_state.set_sun(1.0)
        self.lighting_state.set_interior(1.0)
        self.lighting_state.set_god_rays(0.35)
        self.lighting_state.set_ambient(0.40)
        self.show_hud = previous_hud

        for phase in (0, 14, 15, 31, 32, 47, 48, 59):
            self.update_tour(phase); self.render()
            err = glGetError()
            if err != GL_NO_ERROR: raise RuntimeError(f"OpenGL error at tour phase {phase}: {err}")
        report = {
            "room": self.config["room_id"], "opengl": glGetString(GL_VERSION).decode(),
            "renderer": glGetString(GL_RENDERER).decode(), "boxes": len(self.scene.parts),
            "student_tables": sum(len(group["tables"]) for group in self.scene.seating_layout),
            "student_seats": sum(len(group["chairs"]) for group in self.scene.seating_layout),
            "seating_columns": self.config["furniture"]["blocks"],
            "seats_per_pair": self.config["furniture"]["tables_per_block"]*self.config["furniture"]["seats_per_table"],
            "air_conditioners": self.scene.aircon_locations,
            "front_tv_count": len(self.scene.front_tv_positions),
            "front_tv_dimensions_m": self.scene.front_tv_dimensions,
            "front_tv_floor_stand": True,
            "speakers": 0,
            "outer_tables_wall_clearance_m": self.config["furniture"]["wall_clearance"],
            "instructor_desk_m": self.scene.instructor_desk,
            "computer_type": "iMac all-in-one; no separate computer case",
            "monitor_face_normal": self.scene.monitor_face_normal,
            "instructor_chair_position_m": self.scene.instructor_chair_position,
            "keyboard_position_m": self.scene.keyboard_position,
            "mouse_position_m": self.scene.mouse_position,
            "overhead_tvs": self.scene.overhead_tv_locations,
            "lighting_presets": ["daylight", "sunset"],
            "god_rays_enabled": True,
            "interior_light_pools_enabled": True,
            "fpv_walk_mode": True,
            "lighting_sliders_enabled": True,
            "lighting_slider_channels": ["sunlight", "interior", "god_rays", "ambient"],
            "views": shots, "door_open_rendered": True, "tour_phases_rendered": 8,
            "opengl_errors": 0, "glfw_errors": self.errors,
            "entry_hall_position": "rear right when facing the screen; X=0 side, +Y extension",
            "door_position_m": [round(self.scene.door_x, 3), round(self.scene.door_y, 3)],
            "main_floor_area_m2": round(self.config["room"]["width"]*self.config["room"]["depth"], 3),
            "provisional_total_floor_area_m2": round(self.config["room"]["width"]*self.config["room"]["depth"]+self.config["room"]["vestibule_width"]*self.config["room"]["vestibule_depth"], 3)
        }
        (folder/"verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))

    def run(self):
        last = time.perf_counter()
        while not glfw.window_should_close(self.window):
            now = time.perf_counter(); dt = min(now-last, .05); last = now
            self.update(dt); self.render()
            glfw.swap_buffers(self.window); glfw.poll_events()


def main():
    parser = argparse.ArgumentParser(description="OpenGL model of classroom S13-30612")
    parser.add_argument("--config", type=Path, default=BASE/"room_config.json")
    parser.add_argument("--view", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--size", default="1440x900")
    parser.add_argument("--hidden", action="store_true", help="Hidden OpenGL window for render checks")
    parser.add_argument("--capture", type=Path, help="Render one image and exit")
    parser.add_argument("--verify", type=Path, help="Render all views, open doors and tour phases")
    args = parser.parse_args()
    app = None
    try:
        config = load_config(args.config)
        width, height = map(int, args.size.lower().split("x"))
        app = App(config, width, height, args.hidden)
        app.camera.preset(args.view)
        if args.verify:
            app.verify(args.verify)
        elif args.capture:
            app.capture(args.capture)
        else:
            app.run()
    except Exception as exc:
        print("ERROR:", exc)
        if getattr(sys, "frozen", False) and not (args.capture or args.verify):
            input("Press Enter to close...")
        raise
    finally:
        if app:
            glfw.destroy_window(app.window)
        glfw.terminate()


if __name__ == "__main__":
    main()
