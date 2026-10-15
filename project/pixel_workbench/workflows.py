"""Small, deterministic plans shared by visual workflows and native model edits."""
from __future__ import annotations

import math

from PIL import Image

from .model import Document, PixelError, integer


def symmetric_ops(op, width, height, mode="off"):
    """Reflect supported drawing coordinates; fill and transforms stay single operations."""
    if mode not in ("off", "x", "y", "xy"):
        raise PixelError("Unknown symmetry mode")
    supported = {"pixel", "stroke", "line", "rect", "ellipse", "polygon", "bezier"}
    if mode == "off" or op["op"] not in supported:
        return [op]
    # Reflect the native raster mask, rather than only the center line. Even-width
    # brushes otherwise shift a pixel on the reflected side (Pillow's brush bias).
    renderer = Document(width, height)
    mask = renderer.blank()
    renderer.draw_on(mask, {**op, "color": 7})
    result, seen = [op], {mask.tobytes()}
    for mx, my in [(True, False), (False, True), (True, True)]:
        if mx and "x" not in mode or my and "y" not in mode:
            continue
        reflected = mask
        if mx:
            reflected = reflected.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if my:
            reflected = reflected.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        key = reflected.tobytes()
        if key in seen:
            continue
        seen.add(key)
        box = reflected.getbbox()
        if not box:
            continue
        patch = reflected.crop(box).getchannel("A")
        rows = ["".join("s" if patch.getpixel((x, y)) else "." for x in range(patch.width)) for y in range(patch.height)]
        result.append({"op": "stamp", "x": box[0], "y": box[1], "rows": rows, "colors": {"s": op["color"]},
                       **{k: op[k] for k in ("layer", "frame", "clip") if k in op}})
    return result


def animation_plan(doc, kind, first=0, last=None, count=8, dx=0, dy=2, duration=100, name="loop", color=1):
    """Return an atomic native operation list. No writes, scripts or hidden image replacement."""
    last = len(doc.durations) - 1 if last is None else last
    integer(first, "first", 0, len(doc.durations) - 1)
    integer(last, "last", first, len(doc.durations) - 1)
    integer(duration, "duration", 16, 60_000)
    if kind == "duration":
        return [{"op": "frame_set", "frame": frame, "duration_ms": duration} for frame in range(first, last + 1)]
    if kind == "duplicate":
        return [{"op": "frame_duplicate_range", "start": first, "end": last, "after": last}]
    if kind == "outline":
        return [{"op": "outline", "layer": doc.active_layer, "frame": frame, "color": color} for frame in range(first, last + 1)]
    if kind not in ("float", "travel"):
        raise PixelError("Unknown animation workflow")
    if doc.layer().locked:
        raise PixelError("当前图层已锁定，请先解锁再制作循环")
    integer(count, "count", 2, 32)
    integer(dx, "dx", -512, 512)
    integer(dy, "dy", -512, 512)
    after = len(doc.durations) - 1
    ops = []
    # Every generated cel starts from the same source, so transforms never accumulate.
    for step in range(count):
        frame = after + step + 1
        ops.append({"op": "frame_add", "after": frame - 1, "copy_from": doc.active_frame, "duration_ms": duration})
        if kind == "float":
            phase = math.sin(2 * math.pi * step / count)
            x, y = round(dx * phase), round(dy * phase)
        else:
            x, y = round(dx * step / (count - 1)), round(dy * step / (count - 1))
        if x or y:
            if doc.selection:
                ops.append({"op": "region_transform", "layer": doc.active_layer, "frame": frame,
                            "rect": list(doc.selection), "kind": "translate", "dx": x, "dy": y})
            else:
                ops.append({"op": "translate", "layer": doc.active_layer, "frame": frame, "dx": x, "dy": y})
    if name.strip():
        ops.append({"op": "tag_set", "name": name.strip(), "start": after + 1, "end": after + count,
                    "direction": "pingpong" if kind == "travel" else "forward"})
    if doc.selection:
        ops.append({"op": "selection_set", "rect": list(doc.selection)})
    ops.append({"op": "select", "frame": after + 1})
    return ops
