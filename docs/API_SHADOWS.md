# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

## Genuine cross-layer collisions (24)

_Touch `pythontk` or span 3+ packages — the real DRY review surface._

### `AudioUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`AudioUtils`](blendertk/audio_utils/_audio_utils.py#L73)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L85)
- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L15)

### `Behaviors` — blendertk, mayatk, pythontk

- `blendertk` — [`Behaviors`](blendertk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L231)
- `mayatk` — [`Behaviors`](mayatk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L144)
- `pythontk` — [`Behaviors`](pythontk/core_utils/engines/shots/manifest/behaviors/_behaviors.py#L83)

### `Call` — extapps, pythontk

- `extapps` — [`Call`](extapps/substance_workflow/job.py#L18)
- `pythontk` — [`Call`](pythontk/net_utils/rpc/job.py#L73)

### `CoreUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`CoreUtils`](blendertk/core_utils/_core_utils.py#L336)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L187)
- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L16)

### `MainThreadMarshaller` — blendertk, mayatk, pythontk

- `blendertk` — [`MainThreadMarshaller`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L200)
- `blendertk` — [`MainThreadMarshaller`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L200)
- `mayatk` — [`MainThreadMarshaller`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L200)
- `mayatk` — [`MainThreadMarshaller`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L200)
- `pythontk` — [`MainThreadMarshaller`](pythontk/net_utils/rpc/plugin_core.py#L200)

### `MarmosetEngine` — blendertk, extapps, mayatk

- `blendertk` — [`MarmosetEngine`](blendertk/mat_utils/marmoset_bridge/_marmoset_engine.py#L79)
- `extapps` — [`MarmosetEngine`](extapps/marmoset_workflow/_marmoset_engine.py#L79)
- `mayatk` — [`MarmosetEngine`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L79)

### `OpRegistry` — blendertk, mayatk, pythontk

- `blendertk` — [`OpRegistry`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L84)
- `blendertk` — [`OpRegistry`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L84)
- `mayatk` — [`OpRegistry`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L84)
- `mayatk` — [`OpRegistry`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L84)
- `pythontk` — [`OpRegistry`](pythontk/net_utils/rpc/plugin_core.py#L84)

### `Parameters` — blendertk, mayatk, uitk

- `blendertk` — [`Parameters`](blendertk/env_utils/maya_bridge/parameters.py#L114)
- `blendertk` — [`Parameters`](blendertk/env_utils/unity_bridge/parameters.py#L165)
- `blendertk` — [`Parameters`](blendertk/mat_utils/marmoset_bridge/parameters.py#L409)
- `blendertk` — [`Parameters`](blendertk/mat_utils/substance_bridge/parameters.py#L255)
- `blendertk` — [`Parameters`](blendertk/uv_utils/rizom_bridge/parameters.py#L479)
- `mayatk` — [`Parameters`](mayatk/env_utils/blender_bridge/parameters.py#L230)
- `mayatk` — [`Parameters`](mayatk/env_utils/unity_bridge/parameters.py#L167)
- `mayatk` — [`Parameters`](mayatk/mat_utils/marmoset_bridge/parameters.py#L409)
- `mayatk` — [`Parameters`](mayatk/mat_utils/substance_bridge/parameters.py#L255)
- `mayatk` — [`Parameters`](mayatk/uv_utils/rizom_bridge/parameters.py#L474)
- `uitk` — [`Parameters`](uitk/bridge/parameters.py#L38)

### `RangeResolver` — blendertk, mayatk, pythontk

- `blendertk` — [`RangeResolver`](blendertk/anim_utils/shots/shot_manifest/range_resolver.py#L29)
- `mayatk` — [`RangeResolver`](mayatk/anim_utils/shots/shot_manifest/range_resolver.py#L28)
- `pythontk` — [`RangeResolver`](pythontk/core_utils/engines/shots/manifest/range_resolver.py#L19)

### `Result` — extapps, pythontk

- `extapps` — [`Result`](extapps/substance_workflow/job.py#L27)
- `pythontk` — [`Result`](pythontk/net_utils/rpc/job.py#L86)

### `RpcPlugin` — blendertk, mayatk, pythontk

- `blendertk` — [`RpcPlugin`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L394)
- `blendertk` — [`RpcPlugin`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L394)
- `mayatk` — [`RpcPlugin`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L394)
- `mayatk` — [`RpcPlugin`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L394)
- `pythontk` — [`RpcPlugin`](pythontk/net_utils/rpc/plugin_core.py#L394)

### `Selection` — blendertk, mayatk, tentacle

- `blendertk` — [`Selection`](blendertk/edit_utils/selection.py#L35)
- `mayatk` — [`Selection`](mayatk/edit_utils/selection.py#L19)
- `tentacle` — [`Selection`](tentacle/slots/blender/selection.py#L8)
- `tentacle` — [`Selection`](tentacle/slots/maya/selection.py#L9)

### `ShotApply` — mayatk, pythontk

- `mayatk` — [`ShotApply`](mayatk/anim_utils/shots/_shot_apply.py#L148)
- `pythontk` — [`ShotApply`](pythontk/core_utils/engines/shots/shot_apply.py#L46)

### `ShotManifest` — mayatk, pythontk

- `mayatk` — [`ShotManifest`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L111)
- `pythontk` — [`ShotManifest`](pythontk/core_utils/engines/shots/manifest/manifest_engine.py#L91)

### `ShotStore` — mayatk, pythontk

- `mayatk` — [`ShotStore`](mayatk/anim_utils/shots/_shots.py#L306)
- `pythontk` — [`ShotStore`](pythontk/core_utils/engines/shots/shot_model.py#L269)

### `TemplateParams` — blendertk, extapps, mayatk

- `blendertk` — [`TemplateParams`](blendertk/mat_utils/marmoset_bridge/template_params.py#L97)
- `extapps` — [`TemplateParams`](extapps/marmoset_workflow/template_params.py#L97)
- `mayatk` — [`TemplateParams`](mayatk/mat_utils/marmoset_bridge/template_params.py#L97)

### `ToolbagHelpers` — blendertk, extapps, mayatk

- `blendertk` — [`ToolbagHelpers`](blendertk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L200)
- `extapps` — [`ToolbagHelpers`](extapps/marmoset_workflow/_toolbag_helpers.py#L200)
- `mayatk` — [`ToolbagHelpers`](mayatk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L200)

### `ToolbagLog` — blendertk, extapps, mayatk

- `blendertk` — [`ToolbagLog`](blendertk/mat_utils/marmoset_bridge/toolbag_log.py#L30)
- `extapps` — [`ToolbagLog`](extapps/marmoset_workflow/toolbag_log.py#L30)
- `mayatk` — [`ToolbagLog`](mayatk/mat_utils/marmoset_bridge/toolbag_log.py#L30)

### `close_plugin` — blendertk, extapps, mayatk

- `blendertk` — [`close_plugin`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L80)
- `extapps` — [`close_plugin`](extapps/substance_workflow/plugins/substance_workflow_bridge/__init__.py#L121)
- `mayatk` — [`close_plugin`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L80)

### `launch` — mayatk, tentacle

- `mayatk` — [`launch`](mayatk/node_utils/attributes/channels/__init__.py#L14)
- `tentacle` — [`launch`](tentacle/tcl_blender.py#L2191)

### `main` — blendertk, extapps, mayatk

- `blendertk` — [`main`](blendertk/env_utils/hierarchy_sync/_fbx_stage_worker.py#L30)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/_bake_scene.py#L235)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/_import_scene.py#L775)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/_import_scene_usd.py#L672)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/_save_scene.py#L217)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/import.py#L274)
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
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/_bake_scene.py#L220)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/_import_scene.py#L275)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/_import_scene_usd.py#L564)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/_save_scene.py#L154)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/bake_lightmaps.py#L423)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/import.py#L223)
- `mayatk` — [`main`](mayatk/env_utils/pm_doctor.py#L56)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/bake.py#L662)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/import.py#L35)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/lookdev.py#L38)

### `register` — extapps, tentacle

- `extapps` — [`register`](extapps/substance_workflow/registry.py#L19)
- `tentacle` — [`register`](tentacle/tcl_blender.py#L2196)
- `tentacle` — [`register`](tentacle/tentacle_installer.py#L1254)

### `set_resolution` — blendertk, extapps, mayatk

- `blendertk` — [`set_resolution`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/ops/setup_ops.py#L157)
- `extapps` — [`set_resolution`](extapps/substance_workflow/bake_utils.py#L350)
- `extapps` — [`set_resolution`](extapps/substance_workflow/texture_set_utils.py#L21)
- `mayatk` — [`set_resolution`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/ops/setup_ops.py#L157)

### `start_plugin` — blendertk, extapps, mayatk

- `blendertk` — [`start_plugin`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L73)
- `extapps` — [`start_plugin`](extapps/substance_workflow/plugins/substance_workflow_bridge/__init__.py#L107)
- `mayatk` — [`start_plugin`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L73)

---

## Intentional mayatk↔blendertk port parity (202)

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
- `AudioSegment`
- `AutoInstancer`
- `AutoUnwrapResult`
- `BakeAnalysis`
- `BakeResult`
- `BakeSessionStore`
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
- `FKChainStrategy`
- `FbxUtils`
- `GameShader`
- `GameShaderSlots`
- `GapManagerMixin`
- `GeometryMatcher`
- `HdrManagerSlots`
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
- `InstancingStrategy`
- `Keyframes`
- `LightUtils`
- `LightmapBaker`
- `LightmapBakerSlots`
- `MacroManager`
- `Macros`
- `ManifestData`
- `ManifestTableMixin`
- `MarkerManagerMixin`
- `MarmosetBridge`
- `MarmosetBridgeSlots`
- `MarmosetConnection`
- `MatManifest`
- `MatUpdater`
- `MatUpdaterSlots`
- `MatUtils`
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
- `ReferenceManagerSlots`
- `RenderOpacity`
- `RenderOpacitySlots`
- `RestoreResult`
- `RigUtils`
- `RizomBridgeSlots`
- `RizomUVBridge`
- `ScaleKeys`
- `SceneDataSidecar`
- `SceneExporter`
- `SceneExporterSlots`
- `SceneState`
- `ScriptConsole`
- `ScriptJobManager`
- `SegmentCollector`
- `SegmentKeys`
- `SelectionMacros`
- `ShaderTemplatesSlots`
- `ShadowRig`
- `ShadowRigSlots`
- `ShellXformSlots`
- `ShotEditDialog`
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
- `TelescopeRigBundle`
- `TelescopeRigSlots`
- `TextureBaker`
- `TexturePathEditorSlots`
- `TextureTransfer`
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
- `WebXrPreview`
- `WheelRig`
- `WheelRigSlots`
- `XformUtils`
- `apply_instances`
- `apply_manifest`
- `apply_mesh_maps`
- `apply_scene`
- `autostart`
- `collect_instance_groups`
- `eval_python`
- `export_usd`
- `find_shadows`
- `import_payload`
- `import_source`
- `import_usd`
- `is_running`
- `js_evaluate`
- `list_materials`
- `mesh_reload`
- `mesh_reload_status`
- `pending_setup`
- `project_info`
- `restore_empty_groups`
- `restore_usd_locators`
- `scene_settings`
- `set_high_poly`
- `start_server`
- `stop_server`
- `summary`
- `tag_node_types`
- `teardown`
- `version`
- `write_manifest`
