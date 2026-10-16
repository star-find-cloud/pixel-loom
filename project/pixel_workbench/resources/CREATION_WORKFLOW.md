# 制作流程 / Creation workflow

This is a method for the connected AI to design editable pixel art. It is not a model, a finished-art recipe or a content generator. Follow the actual human task; no reference image, saved brief or documentation example grants permission to change unrelated art.

## 1. Discover and preserve

Call pixel_onboard and inspect current_document, feedback, layers, selection, frames, document_id and revision. Read actual previews before changing existing work. Save outgoing work. Use pixel_projects(action="new") for a new element and fork for a different action/variant; repair the same action in its existing project. Do not remove old projects merely to tidy the shelf.

Read this guide with pixel_help(topic="workflow"). Animation tasks also need pixel_help(topic="animation_workflow"); delivery needs pixel_help(topic="inspection_workflow"). These help calls work without opening a desktop panel or reading local source files. Resources are an optional alternative, not a requirement.

## 2. Turn the brief into a small specification

Decide logical pixel size, transparent/background intent, viewpoint, silhouette, focal color, light direction, palette range, frame count/durations, loop versus one-shot, fixed/moving parts and output formats. Use one independent element unless the human requests a scene. Resolve routine choices yourself; ask only about consequential ambiguity.

Set meaningful pixel_review_settings after selecting the intended project. Requirements should describe this task, not a default object or an arbitrary fixed frame count. For ordinary-image conversion, preserve the automatic draft by default. Artistic redraw needs the human's explicit request; this workflow does not authorize redesign.

Background removal is OPTIONAL: only for an actual removal request or a task clearly requiring an isolated transparent source. Import/conversion alone does not authorize it. Skip already-transparent artwork. Discover pixel_help(topic="cutout") when needed: preview original/result/mask, adjust with base_preview_id to retain protection, apply the inspected result, undo/redo or reset as needed. It is a local color/mask tool, not a semantic segmentation model; existing canvas pixels stay unchanged.

## 3. Design before adding detail

Work in this order: readable silhouette -> proportions -> large color groups -> consistent light/shadow -> restrained identifying details. Check at native size as well as integer enlargement. More pixels, noise and highlights do not automatically improve an icon. Keep material highlights distinct from the main subject and avoid unrelated decorations.

Split layers by edit/motion responsibility, not by every color: fixed structure, moving content, optional particles, fixed foreground highlights/labels. Choose anchors and semantic regions before animating. A small coherent layer stack is easier for the human to repair.

## 4. Use native drawing operations

Read pixel_help(operation="polygon"), bezier, rect, line, clear, frame_add or other needed schemas. Use polygon/bezier for silhouettes and rect/line/pixel for hard edges and corrections. Send coherent batches through pixel_edit with a descriptive label. Preview after each meaningful part; use pixel_validate for substantial or uncertain batches.

Use stable layer IDs and explicit zero-based frames. Rectangles use x/y/width/height, not two corner coordinates. Read selection: it can constrain painting. Clear an unintended selection or supply an appropriate explicit clip according to the schema. Add colors before using them under a strict palette. Never change a locked layer or edit an open .pixloom behind the editor.

Each write uses the document_id/revision actually observed. Inspect the returned state before the next write. A human selecting a frame can also advance revision; on conflict re-read and re-plan rather than blindly replaying stale commands. Batches are undoable and retained as project iterations.

## 5. Optional computation belongs to the host

The host may run its own Python/JavaScript to calculate geometry, masks, phase, constraints and arrays of native operations. Pixel Loom itself does not provide arbitrary script execution or decide artistic content. Without host computation, send smaller direct native batches; do not claim unavailable capabilities.

Use calculation for repeated work, while designing shape and motion for the current brief. Do not require the human to install a fixed object generator. If the task requires native MCP drawing, do not import an externally rendered finished image and claim it was drawn here. If external image generation or imports were actually used, report their provenance honestly.

## 6. Iterate on observed problems

Inspect actual pixel_preview and pixel_contact_sheet images. Classify a defect:
- Design: unclear silhouette/proportions/colors -> revise the static design first.
- Motion: wrong anchor, rigid sliding, abrupt timing -> revise the motion plan.
- Execution: wrong frame/layer/selection/color -> correct the target and parameters.
- Evidence: missing frames or unviewed images -> obtain and inspect them.

Repair only affected parts. For a different design direction, preserve the previous project/iteration. Never assume one geometry formula fits icons, characters, VFX and tiles. Character rotation needs appropriate views/poses; tiles need grid-compatible edges; one-shot effects need readable build-up, impact and dissipation.

Finish with pixel_help(topic="inspection_workflow"). The host AI must view images and make concrete judgments; these instructions cannot guarantee equal quality across models.
