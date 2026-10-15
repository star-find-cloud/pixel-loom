"""Add distribution notices and archive an already-tested portable build."""
from __future__ import annotations

from importlib.metadata import distribution
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pixel_workbench import __version__


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--folder',type=Path,default=ROOT/'dist'/'PixelLoom')
    args=parser.parse_args()
    folder = args.folder.resolve()
    if not (folder / "PixelLoom.exe").exists() or not (folder / "PixelLoomMCP.exe").exists():
        raise SystemExit("Build tools/windows.spec first")
    for name in ("README.md", "README.en.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md"):
        shutil.copy2(ROOT / name, folder / name)
    for name in ("docs", "skills"):
        shutil.copytree(ROOT / name, folder / name, dirs_exist_ok=True)
    shutil.copy2(ROOT/'pixel_workbench/resources/FEEDBACK_IMAGE_GUIDE.md',folder/'截图反馈给AI.md')
    notices = folder / "THIRD_PARTY_LICENSES"
    notices.mkdir(exist_ok=True)
    included = []
    for name in ("pyinstaller", "mcp", "Pillow", "jsonschema", "pydantic", "pywin32"):
        dist = distribution(name)
        number = 0
        for item in dist.files or []:
            source = Path(dist.locate_file(item))
            if source.is_file() and any(word in source.name.lower() for word in ("license", "copying", "notice")):
                number += 1
                shutil.copy2(source, notices / f"{name}-{number}-{source.name}")
        included.append({"name": name, "version": dist.version, "notice_files": number})
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, notices / "Python-LICENSE.txt")
    (notices / "components.json").write_text(json.dumps(included, indent=2), encoding="utf-8")
    target = ROOT / "dist" / f"pixel-loom-{__version__}-windows-x64.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, Path("PixelLoom") / path.relative_to(folder))
    report = {"artifact": target.name, "bytes": target.stat().st_size,
              "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
              "executables": ["PixelLoom.exe", "PixelLoomMCP.exe"], "dependency_notices": included}
    (ROOT / "dist" / "windows-artifact.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "dependency_notices"}, indent=2))


if __name__ == "__main__":
    main()
