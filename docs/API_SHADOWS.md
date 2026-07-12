# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

_Generated: 2026-07-12_

## Genuine cross-layer collisions (65)

_Touch `pythontk` or span 3+ packages — the real DRY review surface._

### `ActiveShotChanged` — mayatk, pythontk

- `mayatk` — [`ActiveShotChanged`](mayatk/anim_utils/shots/_shots.py#L440)
- `pythontk` — [`ActiveShotChanged`](pythontk/core_utils/engines/shots/shot_model.py#L256)

### `AudioMethod` — mayatk, pythontk

- `mayatk` — [`AudioMethod`](mayatk/anim_utils/shots/shot_manifest/mapping/_spec.py#L28)
- `pythontk` — [`AudioMethod`](pythontk/core_utils/engines/shots/manifest/mapping/_spec.py#L28)

### `AudioUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`AudioUtils`](blendertk/audio_utils/_audio_utils.py#L66)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L84)
- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L15)

### `BatchComplete` — mayatk, pythontk

- `mayatk` — [`BatchComplete`](mayatk/anim_utils/shots/_shots.py#L455)
- `pythontk` — [`BatchComplete`](pythontk/core_utils/engines/shots/shot_model.py#L271)

### `BehaviorSpec` — mayatk, pythontk

- `mayatk` — [`BehaviorSpec`](mayatk/anim_utils/shots/shot_manifest/behaviors/_spec.py#L68)
- `pythontk` — [`BehaviorSpec`](pythontk/core_utils/engines/shots/manifest/behaviors/_spec.py#L69)

### `BuilderObject` — mayatk, pythontk

- `mayatk` — [`BuilderObject`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L36)
- `pythontk` — [`BuilderObject`](pythontk/core_utils/engines/shots/manifest/manifest_model.py#L46)

### `BuilderStep` — mayatk, pythontk

- `mayatk` — [`BuilderStep`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L46)
- `pythontk` — [`BuilderStep`](pythontk/core_utils/engines/shots/manifest/manifest_model.py#L56)

### `ColumnMap` — mayatk, pythontk

- `mayatk` — [`ColumnMap`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L358)
- `pythontk` — [`ColumnMap`](pythontk/core_utils/engines/shots/manifest/manifest_model.py#L246)

### `CoreUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`CoreUtils`](blendertk/core_utils/_core_utils.py#L678)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L219)
- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L14)

### `MappingSpec` — mayatk, pythontk

- `mayatk` — [`MappingSpec`](mayatk/anim_utils/shots/shot_manifest/mapping/_spec.py#L101)
- `pythontk` — [`MappingSpec`](pythontk/core_utils/engines/shots/manifest/mapping/_spec.py#L101)

### `MovePlan` — mayatk, pythontk

- `mayatk` — [`MovePlan`](mayatk/anim_utils/shots/_shot_plan.py#L69)
- `pythontk` — [`MovePlan`](pythontk/core_utils/engines/shots/shot_plan.py#L63)

### `ObjectStatus` — mayatk, pythontk

- `mayatk` — [`ObjectStatus`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L277)
- `pythontk` — [`ObjectStatus`](pythontk/core_utils/engines/shots/manifest/manifest_model.py#L165)

### `OutputStream` — blendertk, mayatk, pythontk

- `blendertk` — [`OutputStream`](blendertk/mat_utils/substance_bridge/connection.py#L89)
- `mayatk` — [`OutputStream`](mayatk/mat_utils/substance_bridge/connection.py#L89)
- `pythontk` — [`OutputStream`](pythontk/core_utils/process_stream.py#L37)

### `PlannedShot` — mayatk, pythontk

- `mayatk` — [`PlannedShot`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L113)
- `pythontk` — [`PlannedShot`](pythontk/core_utils/engines/shots/manifest/manifest_model.py#L126)

### `ScenePersistence` — mayatk, pythontk

- `mayatk` — [`ScenePersistence`](mayatk/anim_utils/shots/_shots.py#L102)
- `pythontk` — [`ScenePersistence`](pythontk/core_utils/engines/shots/shot_model.py#L71)

### `Selection` — blendertk, mayatk, tentacle

- `blendertk` — [`Selection`](blendertk/edit_utils/selection.py#L30)
- `mayatk` — [`Selection`](mayatk/edit_utils/selection.py#L19)
- `tentacle` — [`Selection`](tentacle/slots/blender/selection.py#L9)
- `tentacle` — [`Selection`](tentacle/slots/maya/selection.py#L10)

### `SettingsChanged` — mayatk, pythontk

- `mayatk` — [`SettingsChanged`](mayatk/anim_utils/shots/_shots.py#L448)
- `pythontk` — [`SettingsChanged`](pythontk/core_utils/engines/shots/shot_model.py#L264)

### `ShotBlock` — mayatk, pythontk

- `mayatk` — [`ShotBlock`](mayatk/anim_utils/shots/_shots.py#L292)
- `pythontk` — [`ShotBlock`](pythontk/core_utils/engines/shots/shot_model.py#L108)

### `ShotDefined` — mayatk, pythontk

- `mayatk` — [`ShotDefined`](mayatk/anim_utils/shots/_shots.py#L416)
- `pythontk` — [`ShotDefined`](pythontk/core_utils/engines/shots/shot_model.py#L232)

### `ShotManifest` — mayatk, pythontk

- `mayatk` — [`ShotManifest`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L705)
- `pythontk` — [`ShotManifest`](pythontk/core_utils/engines/shots/manifest/manifest_engine.py#L172)

### `ShotMove` — mayatk, pythontk

- `mayatk` — [`ShotMove`](mayatk/anim_utils/shots/_shot_plan.py#L41)
- `pythontk` — [`ShotMove`](pythontk/core_utils/engines/shots/shot_plan.py#L35)

### `ShotRemoved` — mayatk, pythontk

- `mayatk` — [`ShotRemoved`](mayatk/anim_utils/shots/_shots.py#L432)
- `pythontk` — [`ShotRemoved`](pythontk/core_utils/engines/shots/shot_model.py#L248)

### `ShotStore` — mayatk, pythontk

- `mayatk` — [`ShotStore`](mayatk/anim_utils/shots/_shots.py#L478)
- `pythontk` — [`ShotStore`](pythontk/core_utils/engines/shots/shot_model.py#L294)

### `ShotUpdated` — mayatk, pythontk

- `mayatk` — [`ShotUpdated`](mayatk/anim_utils/shots/_shots.py#L424)
- `pythontk` — [`ShotUpdated`](pythontk/core_utils/engines/shots/shot_model.py#L240)

### `StepStatus` — mayatk, pythontk

- `mayatk` — [`StepStatus`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L293)
- `pythontk` — [`StepStatus`](pythontk/core_utils/engines/shots/manifest/manifest_model.py#L181)

### `StoreEvent` — mayatk, pythontk

- `mayatk` — [`StoreEvent`](mayatk/anim_utils/shots/_shots.py#L404)
- `pythontk` — [`StoreEvent`](pythontk/core_utils/engines/shots/shot_model.py#L220)

### `StoreInvalidated` — mayatk, pythontk

- `mayatk` — [`StoreInvalidated`](mayatk/anim_utils/shots/_shots.py#L462)
- `pythontk` — [`StoreInvalidated`](pythontk/core_utils/engines/shots/shot_model.py#L278)

### `TaskFactory` — blendertk, mayatk, pythontk

- `blendertk` — [`TaskFactory`](blendertk/env_utils/scene_exporter/task_factory.py#L14)
- `mayatk` — [`TaskFactory`](mayatk/env_utils/scene_exporter/task_factory.py#L9)
- `pythontk` — [`TaskFactory`](pythontk/core_utils/task_factory.py#L23)

### `Weights` — blendertk, mayatk, pythontk

- `blendertk` — [`Weights`](blendertk/anim_utils/blendshape_animator/weights.py#L13)
- `mayatk` — [`Weights`](mayatk/anim_utils/blendshape_animator/weights.py#L7)
- `pythontk` — [`Weights`](pythontk/math_utils/weights.py#L12)

### `apply` — mayatk, pythontk

- `mayatk` — [`apply`](mayatk/anim_utils/shots/_shot_apply.py#L128)
- `pythontk` — [`apply`](pythontk/core_utils/engines/shots/shot_apply.py#L43)

### `compute_duration` — mayatk, pythontk

- `mayatk` — [`compute_duration`](mayatk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L617)
- `pythontk` — [`compute_duration`](pythontk/core_utils/engines/shots/manifest/behaviors/_behaviors.py#L229)

### `defaults` — blendertk, mayatk, uitk

- `blendertk` — [`defaults`](blendertk/env_utils/maya_bridge/parameters.py#L111)
- `blendertk` — [`defaults`](blendertk/env_utils/unity_bridge/parameters.py#L145)
- `blendertk` — [`defaults`](blendertk/mat_utils/marmoset_bridge/parameters.py#L240)
- `blendertk` — [`defaults`](blendertk/mat_utils/marmoset_bridge/template_params.py#L60)
- `blendertk` — [`defaults`](blendertk/mat_utils/substance_bridge/parameters.py#L179)
- `blendertk` — [`defaults`](blendertk/uv_utils/rizom_bridge/parameters.py#L91)
- `mayatk` — [`defaults`](mayatk/env_utils/blender_bridge/parameters.py#L110)
- `mayatk` — [`defaults`](mayatk/env_utils/unity_bridge/parameters.py#L147)
- `mayatk` — [`defaults`](mayatk/mat_utils/marmoset_bridge/parameters.py#L240)
- `mayatk` — [`defaults`](mayatk/mat_utils/marmoset_bridge/template_params.py#L60)
- `mayatk` — [`defaults`](mayatk/mat_utils/substance_bridge/parameters.py#L179)
- `mayatk` — [`defaults`](mayatk/uv_utils/rizom_bridge/parameters.py#L326)
- `uitk` — [`defaults`](uitk/bridge/parameters.py#L48)

### `detect_behaviors` — mayatk, pythontk

- `mayatk` — [`detect_behaviors`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L339)
- `pythontk` — [`detect_behaviors`](pythontk/core_utils/engines/shots/manifest/manifest_model.py#L227)

### `discover` — mayatk, pythontk

- `mayatk` — [`discover`](mayatk/anim_utils/shots/shot_manifest/mapping/_mapping.py#L103)
- `pythontk` — [`discover`](pythontk/core_utils/engines/shots/manifest/mapping/_mapping.py#L103)

### `format_markdown` — mayatk, pythontk

- `mayatk` — [`format_markdown`](mayatk/anim_utils/shots/shot_manifest/behaviors/_spec.py#L110)
- `mayatk` — [`format_markdown`](mayatk/anim_utils/shots/shot_manifest/mapping/_spec.py#L123)
- `pythontk` — [`format_markdown`](pythontk/core_utils/engines/shots/manifest/behaviors/_spec.py#L111)
- `pythontk` — [`format_markdown`](pythontk/core_utils/engines/shots/manifest/mapping/_spec.py#L123)

### `launch` — mayatk, tentacle

- `mayatk` — [`launch`](mayatk/node_utils/attributes/channels/__init__.py#L14)
- `tentacle` — [`launch`](tentacle/tcl_blender.py#L1405)

### `leaf_name` — mayatk, pythontk

- `mayatk` — [`leaf_name`](mayatk/core_utils/_core_utils.py#L42)
- `pythontk` — [`leaf_name`](pythontk/core_utils/engines/shots/shot_model.py#L39)

### `list_behaviors` — mayatk, pythontk

- `mayatk` — [`list_behaviors`](mayatk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L127)
- `pythontk` — [`list_behaviors`](pythontk/core_utils/engines/shots/manifest/behaviors/_behaviors.py#L124)

### `list_template_modes` — blendertk, mayatk, pythontk

- `blendertk` — [`list_template_modes`](blendertk/env_utils/maya_bridge/_maya_bridge.py#L81)
- `blendertk` — [`list_template_modes`](blendertk/mat_utils/marmoset_bridge/_marmoset_engine.py#L73)
- `blendertk` — [`list_template_modes`](blendertk/mat_utils/substance_bridge/_substance_bridge.py#L186)
- `mayatk` — [`list_template_modes`](mayatk/env_utils/blender_bridge/_blender_bridge.py#L73)
- `mayatk` — [`list_template_modes`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L73)
- `mayatk` — [`list_template_modes`](mayatk/mat_utils/substance_bridge/_substance_bridge.py#L206)
- `pythontk` — [`list_template_modes`](pythontk/core_utils/script_template.py#L81)

### `list_templates` — blendertk, mayatk, pythontk

- `blendertk` — [`list_templates`](blendertk/env_utils/maya_bridge/_maya_bridge.py#L71)
- `blendertk` — [`list_templates`](blendertk/mat_utils/marmoset_bridge/_marmoset_engine.py#L59)
- `blendertk` — [`list_templates`](blendertk/mat_utils/substance_bridge/_substance_bridge.py#L106)
- `blendertk` — [`list_templates`](blendertk/ui_utils/style_setter/_style_setter.py#L99)
- `mayatk` — [`list_templates`](mayatk/env_utils/blender_bridge/_blender_bridge.py#L63)
- `mayatk` — [`list_templates`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L59)
- `mayatk` — [`list_templates`](mayatk/mat_utils/substance_bridge/_substance_bridge.py#L126)
- `mayatk` — [`list_templates`](mayatk/ui_utils/style_setter/_style_setter.py#L113)
- `pythontk` — [`list_templates`](pythontk/core_utils/script_template.py#L47)

### `load_behavior` — mayatk, pythontk

- `mayatk` — [`load_behavior`](mayatk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L69)
- `pythontk` — [`load_behavior`](pythontk/core_utils/engines/shots/manifest/behaviors/_behaviors.py#L71)

### `load_mapping` — mayatk, pythontk

- `mayatk` — [`load_mapping`](mayatk/anim_utils/shots/shot_manifest/mapping/_mapping.py#L126)
- `pythontk` — [`load_mapping`](pythontk/core_utils/engines/shots/manifest/mapping/_mapping.py#L126)

### `main` — blendertk, mayatk, uitk

- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/import.py#L26)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/bake.py#L123)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/import.py#L32)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/lookdev.py#L41)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/import.py#L28)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/bake.py#L123)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/import.py#L32)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/lookdev.py#L41)
- `uitk` — [`main`](uitk/compile.py#L526)

### `parse_csv` — mayatk, pythontk

- `mayatk` — [`parse_csv`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L530)
- `pythontk` — [`parse_csv`](pythontk/core_utils/engines/shots/manifest/manifest_model.py#L418)

### `plan_respace` — mayatk, pythontk

- `mayatk` — [`plan_respace`](mayatk/anim_utils/shots/_shot_plan.py#L215)
- `pythontk` — [`plan_respace`](pythontk/core_utils/engines/shots/shot_plan.py#L209)

### `plan_ripple_downstream` — mayatk, pythontk

- `mayatk` — [`plan_ripple_downstream`](mayatk/anim_utils/shots/_shot_plan.py#L255)
- `pythontk` — [`plan_ripple_downstream`](pythontk/core_utils/engines/shots/shot_plan.py#L249)

### `plan_ripple_upstream` — mayatk, pythontk

- `mayatk` — [`plan_ripple_upstream`](mayatk/anim_utils/shots/_shot_plan.py#L291)
- `pythontk` — [`plan_ripple_upstream`](pythontk/core_utils/engines/shots/shot_plan.py#L359)

### `prune_to_top_boundaries` — mayatk, pythontk

- `mayatk` — [`prune_to_top_boundaries`](mayatk/anim_utils/shots/shot_manifest/manifest_data.py#L84)
- `pythontk` — [`prune_to_top_boundaries`](pythontk/core_utils/engines/shots/manifest/range_resolver.py#L16)

### `python_literal` — blendertk, mayatk, uitk

- `blendertk` — [`python_literal`](blendertk/mat_utils/marmoset_bridge/template_params.py#L49)
- `mayatk` — [`python_literal`](mayatk/mat_utils/marmoset_bridge/template_params.py#L49)
- `uitk` — [`python_literal`](uitk/bridge/formatters.py#L29)

### `referenced_keys` — blendertk, mayatk, uitk

- `blendertk` — [`referenced_keys`](blendertk/env_utils/maya_bridge/parameters.py#L106)
- `blendertk` — [`referenced_keys`](blendertk/env_utils/unity_bridge/parameters.py#L140)
- `blendertk` — [`referenced_keys`](blendertk/mat_utils/marmoset_bridge/parameters.py#L235)
- `blendertk` — [`referenced_keys`](blendertk/mat_utils/substance_bridge/parameters.py#L174)
- `blendertk` — [`referenced_keys`](blendertk/uv_utils/rizom_bridge/parameters.py#L86)
- `mayatk` — [`referenced_keys`](mayatk/env_utils/blender_bridge/parameters.py#L105)
- `mayatk` — [`referenced_keys`](mayatk/env_utils/unity_bridge/parameters.py#L142)
- `mayatk` — [`referenced_keys`](mayatk/mat_utils/marmoset_bridge/parameters.py#L235)
- `mayatk` — [`referenced_keys`](mayatk/mat_utils/substance_bridge/parameters.py#L174)
- `mayatk` — [`referenced_keys`](mayatk/uv_utils/rizom_bridge/parameters.py#L321)
- `uitk` — [`referenced_keys`](uitk/bridge/parameters.py#L34)

### `register` — blendertk, mayatk, tentacle

- `blendertk` — [`register`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L21)
- `mayatk` — [`register`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L21)
- `tentacle` — [`register`](tentacle/tcl_blender.py#L1410)

### `render_context` — blendertk, mayatk, uitk

- `blendertk` — [`render_context`](blendertk/env_utils/maya_bridge/parameters.py#L116)
- `blendertk` — [`render_context`](blendertk/env_utils/unity_bridge/parameters.py#L150)
- `blendertk` — [`render_context`](blendertk/mat_utils/marmoset_bridge/parameters.py#L245)
- `blendertk` — [`render_context`](blendertk/uv_utils/rizom_bridge/parameters.py#L96)
- `mayatk` — [`render_context`](mayatk/env_utils/blender_bridge/parameters.py#L115)
- `mayatk` — [`render_context`](mayatk/env_utils/unity_bridge/parameters.py#L152)
- `mayatk` — [`render_context`](mayatk/mat_utils/marmoset_bridge/parameters.py#L245)
- `mayatk` — [`render_context`](mayatk/uv_utils/rizom_bridge/parameters.py#L331)
- `uitk` — [`render_context`](uitk/bridge/parameters.py#L53)

### `resolve` — mayatk, pythontk

- `mayatk` — [`resolve`](mayatk/anim_utils/shots/shot_manifest/mapping/_mapping.py#L175)
- `pythontk` — [`resolve`](pythontk/core_utils/engines/shots/manifest/mapping/_mapping.py#L175)

### `resolve_clip_specs` — mayatk, pythontk

- `mayatk` — [`resolve_clip_specs`](mayatk/anim_utils/shots/_shots.py#L376)
- `pythontk` — [`resolve_clip_specs`](pythontk/core_utils/engines/shots/shot_model.py#L192)

### `resolve_duration` — mayatk, pythontk

- `mayatk` — [`resolve_duration`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L154)
- `pythontk` — [`resolve_duration`](pythontk/core_utils/engines/shots/manifest/manifest_engine.py#L48)

### `resolve_keys` — mayatk, pythontk

- `mayatk` — [`resolve_keys`](mayatk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L176)
- `pythontk` — [`resolve_keys`](pythontk/core_utils/engines/shots/manifest/behaviors/_behaviors.py#L173)

### `resolve_ranges` — mayatk, pythontk

- `mayatk` — [`resolve_ranges`](mayatk/anim_utils/shots/shot_manifest/range_resolver.py#L17)
- `pythontk` — [`resolve_ranges`](pythontk/core_utils/engines/shots/manifest/range_resolver.py#L37)

### `run_batch` — blendertk, mayatk, pythontk

- `blendertk` — [`run_batch`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/job.py#L30)
- `mayatk` — [`run_batch`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/job.py#L30)
- `pythontk` — [`run_batch`](pythontk/net_utils/rpc/job.py#L55)

### `template_modes` — blendertk, mayatk, pythontk

- `blendertk` — [`template_modes`](blendertk/env_utils/maya_bridge/_maya_bridge.py#L76)
- `blendertk` — [`template_modes`](blendertk/mat_utils/marmoset_bridge/_marmoset_engine.py#L64)
- `mayatk` — [`template_modes`](mayatk/env_utils/blender_bridge/_blender_bridge.py#L68)
- `mayatk` — [`template_modes`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L64)
- `pythontk` — [`template_modes`](pythontk/core_utils/script_template.py#L56)

### `templates` — mayatk, pythontk

- `mayatk` — [`templates`](mayatk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L45)
- `mayatk` — [`templates`](mayatk/anim_utils/shots/shot_manifest/mapping/_mapping.py#L80)
- `pythontk` — [`templates`](pythontk/core_utils/engines/shots/manifest/behaviors/_behaviors.py#L48)
- `pythontk` — [`templates`](pythontk/core_utils/engines/shots/manifest/mapping/_mapping.py#L80)

### `validate_attributes` — mayatk, pythontk

- `mayatk` — [`validate_attributes`](mayatk/anim_utils/shots/shot_manifest/behaviors/_spec.py#L46)
- `pythontk` — [`validate_attributes`](pythontk/core_utils/engines/shots/manifest/behaviors/_spec.py#L47)

### `validate_audio_resolve` — mayatk, pythontk

- `mayatk` — [`validate_audio_resolve`](mayatk/anim_utils/shots/shot_manifest/mapping/_spec.py#L76)
- `pythontk` — [`validate_audio_resolve`](pythontk/core_utils/engines/shots/manifest/mapping/_spec.py#L76)

### `validate_default_behaviors` — mayatk, pythontk

- `mayatk` — [`validate_default_behaviors`](mayatk/anim_utils/shots/shot_manifest/mapping/_spec.py#L89)
- `pythontk` — [`validate_default_behaviors`](pythontk/core_utils/engines/shots/manifest/mapping/_spec.py#L89)

### `validate_duration` — mayatk, pythontk

- `mayatk` — [`validate_duration`](mayatk/anim_utils/shots/shot_manifest/behaviors/_spec.py#L28)
- `pythontk` — [`validate_duration`](pythontk/core_utils/engines/shots/manifest/behaviors/_spec.py#L29)

### `validate_verify` — mayatk, pythontk

- `mayatk` — [`validate_verify`](mayatk/anim_utils/shots/shot_manifest/behaviors/_spec.py#L37)
- `pythontk` — [`validate_verify`](pythontk/core_utils/engines/shots/manifest/behaviors/_spec.py#L38)

---

## Intentional mayatk↔blendertk port parity (200)

_blendertk deliberately mirrors mayatk's public names (branch-free tentacle slots). Expected — not DRY violations. Names only:_

- `AnchorStrategy`
- `AnimUtils`
- `AnimationMacros`
- `Applicator`
- `ApplyStatus`
- `ArnoldBridge`
- `ArnoldBridgeSlots`
- `AssemblyReconstructor`
- `AudioClipsSlots`
- `AutoInstancer`
- `BakeAnalysis`
- `BakeResult`
- `BakeSessionStore`
- `Bevel`
- `BevelSlots`
- `BlendshapeAnimator`
- `BlendshapeAnimatorSlots`
- `Bridge`
- `BridgeSlots`
- `CalculatorController`
- `CalculatorSlots`
- `CamUtils`
- `Channels`
- `ChannelsSlots`
- `ColorId`
- `ColorIdSlots`
- `ControlNodes`
- `Controls`
- `Creator`
- `CurtainRig`
- `CurtainSlots`
- `CurveToTube`
- `CurveToTubeSlots`
- `CutOnAxisSlots`
- `DataNodes`
- `DisplayMacros`
- `DisplayUtils`
- `DuplicateGrid`
- `DuplicateGridSlots`
- `DuplicateLinear`
- `DuplicateLinearSlots`
- `DuplicateRadial`
- `DuplicateRadialSlots`
- `DynamicPipe`
- `DynamicPipeSlots`
- `EditMacros`
- `EditUtils`
- `EnvUtils`
- `ExplodedViewSlots`
- `FKChainStrategy`
- `FbxUtils`
- `GameShaderSlots`
- `GeometryMatcher`
- `HdrManagerSlots`
- `HierarchyManager`
- `HierarchyManagerController`
- `HierarchyManagerSlots`
- `HierarchyMapBuilder`
- `HierarchySidecar`
- `HierarchyTreeRenderer`
- `ImageToPlane`
- `ImageToPlaneSlots`
- `ImageTracer`
- `ImageTracerSlots`
- `InstanceCandidate`
- `InstanceGroup`
- `InstancingStrategy`
- `Keyframes`
- `LightUtils`
- `LightmapBaker`
- `LightmapBakerSlots`
- `MacroManager`
- `MacroManagerSlots`
- `Macros`
- `MarmosetBridge`
- `MarmosetBridgeSlots`
- `MarmosetConnection`
- `MarmosetEngine`
- `MatManifest`
- `MatUpdater`
- `MatUpdaterSlots`
- `MatUtils`
- `Matrices`
- `MeshDiagnostics`
- `MirrorSlots`
- `Naming`
- `NamingSlots`
- `NodeUtils`
- `NurbsUtils`
- `PainterRpcClient`
- `Preview`
- `ReferenceManagerSlots`
- `RenderOpacity`
- `RenderOpacitySlots`
- `RestoreResult`
- `RigUtils`
- `RizomBridgeSlots`
- `RizomUVBridge`
- `ScaleKeys`
- `SceneExporter`
- `SceneExporterSlots`
- `ScriptConsole`
- `ScriptJobManager`
- `SelectionMacros`
- `ShaderTemplatesSlots`
- `ShadowRig`
- `ShadowRigSlots`
- `ShellXformSlots`
- `SmartBake`
- `SmartBakeSlots`
- `SnapSlots`
- `SplineIKStrategy`
- `StaggerKeys`
- `StrategyConfig`
- `StrategyType`
- `StyleSetter`
- `SubstanceBridge`
- `SubstanceBridgeSlots`
- `SubstanceConnection`
- `Target`
- `Targets`
- `TaskManager`
- `TelescopeRig`
- `TelescopeRigSlots`
- `TextureBaker`
- `TexturePathEditorSlots`
- `TransformDiagnostics`
- `TreePathMatcher`
- `TubePath`
- `TubeRig`
- `TubeRigBundle`
- `TubeRigSlots`
- `TubeStrategy`
- `UiMacros`
- `UiUtils`
- `UnityBridge`
- `UnityBridgeSlots`
- `UvUtils`
- `Validator`
- `WheelRig`
- `WheelRigSlots`
- `XformUtils`
- `all_ops`
- `apply_sky_preset`
- `apply_template`
- `auto_instance`
- `autostart`
- `begin_log`
- `build_bake_pairs_manifest`
- `build_hierarchy_structure`
- `classify_log_line`
- `clear`
- `collect_mesh_objects`
- `default_log_path`
- `derive_per_run_log_path`
- `describe`
- `describe_op`
- `dispatch_log_lines`
- `find_material`
- `find_painter_exe`
- `find_tree_item_by_name`
- `frame_in_viewport`
- `get`
- `get_bounding_box`
- `get_selected_object_names`
- `get_selected_tree_items`
- `install`
- `is_installed`
- `is_main_thread_marshalling_active`
- `is_running`
- `list_delivery_modes`
- `list_materials`
- `list_ops`
- `list_styles`
- `load_manifest`
- `log`
- `node_ref`
- `parse_template`
- `ping`
- `render_cli_context`
- `render_js_context`
- `resolve_painter_log_path`
- `resolve_ref`
- `resolve_toolbag_log_path`
- `restore_session`
- `run_on_main_thread`
- `set_style`
- `should_keep_node_by_type`
- `show`
- `split_high_low`
- `start_server`
- `start_toolbag_log_tail`
- `stop_server`
- `summary`
- `to_context`
- `toggle`
- `uninstall`
- `user_plugin_dir`
- `version`
- `wire_materials_from_manifest`
