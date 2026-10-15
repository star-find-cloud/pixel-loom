"""Package the documented app/project handoff without private workspace state."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pixel_workbench import __version__
from build_release import audit, source_files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True, help="Verified portable app folder, including its notices and checksums")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args(argv)
    app = args.app.resolve()
    output = args.output_dir.resolve()
    if output == app or output.is_relative_to(app):
        raise ValueError("Output must be outside the input application folder")
    for name in ("PixelLoom.exe", "PixelLoomMCP.exe", "LICENSE", "THIRD_PARTY_NOTICES.md", "SHA256SUMS.txt"):
        if not (app / name).is_file():
            raise ValueError(f"Missing verified application file: {name}")
    application_files = []
    for line in (app / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        file = (app / name).resolve()
        if not file.is_relative_to(app) or not file.is_file():
            raise ValueError(f"Invalid application manifest path: {name}")
        if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Application checksum mismatch: {name}")
        application_files.append(file)
    application_files.append(app / "SHA256SUMS.txt")
    declared = {p.relative_to(app).as_posix() for p in application_files}
    actual = {p.relative_to(app).as_posix() for p in app.rglob("*") if p.is_file()}
    if declared != actual:
        raise ValueError("Application folder contains files absent from its checksum manifest")
    for package, pattern in (("cffi", "_cffi_backend*"), ("brotli", "_brotli*")):
        if any((app / "_internal").glob(pattern)) and not any(
                p.is_file() and package in p.name.lower() for p in (app / "THIRD_PARTY_LICENSES").rglob("*")):
            raise ValueError(f"Missing bundled {package} notice; collect it from the matching build distribution")
    selected = source_files(ROOT)
    report = audit(selected, ROOT)
    handoff = ROOT.parent
    complete_checkout = handoff / "project" == ROOT and (handoff / "README.md").is_file()
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"pixel-loom-{__version__}-windows-x64.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in selected:
            archive.write(file, "PixelLoom/project/" + file.relative_to(ROOT).as_posix())
        for file in application_files:
            archive.write(file, "PixelLoom/app/" + file.relative_to(app).as_posix())
        if complete_checkout:
            for name in ("README.md", "AGENTS.md", "CLAUDE.md", "LICENSE", "打开像素织机.cmd"):
                archive.write(handoff / name, "PixelLoom/" + name)
        else:
            archive.writestr("PixelLoom/README.md", f"# Pixel Loom {__version__}\n\nRun app/PixelLoom.exe. Keep the entire app folder.\n\nFor humans and AI: read project/README.md and project/docs/AI_GUIDE.md. Register app/PixelLoomMCP.exe --mcp, then call pixel_onboard.\n\nComplete source, tests and build instructions are in project/. Creator support is optional.\n")
            archive.writestr("PixelLoom/AGENTS.md", "Read README.md and project/AGENTS.md. Preserve artwork; start with pixel_onboard.\n")
            archive.writestr("PixelLoom/CLAUDE.md", "Read README.md and project/AGENTS.md. Verify MCP through pixel_onboard.\n")
            archive.writestr("PixelLoom/打开像素织机.cmd", '@echo off\r\nstart "" "%~dp0app\\PixelLoom.exe"\r\n')
            archive.write(ROOT / "LICENSE", "PixelLoom/LICENSE")
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive integrity check failed")
    report.update({"artifact": target.name, "bytes": target.stat().st_size,
                   "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                   "layout": "PixelLoom/app + PixelLoom/project", "application_input_modified": False})
    (output / "windows-artifact.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
