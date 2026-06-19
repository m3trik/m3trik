# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

_Generated: 2026-06-19_

## `AudioUtils` (2 definitions)

- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L15)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L81)

## `CoreUtils` (2 definitions)

- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L14)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L203)

## `Selection` (2 definitions)

- `mayatk` — [`Selection`](mayatk/edit_utils/selection.py#L19)
- `tentacle` — [`Selection`](tentacle/slots/maya/selection.py#L11)

## `defaults` (7 definitions)

- `uitk` — [`defaults`](uitk/bridge/parameters.py#L48)
- `mayatk` — [`defaults`](mayatk/env_utils/blender_bridge/parameters.py#L110)
- `mayatk` — [`defaults`](mayatk/env_utils/unity_bridge/parameters.py#L104)
- `mayatk` — [`defaults`](mayatk/mat_utils/marmoset_bridge/parameters.py#L240)
- `mayatk` — [`defaults`](mayatk/mat_utils/marmoset_bridge/template_params.py#L60)
- `mayatk` — [`defaults`](mayatk/mat_utils/substance_bridge/parameters.py#L179)
- `mayatk` — [`defaults`](mayatk/uv_utils/rizom_bridge/parameters.py#L301)

## `launch` (2 definitions)

- `mayatk` — [`launch`](mayatk/node_utils/attributes/channels/__init__.py#L14)
- `tentacle` — [`launch`](tentacle/tcl_blender.py#L1406)

## `list_template_modes` (4 definitions)

- `pythontk` — [`list_template_modes`](pythontk/core_utils/script_template.py#L81)
- `mayatk` — [`list_template_modes`](mayatk/env_utils/blender_bridge/_blender_bridge.py#L73)
- `mayatk` — [`list_template_modes`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L73)
- `mayatk` — [`list_template_modes`](mayatk/mat_utils/substance_bridge/_substance_bridge.py#L206)

## `list_templates` (4 definitions)

- `pythontk` — [`list_templates`](pythontk/core_utils/script_template.py#L47)
- `mayatk` — [`list_templates`](mayatk/env_utils/blender_bridge/_blender_bridge.py#L63)
- `mayatk` — [`list_templates`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L59)
- `mayatk` — [`list_templates`](mayatk/mat_utils/substance_bridge/_substance_bridge.py#L126)

## `main` (5 definitions)

- `uitk` — [`main`](uitk/compile.py#L526)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/import.py#L28)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/bake.py#L123)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/import.py#L32)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/lookdev.py#L41)

## `python_literal` (2 definitions)

- `uitk` — [`python_literal`](uitk/bridge/formatters.py#L29)
- `mayatk` — [`python_literal`](mayatk/mat_utils/marmoset_bridge/template_params.py#L49)

## `referenced_keys` (6 definitions)

- `uitk` — [`referenced_keys`](uitk/bridge/parameters.py#L34)
- `mayatk` — [`referenced_keys`](mayatk/env_utils/blender_bridge/parameters.py#L105)
- `mayatk` — [`referenced_keys`](mayatk/env_utils/unity_bridge/parameters.py#L99)
- `mayatk` — [`referenced_keys`](mayatk/mat_utils/marmoset_bridge/parameters.py#L235)
- `mayatk` — [`referenced_keys`](mayatk/mat_utils/substance_bridge/parameters.py#L174)
- `mayatk` — [`referenced_keys`](mayatk/uv_utils/rizom_bridge/parameters.py#L296)

## `register` (2 definitions)

- `mayatk` — [`register`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L21)
- `tentacle` — [`register`](tentacle/tcl_blender.py#L1411)

## `render_context` (5 definitions)

- `uitk` — [`render_context`](uitk/bridge/parameters.py#L53)
- `mayatk` — [`render_context`](mayatk/env_utils/blender_bridge/parameters.py#L115)
- `mayatk` — [`render_context`](mayatk/env_utils/unity_bridge/parameters.py#L109)
- `mayatk` — [`render_context`](mayatk/mat_utils/marmoset_bridge/parameters.py#L245)
- `mayatk` — [`render_context`](mayatk/uv_utils/rizom_bridge/parameters.py#L306)

## `run_batch` (2 definitions)

- `pythontk` — [`run_batch`](pythontk/net_utils/rpc/job.py#L55)
- `mayatk` — [`run_batch`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/job.py#L30)

## `template_modes` (3 definitions)

- `pythontk` — [`template_modes`](pythontk/core_utils/script_template.py#L56)
- `mayatk` — [`template_modes`](mayatk/env_utils/blender_bridge/_blender_bridge.py#L68)
- `mayatk` — [`template_modes`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L64)
