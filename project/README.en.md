# Pixel Loom

[中文](README.md) · [Agent guide](docs/AI_GUIDE.md) · [Release preparation](docs/RELEASE.md)

An editable local pixel-art and frame-animation workbench for humans and AI agents. A native desktop window and standard MCP clients share layers, cels, palette, named regions and undo history.

Version **0.7.9 is a local preview; the published GitHub release remains 0.7.7**. Desktop behavior is tested on Windows. A headless backend and cross-platform CI configuration are included; other desktop platforms have not been fully validated.

This is the `project/` source subproject. The complete handoff starts with the parent `README.md`; development commands here run in this directory, next to `pyproject.toml`. Formal tests remain in `tests/`; generated test projects, logs and build caches are excluded.

## Download (Windows)

Download the matching `pixel-loom-<version>-windows-x64.zip` from [GitHub Releases](https://github.com/yangsir2077/pixel-loom/releases), extract the whole `PixelLoom` folder and run the root launcher or `app/PixelLoom.exe`. Keep the complete `app` folder, including `PixelLoomMCP.exe` and `_internal`. The portable build bundles its Python runtime.

## Check for updates

More → Check for updates reads public GitHub release metadata asynchronously and provides notes and Windows ZIP links. Desktop startup also checks in the background, with a 24-hour interval after successful checks and a nonblocking new-version banner. Users can disable startup checks and choose whether to include public previews; 0.x defaults to including them. Headless MCP never checks automatically. No artwork, reference images, local paths or client settings are uploaded. Preferences stay in the user data directory, and browser links open only on explicit clicks. This feature does not install updates automatically.

## Install from source

Python 3.11+ is required. Desktop mode also needs Tk.

```sh
python -m venv .venv
# Activate this environment using your platform's normal command.
python -m pip install -e .
pixel-loom
```

On Windows, `setup.ps1` and the supplied launcher are alternatives. A portable Windows folder contains `PixelLoom.exe`, `PixelLoomMCP.exe` and `_internal`; keep them together.

## Connect MCP

The local service starts with the editor; there is no GUI activation step. For first-time host registration, generate a configuration with `pixel-loom-config --format both`, or use More → MCP setup. By default this prints/copies a configuration without modifying other applications. Explicit `--install codex` or `--install claude-desktop` creates a backup and preserves other settings.

Source MCP command: the virtual environment's absolute Python executable, with arguments `-m pixel_workbench --mcp`.
Portable MCP command: absolute `PixelLoomMCP.exe`, with argument `--mcp`.

Reload MCP in the client, then call **`pixel_onboard`**. It returns the live project, workspace, rules and a runnable native-drawing recipe. No model API key is required by this application; the connected host supplies model reasoning.

The server exposes 23 tools, 44 validated native operations, three resources and four prompts. Tool argument schemas, validation and focused help derive from one registry. A distributable agent skill is in `skills/pixel-loom/SKILL.md`.

## Capabilities

The numbered project shelf retains separate works. Fork before making another action; switch checkpoints the outgoing project, including unnamed work. Saves retain pre-overwrite versions and reject silent external-file changes. Restoring a version creates a separate project. The desktop can play two read-only project snapshots side by side using their own timings and a common pixel scale. `pixel_projects` exposes the same preservation workflow and paged comparison evidence to MCP agents.

Manage projects opens an add/open/remove/restore browser with multiple selection. Shelf tabs also have a right-click remove action. Removal preserves files and saved history in Deleted; restoration keeps the original ids/numbers. Removing the active project checkpoints its edits before opening another project. Removing every project leaves an empty workspace across restarts. These operations never permanently erase artwork files.

- Integer-pixel drawing, strokes, polygons, quadratic/cubic Bézier curves, shapes, flood fill, outlines, dithering and optional ASCII stamps.
- Rectangular selections, copy/cut/paste, local movement, mirroring and 90-degree rotation.
- Layers with locks/opacity/duplication/merging; copied/blank/reordered frames, timing and named action tags.
- Forward/reverse/pingpong playback, onion skin and multi-frame contact sheets.
- Atomic undoable batches, dry-run image previews, exact-request retry protection, content-based dirty tracking and recovery files.
- Editable `.pixloom` documents (0.1 remains readable), PNG import, RGBA PNG/sheet+JSON/GIF export with optional tag/layer filtering.

Desktop labels are primarily Chinese; MCP schemas and agent documentation are in English.

The Project menu contains creation, copying, history and comparison; the empty shelf collapses. Sidebar and timeline dividers are draggable and their sizes are saved locally. Fit supports large canvases below 100%, alongside 12.5%, 25%, 50% and 75% zoom. Pause holds the displayed frame; Stop returns to the action start. View-only navigation preserves drawing undo/redo and refreshes only the necessary views. Erasing always writes transparency; unrestricted full-color PNG selections paste without filling the palette.

Export uses an explicit document snapshot. A changed document displays an old-snapshot warning with a refresh button. Invalid parameters disable export and explain the problem.

## Agent workflow

Read current state; preserve existing artwork; use native tools directly; validate uncertain changes; submit a coherent edit with observed document/revision tokens; inspect its actual image. For animation compare poses with `pixel_contact_sheet`. Save `.pixloom` before exporting engine assets.

`pixel_help(operation="polygon")` gives a focused schema/example. External scripts and image generators are optional, not prerequisites for drawing. Refer to [AI_GUIDE.md](docs/AI_GUIDE.md) for exact targeting, selection, tag and retry semantics.

## Runtime and limits

Data lives in the user's application-data directory, not the installation folder. `--data-dir` / `PIXEL_LOOM_HOME` isolates an instance; `--workspace` / `PIXEL_LOOM_WORKSPACE` chooses project/export paths. `--mcp --headless` works without a desktop display. Local bridge connections bypass system HTTP proxies.

Maximums: 512×512 canvas, 64 layers, 256 frames, 8M total cel pixels, 40 undo steps, 4M preview pixels, 16M export pixels. Not yet supported: `.aseprite`, tile maps, nested groups, lasso selections and arbitrary-angle rotation. GIF has binary alpha and 10ms timing precision. PNG sheets are recommended for engines.

## Test and contribute

```sh
python -m unittest discover -s tests -v
python -m tests.mcp_public_smoke
python -m tests.gui_smoke  # requires Tk/display
python tools/build_release.py --check
```

The MCP test starts two real clients from an isolated temporary directory and uses the server's own onboarding/resources to draw, animate and export. It does not touch the user's live project. External CI execution, public publishing, signing and automatic updates are separate actions.

[Architecture](docs/ARCHITECTURE.md) · [Contributing](CONTRIBUTING.md) · [License](LICENSE)

## Visual desktop workflows

Preview uses the full workspace width with both sidebars hidden. Screenshot mode shows only optional marking tools and a compact capture toolbar. Manual editing reveals the drawing rail, navigator and layer/color/automation dock. First-time MCP setup, collaboration history and legacy feedback records remain in More. Tooltips explain shortcuts. Ctrl+K searches commands; F fits the canvas. New-project templates, resize previews, export dimensions and paginated frame overviews make routine work visible.

Symmetry mirrors the actual native raster, including even-width brushes. The five automation cards plan floating loops, ping-pong travel, frame timing, range duplication and outlines. Preview a contact sheet or timed animation before applying one undoable batch. A document/revision change invalidates the preview. Motion loops copy all layers from the source frame and move only the active unlocked layer or selection; out-of-canvas pixels clip. They do not synthesize new character poses. GUI symmetry never silently changes MCP edits.

## Ordinary image to automatic pixel draft

Open **导入参考** in the desktop. Import an ordinary PNG/JPEG/WebP/BMP/GIF and optionally a style reference. Choose dimensions/colors, crop and tone settings, then click **生成像素底稿**. This creates one editable pixel layer with the exact automatic sampling/quantization result. Preserve proportions, silhouette and facial features by default. **复制 AI 指令** copies the same conversion-only rule. Artistic redraw requires an explicit human request; old briefs, settings and style images do not authorize it.

Style images are optional user/client imports or embedded project references; none are bundled. The style row shows the source and offers import/replace, view and clear. A different source clears the previous style while preserving old project references. Style images do not affect automatic draft sampling.

`pixel_reference` returns actual source/style/draft/artwork images and can dry-run native edits in comparison. `pixel_reference_setup` imports/configures references with observed reference/document tokens. `pixel_redraw_begin(mode="draft")` creates the editable automatic draft by default, protecting unsaved artwork. Explicit `mode="redraw"` supplies layered artistic redraw with an optional locked seed. The `redraw_reference` prompt explains the artistic workflow. Reconnect existing MCP clients to discover these tools. There are 23 tools, 44 native operations and four prompts.

The draft is only quantization/resampling; the connected AI authors proportions, silhouettes and color clusters with native drawing operations. The editor does not autonomously invoke external AI. GUI overlays do not alter exported pixels. References embed in saved .pixloom projects; no original-image path is required after moving a project. Stored references normalize EXIF and sides to at most 1024 pixels; crop uses those coordinates. Local files up to 50 MB / 40 million pixels are accepted.

## Finish, self-review, repair and recheck

Use `pixel_review_settings` to capture the user's brief, exact dimensions/source-frame count, max opaque colors, transparency, fixed named regions, detail regions and retry budget. `pixel_review` returns actual rendered frames, two-loop equal-time samples, seam/detail/reference images and a playable GIF/APNG cache path. The desktop **成品自检** window loops the same snapshot at real durations, supports slow/step playback and displays checks and AI findings. Fetch every evidence page for long animations.

Program checks do not certify aesthetics. The connected AI must inspect evidence and assess silhouette, colors, reference fidelity, motion and timing with concrete observations. Repair through `pixel_edit` and start a fresh review when defective. Submit conclusions through `pixel_review_submit`; uncertainty remains uncertain, and technical/visual failures remain needs_changes. The `finish_and_review` prompt guides the autonomous loop without repeated confirmation for ordinary corrections. At the configured round budget, report unresolved issues rather than inventing a pass. State the method actually used: frame/timing evidence is distinct from direct playback. Equal-time samples can miss short poses, so complete contact sheets and playback remain useful.

Final `pixel_export` requires a current passing record covering the selected frames and layers. `draft=true` (CLI: `--draft`) explicitly labels intermediate output unreviewed. GUI exports distinguish drafts/finals too. Artwork or requirement changes invalidate old evidence/reports; view selection does not. Reports embed in .pixloom, so save again after submission. This workflow uses the connected AI client; the editor does not secretly invoke an external model. There are 20 MCP tools, 43 native operations and four prompts.

## Annotated human feedback (0.6)

The workspace starts with Preview / Circle a problem / Edit by hand. Lasso, rectangle and ellipse marks never paint into the artwork. Reports retain exact coordinates, affected frames, original snapshots, questions and human replies in the project. The connected AI uses pixel_feedback to inspect original/current images, asks before guessing, then repairs and inspects again before resolving. Reports survive painting undo. Unresolved or stale repairs block AI-certified delivery; people can still save and export the current version. Submission saves a local MCP queue item and does not start or wake an external AI client.

## Screenshot-first feedback (0.6.1)

The default workflow is **Screenshot and copy -> paste into the AI conversation**. Optional lasso/rectangle/ellipse marks identify an area; there is no software problem form. The capture contains the real canvas, an enlarged detail when marked, a visible problem designation and document/frame/ROI identity. PNG iTXt stores `pixel_loom_feedback`; visible identity remains when clipboard/chat conversion strips metadata. Windows publishes PNG and CF_DIB clipboard formats and shows a paste reminder. Capturing does not edit the document, create a ticket or send a message. See `pixel_workbench/resources/FEEDBACK_IMAGE_GUIDE.md`, also available via `pixel_help(topic="feedback_images")`. The AI asks in the current conversation when the expected change is unclear. Existing ticket records remain accessible through an advanced history view.


Timeline playback speed: choose 0.25×–4× next to Play. Changes take effect while playing and affect preview only; authored frame durations and exports stay unchanged.

## Startup guide and optional creator support

The desktop opens a short usage guide. Enter, Escape and closing the dialog all allow normal use. The optional support page offers CNY 5/10/15/20 and shows the matching original WeChat receipt image supplied by the maintainer. It never sends a payment request, checks payment status or gates features. Reopen it from More. Headless MCP is unchanged. Receipt images and their amount mapping live in `pixel_workbench/resources/support/`.

## Editable pixel effects (0.7.9 local preview)

**More → Pixel effects** provides arc slash, lightning, magic aura, fire and explosion/sparks in one visual dialog. Adjust the primary color, strength, size, frame count and frame interval, play the preview or inspect every frame, then Generate new project. The main canvas gains no permanent panel. Existing work is checkpointed and each result is a separate saved project, with three ordinary editable layers, its palette, native frame cels, action tag and original generation recipe. Regeneration creates a variant and preserves manual edits in earlier projects. Advanced character/motion tools remain searchable through Ctrl+K.

MCP uses `pixel_effect(action="presets")`, then `preview(settings={"preset":"fire","size":64,"frames":16,"duration_ms":80})`. Inspect the actual all-frame contact image and local draft GIF before `create` with observed document/revision tokens. Preview does not change artwork, history, selection or playback. Settings are `preset` (`slash`, `lightning`, `magic`, `fire`, `burst`), `size` 24–128, `frames` 8–32, `duration_ms` 30–500, `strength` 1–100, opaque primary hex `color`, and deterministic `seed` 0–999999. An explicit partial settings object uses preset defaults; omit settings entirely to reuse the current project's saved original recipe when present. `pixel_help(topic="effects")` and onboarding describe the same workflow.

Effects are parameterized native pixel operations, not a language model or an external image-generation API. Crisp edges use binary alpha; layers and every frame can be hand-edited or changed through pixel_edit, with shared undo. Fire and magic aura are designed as loops. Burst, lightning and slash are single actions repeatedly played in previews; configure one-shot playback in the consuming game engine. Recipe settings retain their original generation size after manual resizing and never silently rerender painted changes. Use the existing pixel_review visual/timing workflow and save before final PNG/sheet+JSON/GIF export. Preview GIFs are explicitly drafts and do not constitute artistic approval.
