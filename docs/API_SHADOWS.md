# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

_Generated: 2026-07-26_

## Genuine cross-layer collisions (7)

_Touch `pythontk` or span 3+ packages — the real DRY review surface._

### `AudioUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`AudioUtils`](blendertk/audio_utils/_audio_utils.py#L66)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L84)
- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L15)

### `CoreUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`CoreUtils`](blendertk/core_utils/_core_utils.py#L746)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L220)
- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L14)

### `Selection` — blendertk, mayatk, tentacle

- `blendertk` — [`Selection`](blendertk/edit_utils/selection.py#L33)
- `mayatk` — [`Selection`](mayatk/edit_utils/selection.py#L19)
- `tentacle` — [`Selection`](tentacle/slots/blender/selection.py#L9)
- `tentacle` — [`Selection`](tentacle/slots/maya/selection.py#L10)

### `ShotManifest` — mayatk, pythontk

- `mayatk` — [`ShotManifest`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L114)
- `pythontk` — [`ShotManifest`](pythontk/core_utils/engines/shots/manifest/manifest_engine.py#L91)

### `ShotStore` — mayatk, pythontk

- `mayatk` — [`ShotStore`](mayatk/anim_utils/shots/_shots.py#L272)
- `pythontk` — [`ShotStore`](pythontk/core_utils/engines/shots/shot_model.py#L269)

### `launch` — mayatk, tentacle

- `mayatk` — [`launch`](mayatk/node_utils/attributes/channels/__init__.py#L14)
- `tentacle` — [`launch`](tentacle/tcl_blender.py#L1633)

### `register` — blendertk, mayatk, tentacle

- `blendertk` — [`register`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L21)
- `mayatk` — [`register`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L21)
- `tentacle` — [`register`](tentacle/tcl_blender.py#L1638)

---

## Intentional mayatk↔blendertk port parity (234)

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
- `HierarchyMapBuilder`
- `HierarchySidecar`
- `HierarchySync`
- `HierarchySyncController`
- `HierarchySyncSlots`
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
- `ObjectSwapper`
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
- `UsdUtils`
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
- `defaults`
- `derive_per_run_log_path`
- `describe`
- `describe_op`
- `dispatch_log_lines`
- `export_usd`
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
- `list_template_modes`
- `list_templates`
- `load_manifest`
- `log`
- `main`
- `node_ref`
- `parse_template`
- `ping`
- `python_literal`
- `referenced_keys`
- `render_cli_context`
- `render_context`
- `render_js_context`
- `resolve_painter_log_path`
- `resolve_ref`
- `resolve_toolbag_log_path`
- `restore_session`
- `run_batch`
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
- `template_modes`
- `to_context`
- `toggle`
- `uninstall`
- `user_plugin_dir`
- `version`
- `wire_materials_from_manifest`
- `write_texture_manifest`
