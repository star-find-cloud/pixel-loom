# Changelog

## 0.7.7 — release checks and download reminders

- Add More → Check for updates and a searchable command. Version checks run in a background thread so editing and MCP remain responsive.
- Check public GitHub releases after desktop startup, at most once per 24 hours after a successful check. A new version produces a nonblocking banner with release notes and a Windows ZIP download button.
- Support stable and public preview channels, including the existing 0.x preview releases. Compare semantic versions numerically and ignore drafts or invalid tags.
- Keep startup/channel preferences in the user's data directory. Allow startup checks to be disabled; headless MCP and diagnostics do not check the network automatically.
- Handle offline requests, rate limits, malformed responses and missing packages without blocking application use. Browser links are restricted to this project's HTTPS release/download paths and open only on explicit clicks.
- Request public version metadata only; never upload artwork, references, saved paths or client settings. Downloading and installing remain explicit user actions.
- Test notification, cache, preferences, slow requests, link opening and shutdown in an isolated GUI runtime; exclude test data and local usage records from release bundles.

## 0.7.6 — reliable editing and a roomier workspace

- Frame, layer and selection navigation preserves drawing undo/redo and avoids serializing the entire document. Refresh only affected timeline thumbnails.
- Erase to transparent pixels independently of palette order. Paste full-color PNG selections without filling a disabled palette; expose the palette constraint in the desktop.
- Honor the human's cancel/save/discard choice when generating a pixel draft.
- Fit large canvases below 100% and add 12.5%, 25%, 50% and 75% nearest-neighbor zoom.
- Pause on the displayed frame, resume there, and provide a separate Stop button returning to the action start.
- Compact the top controls, hide an empty project shelf, and provide resizable sidebar/timeline panes with local layout preferences.
- Warn when an export snapshot becomes old and offer an explicit refresh. Disable invalid exports and provide actionable Chinese desktop error messages.
- Add regression coverage for editing, view transactions, layout, playback and exported snapshot fidelity. Preserve the startup guide and optional creator support.

## 0.7.5 — startup guide and optional creator support

- Show a compact usage guide when the desktop window starts; enter directly, or view voluntary creator support.
- Offer 5, 10, 15 and 20 yuan choices with the author's corresponding original WeChat receipt images.
- Enter, Escape and closing the guide all allow normal use. No payment state, network request or feature gate is introduced.
- Reopen the guide through More. Headless MCP remains unchanged, and the desktop bridge stays responsive while the guide is open.
- Declare the Windows launcher dependency for clean source installations.

## 0.7.4 — optional imported style references

- Identify style images as imported workspace images or embedded project references. Ship no built-in style image.
- Add import/replace, view and clear actions together beside the style name. Clearing keeps original artwork intact and remains undoable in a bound project.
- A different ordinary source clears the previous style without changing the previous project's references. Reloading the same source preserves its chosen style.
- Explain that style images do not affect automatic draft sampling or authorize artistic redraw; expose source information to MCP clients.

## 0.7.3 — automatic draft by default

- Image conversion creates one editable sampling layer by default, preserving the exact automatic draft.
- Artistic redraw is an explicit mode. Align GUI labels, copied instructions, MCP onboarding, prompts and documentation with the human's requested scope.

## 0.7.2 — preview playback speed

- Add 0.25×–4× speed selection beside Play, including changes during playback. Preview speed does not modify frame durations, history or exported timing.

## 0.7.1 — project management

- Add an on-demand project manager for importing existing files without switching the current artwork, opening, selecting multiple projects, reversible removal and restoration.
- Add project-tab context menus and a clear Manage projects entry. Removed projects keep their original files, history, identities and numbers under Deleted.
- Removing the active project saves outgoing changes before selecting a remaining project; removing all leaves an empty workspace that stays empty after restart. New work does not create an extra placeholder project.
- Extend `pixel_projects` with remove/deleted/undelete. Keep removal reversible and require the human's intent before an AI removes any project.
- Cancel desktop timers on close so restarting the editor does not leave callbacks attached to destroyed widgets.

## 0.7.0 — retained projects and animation comparison

- Persistent numbered project shelf with independent file paths, identities and parent links. Fork/new/switch checkpoint the outgoing project, including unnamed and unsaved work.
- Pre-save version backups, external-file-change protection, and restore into a separate project without replacing the source.
- Read-only two-project desktop comparison with independent frame timing, simultaneous playback, time scrubbing and shared pixel magnification.
- New `pixel_projects` MCP tool exposes list/register/fork/new/switch/versions/restore/compare; comparison evidence is paged across every animation frame. Onboarding instructs agents to fork before making a different action or variant.
- Preserve previous drawing, animation, reference, screenshot, review, save and export workflows. Existing explicit unsaved-replacement guards remain available.

## 0.6.2 — contextual workspace

- Preview hides both sidebars and gives the canvas the full workspace width. Manual editing reveals the drawing rail, navigator, layers, palette and automation tools.
- Replace the permanent creation/feedback tab with a compact screenshot toolbar shown only in screenshot mode. Remove the AI connection tab; keep first-time MCP setup, collaboration history, legacy reports and screenshot guidance in More.
- The local service continues to start automatically. MCP initialization and onboarding explain direct tool use and screenshot feedback without asking users to open or enable an AI panel.
- Preserve screenshot clipboard formats, all native drawing/animation operations, legacy project reports, shared history, save and export.

## 0.6.1 — screenshot-first feedback

- Replace the default problem form with one-click canvas screenshot and image copy, followed by a clear reminder to paste into the AI conversation.
- Keep optional lasso/rectangle/ellipse marks; captures include full canvas, marked detail, visible problem designation and document/frame/ROI identity.
- Embed a versioned `pixel_loom_feedback` PNG property, with visible fallback information when chat clients discard metadata. Windows clipboard publishes PNG and CF_DIB formats.
- Bundle a single AI screenshot convention guide and expose it through `pixel_help(topic="feedback_images")`. A capture is not a queued ticket; ambiguous changes are clarified in the user's conversation.
- Preserve existing reports under an advanced history view. Capturing does not edit pixels, add reports, or change painting history.

## 0.6.0 — simpler workspace and annotated feedback

- Three clear entry points: preview the result, circle a problem, or edit by hand. Common tools stay visible; advanced tools and acceptance settings remain available on demand.
- Non-destructive lasso, rectangle and ellipse problem marks with affected frames, original pixel snapshots and portable conversations.
- New `pixel_feedback` MCP tool provides precise masks, original/current frame images, explicit clarification questions, real user answers and evidence-bound resolution. Local submission does not silently start an external AI client.
- Drawing undo preserves user reports and replies. Revisions, changed pixels, removed frames and changed canvas bounds prevent stale repairs from being treated as current.
- Unresolved feedback blocks AI-certified delivery. Human editors can still save and directly export their current version without claiming AI acceptance.
- A user can close an obsolete issue with a reason; its original evidence and conversation remain in the project.
- Integration coverage exercises the real shared Tk/MCP workflow, not a mock interface. No third-party editor code, icons or trial binaries are included.

## 0.5.0 — evidence-based AI self-review

- Acceptance requirements, rendered frame/timing/seam/detail/reference evidence, playable GIF/APNG previews and an in-editor review player.
- Program checks for size, frame count, colors, transparency and planted regions; targeted warnings for rigid cut-outs, timing disparity and loop jumps.
- Three MCP review tools and a finish-and-review prompt enforce concrete visual findings, repair/recheck loops and honest uncertainty.
- Final exports require a current passing review for the selected content/frames/layers. Explicit draft exports remain available and labeled.
- Portable review records expire when artwork or requirements change; verdicts never become artistic passes merely because numeric checks succeed.

## 0.4.0 — reference redraw

- Import ordinary source and optional style images, with a three-way comparison workspace and drag-to-crop controls.
- Configure target size/colors, fit, brightness, contrast, saturation, alpha threshold and an artistic brief. Automatic drafts are explicitly distinguished from AI redraws.
- Three MCP tools expose reference images/settings, dry-run comparisons and protected layered project creation; a redraw prompt and onboarding guide tell agents how to continue.
- Embed normalized source/style PNGs in portable .pixloom projects. Bound reference edits share native undo history; display overlays do not change artwork/export pixels.
- Test reference conflicts, source preservation, transparent export, project portability and real two-client MCP redraws.

## 0.3.0 — visual workspace

- Redesigned native desktop with vector tool icons, contextual hints, an inspector/automation/AI dock and compact thumbnail timeline.
- Exact raster symmetry, visible axes, live polygon/curve previews and cached palette/thumbnail widgets.
- Five parameter-driven workflows with read-only contact/timed previews, document/revision guards and atomic undo.
- New-project size presets, canvas resize previews, export size/layout feedback, paginated frame overview and searchable command palette.
- Fixed manual stroke/path coordinates rejected by strict schema validation; preview/commit pixel equality is covered by the GUI smoke test.
- Added workflow tests for source preservation, independent cels, selection bounds, timing, locks, capacity rollback and even-width symmetry.

## 0.2.0 — public preview

- 41 validated native operations, including polygons, Bézier curves, local transforms, canvas resize/scale, layer duplication/merging and animation tags.
- Rectangular selection, copy/cut/paste, local rotation, interactive polygon/curve tools and tag playback in the desktop editor.
- 12 MCP tools with typed operation schemas, onboarding, dry-run image previews, animation contact sheets and structured recovery errors.
- Three MCP resources and two task prompts; a distributable agent skill and executable native-drawing recipes.
- Per-user runtime/workspace paths, installable package/entry points and generated client configuration.
- Duplicate-request protection, unsaved artwork protection, export collision checks and content-based dirty tracking.
- Isolated tests, source/wheel release preparation and a Windows portable-build specification.

## 0.1.0 — local prototype

Layered integer-pixel editing, basic animation, local MCP bridge and PNG/sheet/GIF export.
