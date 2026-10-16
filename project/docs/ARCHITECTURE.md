# Architecture

`Document` stores full-canvas RGBA cels for each layer/frame. Editing clones validated state, executes a batch, then commits it as one history step. The file format remains `pixel-loom/v1`; optional tags/selection/reference fields default safely when opening earlier projects.

`operations.py` is the operation registry. JSON Schema validation, focused help and discriminated MCP argument types derive from it. Recipes are executable examples rather than prose-only instructions.

`DocumentService` handles workspace paths, dry runs, revisions, exact-request retries, saved-content fingerprints, recovery and file collision behavior. Desktop and optional headless runners use the same service. The desktop manually draws through the same model operations.

The loopback bridge dispatches document work to one owner thread. The desktop pumps requests through Tk's event loop; the headless runner pumps them through its main loop. During a human stroke/polygon path, external writes are rejected. Image snapshots and their revision metadata are produced in one service request.

MCP uses the official Python SDK's stdio transport. The current dependency range deliberately remains on compatible SDK 1.x. Tools return structured data plus text and image content; structured errors include a recovery hint. There are no model credentials or external generation calls.

`reference.py` normalizes local image imports, crops/fits them to a target, and produces deterministic limited-palette draft guides. A separate per-user `ReferenceWorkspace` stages imports without replacing artwork and has its own conflict token. Creating a redraw embeds bounded, metadata-free subject/style PNGs and settings in the document. Bound parameter edits use the native `reference_context` operation and shared undo history; opening/undoing restores project reference settings. Comparison previews can run native edits on a clone. The AI authors the artistic redraw; the draft processor does no semantic background removal or pose generation. `reference_ui.py` uses the same service as MCP. GUI reference overlays remain outside document pixels and exports.

## Runtime paths

The default application data directory is `%LOCALAPPDATA%/PixelLoom` on Windows, `~/Library/Application Support/PixelLoom` on macOS, or `$XDG_DATA_HOME/pixel-loom` on Linux. Projects/exports default to its `workspace` subdirectory.

`--data-dir` / `PIXEL_LOOM_HOME` selects an isolated runtime. `--workspace` / `PIXEL_LOOM_WORKSPACE` selects project/export paths. Clients sharing these paths connect to one backend. Tests use temporary paths and a different working directory; source checkouts may be read-only.

On Windows an existing Explorer automation object launches the GUI outside a particular MCP host's kill-on-close job. The frozen build has separate GUI and console executables so a windowed Python bootloader cannot swallow MCP stdin/stdout. Other platforms use detached process sessions. Headless mode is explicit and reported in state.

## Limits

Canvas sides: 1–512 pixels. Layers: 64. Frames: 256. Total cel pixels: 8M. History: 40 steps. Preview/contact images: 4M output pixels. Exports: 16M output pixels. This preview release does not include tile maps, nested layer groups, freeform lasso selections, arbitrary-angle rotation, .aseprite compatibility or a built-in language model.

Desktop operation is tested on Windows. Cross-platform CI configuration is supplied; it is not a claim that those external CI runs have already completed.

## Self-review evidence and delivery

`quality.py` creates immutable document snapshots with scope-aware analysis, paginated contact/detail sheets, equal-time sampling, loop seams and exact-palette GIF or lossless RGBA APNG playback. Numeric findings remain distinct from the AI's visual judgments. Review ids bind to a content hash excluding view state and review records. Policy edits are native undoable operations; submitting a verdict advances revision without adding a drawing undo step. Reports persist in the project and are valid only for matching content, frames and layer sets. Private evidence caches stay in the user runtime.

Final MCP exports check a current passing report; explicit drafts remain available. `quality_ui.py` uses the same manager and a real-duration snapshot player, exposing stale status and actual inspection method. No external model is invoked by the editor: MCP instructions, structured findings, export guards and the finish-and-review prompt guide the connected model through repairs and rechecks. A report is an AI assessment, not a guarantee of human preference.

## Character and motion

`character.py` validates bounded portable metadata; `character_profile` is a native transaction shared by GUI/MCP/history. Model persistence, fork and canvas transforms retain the specification. `motion.py` scans immutable document snapshots and exposes exact frame/ROI findings. MotionManager caches two content-bound paged reports; view changes do not invalidate them, artwork/requirements changes do. `character_ui.py` runs scans on a worker with no Tk calls, displays evidence on the main thread, guards stale actions and cancels polling on destruction. Cleanup uses existing pixel operations with explicit layer/frame/clip in one undo step. Numeric suspicions do not replace quality.py visual acceptance.
