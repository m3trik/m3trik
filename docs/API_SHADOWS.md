# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

_Generated: 2026-07-15_

## Genuine cross-layer collisions (21)

_Touch `pythontk` or span 3+ packages — the real DRY review surface._

### `AudioUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`AudioUtils`](blendertk/audio_utils/_audio_utils.py#L66)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L84)
- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L15)

### `CoreUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`CoreUtils`](blendertk/core_utils/_core_utils.py#L721)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L219)
- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L14)

### `Selection` — blendertk, mayatk, tentacle

- `blendertk` — [`Selection`](blendertk/edit_utils/selection.py#L33)
- `mayatk` — [`Selection`](mayatk/edit_utils/selection.py#L19)
- `tentacle` — [`Selection`](tentacle/slots/blender/selection.py#L9)
- `tentacle` — [`Selection`](tentacle/slots/maya/selection.py#L10)

### `ShotManifest` — mayatk, pythontk

- `mayatk` — [`ShotManifest`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L156)
- `pythontk` — [`ShotManifest`](pythontk/core_utils/engines/shots/manifest/manifest_engine.py#L172)

### `ShotStore` — mayatk, pythontk

- `mayatk` — [`ShotStore`](mayatk/anim_utils/shots/_shots.py#L272)
- `pythontk` — [`ShotStore`](pythontk/core_utils/engines/shots/shot_model.py#L294)

### `apply` — mayatk, pythontk

- `mayatk` — [`apply`](mayatk/anim_utils/shots/_shot_apply.py#L133)
- `pythontk` — [`apply`](pythontk/core_utils/engines/shots/shot_apply.py#L43)

### `compute_duration` — mayatk, pythontk

- `mayatk` — [`compute_duration`](mayatk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L449)
- `pythontk` — [`compute_duration`](pythontk/core_utils/engines/shots/manifest/behaviors/_behaviors.py#L229)

### `defaults` — blendertk, mayatk, uitk

- `blendertk` — [`defaults`](blendertk/env_utils/maya_bridge/parameters.py#L111)
- `blendertk` — [`defaults`](blendertk/env_utils/unity_bridge/parameters.py#L145)
- `blendertk` — [`defaults`](blendertk/mat_utils/marmoset_bridge/parameters.py#L240)
- `blendertk` — [`defaults`](blendertk/mat_utils/marmoset_bridge/template_params.py#L60)
- `blendertk` — [`defaults`](blendertk/mat_utils/substance_bridge/parameters.py#L179)
- `blendertk` — [`defaults`](blendertk/uv_utils/rizom_bridge/parameters.py#L332)
- `mayatk` — [`defaults`](mayatk/env_utils/blender_bridge/parameters.py#L110)
- `mayatk` — [`defaults`](mayatk/env_utils/unity_bridge/parameters.py#L147)
- `mayatk` — [`defaults`](mayatk/mat_utils/marmoset_bridge/parameters.py#L240)
- `mayatk` — [`defaults`](mayatk/mat_utils/marmoset_bridge/template_params.py#L60)
- `mayatk` — [`defaults`](mayatk/mat_utils/substance_bridge/parameters.py#L179)
- `mayatk` — [`defaults`](mayatk/uv_utils/rizom_bridge/parameters.py#L326)
- `uitk` — [`defaults`](uitk/bridge/parameters.py#L48)

### `launch` — mayatk, tentacle

- `mayatk` — [`launch`](mayatk/node_utils/attributes/channels/__init__.py#L14)
- `tentacle` — [`launch`](tentacle/tcl_blender.py#L1405)

### `leaf_name` — mayatk, pythontk

- `mayatk` — [`leaf_name`](mayatk/core_utils/_core_utils.py#L42)
- `pythontk` — [`leaf_name`](pythontk/core_utils/engines/shots/shot_model.py#L39)

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

### `main` — blendertk, mayatk, uitk

- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/import.py#L26)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/bake.py#L123)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/import.py#L32)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/lookdev.py#L41)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/import.py#L28)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/bake.py#L123)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/import.py#L32)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/lookdev.py#L41)
- `uitk` — [`main`](uitk/compile.py#L521)

### `python_literal` — blendertk, mayatk, uitk

- `blendertk` — [`python_literal`](blendertk/mat_utils/marmoset_bridge/template_params.py#L49)
- `mayatk` — [`python_literal`](mayatk/mat_utils/marmoset_bridge/template_params.py#L49)
- `uitk` — [`python_literal`](uitk/bridge/formatters.py#L29)

### `referenced_keys` — blendertk, mayatk, uitk

- `blendertk` — [`referenced_keys`](blendertk/env_utils/maya_bridge/parameters.py#L106)
- `blendertk` — [`referenced_keys`](blendertk/env_utils/unity_bridge/parameters.py#L140)
- `blendertk` — [`referenced_keys`](blendertk/mat_utils/marmoset_bridge/parameters.py#L235)
- `blendertk` — [`referenced_keys`](blendertk/mat_utils/substance_bridge/parameters.py#L174)
- `blendertk` — [`referenced_keys`](blendertk/uv_utils/rizom_bridge/parameters.py#L327)
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
- `blendertk` — [`render_context`](blendertk/uv_utils/rizom_bridge/parameters.py#L337)
- `mayatk` — [`render_context`](mayatk/env_utils/blender_bridge/parameters.py#L115)
- `mayatk` — [`render_context`](mayatk/env_utils/unity_bridge/parameters.py#L152)
- `mayatk` — [`render_context`](mayatk/mat_utils/marmoset_bridge/parameters.py#L245)
- `mayatk` — [`render_context`](mayatk/uv_utils/rizom_bridge/parameters.py#L331)
- `uitk` — [`render_context`](uitk/bridge/parameters.py#L53)

### `resolve_duration` — mayatk, pythontk

- `mayatk` — [`resolve_duration`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L110)
- `pythontk` — [`resolve_duration`](pythontk/core_utils/engines/shots/manifest/manifest_engine.py#L48)

### `resolve_ranges` — mayatk, pythontk

- `mayatk` — [`resolve_ranges`](mayatk/anim_utils/shots/shot_manifest/range_resolver.py#L25)
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

---

## Intentional mayatk↔blendertk port parity (222)

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
- `ClipMotionMixin`
- `ColorId`
- `ColorIdSlots`
- `ControlNodes`
- `Controls`
- `Creator`
- `CurtainDrape`
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
- `GapManagerMixin`
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
- `ManifestTableMixin`
- `MarkerManagerMixin`
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
- `ShotManifestController`
- `ShotManifestSlots`
- `ShotNavMixin`
- `ShotSequencer`
- `ShotSequencerController`
- `ShotSequencerSlots`
- `ShotsController`
- `ShotsSlots`
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
- `active_object_set`
- `all_ops`
- `apply_sky_preset`
- `apply_template`
- `auto_instance`
- `autostart`
- `begin_log`
- `build_bake_pairs_manifest`
- `build_curve_preview`
- `build_hierarchy_structure`
- `classify_log_line`
- `clear`
- `collect_mesh_objects`
- `collect_segments`
- `curves_for_attr`
- `default_log_path`
- `derive_per_run_log_path`
- `describe`
- `describe_op`
- `dispatch_log_lines`
- `extract_attributes`
- `find_material`
- `find_painter_exe`
- `find_tree_item_by_name`
- `fmt_behavior`
- `format_behavior_html`
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
- `scale_attribute_keys`
- `set_style`
- `should_keep_node_by_type`
- `show`
- `split_high_low`
- `start_server`
- `start_toolbag_log_tail`
- `stop_server`
- `strip_unsupported`
- `summary`
- `to_context`
- `toggle`
- `uninstall`
- `user_plugin_dir`
- `version`
- `wire_materials_from_manifest`
