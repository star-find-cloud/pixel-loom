"""Portable, undoable character specifications; importing never repaints artwork."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from PIL import Image
from typing_extensions import TypedDict

from .model import PixelError, hexcolor, integer, pixels, rgba
from .reference import decoded_asset, encode_png, load_asset, validate_context

VIEWS = ("front", "left", "right", "back")
MAX_BYTES = 26_000_000


class CharacterSettings(TypedDict, total=False):
    name: str
    notes: str
    baseline_y: int
    fixed_regions: list[str]


def asset(image, name="approved-pose.png"):
    import base64
    encoded = encode_png(image)
    return {"name": name, "id": hashlib.sha256(base64.b64decode(encoded)).hexdigest(),
            "size": list(image.size), "original_size": list(image.size),
            "png": encoded, "first_frame_only": False}


def _asset(value):
    if not isinstance(value, dict):
        raise PixelError("Character pose/view must contain an embedded PNG asset")
    value = validate_context({"subject": value})["subject"]
    # References are portable: no machine paths in either platform's syntax.
    if "/" in value["name"] or "\\" in value["name"]:
        raise PixelError("Reference name must be a filename, not a local path")
    return value


def validate_profile(value, width, height):
    if not isinstance(value, dict) or set(value) != {
        "format", "name", "notes", "width", "height", "palette", "baseline_y",
        "pose", "pose_frame", "fixed_parts", "views"
    } or value.get("format") != "pixel-loom/character/v1":
        raise PixelError("Unsupported character specification")
    integer(value["width"], "character width", 1, 512)
    integer(value["height"], "character height", 1, 512)
    if value["width"] != width or value["height"] != height:
        raise PixelError("Character canvas dimensions must match this project", "CHARACTER_SIZE_MISMATCH")
    for key, limit in (("name", 120), ("notes", 2000)):
        if not isinstance(value[key], str) or len(value[key]) > limit or key == "name" and not value[key].strip():
            raise PixelError(f"Invalid character {key}")
    integer(value["baseline_y"], "baseline_y", 0, height)
    integer(value["pose_frame"], "pose_frame", 0, 255)
    palette = value["palette"]
    if not isinstance(palette, list) or not 1 <= len(palette) <= 256:
        raise PixelError("Character palette needs 1–256 colors")
    palette = list(dict.fromkeys(hexcolor(rgba(color)) for color in palette))
    pose = _asset(value["pose"])
    if pose["size"] != [width, height]:
        raise PixelError("Approved pose must use the project canvas dimensions")
    pose_colors = decoded_asset(pose["png"]).getcolors(257)
    if pose_colors is None or any(p[3] and hexcolor(p) not in palette for _, p in pose_colors):
        raise PixelError("Character palette must cover all visible approved-pose colors")
    parts, names = value["fixed_parts"], set()
    if not isinstance(parts, list) or len(parts) > 8:
        raise PixelError("Choose at most eight fixed regions")
    for part in parts:
        if not isinstance(part, dict) or set(part) != {"name", "rect"}:
            raise PixelError("Invalid fixed region")
        name, rect = part["name"], part["rect"]
        if not isinstance(name, str) or not 1 <= len(name) <= 120 or name in names:
            raise PixelError("Fixed region names must be unique")
        names.add(name)
        if not isinstance(rect, list) or len(rect) != 4:
            raise PixelError("Fixed region needs [x,y,width,height]")
        x, y, w, h = [integer(v, "region coordinate", 0, 512) for v in rect]
        if w < 1 or h < 1 or x + w > width or y + h > height:
            raise PixelError("Fixed region must stay inside the canvas")
    if not isinstance(value["views"], dict) or set(value["views"]) - set(VIEWS):
        raise PixelError("Character views: front, left, right, back")
    views = {key: _asset(item) for key, item in value["views"].items()}
    if sum(len(item["png"]) for item in [pose, *views.values()]) > 24_000_000:
        raise PixelError("Character references too large; use smaller reference images")
    return {**deepcopy(value), "pose": pose, "views": views, "palette": palette}


def capture(doc, settings=None):
    image = doc.composite(doc.active_frame)
    bounds = image.getbbox()
    if not bounds:
        raise PixelError("Draw or import a character before saving its pose")
    colors = list(dict.fromkeys(hexcolor(p) for p in pixels(image) if p[3]))
    palette = list(dict.fromkeys(["#00000000", *doc.palette, *colors]))
    if len(palette) > 256:
        palette = ["#00000000", *colors]
    if len(palette) > 256:
        raise PixelError("Reduce the pose to at most 255 visible colors first")
    old = doc.character or {}
    value = {"format": "pixel-loom/character/v1", "name": old.get("name", doc.name),
             "notes": old.get("notes", ""), "width": doc.width, "height": doc.height,
             "palette": palette, "baseline_y": old.get("baseline_y", bounds[3]),
             "pose": asset(image), "pose_frame": doc.active_frame,
             "fixed_parts": deepcopy(old.get("fixed_parts", [])), "views": deepcopy(old.get("views", {}))}
    return configure(doc, value, settings or {})


def configure(doc, value, settings):
    if value is None:
        raise PixelError("Save an approved pose first")
    if not isinstance(settings, dict) or set(settings) - {"name", "notes", "baseline_y", "fixed_regions"}:
        raise PixelError("Unknown character settings")
    value = deepcopy(value)
    for key in ("name", "notes", "baseline_y"):
        if key in settings:
            value[key] = settings[key]
    if "fixed_regions" in settings:
        names = settings["fixed_regions"]
        if not isinstance(names, list) or len(names) > 8 or any(not isinstance(n, str) for n in names):
            raise PixelError("Choose up to eight named regions")
        available = {part["name"]: part["rect"] for part in value["fixed_parts"]}
        available.update(doc.regions)
        if any(name not in available for name in names):
            raise PixelError("Define a named region before protecting it")
        value["fixed_parts"] = [{"name": name, "rect": list(available[name])} for name in dict.fromkeys(names)]
    return validate_profile(value, doc.width, doc.height)


def resized(value, width, height, transform, dx, dy, scale):
    value = deepcopy(value)
    old_h = value["height"]
    pose = decoded_asset(value["pose"]["png"])
    if scale:
        pose = pose.resize((width, height), Image.Resampling.NEAREST)
    else:
        canvas = Image.new("RGBA", (width, height))
        canvas.paste(pose, (dx, dy))
        pose = canvas
    value["pose"] = asset(pose)
    value["fixed_parts"] = [{"name": p["name"], "rect": rect} for p in value["fixed_parts"]
                            if (rect := transform(p["rect"]))]
    baseline = round(value["baseline_y"] * height / old_h) if scale else value["baseline_y"] + dy
    value.update(width=width, height=height, baseline_y=max(0, min(height, baseline)))
    return validate_profile(value, width, height)


def summary(value):
    if not value:
        return {"configured": False, "help": "pixel_character capture saves an approved pose; it never redraws artwork."}
    return {"configured": True, **{key: deepcopy(value[key]) for key in
            ("name", "notes", "width", "height", "palette", "baseline_y", "pose_frame", "fixed_parts")},
            "views": {key: {"name": item["name"], "size": item["size"]} for key, item in value["views"].items()},
            "help": "Inspect approved pose/views before animating. Configure preserves the pose; capture replaces it explicitly."}


def action(service, payload):
    doc, verb = service.doc, payload.get("action", "status")
    if verb in ("save", "load", "reference_load") and not isinstance(payload.get("path"), str):
        raise PixelError("Provide a local file path for this character action")
    if verb not in ("status", "save"):
        if service.view.get("gesture_active"):
            raise PixelError("Finish the active canvas gesture first", "GESTURE_ACTIVE")
        service.guard(payload)
    if verb == "save":
        if not doc.character:
            raise PixelError("No character specification to export")
        path = service.resolve(payload.get("path"))
        if path.suffix.lower() != ".pixelchar":
            raise PixelError("Use the .pixelchar extension")
        if path.exists() and not payload.get("overwrite", False):
            raise PixelError("File exists; choose another name or explicitly allow overwrite")
        from .model import atomic_json
        atomic_json(path, doc.character)
    elif verb != "status":
        value = deepcopy(doc.character)
        if verb == "capture":
            value = capture(doc, payload.get("settings"))
        elif verb == "configure":
            value = configure(doc, value, payload.get("settings") or {})
        elif verb in ("reference_load", "reference_clear"):
            role = payload.get("role", "front")
            if role not in VIEWS or value is None:
                raise PixelError("Save a pose first, then choose front/left/right/back")
            if verb == "reference_load":
                value["views"][role] = load_asset(service.resolve(payload.get("path")))
            else:
                value["views"].pop(role, None)
        elif verb == "load":
            path = service.resolve(payload.get("path"))
            if path.stat().st_size > MAX_BYTES:
                raise PixelError("Character specification exceeds size limit")
            value = validate_profile(json.loads(path.read_text(encoding="utf-8-sig")), doc.width, doc.height)
        elif verb == "clear":
            value = None
        else:
            raise PixelError("Unknown character action")
        doc.apply([{"op": "character_profile", "data": value}], "角色规范", source=payload.get("source", "AI"))
        service.autosave()
    data = {"ok": True, "document_id": doc.id, "revision": doc.revision, "character": summary(doc.character)}
    if verb == "save":
        data["path"] = str(path)
    if payload.get("include_images", True) and doc.character:
        role = payload.get("role", "all")
        if role not in (*VIEWS, "all"):
            raise PixelError("Invalid character view")
        items = [("approved_pose", doc.character["pose"]),
                 *[(key, item) for key, item in doc.character["views"].items() if role in (key, "all")]]
        data["image_roles"] = [key for key, _ in items]
        data["images_png"] = [item["png"] for _, item in items]
    return data
