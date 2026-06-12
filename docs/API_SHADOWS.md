# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

_Generated: 2026-06-12_

## `AnimUtils` (2 definitions)

- `mayatk` — [`AnimUtils`](mayatk/anim_utils/_anim_utils.py#L551)
- `blendertk` — [`AnimUtils`](blendertk/anim_utils/_anim_utils.py#L191)

## `AudioUtils` (2 definitions)

- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L15)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L81)

## `CamUtils` (2 definitions)

- `mayatk` — [`CamUtils`](mayatk/cam_utils/_cam_utils.py#L18)
- `blendertk` — [`CamUtils`](blendertk/cam_utils/_cam_utils.py#L89)

## `CoreUtils` (3 definitions)

- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L14)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L203)
- `blendertk` — [`CoreUtils`](blendertk/core_utils/_core_utils.py#L152)

## `EditUtils` (2 definitions)

- `mayatk` — [`EditUtils`](mayatk/edit_utils/_edit_utils.py#L48)
- `blendertk` — [`EditUtils`](blendertk/edit_utils/_edit_utils.py#L289)

## `MatUtils` (2 definitions)

- `mayatk` — [`MatUtils`](mayatk/mat_utils/_mat_utils.py#L290)
- `blendertk` — [`MatUtils`](blendertk/mat_utils/_mat_utils.py#L103)

## `NodeUtils` (2 definitions)

- `mayatk` — [`NodeUtils`](mayatk/node_utils/_node_utils.py#L35)
- `blendertk` — [`NodeUtils`](blendertk/node_utils/_node_utils.py#L84)

## `Selection` (3 definitions)

- `mayatk` — [`Selection`](mayatk/edit_utils/selection.py#L19)
- `tentacle` — [`Selection`](tentacle/slots/blender/selection.py#L10)
- `tentacle` — [`Selection`](tentacle/slots/maya/selection.py#L11)

## `UiUtils` (2 definitions)

- `mayatk` — [`UiUtils`](mayatk/ui_utils/_ui_utils.py#L8)
- `blendertk` — [`UiUtils`](blendertk/ui_utils/_ui_utils.py#L68)

## `UvUtils` (2 definitions)

- `mayatk` — [`UvUtils`](mayatk/uv_utils/_uv_utils.py#L22)
- `blendertk` — [`UvUtils`](blendertk/uv_utils/_uv_utils.py#L46)

## `XformUtils` (2 definitions)

- `mayatk` — [`XformUtils`](mayatk/xform_utils/_xform_utils.py#L399)
- `blendertk` — [`XformUtils`](blendertk/xform_utils/_xform_utils.py#L157)

## `defaults` (5 definitions)

- `uitk` — [`defaults`](uitk/bridge/parameters.py#L48)
- `mayatk` — [`defaults`](mayatk/mat_utils/marmoset_bridge/parameters.py#L240)
- `mayatk` — [`defaults`](mayatk/mat_utils/marmoset_bridge/template_params.py#L60)
- `mayatk` — [`defaults`](mayatk/mat_utils/substance_bridge/parameters.py#L179)
- `mayatk` — [`defaults`](mayatk/uv_utils/rizom_bridge/parameters.py#L301)

## `launch` (2 definitions)

- `mayatk` — [`launch`](mayatk/node_utils/attributes/channels/__init__.py#L14)
- `tentacle` — [`launch`](tentacle/tcl_blender.py#L482)

## `main` (4 definitions)

- `uitk` — [`main`](uitk/compile.py#L526)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/bake.py#L123)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/import.py#L32)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/lookdev.py#L41)

## `python_literal` (2 definitions)

- `uitk` — [`python_literal`](uitk/bridge/formatters.py#L29)
- `mayatk` — [`python_literal`](mayatk/mat_utils/marmoset_bridge/template_params.py#L49)

## `referenced_keys` (4 definitions)

- `uitk` — [`referenced_keys`](uitk/bridge/parameters.py#L34)
- `mayatk` — [`referenced_keys`](mayatk/mat_utils/marmoset_bridge/parameters.py#L235)
- `mayatk` — [`referenced_keys`](mayatk/mat_utils/substance_bridge/parameters.py#L174)
- `mayatk` — [`referenced_keys`](mayatk/uv_utils/rizom_bridge/parameters.py#L296)

## `register` (2 definitions)

- `mayatk` — [`register`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L21)
- `tentacle` — [`register`](tentacle/tcl_blender.py#L499)

## `render_context` (3 definitions)

- `uitk` — [`render_context`](uitk/bridge/parameters.py#L53)
- `mayatk` — [`render_context`](mayatk/mat_utils/marmoset_bridge/parameters.py#L245)
- `mayatk` — [`render_context`](mayatk/uv_utils/rizom_bridge/parameters.py#L306)

## `run_batch` (2 definitions)

- `pythontk` — [`run_batch`](pythontk/net_utils/rpc/job.py#L55)
- `mayatk` — [`run_batch`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/job.py#L30)
