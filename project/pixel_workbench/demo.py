"""A hand-authored layered sprite built through the same operation API exposed to AI."""
import json

from .paths import WORKSPACE as ROOT
from .model import Document


def demo_operations():
    ops = [{"op": "layer_set", "name": "地面阴影"},
           {"op": "ellipse", "x": 12, "y": 40, "width": 25, "height": 4, "color": 1},
           {"op": "layer_set", "opacity": 120, "locked": True},
           {"op": "layer_add", "name": "机体", "id": "body"}]

    def rect(x, y, w, h, color, **kwargs):
        ops.append(dict(op="rect", x=x, y=y, width=w, height=h, color=color, **kwargs))

    # Feet, flexible arms and the small tin body.
    rect(15, 37, 8, 5, 1)
    rect(27, 37, 8, 5, 1)
    rect(16, 38, 6, 2, 3)
    rect(28, 38, 6, 2, 3)
    rect(17, 28, 16, 11, 1)
    rect(18, 29, 14, 8, 17)
    rect(18, 29, 3, 7, 18)
    rect(29, 30, 3, 7, 16)
    rect(22, 31, 6, 4, 1)
    rect(23, 32, 4, 2, 13)
    rect(23, 32, 2, 1, 15)
    rect(12, 29, 5, 4, 1)
    rect(10, 30, 5, 6, 1)
    rect(11, 31, 3, 3, 17)
    rect(33, 29, 5, 4, 1)
    rect(36, 28, 4, 7, 1)
    rect(37, 29, 2, 4, 18)
    # Rounded rectangular head, un-smoothed at every edge.
    rect(14, 13, 21, 18, 1)
    rect(12, 15, 25, 14, 1)
    rect(14, 14, 21, 15, 17)
    rect(13, 16, 23, 11, 17)
    rect(14, 14, 20, 2, 18)
    rect(13, 16, 2, 10, 18)
    rect(34, 16, 2, 12, 16)
    rect(15, 27, 19, 2, 16)
    rect(16, 16, 17, 10, 1)
    rect(17, 17, 15, 8, 20)
    rect(17, 17, 15, 1, 2)
    rect(14, 18, 1, 1, 19)
    rect(34, 24, 1, 1, 18)
    rect(15, 28, 1, 1, 4)
    rect(33, 28, 1, 1, 4)
    ops.append({"op": "layer_add", "name": "眼睛与表情", "id": "face"})
    rect(19, 19, 3, 4, 22)
    rect(27, 19, 3, 4, 22)
    rect(19, 19, 2, 2, 23)
    rect(27, 19, 2, 2, 23)
    rect(23, 23, 3, 1, 22)
    ops.append({"op": "layer_add", "name": "嫩芽与火花", "id": "sprout"})
    rect(24, 8, 2, 5, 1)
    rect(24, 8, 1, 4, 17)
    ops += [{"op": "stamp_define", "name": "leaf", "rows": [".ddddd", "dllll.", ".ll..."],
             "colors": {"d": 17, "l": 19}},
            {"op": "stamp", "name": "leaf", "x": 25, "y": 6},
            {"op": "stamp", "rows": ["ddd...", ".llld.", "...ll."], "colors": {"d": 17, "l": 18}, "x": 19, "y": 5},
            {"op": "stamp_define", "name": "spark", "rows": ["..s..", "..s..", "sssss", "..s..", "..s.."], "colors": {"s": 15}},
            {"op": "stamp", "name": "spark", "x": 37, "y": 10},
            {"op": "pixel", "x": 8, "y": 22, "color": 22},
            {"op": "pixel", "x": 9, "y": 23, "color": 23},
            {"op": "region_define", "name": "face", "rect": [17, 18, 15, 7]},
            {"op": "region_define", "name": "sprout", "rect": [18, 4, 15, 9]},
            {"op": "frame_set", "duration_ms": 400},
            {"op": "frame_add", "copy_from": 0, "after": 0, "duration_ms": 300}]
    for layer in ("body", "face", "sprout"):
        ops.append({"op": "translate", "layer": layer, "frame": 1, "dx": 0, "dy": -1})
    ops += [{"op": "frame_add", "copy_from": 0, "after": 1, "duration_ms": 550},
            {"op": "frame_add", "copy_from": 0, "after": 2, "duration_ms": 130},
            {"op": "clear", "layer": "face", "frame": 3},
            {"op": "rect", "layer": "face", "frame": 3, "x": 19, "y": 21, "width": 3, "height": 1, "color": 22},
            {"op": "rect", "layer": "face", "frame": 3, "x": 27, "y": 21, "width": 3, "height": 1, "color": 22},
            {"op": "rect", "layer": "face", "frame": 3, "x": 23, "y": 23, "width": 3, "height": 1, "color": 22},
            {"op": "select", "layer": "face", "frame": 0}]
    return ops


def create_demo():
    target = ROOT / "examples"
    target.mkdir(exist_ok=True)
    doc = Document(48, 48, "苔藓机器人 · 待机")
    ops = demo_operations()
    doc.apply(ops, "绘制四帧苔藓机器人", source="AI")
    doc.save(target / "moss-bot.pixloom")
    doc.preview(scale=10).save(target / "moss-bot-preview.png")
    doc.export(target / "moss-bot-sheet.png", "sheet", columns=4)
    doc.export(target / "moss-bot.gif", "gif", scale=6)
    (target / "draw-moss-bot.json").write_text(json.dumps({"label": "绘制分层苔藓机器人", "ops": ops}, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


if __name__ == "__main__":
    create_demo()
    print("Created examples/moss-bot.pixloom, preview, sheet, GIF and operation recipe.")
