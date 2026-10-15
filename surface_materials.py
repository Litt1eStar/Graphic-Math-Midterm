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
    size = 512
    raw = bytearray(size * size * 3)
    for index in range(0, len(raw), 3):
        variation = rng.uniform(-2.0, 2.0)
        raw[index:index + 3] = bytes(_clamp(c + variation) for c in (194, 195, 189))
    image = Image.frombytes("RGB", (size, size), bytes(raw))
    draw = ImageDraw.Draw(image)
    # Fine light aggregate dominates. Dark pieces are sparse enough to avoid
    # the salt-and-pepper screen-noise look of the earlier floor material.
    for _ in range(19000):
        x, y = rng.randrange(size), rng.randrange(size)
        value = rng.randrange(176, 220)
        draw.point((x, y), fill=(value, value + 1, max(0, value - 5)))
    for _ in range(3300):
        x, y = rng.randrange(size), rng.randrange(size)
        radius = rng.choices((1, 2, 3, 4), (55, 30, 12, 3))[0]
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


def _daylight():
    """A soft generic outside view; it makes clear glass read as clear glass."""
    rng = random.Random(6120)
    width = height = 512
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = min(1., y / (height * .72))
        colour = tuple(round(a + (b - a) * t) for a, b in
                       zip((184, 208, 218), (235, 237, 223)))
        draw.line((0, y, width, y), fill=colour)
    # Distant low-contrast campus-like masses with restrained glazing bands.
    for x, top, breadth in ((-38, 242, 153), (115, 274, 120), (309, 229, 233)):
        draw.rectangle((x, top, x + breadth, 480), fill=(216, 219, 210))
        draw.rectangle((x - 3, top, x + breadth + 3, top + 7), fill=(226, 228, 219))
        for yy in range(top + 23, 445, 39):
            draw.rectangle((x + 12, yy, x + breadth - 12, yy + 15), fill=(169, 185, 183))
            for xx in range(x + 22, x + breadth - 10, 22):
                draw.line((xx, yy, xx, yy + 15), fill=(210, 215, 205), width=3)
    # Muted planting below the view line, not an invented named landscape.
    for _ in range(220):
        x = rng.randrange(-40, 540)
        y = rng.randrange(355, 540)
        radius = rng.randrange(12, 35)
        offset = rng.randrange(-12, 13)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                     fill=(143 + offset, 166 + offset, 128 + offset))
    return image.filter(ImageFilter.GaussianBlur(2.3))


def _sunset():
    """A warm golden-hour sunset view for dramatic low-angle window lighting."""
    rng = random.Random(6121)
    width = height = 512
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        # Two-stage gradient: twilight purple/indigo at top -> golden amber at horizon -> warm crimson at base
        if y < height * 0.65:
            t = y / (height * 0.65)
            # (46, 38, 72) -> (245, 148, 52)
            c1, c2 = (46, 38, 72), (245, 148, 52)
            colour = tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))
        else:
            t = (y - height * 0.65) / (height * 0.35)
            # (245, 148, 52) -> (175, 62, 45)
            c1, c2 = (245, 148, 52), (175, 62, 45)
            colour = tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))
        draw.line((0, y, width, y), fill=colour)
    # Low-contrast distant campus silhouettes backlit by sunset
    for x, top, breadth in ((-38, 246, 153), (115, 278, 120), (309, 235, 233)):
        draw.rectangle((x, top, x + breadth, 480), fill=(65, 48, 56))
        draw.rectangle((x - 3, top, x + breadth + 3, top + 6), fill=(78, 56, 64))
        for yy in range(top + 23, 445, 39):
            draw.rectangle((x + 12, yy, x + breadth - 12, yy + 15), fill=(95, 68, 62))
            for xx in range(x + 22, x + breadth - 10, 22):
                draw.line((xx, yy, xx, yy + 15), fill=(195, 120, 70), width=2)
    # Muted dark foliage below the horizon
    for _ in range(220):
        x = rng.randrange(-40, 540)
        y = rng.randrange(355, 540)
        radius = rng.randrange(12, 35)
        offset = rng.randrange(-8, 9)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                     fill=(52 + offset, 44 + offset, 40 + offset))
    return image.filter(ImageFilter.GaussianBlur(2.0))


def make_surface_images():
    """Return RGB PIL images ready for OpenGL; no files or network needed."""
    return {
        "floor": _terrazzo(),
        "wood": _grain_image(512, 256, (208, 185, 145), seed=612),
        "panel": _grain_image(256, 512, (163, 139, 106), vertical=True, seed=613),
        "daylight": _daylight(),
        "sunset": _sunset(),
    }

