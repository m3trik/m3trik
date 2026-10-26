# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

## Genuine cross-layer collisions (28)

_Touch `pythontk` or span 3+ packages — the real DRY review surface._

### `AudioUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`AudioUtils`](blendertk/audio_utils/_audio_utils.py#L75)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L88)
- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L24)

### `Behaviors` — blendertk, mayatk, pythontk

- `blendertk` — [`Behaviors`](blendertk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L240)
- `mayatk` — [`Behaviors`](mayatk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L157)
- `pythontk` — [`Behaviors`](pythontk/core_utils/engines/shots/manifest/behaviors/_behaviors.py#L110)

### `CoreUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`CoreUtils`](blendertk/core_utils/_core_utils.py#L462)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L280)
- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L16)

### `Finding` — mayatk, pythontk

- `mayatk` — [`Finding`](mayatk/core_utils/diagnostics/audit_records.py#L113)
- `pythontk` — [`Finding`](pythontk/file_utils/mesh_convert/export_verify.py#L43)

### `HierarchyBaseline` — blendertk, mayatk, pythontk

- `blendertk` — [`HierarchyBaseline`](blendertk/env_utils/hierarchy_sync/hierarchy_baseline.py#L43)
- `mayatk` — [`HierarchyBaseline`](mayatk/env_utils/hierarchy_sync/hierarchy_baseline.py#L50)
- `pythontk` — [`HierarchyBaseline`](pythontk/core_utils/engines/scene_export/hierarchy_baseline.py#L51)

### `InstancingStrategy` — blendertk, mayatk, pythontk

- `blendertk` — [`InstancingStrategy`](blendertk/core_utils/auto_instancer/instancing_strategy.py#L20)
- `mayatk` — [`InstancingStrategy`](mayatk/core_utils/auto_instancer/instancing_strategy.py#L23)
- `pythontk` — [`InstancingStrategy`](pythontk/core_utils/engines/instancing/instancing_strategy.py#L48)

### `KeyStash` — blendertk, mayatk, pythontk

- `blendertk` — [`KeyStash`](blendertk/anim_utils/key_stash/_key_stash.py#L214)
- `mayatk` — [`KeyStash`](mayatk/anim_utils/key_stash/_key_stash.py#L237)
- `pythontk` — [`KeyStash`](pythontk/core_utils/engines/key_stash/key_stash_model.py#L194)

### `MainThreadMarshaller` — blendertk, mayatk, pythontk

- `blendertk` — [`MainThreadMarshaller`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L200)
- `blendertk` — [`MainThreadMarshaller`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L200)
- `mayatk` — [`MainThreadMarshaller`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L200)
- `mayatk` — [`MainThreadMarshaller`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L200)
- `pythontk` — [`MainThreadMarshaller`](pythontk/net_utils/rpc/plugin_core.py#L200)

### `MarmosetEngine` — blendertk, extapps, mayatk

- `blendertk` — [`MarmosetEngine`](blendertk/mat_utils/marmoset_bridge/_marmoset_engine.py#L76)
- `extapps` — [`MarmosetEngine`](extapps/marmoset_workflow/_marmoset_engine.py#L76)
- `mayatk` — [`MarmosetEngine`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L76)

### `MaterialRecord` — mayatk, pythontk

- `mayatk` — [`MaterialRecord`](mayatk/core_utils/diagnostics/audit_records.py#L85)
- `pythontk` — [`MaterialRecord`](pythontk/core_utils/engines/scene_export/material_record.py#L120)

### `OpRegistry` — blendertk, mayatk, pythontk

- `blendertk` — [`OpRegistry`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L84)
- `blendertk` — [`OpRegistry`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L84)
- `mayatk` — [`OpRegistry`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L84)
- `mayatk` — [`OpRegistry`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L84)
- `pythontk` — [`OpRegistry`](pythontk/net_utils/rpc/plugin_core.py#L84)

### `Parameters` — blendertk, extapps, mayatk, uitk

- `blendertk` — [`Parameters`](blendertk/env_utils/maya_bridge/parameters.py#L149)
- `blendertk` — [`Parameters`](blendertk/env_utils/unity_bridge/parameters.py#L163)
- `blendertk` — [`Parameters`](blendertk/mat_utils/marmoset_bridge/parameters.py#L418)
- `blendertk` — [`Parameters`](blendertk/mat_utils/substance_bridge/parameters.py#L266)
- `blendertk` — [`Parameters`](blendertk/uv_utils/rizom_bridge/parameters.py#L526)
- `extapps` — [`Parameters`](extapps/marmoset_workflow/parameters.py#L52)
- `extapps` — [`Parameters`](extapps/photogrammetry/gaussian_splat_workflow/parameters.py#L117)
- `extapps` — [`Parameters`](extapps/photogrammetry/metashape_workflow/parameters.py#L372)
- `extapps` — [`Parameters`](extapps/photogrammetry/realityscan_workflow/parameters.py#L163)
- `extapps` — [`Parameters`](extapps/unity_workflow/parameters.py#L125)
- `extapps` — [`Parameters`](extapps/webxr_preview/parameters.py#L360)
- `mayatk` — [`Parameters`](mayatk/env_utils/blender_bridge/parameters.py#L508)
- `mayatk` — [`Parameters`](mayatk/env_utils/unity_bridge/parameters.py#L165)
- `mayatk` — [`Parameters`](mayatk/mat_utils/marmoset_bridge/parameters.py#L418)
- `mayatk` — [`Parameters`](mayatk/mat_utils/substance_bridge/parameters.py#L266)
- `mayatk` — [`Parameters`](mayatk/uv_utils/rizom_bridge/parameters.py#L520)
- `uitk` — [`Parameters`](uitk/bridge/parameters.py#L39)

### `ProbePlacement` — blendertk, mayatk, pythontk

- `blendertk` — [`ProbePlacement`](blendertk/light_utils/lightmap_baker/_probe_placement.py#L68)
- `mayatk` — [`ProbePlacement`](mayatk/light_utils/lightmap_baker/_probe_placement.py#L95)
- `pythontk` — [`ProbePlacement`](pythontk/geo_utils/probe_placement.py#L208)

### `RangeResolver` — blendertk, mayatk, pythontk

- `blendertk` — [`RangeResolver`](blendertk/anim_utils/shots/shot_manifest/range_resolver.py#L29)
- `mayatk` — [`RangeResolver`](mayatk/anim_utils/shots/shot_manifest/range_resolver.py#L28)
- `pythontk` — [`RangeResolver`](pythontk/core_utils/engines/shots/manifest/range_resolver.py#L19)

### `RpcPlugin` — blendertk, mayatk, pythontk

- `blendertk` — [`RpcPlugin`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L451)
- `blendertk` — [`RpcPlugin`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L451)
- `mayatk` — [`RpcPlugin`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L451)
- `mayatk` — [`RpcPlugin`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L451)
- `pythontk` — [`RpcPlugin`](pythontk/net_utils/rpc/plugin_core.py#L451)

### `ShotApply` — mayatk, pythontk

- `mayatk` — [`ShotApply`](mayatk/anim_utils/shots/_shot_apply.py#L329)
- `pythontk` — [`ShotApply`](pythontk/core_utils/engines/shots/shot_apply.py#L55)

### `ShotManifest` — mayatk, pythontk

- `mayatk` — [`ShotManifest`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L118)
- `pythontk` — [`ShotManifest`](pythontk/core_utils/engines/shots/manifest/manifest_engine.py#L103)

### `ShotSequencer` — blendertk, mayatk, pythontk

- `blendertk` — [`ShotSequencer`](blendertk/anim_utils/shots/shot_sequencer/_shot_sequencer.py#L249)
- `mayatk` — [`ShotSequencer`](mayatk/anim_utils/shots/shot_sequencer/_shot_sequencer.py#L62)
- `pythontk` — [`ShotSequencer`](pythontk/core_utils/engines/shots/shot_sequencer.py#L375)

### `ShotStore` — mayatk, pythontk

- `mayatk` — [`ShotStore`](mayatk/anim_utils/shots/_shots.py#L382)
- `pythontk` — [`ShotStore`](pythontk/core_utils/engines/shots/shot_model.py#L428)

### `TemplateParams` — blendertk, extapps, mayatk

- `blendertk` — [`TemplateParams`](blendertk/mat_utils/marmoset_bridge/template_params.py#L101)
- `extapps` — [`TemplateParams`](extapps/marmoset_workflow/template_params.py#L101)
- `mayatk` — [`TemplateParams`](mayatk/mat_utils/marmoset_bridge/template_params.py#L101)

### `TestSandbox` — pythontk, uitk

- `pythontk` — [`TestSandbox`](pythontk/core_utils/test_sandbox.py#L228)
- `uitk` — [`TestSandbox`](uitk/testing.py#L101)

### `ToolbagHelpers` — blendertk, extapps, mayatk

- `blendertk` — [`ToolbagHelpers`](blendertk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L200)
- `extapps` — [`ToolbagHelpers`](extapps/marmoset_workflow/_toolbag_helpers.py#L200)
- `mayatk` — [`ToolbagHelpers`](mayatk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L200)

### `ToolbagLog` — blendertk, extapps, mayatk

- `blendertk` — [`ToolbagLog`](blendertk/mat_utils/marmoset_bridge/toolbag_log.py#L30)
- `extapps` — [`ToolbagLog`](extapps/marmoset_workflow/toolbag_log.py#L30)
- `mayatk` — [`ToolbagLog`](mayatk/mat_utils/marmoset_bridge/toolbag_log.py#L30)

### `UnityPanelMixin` — blendertk, extapps, mayatk

- `blendertk` — [`UnityPanelMixin`](blendertk/env_utils/unity_bridge/_unity_panel.py#L34)
- `extapps` — [`UnityPanelMixin`](extapps/unity_workflow/_unity_panel.py#L34)
- `mayatk` — [`UnityPanelMixin`](mayatk/env_utils/unity_bridge/_unity_panel.py#L34)

### `close_plugin` — blendertk, extapps, mayatk

- `blendertk` — [`close_plugin`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L81)
- `extapps` — [`close_plugin`](extapps/substance_workflow/plugins/startup/substance_workflow_bridge/__init__.py#L126)
- `mayatk` — [`close_plugin`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L81)

### `main` — blendertk, extapps, mayatk, pythontk

- `blendertk` — [`main`](blendertk/env_utils/hierarchy_sync/_fbx_stage_worker.py#L42)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/_bake_scene.py#L64)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/_import_scene.py#L1259)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/_import_scene_usd.py#L1123)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/_save_scene.py#L289)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/import.py#L314)
- `blendertk` — [`main`](blendertk/env_utils/pm_doctor.py#L56)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/bake.py#L662)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/import.py#L35)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/lookdev.py#L38)
- `extapps` — [`main`](extapps/marmoset_workflow/templates/import.py#L35)
- `extapps` — [`main`](extapps/marmoset_workflow/templates/lookdev.py#L38)
- `extapps` — [`main`](extapps/photogrammetry/gaussian_splat_workflow/_install_brush.py#L19)
- `extapps` — [`main`](extapps/photogrammetry/gaussian_splat_workflow/run_combined.py#L46)
- `extapps` — [`main`](extapps/photogrammetry/metashape_workflow/run_combined.py#L271)
- `extapps` — [`main`](extapps/photogrammetry/realityscan_workflow/run_combined.py#L116)
- `extapps` — [`main`](extapps/photogrammetry/sugar_mesh_workflow/run_combined.py#L37)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/_bake_scene.py#L222)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/_import_scene.py#L1251)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/_import_scene_usd.py#L1598)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/_save_scene.py#L138)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/bake_lightmaps.py#L770)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/import.py#L120)
- `mayatk` — [`main`](mayatk/env_utils/pm_doctor.py#L56)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/bake.py#L662)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/import.py#L35)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/lookdev.py#L38)
- `pythontk` — [`main`](pythontk/core_utils/execution_monitor/_sidecar.py#L456)

### `set_resolution` — blendertk, extapps, mayatk

- `blendertk` — [`set_resolution`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/ops/setup_ops.py#L169)
- `extapps` — [`set_resolution`](extapps/substance_workflow/bake_utils.py#L444)
- `extapps` — [`set_resolution`](extapps/substance_workflow/texture_set_utils.py#L21)
- `mayatk` — [`set_resolution`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/ops/setup_ops.py#L169)

### `start_plugin` — blendertk, extapps, mayatk

- `blendertk` — [`start_plugin`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L74)
- `extapps` — [`start_plugin`](extapps/substance_workflow/plugins/startup/substance_workflow_bridge/__init__.py#L114)
- `mayatk` — [`start_plugin`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L74)

---

## Intentional mayatk↔blendertk port parity (237)

_blendertk deliberately mirrors mayatk's public names (branch-free tentacle slots). Expected — not DRY violations. Names only:_

- `AnchorStrategy`
- `AnimUtils`
- `AnimationMacros`
- `Applicator`
- `ApplyStatus`
- `ArnoldBridge`
- `ArnoldBridgeSlots`
- `ArticulatedRig`
- `ArticulatedRigGrab`
- `ArticulatedRigSlots`
- `AssemblyReconstructor`
- `AudioClipsSlots`
- `AudioSegment`
- `AutoInstancer`
- `AutoUnwrapResult`
- `BakeAnalysis`
- `BakeResult`
- `BakeSessionStore`
- `BakeSet`
- `BakeSourceSet`
- `BatchJob`
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
- `ClipMenuMixin`
- `ClipMotionMixin`
- `ColorId`
- `ColorIdSlots`
- `CombineInputs`
- `ControlNodes`
- `Controls`
- `Creator`
- `CurtainDrape`
- `CurtainMesh`
- `CurtainRig`
- `CurtainSlots`
- `CurveToTube`
- `CurveToTubeSlots`
- `CutOnAxisSlots`
- `DataNodes`
- `Detection`
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
- `EmissiveGroups`
- `EmissiveGroupsSlots`
- `EnvUtils`
- `ExplodedViewSlots`
- `ExportPreviewMixin`
- `FKChainStrategy`
- `FbxUtils`
- `GameShader`
- `GameShaderSlots`
- `GapManagerMixin`
- `GeometryMatcher`
- `GraphSync`
- `HdrManagerSlots`
- `HeaderMenuMixin`
- `HierarchyMapBuilder`
- `HierarchySync`
- `HierarchySyncController`
- `HierarchySyncSlots`
- `HierarchyTreeRenderer`
- `ImageToPlane`
- `ImageToPlaneSlots`
- `ImageTracer`
- `ImageTracerSlots`
- `Installer`
- `InstanceCandidate`
- `InstanceGroup`
- `KeyMenuMixin`
- `KeyStashSlots`
- `Keyframes`
- `LightUtils`
- `LightmapBakeResult`
- `LightmapBaker`
- `LightmapBakerSlots`
- `LightmapExcludeSet`
- `LightmapIsolateSet`
- `LightmapRecords`
- `MacroManager`
- `Macros`
- `ManifestData`
- `ManifestEditor`
- `ManifestHost`
- `ManifestSourceMixin`
- `ManifestTableMixin`
- `MappingPickerMixin`
- `MarkerManagerMixin`
- `MarmosetBridge`
- `MarmosetBridgeSlots`
- `MarmosetConnection`
- `MatManifest`
- `MatUpdater`
- `MatUpdaterSlots`
- `MatUtils`
- `MaterialRecords`
- `Matrices`
- `MeshDiagnostics`
- `MirrorSlots`
- `Naming`
- `NamingSlots`
- `NodeIcons`
- `NodeUtils`
- `NurbsUtils`
- `ObjectSwapper`
- `PainterRpcClient`
- `Preview`
- `Rail`
- `RangeColumnMixin`
- `ReferenceManagerSlots`
- `RenderEffects`
- `RenderEffectsSlots`
- `RestoreResult`
- `RigGraphBuilder`
- `RigGraphExtractor`
- `RigUtils`
- `RizomBridgeSlots`
- `RizomUVBridge`
- `RowMenusMixin`
- `ScaleKeys`
- `SceneAnalyzer`
- `SceneCallbacksMixin`
- `SceneDataSidecar`
- `SceneExporter`
- `SceneExporterSlots`
- `SceneInfoSection`
- `SceneSelectionMixin`
- `SceneState`
- `ScriptConsole`
- `ScriptJobManager`
- `SegmentCollector`
- `SegmentKeys`
- `Selection`
- `SelectionMacros`
- `ShaderTemplatesSlots`
- `ShadowPreview`
- `ShadowRig`
- `ShadowRigSlots`
- `ShellXformSlots`
- `ShotEditDialog`
- `ShotLaneMixin`
- `ShotManifestController`
- `ShotManifestSlots`
- `ShotNavMixin`
- `ShotSequencerController`
- `ShotSequencerSlots`
- `ShotsController`
- `ShotsSlots`
- `SmartBake`
- `SmartBakeSlots`
- `SnapSlots`
- `SplineIKStrategy`
- `StaggerKeys`
- `StoreFollowMixin`
- `StyleSetter`
- `SubstanceBridge`
- `SubstanceBridgeSlots`
- `SubstanceConnection`
- `SubstanceEngine`
- `Target`
- `Targets`
- `TaskManager`
- `TelescopeRig`
- `TelescopeRigBundle`
- `TelescopeRigSlots`
- `TextureBaker`
- `TextureCombine`
- `TextureCombineSlots`
- `TexturePathEditorSlots`
- `TextureTransfer`
- `TransformDiagnostics`
- `TransportMixin`
- `TreePathMatcher`
- `TubePath`
- `TubeRig`
- `TubeRigBundle`
- `TubeRigSlots`
- `TubeStrategy`
- `UiMacros`
- `UiUtils`
- `UndoLedgerMixin`
- `Units`
- `UnityBridge`
- `UnityBridgeSlots`
- `UsdUtils`
- `UvDiagnostics`
- `UvUtils`
- `Validator`
- `ViewCombosMixin`
- `WebXrPreview`
- `WheelRig`
- `WheelRigSlots`
- `WidgetSyncMixin`
- `XformUtils`
- `apply_mesh_maps`
- `autostart`
- `collect_instance_groups`
- `covering_take`
- `eval_python`
- `export_usd`
- `find_shadows`
- `import_payload`
- `is_running`
- `js_evaluate`
- `list_materials`
- `mesh_reload`
- `mesh_reload_status`
- `pending_setup`
- `project_info`
- `restore_usd_locators`
- `scene_data_sections`
- `scene_settings`
- `set_high_poly`
- `start_server`
- `stop_server`
- `summary`
- `teardown`
- `version`
- `write_manifest`
