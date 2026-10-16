"""Task-independent creation guidance served through MCP, without artwork presets."""
from pathlib import Path

from . import __version__

GUIDE_DIR = Path(__file__).with_name("resources")
TOPICS = {
    "workflow": ("CREATION_WORKFLOW.md", "Design, native drawing and iteration"),
    "animation_workflow": ("ANIMATION_WORKFLOW.md", "Layers, motion planning and clean frames"),
    "inspection_workflow": ("INSPECTION_WORKFLOW.md", "Visual evidence, repairs and delivery"),
}


def workflow_entry():
    """Keep discovery compact; detailed guidance is fetched explicitly via tools."""
    return {
        "read_next": {"tool": "pixel_help", "arguments": {"topic": "workflow"}},
        "details": [{"tool": "pixel_help", "arguments": {"topic": topic}} for topic in TOPICS if topic != "workflow"],
        "resource": "pixel-loom://workflow",
        "stages": [
            "Read current art and the human's task; preserve existing projects.",
            "Define size, palette, viewpoint, timing, fixed/moving parts and acceptance requirements.",
            "Design silhouette and large color groups; split static and moving layers.",
            "Draw native operations in coherent batches and inspect actual previews.",
            "Compute task-specific motion if useful; rebuild clean moving cels rather than accumulating old pixels.",
            "Inspect all frames, local details, actual timing and loop seams; repair and obtain new evidence.",
            "Submit specific visual findings, save the editable project and verify final exports.",
        ],
        "capabilities": {
            "vision": "The host AI must actually view returned images to judge appearance. Text metrics alone are insufficient.",
            "computation": "Optional host-side Python/JavaScript can calculate coordinates and native ops. Pixel Loom does not execute arbitrary host code.",
        },
        "scope": "General methods, not finished-art presets. The connected AI designs each task; documentation cannot guarantee every model's artistic quality.",
    }


def workflow_help(topic="workflow"):
    if topic not in TOPICS:
        raise ValueError(f"Unknown creation guide topic: {topic}")
    filename, title = TOPICS[topic]
    return {
        "topic": topic,
        "application_version": __version__,
        "title": title,
        "guide": (GUIDE_DIR / filename).read_text(encoding="utf-8"),
        "related": [{"tool": "pixel_help", "arguments": {"topic": other}} for other in TOPICS if other != topic],
        "operation_help": "pixel_help(operation='<observed operation name>') returns exact current schemas.",
    }


def workflow_resource():
    return {topic: workflow_help(topic) for topic in TOPICS}
