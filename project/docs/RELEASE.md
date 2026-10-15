# Release preparation

The repository can be prepared locally without publishing a repository, uploading artwork or changing accounts.

```powershell
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m tests.mcp_public_smoke
python -m tests.mcp_reference_smoke
python -m tests.mcp_quality_smoke
python -m tests.mcp_feedback_smoke
python -m tests.mcp_projects_smoke
python -m tests.gui_smoke
python -m tests.gui_editing_smoke
python -m tests.gui_welcome_smoke
python -m tests.gui_feedback_smoke
python -m tests.gui_capture_smoke
python -m tests.gui_projects_smoke
python tools/build_release.py --check
python tools/build_release.py
python -m build
```

The source ZIP uses an explicit allowlist. Private artwork, reference media, third-party research artifacts, client registration records, local tokens, virtual environments and build caches stay out. The sdist also prunes private workspace trees. The wheel contains the application package and bundled example only.

## Windows portable folder

Install PyInstaller 6.x in the development environment, then:

```powershell
python -m PyInstaller tools/windows.spec --noconfirm
```

`dist/PixelLoom/PixelLoom.exe` is the native GUI. `PixelLoomMCP.exe --mcp` is the stdio server. Keep the whole folder together, including `_internal`.

The two executables share libraries. A dedicated console entry point is necessary for MCP JSON-RPC pipes. The GUI's MCP setup dialog generates a configuration pointing to that sibling console executable. No Python installation is intended on a recipient's machine; verify the bundled executables separately before sharing.

Run `PixelLoomMCP.exe --doctor` to inspect bundled dependency versions. For isolated protocol testing use `--mcp --headless --data-dir <temporary-dir> --workspace <temporary-workspace>`.

Include README, LICENSE and dependency notices in the folder archive. Keep release checksums and validation notes. The MIT license file is included as the initial open-source license choice; change it before public distribution if the project owner chooses another license.

Publishing, code signing, automatic updates, store submission and external GitHub CI execution are separate release actions and have not been performed by these local build commands.
