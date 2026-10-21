"""Deterministic, code-generated surface images for the classroom model.

The colours already describe the materials: upload with a white OpenGL tint.
These are approximate materials, not photographs or an exact exterior view.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter


def _clamp(value):
    return max(0, min(255, round(value)))


def _grain_image(width, height, base, vertical=False, seed=612):
    """Low-contrast laminate/veneer grain without the old orange zebra lines."""
    rng = random.Random(seed)
    raw = bytearray(width * height * 3)
    for y in range(height):
        for x in range(width):
            along = y / height if vertical else x / width
            across = x / width if vertical else y / height
            warp = .004 * math.sin(2 * math.pi * along)
            warp += .002 * math.sin(6 * math.pi * along + 2 * across)
            grain = across + warp
            shade = 2.7 * math.sin(2 * math.pi * grain * 8)
            shade += 1.25 * math.sin(2 * math.pi * grain * 31)
            shade += .7 * math.sin(2 * math.pi * grain * 83)
            shade += rng.uniform(-1.4, 1.4)
            index = (y * width + x) * 3
            raw[index:index + 3] = bytes(_clamp(c + shade) for c in base)
    image = Image.frombytes("RGB", (width, height), bytes(raw))
    # A few faint broken fibres; no bold outlines, plank joints or dark knots.
    layer = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(layer)
    for _ in range(100):
        u, v = rng.random(), rng.random()
        span = rng.uniform(.025, .18)
        points = []
        for step in range(9):
            a = u + span * step / 8
            b = v + .0015 * math.sin(a * math.pi * 4)
            points.append((b * width, a * height) if vertical else (a * width, b * height))
        draw.line(points, fill=(91, 73, 53, rng.randrange(6, 18)), width=1)
    return Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")


def _terrazzo():
    rng = random.Random(30612)
    size = 1024
    raw = bytearray(size * size * 3)
    for index in range(0, len(raw), 3):
        variation = rng.uniform(-2.0, 2.0)
        raw[index:index + 3] = bytes(_clamp(c + variation) for c in (194, 195, 189))
    image = Image.frombytes("RGB", (size, size), bytes(raw))
    draw = ImageDraw.Draw(image)
    # Fine light aggregate dominates.
    for _ in range(40000):
        x, y = rng.randrange(size), rng.randrange(size)
        value = rng.randrange(176, 220)
        draw.point((x, y), fill=(value, value + 1, max(0, value - 5)))
    for _ in range(7000):
        x, y = rng.randrange(size), rng.randrange(size)
        radius = rng.choices((2, 3, 4, 6), (55, 30, 12, 3))[0]
        value = rng.randrange(101, 166) if rng.random() < .68 else rng.randrange(208, 230)
        tint = rng.randrange(-3, 4)
        colour = (_clamp(value + tint), _clamp(value + 1), _clamp(value - 4))
        polygon = [(x, y), (x + radius, y + rng.choice((0, 1))),
                   (x + radius + 1, y + max(1, radius // 2)),
                   (x + 1, y + radius)]
        # Wrap chips crossing a boundary so repeated tiles do not gain seams.
        for dx in (0, -size):
            for dy in (0, -size):
                draw.polygon([(px + dx, py + dy) for px, py in polygon], fill=colour)
    return image


def _oak_wood(width=1024, height=512, seed=612):
    """Authentic warm golden Oak wood with cathedral arches and latewood pore striae."""
    rng = random.Random(seed)
    base = (196, 154, 106)
    raw = bytearray(width * height * 3)
    num_planks = 3
    plank_h = height / num_planks
    centers = [
        (0.35, 0.45, 1.4),
        (0.75, 0.52, 1.1),
        (1.20, 0.38, 1.6),
    ]
    for y in range(height):
        plank_idx = int(y / plank_h)
        plank_offset = ((plank_idx * 17 + 5) % 9) - 4
        norm_y = y / height
        for x in range(width):
            norm_x = x / width
            d_center = min(
                math.hypot(norm_x - cx, (norm_y - cy) * 2.8) * scale
                for cx, cy, scale in centers
            )
            wander = 0.012 * math.sin(norm_x * math.pi * 3.0) + 0.006 * math.sin(norm_x * math.pi * 7.5 + norm_y)
            grain_val = (norm_y + wander) * 12.0 + d_center * 8.0
            ring_phase = grain_val * 2.0 * math.pi
            r_major = math.sin(ring_phase)
            r_fine = math.sin(ring_phase * 3.7)
            r_micro = math.sin(ring_phase * 11.3)
            ring_shape = 0.5 * (1.0 - math.cos(ring_phase))
            latewood = math.pow(ring_shape, 2.5) * 28.0 - math.pow(1.0 - ring_shape, 1.8) * 12.0
            shade = latewood + 6.0 * r_fine + 2.5 * r_micro + rng.uniform(-2.0, 2.0) + plank_offset
            if r_major > 0.82:
                shade -= 14.0 * ((r_major - 0.82) / 0.18)
            r = _clamp(base[0] + shade * 0.95)
            g = _clamp(base[1] + shade * 0.86)
            b = _clamp(base[2] + shade * 0.68)
            idx = (y * width + x) * 3
            raw[idx:idx + 3] = bytes((r, g, b))
    image = Image.frombytes("RGB", (width, height), bytes(raw))
    layer = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(layer)
    for _ in range(600):
        u, v = rng.random(), rng.random()
        pore_len = rng.uniform(0.01, 0.06) * width
        y_pos = v * height
        x_pos = u * width
        alpha = rng.randrange(18, 55)
        draw.line([(x_pos, y_pos), (x_pos + pore_len, y_pos + rng.uniform(-0.3, 0.3))],
                  fill=(105, 72, 42, alpha), width=1)
    for _ in range(120):
        rx, ry = rng.randrange(width), rng.randrange(height)
        rlen = rng.uniform(3, 14)
        draw.line([(rx, ry), (rx + rng.uniform(-1, 1), ry + rlen)],
                  fill=(225, 190, 145, rng.randrange(22, 55)), width=1)
    result = Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")
    return result.filter(ImageFilter.GaussianBlur(0.6))


def _daylight(width=1024, height=512):
    """Expansive daytime sky, distant city architecture, and tree canopy."""
    rng = random.Random(6120)
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / height
        if t < 0.55:
            s = t / 0.55
            c1, c2 = (70, 140, 215), (150, 195, 238)
            col = tuple(round(a + (b - a) * s) for a, b in zip(c1, c2))
        else:
            s = (t - 0.55) / 0.45
            c1, c2 = (150, 195, 238), (218, 230, 240)
            col = tuple(round(a + (b - a) * s) for a, b in zip(c1, c2))
        draw.line((0, y, width, y), fill=col)
    cloud_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(cloud_layer)
    for cx, cy, rad in [
        (120, 110, 65), (170, 95, 80), (230, 105, 70), (280, 120, 50),
        (540, 130, 75), (600, 115, 90), (660, 125, 80), (710, 140, 55),
        (880, 100, 60), (930, 90, 70), (980, 110, 55),
    ]:
        for _ in range(8):
            ox = rng.gauss(0, rad * 0.45)
            oy = rng.gauss(0, rad * 0.28)
            r = rng.uniform(rad * 0.6, rad * 1.1)
            alpha = rng.randrange(40, 110)
            for wrap in (0, width, -width):
                wx = cx + ox + wrap
                cdraw.ellipse([wx - r, cy + oy - r * 0.6, wx + r, cy + oy + r * 0.6],
                              fill=(255, 255, 255, alpha))
    cloud_layer = cloud_layer.filter(ImageFilter.GaussianBlur(14.0))
    image = Image.alpha_composite(image.convert("RGBA"), cloud_layer).convert("RGB")
    draw = ImageDraw.Draw(image)
    horizon_y = int(height * 0.68)
    for bx in range(0, width, 18):
        h_ridge = int(horizon_y - rng.uniform(8, 28))
        draw.rectangle([bx, h_ridge, bx + 22, horizon_y], fill=(168, 185, 202))
    building_configs = [
        (20, 55, 110, (135, 150, 165)),
        (70, 40, 85, (155, 168, 180)),
        (120, 70, 140, (120, 138, 155)),
        (185, 45, 95, (160, 172, 185)),
        (240, 80, 125, (130, 145, 160)),
        (330, 60, 160, (115, 130, 148)),
        (385, 50, 105, (150, 165, 178)),
        (445, 75, 135, (125, 142, 158)),
        (530, 55, 90, (165, 175, 185)),
        (595, 85, 150, (118, 135, 152)),
        (690, 65, 115, (140, 155, 170)),
        (765, 50, 80, (170, 180, 190)),
        (825, 90, 145, (122, 140, 156)),
        (925, 70, 120, (138, 152, 168)),
    ]
    for bx, bw, bh, bcol in building_configs:
        by_top = horizon_y - bh
        for wrap in (0, width, -width):
            wx = bx + wrap
            draw.rectangle([wx, by_top, wx + bw, horizon_y + 40], fill=bcol)
            draw.rectangle([wx + int(bw * 0.2), by_top - 12, wx + int(bw * 0.8), by_top],
                           fill=tuple(max(0, c - 20) for c in bcol))
            win_col = (195, 215, 235)
            for wy in range(by_top + 14, horizon_y - 8, 16):
                for wx_sub in range(wx + 8, wx + bw - 8, 12):
                    draw.rectangle([wx_sub, wy, wx_sub + 6, wy + 9], fill=win_col)
    foliage_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    fdraw = ImageDraw.Draw(foliage_layer)
    for _ in range(350):
        tx = rng.randrange(0, width)
        ty = rng.randrange(horizon_y - 12, height + 20)
        radius = rng.randrange(14, 38)
        green_tone = (
            rng.randrange(52, 88),
            rng.randrange(115, 165),
            rng.randrange(55, 95),
            rng.randrange(180, 245)
        )
        for wrap in (0, width, -width):
            wx = tx + wrap
            fdraw.ellipse([wx - radius, ty - radius * 0.7, wx + radius, ty + radius * 0.7], fill=green_tone)
    foliage_layer = foliage_layer.filter(ImageFilter.GaussianBlur(1.8))
    return Image.alpha_composite(image.convert("RGBA"), foliage_layer).convert("RGB")


def _sunset(width=1024, height=512):
    """Dramatic golden-hour twilight sky with lit city office windows."""
    rng = random.Random(6121)
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / height
        if t < 0.45:
            s = t / 0.45
            c1, c2 = (38, 30, 68), (242, 142, 45)
            col = tuple(round(a + (b - a) * s) for a, b in zip(c1, c2))
        elif t < 0.70:
            s = (t - 0.45) / 0.25
            c1, c2 = (242, 142, 45), (215, 68, 38)
            col = tuple(round(a + (b - a) * s) for a, b in zip(c1, c2))
        else:
            s = (t - 0.70) / 0.30
            c1, c2 = (215, 68, 38), (65, 32, 28)
            col = tuple(round(a + (b - a) * s) for a, b in zip(c1, c2))
        draw.line((0, y, width, y), fill=col)
    cloud_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(cloud_layer)
    for cx, cy, rad in [
        (140, 130, 80), (220, 110, 95), (600, 120, 110), (700, 140, 75), (920, 115, 85)
    ]:
        for _ in range(7):
            ox = rng.gauss(0, rad * 0.5)
            oy = rng.gauss(0, rad * 0.25)
            r = rng.uniform(rad * 0.7, rad * 1.2)
            alpha = rng.randrange(35, 95)
            for wrap in (0, width, -width):
                wx = cx + ox + wrap
                cdraw.ellipse([wx - r, cy + oy - r * 0.5, wx + r, cy + oy + r * 0.5],
                              fill=(255, 185, 75, alpha))
                cdraw.ellipse([wx - r * 0.75, cy + oy - r * 0.35, wx + r * 0.75, cy + oy + r * 0.35],
                              fill=(120, 65, 75, int(alpha * 0.8)))
    cloud_layer = cloud_layer.filter(ImageFilter.GaussianBlur(12.0))
    image = Image.alpha_composite(image.convert("RGBA"), cloud_layer).convert("RGB")
    draw = ImageDraw.Draw(image)
    horizon_y = int(height * 0.68)
    building_configs = [
        (20, 55, 110, (52, 35, 45)),
        (70, 40, 85, (62, 40, 50)),
        (120, 70, 140, (45, 30, 40)),
        (185, 45, 95, (58, 38, 48)),
        (240, 80, 125, (48, 32, 42)),
        (330, 60, 160, (40, 26, 36)),
        (385, 50, 105, (55, 36, 46)),
        (445, 75, 135, (46, 30, 40)),
        (530, 55, 90, (60, 40, 50)),
        (595, 85, 150, (42, 28, 38)),
        (690, 65, 115, (50, 34, 44)),
        (765, 50, 80, (64, 42, 52)),
        (825, 90, 145, (44, 29, 39)),
        (925, 70, 120, (52, 35, 45)),
    ]
    for bx, bw, bh, bcol in building_configs:
        by_top = horizon_y - bh
        for wrap in (0, width, -width):
            wx = bx + wrap
            draw.rectangle([wx, by_top, wx + bw, horizon_y + 40], fill=bcol)
            draw.rectangle([wx + int(bw * 0.2), by_top - 12, wx + int(bw * 0.8), by_top],
                           fill=tuple(max(0, c - 10) for c in bcol))
            win_col = (255, 210, 115)
            for wy in range(by_top + 14, horizon_y - 8, 16):
                for wx_sub in range(wx + 8, wx + bw - 8, 12):
                    if rng.random() < 0.65:
                        draw.rectangle([wx_sub, wy, wx_sub + 6, wy + 9], fill=win_col)
    foliage_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    fdraw = ImageDraw.Draw(foliage_layer)
    for _ in range(350):
        tx = rng.randrange(0, width)
        ty = rng.randrange(horizon_y - 12, height + 20)
        radius = rng.randrange(14, 38)
        dark_tone = (
            rng.randrange(28, 45),
            rng.randrange(22, 38),
            rng.randrange(25, 42),
            rng.randrange(200, 255)
        )
        for wrap in (0, width, -width):
            wx = tx + wrap
            fdraw.ellipse([wx - radius, ty - radius * 0.7, wx + radius, ty + radius * 0.7], fill=dark_tone)
    foliage_layer = foliage_layer.filter(ImageFilter.GaussianBlur(1.8))
    return Image.alpha_composite(image.convert("RGBA"), foliage_layer).convert("RGB")


def _plaster():
    """Subtle plaster wall texture with fine grain and faint scuffs."""
    rng = random.Random(30614)
    size = 512
    raw = bytearray(size * size * 3)
    # Slight base plaster tonal variation
    for index in range(0, len(raw), 3):
        variation = rng.uniform(-1.5, 1.5)
        raw[index:index + 3] = bytes(_clamp(c + variation) for c in (226, 226, 221))
    image = Image.frombytes("RGB", (size, size), bytes(raw))
    draw = ImageDraw.Draw(image)
    # Stipple micro-texture
    for _ in range(12000):
        x, y = rng.randrange(size), rng.randrange(size)
        v = rng.randrange(218, 235)
        draw.point((x, y), fill=(v, v, max(0, v - 3)))
    # Faint drywall striae and scuffs
    layer = Image.new("RGBA", image.size)
    ldraw = ImageDraw.Draw(layer)
    for _ in range(40):
        x = rng.randrange(size)
        y = rng.randrange(size)
        length = rng.randrange(10, 45)
        ldraw.line([(x, y), (x + rng.randrange(-5, 6), y + length)], fill=(180, 180, 175, rng.randrange(8, 22)), width=1)
    return Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")


def make_surface_images():
    """Return RGB PIL images ready for OpenGL; no files or network needed."""
    return {
        "floor": _terrazzo(),
        "wood": _oak_wood(1024, 512, seed=612),
        "panel": _grain_image(256, 512, (163, 139, 106), vertical=True, seed=613),
        "plaster": _plaster(),
        "daylight": _daylight(1024, 512),
        "sunset": _sunset(1024, 512),
    }

