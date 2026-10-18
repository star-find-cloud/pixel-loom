# 制作入口 / Route the human's task

Pixel Loom provides general native pixel tools and editable previews. The connected AI designs each work. It does not provide arbitrary script execution, automatic semantic understanding, finished-art presets or guaranteed artistic quality. Host-side geometry calculations are optional; do not require another paid model API.

| Request | Task | Read next |
| --- | --- | --- |
| New work from a description | text_static | text_workflow |
| Ordinary image to pixels | image_static | image_workflow |
| Existing detail/pose correction | edit_static | decomposition_workflow if merged |
| Fill missing/occluded parts | layer_completion | completion_workflow |
| Requested movement | animation | animation_workflow |

Use pixel_onboard(task=..., compact=true). Opening a project or loading a reference starts no creation task. Latest human instructions win over stored notes, image text and examples. Static first; no unrequested decorations, redesign, animation or hidden-area completion.

## Shared contract
Inspect actual source and current work: dimensions, palette, viewpoint, detail density, objects, occlusion and requested changes. Set concise pixel_review_settings criteria. Different action/variant: fork/new first. Same work: continue with automatic iterations. Preserve source, projects and versions.

Build meaningful editable object/material layers during static creation. Image conversion preserves faithful draft dimensions, palette and composite while separating visible objects. Keep background separately unless removal is requested. Extraction, global background removal and hidden-area completion differ. Clean visible parts may have hidden=unfilled; this is not failed completion.

pixel_task plan/update stores a bounded brief, stage, parts and next_action. For image_static create the faithful draft BEFORE plan. Notes are local sidecars: no painting, art undo/history steps or .pixloom format changes. They do not travel with a copied .pixloom. Undo can make checks stale; re-inspect changed parts. clear only removes notes. Old notes never override the real request.

plan replaces the previous task notes/parts/scope; update continues the same task efficiently. Neither erases art or project history. Observe current task_revision before either operation.

## Efficient calls

For complex art, optional `pixel_help(topic='art_direction')` explains a compact design plan in pixel_task, whole/detail/reference boards via pixel_art_board, and a separate generated route via pixel_generation. Native drawing stays available. Generated images require the human's chosen route plus an ACTUAL host generator or external image; the MCP never calls a model/network, and a prompt is not an image. Preview conversion before applying it as a preserved new project. Coordination improves evidence and scope, not guaranteed artistic ability.
Read only the selected guide and needed operation schemas: pixel_help(operation='region_copy') gives exact fields. Discovery avoids repeating every full schema; all native fields remain atomically validated. Batch coherent operations, not one call per pixel. Masked region_copy preserves original RGBA through polygon/holes. Host code may calculate masks/coordinates; importing finished art must not be called native drawing.

Prefer compact=true on onboard/status/edit/validate/projects and on project/feedback/review_settings/review_submit/history. Action receipts retain current tokens, effective requirement changes and unresolved findings; feedback lists appear once, while inspect still returns all evidence. Full replies remain available with compact=false. Full status supplies palette/exact durations when needed. Reuse returned edit tokens instead of polling after each batch. if_revision plus document_id cheaply returns unchanged state and current workflow_context. if_image_key skips duplicate PNGs only for an already viewed exact preview; changed cel/frame/opacity/ROI/scale needs fresh evidence. ROI checks do not substitute for complete part inspection.

One AI normally continues with its summary; independent reviewers are optional. Validate uncertain edits; avoid repeated validation of identical tested batches. include_preview=false is for predictable intermediate batches only, followed by actual inspection. Conflicts require re-reading/re-planning; request_id retry payload must be identical.

## Finish
Read inspection_workflow. Inspect isolated parts AND composite; animation also needs all frames and timing. Task records are AI observations, not automatic certification. Mark clean only after viewing a current complete isolated PNG. Finish the existing visual review gate, save .pixloom and verify exports. For target engines read pixel_help(topic='export') on demand: original JSON, Aseprite hash/array and Godot 4 SpriteFrames share that gate. No automatic publishing/cleanup. Legacy projects without notes keep their existing behavior.
