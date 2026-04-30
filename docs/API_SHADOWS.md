# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

_Generated: 2026-04-29_

## `AudioUtils` (2 definitions)

- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L17)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L81)

## `CoreUtils` (2 definitions)

- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L14)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L195)

## `Selection` (2 definitions)

- `mayatk` — [`Selection`](mayatk/edit_utils/selection.py#L18)
- `tentacle` — [`Selection`](tentacle/slots/maya/selection.py#L13)
