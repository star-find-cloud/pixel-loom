# Pixel Loom

In the complete handoff, read `../README.md` first. In a standalone source archive, read this directory's `README.md`.
Start actual editor work with `pixel_onboard`; reading files does not register MCP.
Preserve existing projects. Default image conversion is automatic draft only; artistic redraw needs the human's explicit request.
Do not add personal artwork, tokens, client settings, caches or build outputs to the repository.

## Development

- Run from this source directory (containing `pyproject.toml`) with its virtual environment. Install with `python -m pip install -e .`.
- This project is an AI-oriented native pixel editor with a shared, live MCP document.
- For artwork, prefer the Pixel Loom MCP tools. Start with `pixel_onboard`; `pixel_help(operation=...)` exposes exact schemas.
- Keep unrelated user artwork intact. Use stable layer ids and explicit frames.
- Always preserve and pass the document id and revision you actually observed; re-read on conflicts.
- Inspect returned images after coherent drawing batches; exact pixel inspection helps with small corrections.
- Do not change `.pixloom` files behind an open editor. The CLI is available as a transport fallback.
- GUI and AI drawing must use the same model operations, history and palette validation.
- Validate changes with `python -m unittest discover -s tests -v` and `python -m tests.mcp_public_smoke`. The MCP test uses isolated temporary data/workspace paths and never replaces the user's live document.
- Run `python -m tests.mcp_quality_smoke` for evidence/review/export-gate changes; use `python -m tests.gui_smoke` for desktop widgets.
- Before finished-art delivery, use `pixel_review`, inspect all actual image/timing pages, repair/recheck, then submit concrete findings with `pixel_review_submit`. Numeric checks alone are not artistic approval; uncertainty remains unapproved.
- Final exports require a current passing review for the output scope. Explicit `draft=true` exports are intermediate and must be labeled as such. Save the project after submitting its portable review record.
- Keep stdout protocol-clean in MCP entry points. Never print tokens or existing client configuration contents.
- Keep operation validation, JSON Schema and MCP argument types in `operations.py`; update executable examples and invariants together.
- Store runtime state in the per-user data directory. Never rely on the source checkout being writable or located at a specific path.
- Release packages use the explicit allowlist in `tools/build_release.py`; exclude private artwork, session tokens, local client settings and reference videos.
- The portable Windows build is distributed through GitHub Releases. The local `app/` folder is ignored and never committed.
- Windows desktop support is tested locally. CI configuration for other platforms does not itself prove those platforms passed.
