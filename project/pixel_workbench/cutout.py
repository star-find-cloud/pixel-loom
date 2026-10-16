"""Local, non-generative color matting. Original reference pixels are never replaced."""
from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
from functools import lru_cache
import json
import time
import uuid
from typing_extensions import TypedDict

from PIL import Image, ImageChops, ImageDraw

from .model import PixelError, integer, rgba


class CutoutSettings(TypedDict, total=False):
    background_color: str | None
    points: list[list[int]]
    tolerance: int
    softness: int
    connected: bool
    protect_regions: list[list[int]]
    keep_polygons: list[list[list[int]]]
    remove_polygons: list[list[list[int]]]


DEFAULTS = {"background_color": None, "points": [], "tolerance": 24, "softness": 0,
            "connected": True, "protect_regions": [], "keep_polygons": [], "remove_polygons": []}


def validate_settings(settings, size):
    if not isinstance(settings, dict) or set(settings) - set(DEFAULTS):
        raise PixelError("Unknown cutout settings; read pixel_help(topic='cutout')")
    result = {**deepcopy(DEFAULTS), **deepcopy(settings)}
    integer(result["tolerance"], "tolerance", 0, 120)
    integer(result["softness"], "softness", 0, 40)
    if not isinstance(result["connected"], bool):
        raise PixelError("connected must be boolean")
    if result["background_color"] is not None:
        color = rgba(result["background_color"])
        if color[3] != 255:
            raise PixelError("Background color must be opaque")
        result["background_color"] = "#" + "".join(f"{c:02x}" for c in color[:3])
    width, height = size

    def point(value):
        if not isinstance(value, list) or len(value) != 2:
            raise PixelError("Cutout points must be [x,y] in stored source pixels")
        integer(value[0], "point.x", 0, width - 1)
        integer(value[1], "point.y", 0, height - 1)

    if not isinstance(result["points"], list) or len(result["points"]) > 16:
        raise PixelError("Use at most 16 background seed points")
    for value in result["points"]:
        point(value)
    if not isinstance(result["protect_regions"], list) or len(result["protect_regions"]) > 32:
        raise PixelError("Use at most 32 protected rectangles")
    for rect in result["protect_regions"]:
        if not isinstance(rect, list) or len(rect) != 4:
            raise PixelError("Protected rectangles use [x,y,width,height]")
        x, y, w, h = rect
        integer(x, "rect.x", 0, width - 1)
        integer(y, "rect.y", 0, height - 1)
        integer(w, "rect.width", 1, width)
        integer(h, "rect.height", 1, height)
        if x + w > width or y + h > height:
            raise PixelError("Protected rectangle extends outside the source")
    for key in ("keep_polygons", "remove_polygons"):
        if not isinstance(result[key], list) or len(result[key]) > 16:
            raise PixelError("Use at most 16 polygons per mask role")
        for polygon in result[key]:
            if not isinstance(polygon, list) or not 3 <= len(polygon) <= 128:
                raise PixelError("Mask polygons need 3–128 vertices")
            for value in polygon:
                point(value)
    return result


def auto_background(image):
    """Dominant border cluster, rather than a corner that may contain the subject."""
    w, h = image.size
    xy = [(x, 0) for x in range(w)] + [(x, h-1) for x in range(w)]
    xy += [(0, y) for y in range(1, h-1)] + [(w-1, y) for y in range(1, h-1)]
    colors = [image.getpixel(p)[:3] for p in xy if image.getpixel(p)[3] >= 128]
    if not colors:
        return None, 0.0
    counts = Counter(tuple(v // 16 for v in color) for color in colors)
    group, count = counts.most_common(1)[0]
    matching = [c for c in colors if tuple(v // 16 for v in c) == group]
    color = tuple(sorted(c[i] for c in matching)[len(matching)//2] for i in range(3))
    return color, round(count / len(colors), 4)


def connected_mask(allowed, seeds):
    """Scanline flood fill: bounded memory even for a million-pixel background."""
    width, height = allowed.size
    eligible = bytearray(allowed.tobytes())
    found = bytearray(width * height)
    queue = deque(y * width + x for x, y in seeds)
    while queue:
        pos = queue.popleft()
        if not eligible[pos]:
            continue
        row = pos // width
        lo, hi = row * width, (row + 1) * width
        left, right = pos, pos + 1
        while left > lo and eligible[left-1]:
            left -= 1
        while right < hi and eligible[right]:
            right += 1
        eligible[left:right] = b"\0" * (right-left)
        found[left:right] = b"\xff" * (right-left)
        for offset in (-width, width):
            if not 0 <= left + offset < width * height:
                continue
            index, end = left + offset, right + offset
            while index < end:
                if eligible[index]:
                    queue.append(index)
                    while index < end and eligible[index]:
                        index += 1
                index += 1
    return Image.frombytes("L", allowed.size, bytes(found))


def render(image, settings):
    settings = validate_settings(settings, image.size)
    source = image.convert("RGBA")
    width, height = source.size
    auto, confidence = auto_background(source)
    colors = []
    if settings["background_color"]:
        colors.append(rgba(settings["background_color"])[:3])
    colors += [source.getpixel(tuple(point))[:3] for point in settings["points"]
               if source.getpixel(tuple(point))[3]]
    if not colors and auto is not None:
        colors.append(auto)
    colors = list(dict.fromkeys(colors))
    protected = Image.new("L", source.size)
    draw = ImageDraw.Draw(protected)
    for x, y, w, h in settings["protect_regions"]:
        draw.rectangle((x, y, x+w-1, y+h-1), fill=255)
    for polygon in settings["keep_polygons"]:
        draw.polygon([tuple(p) for p in polygon], fill=255)
    distances = Image.new("L", source.size, 255)
    rgb = source.convert("RGB")
    for color in colors:
        channels = ImageChops.difference(rgb, Image.new("RGB", source.size, color)).split()
        distance = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
        distances = ImageChops.darker(distances, distance)
    tolerance, softness = settings["tolerance"], settings["softness"]
    boundary = min(255, tolerance + softness)
    allowed = distances.point(lambda v: 255 if v <= boundary else 0)
    # Existing transparency connects separated border regions, without sampling its RGB.
    allowed = ImageChops.lighter(allowed, source.getchannel("A").point(lambda v: 255 if v == 0 else 0))
    allowed = ImageChops.subtract(allowed, protected)
    seeds = [tuple(p) for p in settings["points"]]
    if not settings["points"] or settings["background_color"]:
        seeds += [(x, 0) for x in range(width)] + [(x, height-1) for x in range(width)]
        seeds += [(0, y) for y in range(1, height-1)] + [(width-1, y) for y in range(1, height-1)]
    selected = connected_mask(allowed, seeds) if settings["connected"] else allowed
    forced = Image.new("L", source.size)
    draw = ImageDraw.Draw(forced)
    for polygon in settings["remove_polygons"]:
        draw.polygon([tuple(p) for p in polygon], fill=255)
    selected = ImageChops.lighter(selected, forced)
    selected = ImageChops.subtract(selected, protected)  # Explicit keep always wins.
    distance_data, selected_data, forced_data = distances.tobytes(), selected.tobytes(), forced.tobytes()
    raw = bytearray(source.tobytes())
    removed = bytearray(width * height)
    changed = soft_pixels = 0
    for i, chosen in enumerate(selected_data):
        if not chosen:
            continue
        k = i * 4
        old_alpha = raw[k+3]
        if not old_alpha:
            continue
        fraction = 0.0 if forced_data[i] or distance_data[i] <= tolerance else (
            min(1.0, (distance_data[i] - tolerance) / softness) if softness else 1.0)
        new_alpha = round(old_alpha * fraction)
        if new_alpha == old_alpha:
            continue
        changed += 1
        removed[i] = old_alpha - new_alpha
        if new_alpha == 0:
            raw[k:k+4] = b"\0\0\0\0"
        else:
            soft_pixels += 1
            # Unmatte newly softened edges to reduce a white/green background fringe.
            if colors:
                pixel = tuple(raw[k:k+3])
                bg = min(colors, key=lambda c: max(abs(pixel[j]-c[j]) for j in range(3)))
                for j in range(3):
                    raw[k+j] = max(0, min(255, round((pixel[j] - (1-fraction)*bg[j]) / fraction)))
            raw[k+3] = new_alpha
    output = Image.frombytes("RGBA", source.size, bytes(raw))
    visible = sum(1 for a in source.getchannel("A").tobytes() if a)
    warnings = []
    if not settings["points"] and not settings["background_color"] and confidence < 0.35:
        warnings.append("边缘颜色较杂，自动取色不可靠；请点选背景或使用保护/蒙版。")
    if visible and changed / visible > 0.95:
        warnings.append("超过95%的可见像素受影响，请检查是否误删主体，降低强度或添加保护区域。")
    if not changed:
        warnings.append("没有找到可去除的背景；可点选背景、调整强度或为封闭空隙添加取样点。")
    stats = {"changed_pixels": changed, "softened_pixels": soft_pixels,
             "affected_fraction": round(changed / visible, 4) if visible else 0,
             "background_colors": ["#"+"".join(f"{v:02x}" for v in c) for c in colors],
             "auto_border_confidence": confidence, "warnings": warnings,
             "method": "local_color_connected_mask", "semantic_segmentation": False}
    return output, Image.frombytes("L", source.size, bytes(removed)), stats


@lru_cache(maxsize=4)
def rendered(encoded, settings_json):
    from .reference import decoded_asset
    return render(decoded_asset(encoded), json.loads(settings_json))[0]


def cutout_subject(asset, settings):
    return rendered(asset["png"], json.dumps(settings, sort_keys=True)).copy()


HELP = {"topic": "cutout", "method": "Local color/connected background removal; no semantic model, network or API key.",
        "when_to_use": "OPTIONAL. Only for a real background-removal request or a task clearly requiring an isolated transparent source. Importing/converting an image alone is not permission to remove its background. Skip already-transparent sources and unrelated artwork; do not make this a mandatory creation step.",
        "workflow": ["pixel_reference_setup(action='load', role='subject')", "pixel_cutout_preview(settings=...) → inspect ALL original/result/mask images",
                     "Adjust tolerance/points/protect_regions or polygons and preview again", "pixel_cutout(action='apply', preview_id=...) with the latest three observed tokens",
                     "Optional undo/redo/reset or export transparent reference PNG; pixel_redraw_begin uses the applied cutout"],
        "coordinates": "Stored, EXIF-normalized reference pixels, at most 1024 per side. NOT pixel canvas coordinates. Rectangles [x,y,width,height].",
        "settings": DEFAULTS, "ranges": {"tolerance": [0,120], "softness": [0,40], "points": "0–16 [x,y] seeds; each also samples background RGB",
            "protect_regions": "0–32 rectangles", "keep_polygons": "0–16 polygons with 3–128 vertices", "remove_polygons": "0–16 polygons; explicit keep wins"},
        "behavior": "Original subject never changes. Every preview recomputes from it, including after apply. Default removes only connected background; click isolated holes with additional seeds. Preview is read-only and expires after 5 minutes. Apply requires the inspected preview_id. Undo/redo are specific to cutout settings and never undo unrelated artwork. Original file is untouched; saved draft projects embed original plus applied settings. Already-painted canvas pixels never change.",
        "limits": "Best for solid/simple backgrounds. Similar foreground/background colors, hair, glass, shadows and busy scenes require protection/masks; do not claim automatic semantic or hair-level matting. Imported references use existing 1024px limit; PNG export is at stored resolution. Animated imports process first frame only.",
        "discovery": "pixel_reference(view='status') reports current settings and cutout undo/redo availability."}
HELP["adjustment"] = "settings is a partial patch over the currently applied settings, or base_preview_id's settings when supplied. Without either, defaults apply. Passing empty points/protect_regions/polygons explicitly clears them. base_preview_id must still match all observed tokens. Every render uses original pixels, never a previously cut result."
HELP["decision_guide"] = [
    "First read source size, original transparency and current cutout status. Do not use pixel-canvas coordinates.",
    "Solid/simple background: start connected=true, modest tolerance, softness=0 for crisp pixels. Inspect the result and mask, not only changed-pixel counts.",
    "Remaining background: increase tolerance modestly or add seeds in enclosed holes; pass base_preview_id to retain other adjustments.",
    "Missing clothing/details: lower tolerance or protect_regions/keep_polygons; connected=false removes interior matching colors too.",
    "Soft color fringe: try small softness and inspect against checker/light/dark backgrounds; do not erase intentional pale details.",
    "Busy background or subject-colored edges: use explicit remove/keep polygons or tell the human the current local method cannot isolate it reliably. This tool never infers semantic subjects.",
    "Apply exactly the inspected preview_id, then re-read returned tokens. Source PNG export is not an artistic quality review or permission to redraw."]


class CutoutManager:
    def __init__(self):
        self.tickets = {}
        self.key = None
        self.undo = []
        self.redo = []

    def sync(self, document_id, context):
        key = (document_id, (context.get("subject") or {}).get("id"))
        current = context.get("cutout")
        if key != self.key or (self.undo and self.undo[-1][1] != current) or (self.redo and self.redo[-1][0] != current):
            self.undo.clear()
            self.redo.clear()
        self.key = key

    def status(self, document_id, context):
        self.sync(document_id, context)
        return {"applied": context.get("cutout") is not None, "settings": deepcopy(context.get("cutout")),
                "can_undo": bool(self.undo), "can_redo": bool(self.redo), "original_preserved": True,
                "method": "local_color_connected_mask", "help": "pixel_help(topic='cutout')"}

    def preview(self, document_id, revision, reference_revision, asset, settings):
        settings = validate_settings(settings, asset["size"])
        from .reference import decoded_asset
        output, mask, stats = render(decoded_asset(asset["png"]), settings)
        ticket_id = uuid.uuid4().hex
        self.tickets = {k:v for k,v in self.tickets.items() if time.monotonic()-v["time"] < 300}
        while len(self.tickets) >= 4:
            self.tickets.pop(next(iter(self.tickets)))
        ticket = {"time": time.monotonic(), "document_id": document_id, "revision": revision,
                  "reference_revision": reference_revision, "source_id": asset["id"], "settings": settings,
                  "output": output, "mask": mask, "stats": stats}
        self.tickets[ticket_id] = ticket
        return ticket_id, ticket

    def ticket(self, ticket_id, document_id, revision, reference_revision, source_id):
        ticket = self.tickets.get(ticket_id)
        if not ticket or time.monotonic()-ticket["time"] >= 300:
            raise PixelError("Cutout preview expired; preview and inspect again", code="CUTOUT_PREVIEW_REQUIRED")
        if (ticket["document_id"], ticket["revision"], ticket["reference_revision"], ticket["source_id"]) != (document_id, revision, reference_revision, source_id):
            raise PixelError("Reference or artwork changed; preview the cutout again", code="CUTOUT_PREVIEW_STALE")
        return ticket
