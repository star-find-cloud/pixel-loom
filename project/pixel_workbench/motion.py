"""Explainable animation suspicions, immutable paged evidence, no automatic erasure."""
from __future__ import annotations

from collections import Counter, OrderedDict
from copy import deepcopy
import math
import statistics
import uuid

from PIL import Image, ImageChops, ImageDraw

from .model import Document, PixelError, integer, pixels, rgba
from .reference import decoded_asset, encode_png


def difference(a, b):
    bands = ImageChops.difference(a, b).split()
    mask = bands[0]
    for band in bands[1:]:
        mask = ImageChops.lighter(mask, band)
    return mask


def rect_of(points):
    xs, ys = zip(*points)
    return [min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1]


def box_rect(box):
    return [box[0], box[1], box[2] - box[0], box[3] - box[1]]


def components(image):
    width, height = image.size
    occupied = {i for i, alpha in enumerate(pixels(image.getchannel("A"))) if alpha}
    found = []
    while occupied:
        seed = occupied.pop()
        todo, part = [seed], []
        while todo:
            index = todo.pop()
            x, y = index % width, index // width
            part.append((x, y))
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = ny * width + nx
                    if neighbor in occupied:
                        occupied.remove(neighbor)
                        todo.append(neighbor)
        found.append(part)
    return sorted(found, key=lambda p: (-len(p), min(p)))


def repair_ops(doc, frame, points):
    ops = []
    for layer in doc.layers:
        if not layer.visible or not layer.opacity:
            continue
        affected = [(x, y) for x, y in points if layer.cels[frame].getpixel((x, y))[3]]
        if affected and layer.locked:
            return [], "可见像素来自锁定图层，请先人工核对。"
        ops.extend({"op": "pixel", "x": x, "y": y, "color": "#00000000", "layer": layer.id,
                    "frame": frame, "clip": [x, y, 1, 1]} for x, y in sorted(affected))
    return ops, "只清理这些坐标的可见图层像素；先观察，再决定是否应用。"


def analyze_motion(doc, tag=None, mode="general"):
    if mode not in ("general", "grounded"):
        raise PixelError("mode must be general or grounded")
    frames = list(range(len(doc.durations)))
    if tag is not None:
        if tag not in doc.tags:
            raise PixelError("Unknown animation tag")
        frames = list(range(doc.tags[tag]["start"], doc.tags[tag]["end"] + 1))
    images = {frame: doc.composite(frame) for frame in frames}
    profile = doc.character
    pose = decoded_asset(profile["pose"]["png"]) if profile else images[frames[0]]
    persistent = {frozenset(part) for part in components(pose) if len(part) <= 3}
    findings = []
    dropped = 0

    def add(kind, frame, rect, message, **data):
        nonlocal dropped
        if len(findings) >= 2048:
            dropped += 1
            return
        findings.append({"id": f"finding-{len(findings) + 1}", "kind": kind, "frame": frame,
                         "rect": rect, "message": message, **data})

    allowed = {rgba(color) for color in profile["palette"]} if profile else None
    for frame, image in images.items():
        bounds = image.getbbox()
        if not bounds:
            add("empty_frame", frame, [0, 0, doc.width, doc.height], "此帧为空，请核对是否有意留空。")
            continue
        parts = components(image)
        if len(parts[0]) >= 16:
            for part in parts[1:]:
                if len(part) <= 3 and frozenset(part) not in persistent:
                    ops, note = repair_ops(doc, frame, part)
                    add("orphan_pixels", frame, rect_of(part), "新增的独立小块，可能是残点，也可能是装饰或粒子。",
                        pixel_count=len(part), repair_ops=ops, repair_note=note)
        if profile:
            for part in profile["fixed_parts"]:
                x, y, w, h = part["rect"]
                diff = difference(pose.crop((x, y, x + w, y + h)), image.crop((x, y, x + w, y + h)))
                if (box := diff.getbbox()):
                    add("fixed_region", frame, [x + box[0], y + box[1], box[2] - box[0], box[3] - box[1]],
                        f'固定部位「{part["name"]}」与基准造型不同；核对是否是有意运动。', region=part["name"])
            colors = image.getcolors(257)
            conforms = colors is not None and all(not p[3] or p in allowed for _, p in colors)
            outside = [] if conforms else [(i % doc.width, i // doc.width) for i, p in enumerate(pixels(image))
                                           if p[3] and p not in allowed]
            if outside:
                add("palette_drift", frame, rect_of(outside), "出现角色规范以外的颜色，请核对混色或改色。", pixel_count=len(outside))
            if mode == "grounded" and bounds[3] != profile["baseline_y"]:
                add("baseline", frame, [bounds[0], max(0, bounds[3] - 2), bounds[2] - bounds[0], min(2, bounds[3])],
                    "轮廓底边偏离落地基准；请核对脚底、披风或有意跳跃。",
                    expected_y=profile["baseline_y"], actual_y=bounds[3])
    if len(frames) > 2:
        pairs = [(frames[i - 1], frame) for i, frame in enumerate(frames)]
        changes = [(a, b, difference(images[a], images[b])) for a, b in pairs]
        counts = [sum(1 for p in pixels(diff) if p) for _, _, diff in changes]
        typical = statistics.median(counts)
        for (a, b, diff), count in zip(changes, counts):
            if count > max(12, typical * 2.5):
                add("loop_jump" if b == frames[0] else "abrupt_change", b, box_rect(diff.getbbox()),
                    "相邻帧变化明显高于本段通常幅度，请看前后帧和播放节奏。",
                    previous_frame=a, changed_pixels=count, typical_changed_pixels=typical)
    return {"frames": frames, "mode": mode, "tag": tag, "findings": findings,
            "counts": dict(Counter(f["kind"] for f in findings)), "omitted_findings": dropped,
            "notice": "这些是待观察的线索，不是缺陷判决。逐帧和播放复核；未选中前不会删除像素。",
            "baseline_available": bool(profile), "scanned_frames": len(frames)}


def evidence(doc, frames, finding):
    index = frames.index(finding["frame"])
    selected = [frames[(index - 1) % len(frames)], finding["frame"], frames[(index + 1) % len(frames)]]
    x, y, w, h = finding["rect"]
    margin = max(4, min(16, max(w, h) // 4))
    left, top = max(0, x - margin), max(0, y - margin)
    right, bottom = min(doc.width, x + w + margin), min(doc.height, y + h + margin)
    scale = max(1, min(12, 300 // max(right - left, bottom - top)))
    size = ((right - left) * scale, (bottom - top) * scale)
    result = Image.new("RGB", (size[0] * 3, size[1] + 24), "#1a1f2b")
    draw = ImageDraw.Draw(result)
    for i, frame in enumerate(selected):
        crop = doc.composite(frame).crop((left, top, right, bottom)).resize(size, Image.Resampling.NEAREST)
        checker = Image.new("RGBA", size, "#303a4d")
        grid = ImageDraw.Draw(checker)
        cell = max(4, scale * 2)
        for cy in range(0, size[1], cell):
            for cx in range(0, size[0], cell):
                if (cx // cell + cy // cell) % 2:
                    grid.rectangle((cx, cy, cx + cell - 1, cy + cell - 1), fill="#252d3d")
        checker.alpha_composite(crop)
        result.paste(checker.convert("RGB"), (i * size[0], 24))
        draw.text((i * size[0] + 3, 4), f'{("PREV", "CURRENT", "NEXT")[i]} F{frame + 1}', fill="white")
        if i == 1:
            draw.rectangle((i * size[0] + (x - left) * scale, 24 + (y - top) * scale,
                            i * size[0] + (x + w - left) * scale - 1, 24 + (y + h - top) * scale - 1), outline="#ffb56b", width=1)
    return encode_png(result)


class MotionManager:
    def __init__(self):
        self.reports = OrderedDict()

    def check(self, doc, payload):
        from .quality import content_digest
        report_id = payload.get("report_id")
        if report_id:
            ticket = self.reports.get(report_id)
            if not ticket or ticket["document_id"] != doc.id or ticket["digest"] != content_digest(doc):
                raise PixelError("Artwork changed or report expired; run pixel_motion_check again", "MOTION_STALE")
        else:
            clone = Document.from_dict(doc.to_dict())
            report = analyze_motion(clone, payload.get("tag"), payload.get("mode", "general"))
            report_id = uuid.uuid4().hex
            ticket = {"document_id": doc.id, "digest": content_digest(doc), "doc": clone, "report": report}
            self.reports[report_id] = ticket
            while len(self.reports) > 2:
                self.reports.popitem(last=False)
        report = ticket["report"]
        pages = max(1, math.ceil(len(report["findings"]) / 3))
        page = integer(payload.get("page", 0), "page", 0, pages - 1)
        findings = deepcopy(report["findings"][page * 3:page * 3 + 3])
        return {"ok": True, "report_id": report_id, "document_id": doc.id, "revision": doc.revision,
                **{k: v for k, v in report.items() if k != "findings"},
                "page": page, "pages": pages, "total_findings": len(report["findings"]), "findings": findings,
                "images_png": [evidence(ticket["doc"], report["frames"], finding) for finding in findings],
                "image_roles": [finding["id"] for finding in findings],
                "next": "Read every page and inspect images. Apply only chosen repair_ops through pixel_validate/pixel_edit using current document tokens; then recheck and pixel_review."}
