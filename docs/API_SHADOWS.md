# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

_Generated: 2026-07-29_

## Genuine cross-layer collisions (23)

_Touch `pythontk` or span 3+ packages — the real DRY review surface._

### `AudioUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`AudioUtils`](blendertk/audio_utils/_audio_utils.py#L66)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L85)
- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L15)

### `Behaviors` — mayatk, pythontk

- `mayatk` — [`Behaviors`](mayatk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L144)
- `pythontk` — [`Behaviors`](pythontk/core_utils/engines/shots/manifest/behaviors/_behaviors.py#L83)

### `Call` — extapps, pythontk

- `extapps` — [`Call`](extapps/substance_workflow/job.py#L18)
- `pythontk` — [`Call`](pythontk/net_utils/rpc/job.py#L73)

### `CoreUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`CoreUtils`](blendertk/core_utils/_core_utils.py#L166)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L171)
- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L14)

### `MarmosetEngine` — blendertk, extapps, mayatk

- `blendertk` — [`MarmosetEngine`](blendertk/mat_utils/marmoset_bridge/_marmoset_engine.py#L58)
- `extapps` — [`MarmosetEngine`](extapps/marmoset_workflow/_marmoset_engine.py#L58)
- `mayatk` — [`MarmosetEngine`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L58)

### `Parameters` — blendertk, mayatk, uitk

- `blendertk` — [`Parameters`](blendertk/env_utils/maya_bridge/parameters.py#L101)
- `blendertk` — [`Parameters`](blendertk/env_utils/unity_bridge/parameters.py#L135)
- `blendertk` — [`Parameters`](blendertk/mat_utils/marmoset_bridge/parameters.py#L230)
- `blendertk` — [`Parameters`](blendertk/mat_utils/substance_bridge/parameters.py#L168)
- `blendertk` — [`Parameters`](blendertk/uv_utils/rizom_bridge/parameters.py#L437)
- `mayatk` — [`Parameters`](mayatk/env_utils/blender_bridge/parameters.py#L100)
- `mayatk` — [`Parameters`](mayatk/env_utils/unity_bridge/parameters.py#L137)
- `mayatk` — [`Parameters`](mayatk/mat_utils/marmoset_bridge/parameters.py#L230)
- `mayatk` — [`Parameters`](mayatk/mat_utils/substance_bridge/parameters.py#L168)
- `mayatk` — [`Parameters`](mayatk/uv_utils/rizom_bridge/parameters.py#L432)
- `uitk` — [`Parameters`](uitk/bridge/parameters.py#L38)

### `RangeResolver` — mayatk, pythontk

- `mayatk` — [`RangeResolver`](mayatk/anim_utils/shots/shot_manifest/range_resolver.py#L28)
- `pythontk` — [`RangeResolver`](pythontk/core_utils/engines/shots/manifest/range_resolver.py#L19)

### `Result` — extapps, pythontk

- `extapps` — [`Result`](extapps/substance_workflow/job.py#L27)
- `pythontk` — [`Result`](pythontk/net_utils/rpc/job.py#L86)

### `Selection` — blendertk, mayatk, tentacle

- `blendertk` — [`Selection`](blendertk/edit_utils/selection.py#L35)
- `mayatk` — [`Selection`](mayatk/edit_utils/selection.py#L19)
- `tentacle` — [`Selection`](tentacle/slots/blender/selection.py#L9)
- `tentacle` — [`Selection`](tentacle/slots/maya/selection.py#L10)

### `ShotApply` — mayatk, pythontk

- `mayatk` — [`ShotApply`](mayatk/anim_utils/shots/_shot_apply.py#L148)
- `pythontk` — [`ShotApply`](pythontk/core_utils/engines/shots/shot_apply.py#L46)

### `ShotManifest` — mayatk, pythontk

- `mayatk` — [`ShotManifest`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L111)
- `pythontk` — [`ShotManifest`](pythontk/core_utils/engines/shots/manifest/manifest_engine.py#L91)

### `ShotStore` — mayatk, pythontk

- `mayatk` — [`ShotStore`](mayatk/anim_utils/shots/_shots.py#L310)
- `pythontk` — [`ShotStore`](pythontk/core_utils/engines/shots/shot_model.py#L269)

### `TemplateParams` — blendertk, extapps, mayatk

- `blendertk` — [`TemplateParams`](blendertk/mat_utils/marmoset_bridge/template_params.py#L50)
- `extapps` — [`TemplateParams`](extapps/marmoset_workflow/template_params.py#L50)
- `mayatk` — [`TemplateParams`](mayatk/mat_utils/marmoset_bridge/template_params.py#L50)

### `ToolbagHelpers` — blendertk, extapps, mayatk

- `blendertk` — [`ToolbagHelpers`](blendertk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L120)
- `extapps` — [`ToolbagHelpers`](extapps/marmoset_workflow/_toolbag_helpers.py#L120)
- `mayatk` — [`ToolbagHelpers`](mayatk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L120)

### `ToolbagLog` — blendertk, extapps, mayatk

- `blendertk` — [`ToolbagLog`](blendertk/mat_utils/marmoset_bridge/toolbag_log.py#L30)
- `extapps` — [`ToolbagLog`](extapps/marmoset_workflow/toolbag_log.py#L30)
- `mayatk` — [`ToolbagLog`](mayatk/mat_utils/marmoset_bridge/toolbag_log.py#L30)

### `all_ops` — blendertk, extapps, mayatk

- `blendertk` — [`all_ops`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L41)
- `blendertk` — [`all_ops`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/registry.py#L46)
- `extapps` — [`all_ops`](extapps/substance_workflow/registry.py#L43)
- `mayatk` — [`all_ops`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L41)
- `mayatk` — [`all_ops`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/registry.py#L46)

### `close_plugin` — blendertk, extapps, mayatk

- `blendertk` — [`close_plugin`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L45)
- `extapps` — [`close_plugin`](extapps/substance_workflow/plugins/substance_workflow_bridge/__init__.py#L75)
- `mayatk` — [`close_plugin`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L45)

### `describe` — blendertk, extapps, mayatk

- `blendertk` — [`describe`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L46)
- `blendertk` — [`describe`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/registry.py#L51)
- `extapps` — [`describe`](extapps/substance_workflow/registry.py#L47)
- `mayatk` — [`describe`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L46)
- `mayatk` — [`describe`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/registry.py#L51)

### `get` — blendertk, extapps, mayatk

- `blendertk` — [`get`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L36)
- `blendertk` — [`get`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/registry.py#L41)
- `extapps` — [`get`](extapps/substance_workflow/registry.py#L39)
- `mayatk` — [`get`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L36)
- `mayatk` — [`get`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/registry.py#L41)

### `launch` — mayatk, tentacle

- `mayatk` — [`launch`](mayatk/node_utils/attributes/channels/__init__.py#L14)
- `tentacle` — [`launch`](tentacle/tcl_blender.py#L1773)

### `main` — blendertk, extapps, mayatk

- `blendertk` — [`main`](blendertk/env_utils/hierarchy_sync/_fbx_stage_worker.py#L30)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/_bake_scene.py#L126)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/_import_scene.py#L443)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/_import_scene_usd.py#L220)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/import.py#L26)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/bake.py#L123)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/import.py#L32)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/lookdev.py#L35)
- `extapps` — [`main`](extapps/marmoset_workflow/templates/import.py#L32)
- `extapps` — [`main`](extapps/marmoset_workflow/templates/lookdev.py#L35)
- `extapps` — [`main`](extapps/photogrammetry/gaussian_splat_workflow/_install_brush.py#L19)
- `extapps` — [`main`](extapps/photogrammetry/gaussian_splat_workflow/run_combined.py#L46)
- `extapps` — [`main`](extapps/photogrammetry/metashape_workflow/run_combined.py#L224)
- `extapps` — [`main`](extapps/photogrammetry/realityscan_workflow/run_combined.py#L133)
- `extapps` — [`main`](extapps/photogrammetry/sugar_mesh_workflow/run_combined.py#L37)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/_bake_scene.py#L94)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/_import_scene.py#L191)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/_import_scene_usd.py#L85)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/import.py#L28)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/bake.py#L123)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/import.py#L32)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/lookdev.py#L35)

### `register` — blendertk, extapps, mayatk, tentacle

- `blendertk` — [`register`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L21)
- `blendertk` — [`register`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/registry.py#L26)
- `extapps` — [`register`](extapps/substance_workflow/registry.py#L19)
- `mayatk` — [`register`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L21)
- `mayatk` — [`register`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/registry.py#L26)
- `tentacle` — [`register`](tentacle/tcl_blender.py#L1778)

### `start_plugin` — blendertk, extapps, mayatk

- `blendertk` — [`start_plugin`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L33)
- `extapps` — [`start_plugin`](extapps/substance_workflow/plugins/substance_workflow_bridge/__init__.py#L61)
- `mayatk` — [`start_plugin`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L33)

---

## Intentional mayatk↔blendertk port parity (183)

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
- `SegmentCollector`
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
- `apply_manifest`
- `autostart`
- `clear`
- `describe_op`
- `eval_python`
- `export_usd`
- `import_fbx`
- `is_main_thread_marshalling_active`
- `is_running`
- `js_evaluate`
- `list_materials`
- `list_ops`
- `mesh_reload`
- `mesh_reload_status`
- `ping`
- `project_info`
- `run_on_main_thread`
- `start_server`
- `stop_server`
- `summary`
- `version`
