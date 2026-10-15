"""Portable stdio configuration generation; never changes clients unless requested."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tomllib

from .model import atomic_json


def configurations(executable=None, headless=False):
    # Resolving a virtualenv's python symlink would select the base interpreter
    # and lose the environment containing Pixel Loom and its dependencies.
    executable = Path(os.path.abspath(os.path.expanduser(str(executable or sys.executable))))
    frozen = getattr(sys, "frozen", False)
    if not frozen and executable.name.lower() == "pythonw.exe":
        # A source-installed GUI may itself run under pythonw; MCP still needs
        # the console interpreter so stdin/stdout pipes are available.
        executable = executable.with_name("python.exe")
    if frozen and executable.with_name("PixelLoomMCP.exe").exists():
        executable = executable.with_name("PixelLoomMCP.exe")
    executable = str(executable)
    args = ["--mcp"] if frozen else ["-m", "pixel_workbench", "--mcp"]
    if headless:
        args.append("--headless")
    entry = {"command": executable, "args": args}
    codex = ("[mcp_servers.pixel_loom]\ncommand = " + json.dumps(executable) + "\nargs = " + json.dumps(args) +
             "\nstartup_timeout_sec = 25\ntool_timeout_sec = 60\n")
    return {"codex": codex, "claude": {"mcpServers": {"pixel-loom": entry}}, "entry": entry}


def backup(path):
    if not path.exists():
        return None
    name = path.name + ".pixel-loom-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = path.with_name(name)
    shutil.copy2(path, target)
    return str(target)


def install_codex(path=None):
    path = Path(path) if path else Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    original = tomllib.loads(text)
    config = configurations()
    current = original.get("mcp_servers", {}).get("pixel_loom", {})
    if all(current.get(key) == value for key, value in config["entry"].items()):
        return {"client": "Codex", "status": "already_configured", "path": str(path)}
    match = re.search(r"(?m)^[ \t]*\[mcp_servers\.pixel_loom\][ \t]*(?:#.*)?$", text)
    if match:
        following = re.search(r"(?m)^[ \t]*\[", text[match.end():])
        end = match.end() + following.start() if following else len(text)
        candidate = text[:match.start()] + config["codex"] + "\n" + text[end:]
    else:
        candidate = text.rstrip() + "\n\n" + config["codex"]
    parsed = tomllib.loads(candidate)
    before, after = deepcopy(original), deepcopy(parsed)
    before.setdefault("mcp_servers", {}).pop("pixel_loom", None)
    after.setdefault("mcp_servers", {}).pop("pixel_loom", None)
    if before != after:
        raise ValueError("Existing nested Pixel Loom settings prevent a safe update; update this server entry manually")
    saved = backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".pixel-loom-writing")
    temporary.write_text(candidate, encoding="utf-8")
    os.replace(temporary, path)
    return {"client": "Codex", "status": "configured", "path": str(path), "backup": saved}


def install_claude(path=None):
    if path is None:
        if sys.platform == "darwin":
            path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        elif sys.platform == "win32":
            path = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "Claude" / "claude_desktop_config.json"
        else:
            path = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "Claude" / "claude_desktop_config.json"
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    entry = configurations()["entry"]
    servers = data.setdefault("mcpServers", {})
    if servers.get("pixel-loom") == entry:
        return {"client": "Claude Desktop", "status": "already_configured", "path": str(path)}
    saved = backup(path)
    servers["pixel-loom"] = entry
    atomic_json(path, data)
    return {"client": "Claude Desktop", "status": "configured", "path": str(path), "backup": saved}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate or explicitly install local MCP client configuration")
    parser.add_argument("--format", choices=("codex", "claude", "both"), default="both")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--install", choices=("codex", "claude-desktop", "both"), help="Explicitly update client settings, preserving a backup")
    args = parser.parse_args(argv)
    if args.install:
        results = []
        if args.install in ("codex", "both"):
            results.append(install_codex())
        if args.install in ("claude-desktop", "both"):
            results.append(install_claude())
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    config = configurations(headless=args.headless)
    if args.format in ("codex", "both"):
        print(config["codex"])
    if args.format in ("claude", "both"):
        print(json.dumps(config["claude"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
