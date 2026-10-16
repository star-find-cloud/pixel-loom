"""Parametric pixel VFX compiled into normal editable native layer/cel operations."""
from __future__ import annotations

import colorsys
from copy import deepcopy
import hashlib
import json
import math

from typing_extensions import TypedDict
from typing import Literal

from .model import Document, PixelError, hexcolor, integer, rgba
from .reference import encode_png

PRESETS = {
    "slash": {"label": "弧形斩击", "color": "#48bfff", "loop": False, "frames": 12, "duration_ms": 30,
              "description": "弧光扫过后收窄，保留亮刃与碎光；预览重复单次斩击。"},
    "lightning": {"label": "闪电电弧", "color": "#62baff", "loop": False, "frames": 16, "duration_ms": 40,
                  "description": "电弧向下贯穿，分叉闪烁后消退，留下电火花；预览重复单次放电。"},
    "magic": {"label": "魔法光环", "color": "#b47aff", "loop": True, "frames": 24, "duration_ms": 80,
              "description": "旋转法阵、符文亮线与上浮光点分层，可循环播放。"},
    "fire": {"label": "循环火焰", "color": "#ff743d", "loop": True, "frames": 16, "duration_ms": 80,
             "description": "焰体、亮芯和火星独立分层；轮廓随上升热流变化。"},
    "burst": {"label": "爆炸火花", "color": "#ff9347", "loop": False, "frames": 16, "duration_ms": 40,
              "description": "闪光、膨胀烟团和飞散火星；预览会重复播放单次爆发。"},
}
DEFAULTS = {"preset": "slash", "size": 64, "frames": 12, "duration_ms": 30,
            "strength": 55, "color": "#48bfff", "seed": 0}


class EffectSettings(TypedDict, total=False):
    preset: Literal["slash", "lightning", "magic", "fire", "burst"]
    size: int
    frames: int
    duration_ms: int
    strength: int
    color: str
    seed: int


def settings(value=None):
    if value is not None and (not isinstance(value, dict) or set(value) - set(DEFAULTS)):
        raise PixelError("Unknown effect settings")
    result = {**DEFAULTS, **(value or {})}
    if not isinstance(result["preset"], str) or result["preset"] not in PRESETS:
        raise PixelError("Effect preset must be slash, lightning, magic, fire or burst")
    for key in ("color", "frames", "duration_ms"):
        if not value or key not in value:
            result[key] = PRESETS[result["preset"]][key]
    for key, low, high in (("size", 24, 128), ("frames", 8, 32), ("duration_ms", 30, 500),
                           ("strength", 1, 100), ("seed", 0, 999999)):
        integer(result[key], key, low, high)
    color = rgba(result["color"])
    if color[3] != 255:
        raise PixelError("Choose an opaque effect color; the background remains transparent")
    result["color"] = hexcolor(color)
    return result


def palette(color):
    r, g, b, _ = rgba(color)
    h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    def tone(hue, saturation, brightness):
        return hexcolor((*[round(c * 255) for c in colorsys.hsv_to_rgb(hue % 1, saturation, brightness)], 255))
    return ["#00000000", tone(h - .035, max(.65, s), .63), hexcolor((r, g, b, 255)),
            tone(h + .065, .62, 1), tone(h + .07, .16, 1), "#3d4059ff", "#8b91a5ff",
            tone(h + .012, .69, .83), "#925d63ff"]


def noise(index, seed):
    return math.sin(index * 127.1 + seed * 31.7) * .5 + .5


def empty(size):
    return [[0] * size for _ in range(size)]


def dot(grid, x, y, color, radius=0):
    size = len(grid)
    for yy in range(round(y) - radius, round(y) + radius + 1):
        for xx in range(round(x) - radius, round(x) + radius + 1):
            if 0 <= xx < size and 0 <= yy < size:
                grid[yy][xx] = color


def line(grid, start, end, color, radius=0):
    x, y, x2, y2 = *map(round, start), *map(round, end)
    dx, dy = abs(x2 - x), -abs(y2 - y)
    sx, sy = 1 if x < x2 else -1, 1 if y < y2 else -1
    error = dx + dy
    while True:
        dot(grid, x, y, color, radius)
        if (x, y) == (x2, y2):
            break
        twice = 2 * error
        if twice >= dy:
            error += dy
            x += sx
        if twice <= dx:
            error += dx
            y += sy


def lightning(size, phase, strength, seed):
    arc, core, sparks = empty(size), empty(size), empty(size)
    points = [(size * (.5 + (.045 + strength / 1100) * (noise(i + phase * 64, seed) * 2 - 1)),
               size * (.08 + i * .085)) for i in range(10)]
    points[0], points[-1] = (size * .5, size * .08), (size * .5, size * .845)
    end = min(9, max(1, round(1 + phase * 32)))
    start = min(9, max(0, math.floor((phase - .6) * 29)))
    outer = max(1, round(size * .032))
    middle = max(0, outer - 1)
    def bolt(a, b, width):
        line(arc, a, b, 1, width)
        line(arc, a, b, 2 if phase < .75 else 1, max(0, width - 1))
        line(core, a, b, 4 if phase < .7 else 3)
    for i in range(start, end):
        bolt(points[i], points[i + 1], outer)
    if .16 < phase < .68:
        for i, direction in ((3, -1), (5, 1)):
            if i >= end:
                continue
            x, y = points[i]
            turn = (x + direction * size * .12, y + size * .06)
            tip = (x + direction * size * (.2 + .06 * noise(i, seed)), y + size * .18)
            bolt((x, y), turn, middle)
            bolt(turn, tip, middle)
    if phase > .25:
        radius = size * (.04 + .29 * (phase - .25))
        for i in range(7):
            angle = i * 2.39996 + seed
            x = size * .5 + math.cos(angle) * radius
            y = size * .845 + math.sin(angle) * radius * .46
            dot(sparks, x, y, 4 if phase < .6 else 3)
        if phase < .55:
            line(core, (size * .5 - radius, size * .845), (size * .5 + radius, size * .845), 4)
    return arc, core, sparks


def magic(size, phase, strength, seed):
    ring, runes, sparks = empty(size), empty(size), empty(size)
    cx, cy = size * .5, size * .66
    t = phase * math.tau + seed * .41
    power = .9 + strength / 500
    for radius in (.34, .245):
        points = [(cx + math.cos(i * math.tau / 80) * size * radius * power,
                   cy + math.sin(i * math.tau / 80) * size * radius * .5 * power) for i in range(81)]
        for a, b in zip(points, points[1:]):
            line(ring, a, b, 1, 1 if size >= 48 else 0)
        for a, b in zip(points, points[1:]):
            line(ring, a, b, 2)
    vertices = [(cx + math.cos(i * math.pi / 3 + t / 6) * size * .235 * power,
                 cy + math.sin(i * math.pi / 3 + t / 6) * size * .1175 * power) for i in range(6)]
    for i in range(6):
        line(runes, vertices[i], vertices[(i + 2) % 6], 3)
    for i in range(8):
        angle = i * math.tau / 8 - t / 4
        x = cx + math.cos(angle) * size * .292 * power
        y = cy + math.sin(angle) * size * .146 * power
        tangent = (-math.sin(angle) * size * .026, math.cos(angle) * size * .013)
        line(runes, (x - tangent[0], y - tangent[1] - size * .016),
             (x + tangent[0], y + tangent[1] + size * .016), 4 if i % 2 == 0 else 3)
    for i in range(8):
        age = (phase + i / 8) % 1
        x = cx + math.sin(i * 2.4 + age * 1.6 + seed) * size * (.22 - age * .05)
        y = size * (.62 - age * .53)
        dot(sparks, x, y, 4 if age < .65 else 3)
        if age < .4 and size >= 48:
            dot(sparks, x - 1, y, 3)
            dot(sparks, x + 1, y, 3)
            dot(sparks, x, y - 1, 3)
            dot(sparks, x, y + 1, 3)
    return ring, runes, sparks


def fire(size, phase, strength, seed):
    body, core, sparks = empty(size), empty(size), empty(size)
    t = phase * math.tau + seed * .79
    power = .8 + strength / 250
    base = size * .91
    for y in range(size):
        z = (base - y) / (size * .68 * power)
        if not 0 < z < 1:
            continue
        bottom = math.sin(min(1, z / .2) * math.pi / 2)
        center = size * (.5 + z * (.055 * math.sin(t - 5 * z) + .027 * math.sin(2 * t - 9 * z)))
        width = size * .225 * (1 - z) ** .7 * bottom
        width *= 1 + .19 * math.sin(2 * t - 11 * z) + .1 * math.sin(3 * t + 15 * z)
        # Two secondary tongues grow from the body rather than moving a pasted patch.
        tongues = [(center, width)]
        for side, height, offset in ((-1, .68, .12), (1, .77, .1)):
            u = (z - .12) / height
            if 0 < u < 1:
                tongues.append((center + side * size * offset * math.sin(u * math.pi / 2),
                                size * .087 * math.sin(u * math.pi) ** .8))
        for x in range(size):
            q = min(abs(x - cx) / max(.25, w) for cx, w in tongues)
            if q > 1:
                continue
            body[y][x] = 1 if q > .82 else 2
            u = (base - y) / (size * .43 * power)
            inner_x = size * (.5 + .033 * u * math.sin(t - 7 * u))
            inner_w = size * .12 * max(0, 1 - u) ** .7 * bottom
            if 0 < u < 1 and abs(x - inner_x) < inner_w:
                core[y][x] = 3
                if u < .48 and abs(x - inner_x) < inner_w * .43:
                    core[y][x] = 4
    count = 3 + strength // 20
    for index in range(count):
        age = (phase + index / count + noise(index, seed) * .13) % 1
        if age > .83:
            continue
        x = size * (.36 + .28 * noise(index + 10, seed) + .07 * age * math.sin(t + index))
        y = size * (.44 - .38 * age)
        dot(sparks, x, y, 3 if age > .52 else 4, 0 if age > .5 or size < 64 else 1)
    return body, core, sparks


def burst(size, phase, strength, seed):
    cloud, heat, sparks = empty(size), empty(size), empty(size)
    p = phase
    power = .8 + strength / 250
    spread = size * (.03 + .31 * (1 - (1 - p) ** 2)) * power
    bubble = size * (.1 + .095 * math.sin(min(1, p * 1.8) * math.pi)) * max(.1, 1 - p * .9)
    centers = [(size * .5 + math.cos(i * math.tau / 7 + seed) * spread * (.62 + .38 * noise(i, seed)),
                size * .51 + math.sin(i * math.tau / 7 + seed) * spread * .78 - size * (.05 + .07 * noise(i + 20, seed)) * p)
               for i in range(7)]
    if p < .85:
        for y in range(size):
            for x in range(size):
                distance, index = min(((x - cx) ** 2 + (y - cy) ** 2, i) for i, (cx, cy) in enumerate(centers))
                if distance < bubble * bubble:
                    local = p + .06 * math.sin(index * 2.3)
                    colors = (5, 6) if local > .67 else (5, 8) if local > .53 else (8, 7) if local > .39 else (1, 2)
                    cloud[y][x] = colors[0] if distance > (bubble * .78) ** 2 else colors[1]
                radius = size * .19 * max(0, 1 - p * 1.75)
                if radius > 0 and (x - size * .5) ** 2 + (y - size * .51) ** 2 < radius * radius:
                    heat[y][x] = 4 if p < .15 else 3
    for i in range(10 + strength // 15):
        angle = i * 2.39996 + seed * .9
        radius = size * (.11 + .34 * p) * (.7 + .3 * noise(i + 70, seed))
        x = size * .5 + math.cos(angle) * radius
        y = size * .5 + math.sin(angle) * radius * .88 + size * .11 * p * p
        length = size * .055 * (1 - p)
        for step in range(max(1, round(length))):
            dot(sparks, x - math.cos(angle) * step, y - math.sin(angle) * step, 4 if p < .3 else 3 if p < .8 else 2)
    return cloud, heat, sparks


def slash(size, phase, strength, seed):
    trail, edge, sparks = empty(size), empty(size), empty(size)
    angle = math.radians(-160 + phase * 250 + (noise(0, seed) - .5) * 30)
    length = math.radians(18 + 130 * math.sin(math.pi * min(1, phase / 1.06)))
    radius = size * (.27 + .08 * phase)
    width = size * (.045 + strength / 1400) * max(.17, 1 - phase * .7)
    cx, cy = size * .5, size * .5
    for y in range(size):
        for x in range(size):
            theta = math.atan2((y - cy) / .72, x - cx)
            behind = (angle - theta) % math.tau
            if behind > length:
                continue
            taper = 1 - behind / length
            distance = math.hypot(x - cx, (y - cy) / .72)
            thickness = width * (.15 + .85 * taper)
            if abs(distance - radius) < thickness:
                trail[y][x] = 1 if abs(distance - radius) > thickness * .7 else 2
                if abs(distance - radius) < thickness * .42:
                    edge[y][x] = 4 if taper > .68 else 3
    head_x, head_y = cx + math.cos(angle) * radius, cy + math.sin(angle) * radius * .72
    dot(edge, head_x, head_y, 4)
    for index in range(4):
        a = angle - length * (.25 + index * .21)
        r = radius + size * (.07 + .025 * noise(index, seed)) * phase
        if phase > .15:
            dot(sparks, cx + math.cos(a) * r, cy + math.sin(a) * r * .72, 3)
    return trail, edge, sparks


def make_effect(value=None):
    config = settings(value)
    preset, size, count = config["preset"], config["size"], config["frames"]
    doc = Document(size, size, PRESETS[preset]["label"])
    doc.effect_recipe = {"format": "pixel-loom/effect/v1", "settings": config.copy()}
    colors = palette(config["color"])
    ids = [doc.active_layer, "effect-core", "effect-particles"]
    names = {"fire": ["焰体", "亮芯", "火星"], "burst": ["爆炸与烟团", "闪光", "飞散火星"],
             "lightning": ["电弧", "亮芯", "电火花"], "magic": ["法阵", "符文亮线", "上浮光点"],
             "slash": ["弧光", "亮刃", "碎光"]}[preset]
    ops = [{"op": "palette_set", "colors": colors},
           {"op": "layer_set", "layer": ids[0], "name": names[0]},
           *[{"op": "layer_add", "id": ids[i], "name": names[i]} for i in (1, 2)],
           {"op": "frame_set", "frame": 0, "duration_ms": config["duration_ms"]}]
    render = {"fire": fire, "burst": burst, "slash": slash, "lightning": lightning, "magic": magic}[preset]
    for frame in range(count):
        if frame:
            ops.append({"op": "frame_add", "blank": True, "duration_ms": config["duration_ms"]})
        grids = render(size, frame / count, config["strength"], config["seed"])
        for layer, grid in zip(ids, grids):
            points = [(x, y) for y, row in enumerate(grid) for x, p in enumerate(row) if p]
            if not points:
                continue
            xs, ys = zip(*points)
            left, top, right, bottom = min(xs), min(ys), max(xs) + 1, max(ys) + 1
            rows = ["".join(".abcdefgh"[p] for p in row[left:right]) for row in grid[top:bottom]]
            ops.append({"op": "stamp", "layer": layer, "frame": frame, "x": left, "y": top, "rows": rows,
                        "colors": {c: colors[i] for i, c in enumerate("abcdefgh", 1)}})
    ops += [{"op": "tag_set", "name": preset, "start": 0, "end": count - 1}, {"op": "select", "frame": 0, "layer": ids[0]}]
    doc.apply(ops, "生成像素特效", source="像素特效工具")
    return doc, config


def action(service, payload):
    verb = payload.get("action", "presets")
    if verb == "presets":
        return {"ok": True, "presets": deepcopy(PRESETS), "defaults": DEFAULTS.copy(),
                "limits": {"size": [24, 128], "frames": [8, 32], "duration_ms": [30, 500], "strength": [1, 100]},
                "workflow": "preview -> inspect actual images/timing -> create with observed tokens -> editable independent project -> review/save/export"}
    if verb not in ("preview", "create"):
        raise PixelError("Effect action must be presets, preview or create")
    if verb == "create":
        service.guard(payload)
    value = payload.get("settings")
    if value is None and service.doc.effect_recipe:
        value = service.doc.effect_recipe["settings"]
    doc, config = make_effect(value)
    data = {"ok": True, "settings": config, "effect": {"name": doc.name, "width": doc.width, "height": doc.height,
            "frames": len(doc.durations), "duration_ms": sum(doc.durations), "loop": PRESETS[config["preset"]]["loop"],
            "layers": [layer.name for layer in doc.layers], "editable": True},
            "notice": "参数化像素特效，不调用外部生图；预览是未验收的中间稿。单次特效的预览会重复播放。"}
    if verb == "create":
        name = payload.get("name")
        if name is not None:
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
                raise PixelError("Effect project name must contain 1–120 characters")
            doc.name = name.strip()
        target = service.projects.new_path(doc.name)
        service.checkpoint_current()
        service.replace(doc)
        service.saved_fingerprint = ""
        service.save_project(target)
        data.update(service.state())
    if payload.get("include_images", True):
        data["images_png"] = [encode_png(doc.contact_sheet(columns=8, scale=max(1, min(3, 128 // doc.width))))]
        data["image_roles"] = ["effect_all_frames"]
        folder = service.runtime / "effect-previews"
        folder.mkdir(exist_ok=True)
        key = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:20]
        path = folder / (key + ".gif")
        doc.export(path, "gif", scale=max(1, min(4, 256 // doc.width)))
        data["preview_animation"] = {"path": str(path), "draft": True, "looping_preview": True}
    return data
