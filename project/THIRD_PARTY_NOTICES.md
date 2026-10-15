# Third-party components

Pixel Loom application code is distributed under the MIT license in `LICENSE`.
Dependencies retain their own licenses. Python, Tk, Pillow, the official MCP Python SDK, Pydantic, JSON Schema tooling, pywin32 on Windows and their transitive dependencies are not relicensed by this project.

The source distribution declares dependencies in `pyproject.toml`; source installers obtain their original distributions. Windows portable builds include dependency metadata/license files collected by the build specification and PyInstaller hooks. Consult those files for exact notices for the built versions.

Bundled example artwork is produced using this project's own drawing recipes. User projects and reference videos are not included in public release packages.

The maintainer explicitly supplied the WeChat receipt posters in `pixel_workbench/resources/support/` for the optional creator-support screen. They are distributed intentionally with this feature; private project artwork and reference media remain excluded.
