"""Install-location-independent application and workspace paths."""
from __future__ import annotations

import os
from pathlib import Path
import sys

PACKAGE = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE.parent


def user_data_dir():
    override = os.environ.get("PIXEL_LOOM_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return base / "PixelLoom"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PixelLoom"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "pixel-loom"


DATA_HOME = user_data_dir()
RUNTIME = DATA_HOME / "runtime"
SESSION = RUNTIME / "session.json"
WORKSPACE = Path(os.environ.get("PIXEL_LOOM_WORKSPACE", str(DATA_HOME / "workspace"))).expanduser().resolve()


def prepare():
    for path in (DATA_HOME, RUNTIME, WORKSPACE, WORKSPACE / "projects", WORKSPACE / "exports", RUNTIME / "recovery"):
        path.mkdir(parents=True, exist_ok=True)


def resolve_workspace_path(value):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else WORKSPACE / path).resolve()


def description():
    return {"workspace": str(WORKSPACE), "projects": str(WORKSPACE / "projects"),
            "exports": str(WORKSPACE / "exports"), "recovery": str(RUNTIME / "recovery"),
            "data_home": str(DATA_HOME)}
