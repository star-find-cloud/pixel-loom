# 动画制作 / Animation workflow

Read pixel_help(topic="workflow") first. Design motion for the current brief; this guide contains no object preset or finished artwork coordinates.

## Before animation from a flattened image

Animation needs the human's request. Choose animation from compact onboarding and preserve a different action in a fork. Read decomposition_workflow for merged source images. Analyze structure, occlusion, joints and grips; separate visible objects, inspect each isolated part and restored composite first. Hidden completion is a separate requested scope: if movement needs missing surfaces, clarify before painting them. Static conversion also needs clean visible-object layers, but no animation trial or hidden filling. Matching rest pixels does not certify correct ownership. pixel_task records brief, parts and next_action without art/history changes; frame-0 part checks complement the full-frame review below.

## 1. Define the motion contract

Specify fixed parts, anchors, moving parts, extent, frame durations and whether motion loops. Keep static geometry/highlights/labels fixed unless the intended material calls for movement. Do not move an entire object layer when only one internal part should change.

A loop uses phase = 2*pi*frame/frame_count. Use periodic terms or deliberately matched endpoints. Secondary parts may lag the main action instead of moving in lockstep. One-shot effects should be reviewed as one-shot; do not force an impact to look like seamless idle motion.

## 2. Separate static and moving cels

Draw and inspect a convincing static design first. Then use either clean-frame strategy:
- Before drawing frame-0 motion, copy the static composition and empty moving layers to all frames, then paint each moving cel explicitly.
- If the source already contains motion, copy it, clear ONLY the moving layer in each target frame and redraw that frame. Never clear static layers by accident.
frame_add(blank=true) creates blank cels for all layers; it does not preserve a static background. Use copy_from for static content, then clear the appropriate moving cels. Query the current operation schemas.

Do not accumulate new silhouettes over old ones. For a local repair, clear/rebuild the affected moving cel or an explicit bounded clip. Keep unrelated layers, anchors, palette and frames intact. Use tags for the intended action range.

## 3. Calculate useful constraints, not a full-image shortcut

Host-side code can compute per-frame geometry and output native rect/polygon/line/pixel operations. Merge adjacent same-color pixels into runs where helpful instead of making a network call per pixel.

Possible task-dependent constraints:
- A liquid interior can use a periodic tilted/wavy surface inside a bottle mask. Choose a target filled-pixel count from THAT design, rank interior pixels by depth below the proposed surface, and select the same count each frame. This preserves 2D pixel area, not a full 3D fluid simulation.
- A flexible part can keep its attachment fixed while its tip lags. Rebuild its contour; simple whole-patch translation can detach it.
- A tiled surface needs a specified grid, neighbor rules, edge continuity and consistent frame placement. Validate it in the target engine when the task asks for engine-ready tiles.
- Particles may intentionally be disconnected. Their origin, path, fade and lifetime should be designed rather than treated as accidental orphan pixels.

These are design principles, not an invitation to add built-in content presets or copy a finished example. Choose new geometry, colors, constraints and timing from the human's task.

## 4. Inspect complete motion evidence

Use pixel_contact_sheet for EVERY frame, paging/chunking long ranges. Inspect native size, integer zoom and named local regions. Check anchor contact, silhouette/volume consistency, material highlights, color drift, clipping, ghost pixels and trajectory continuity.

Use pixel_motion_check and read every returned page. It reports suspicions, not a natural-motion verdict. View before/current/after crops; only apply selected repairs justified by actual images. Do not bulk-erase particles or decorations.

Examine actual durations, a two-loop timing sheet and last/first frames for loops. Short key poses can be missed by elapsed-time sampling, so also inspect the complete frame list. The desktop preview playback rate does not change export timing. GIF uses 10ms timing units; choose compatible durations or report rounding.

Continue with pixel_help(topic="inspection_workflow"), repair observed defects, obtain fresh evidence and save the editable project after submitting the review.
