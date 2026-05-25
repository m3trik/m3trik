# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

_Generated: 2026-05-25_

## `AudioUtils` (2 definitions)

- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L17)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L81)

## `CoreUtils` (2 definitions)

- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L14)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L195)

## `Selection` (2 definitions)

- `mayatk` — [`Selection`](mayatk/edit_utils/selection.py#L19)
- `tentacle` — [`Selection`](tentacle/slots/maya/selection.py#L11)

## `defaults` (4 definitions)

- `uitk` — [`defaults`](uitk/bridge/parameters.py#L48)
- `mayatk` — [`defaults`](mayatk/mat_utils/marmoset_bridge/parameters.py#L240)
- `mayatk` — [`defaults`](mayatk/mat_utils/substance_bridge/parameters.py#L179)
- `mayatk` — [`defaults`](mayatk/uv_utils/rizom_bridge/parameters.py#L301)

## `main` (4 definitions)

- `uitk` — [`main`](uitk/compile.py#L526)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/bake.py#L123)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/import.py#L31)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/lookdev.py#L41)

## `referenced_keys` (4 definitions)

- `uitk` — [`referenced_keys`](uitk/bridge/parameters.py#L34)
- `mayatk` — [`referenced_keys`](mayatk/mat_utils/marmoset_bridge/parameters.py#L235)
- `mayatk` — [`referenced_keys`](mayatk/mat_utils/substance_bridge/parameters.py#L174)
- `mayatk` — [`referenced_keys`](mayatk/uv_utils/rizom_bridge/parameters.py#L296)

## `render_context` (3 definitions)

- `uitk` — [`render_context`](uitk/bridge/parameters.py#L53)
- `mayatk` — [`render_context`](mayatk/mat_utils/marmoset_bridge/parameters.py#L245)
- `mayatk` — [`render_context`](mayatk/uv_utils/rizom_bridge/parameters.py#L306)

## `run_batch` (2 definitions)

- `pythontk` — [`run_batch`](pythontk/net_utils/rpc/job.py#L55)
- `mayatk` — [`run_batch`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/job.py#L30)
