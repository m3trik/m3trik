# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

_Generated: 2026-07-29_

## Genuine cross-layer collisions (11)

_Touch `pythontk` or span 3+ packages — the real DRY review surface._

### `AudioUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`AudioUtils`](blendertk/audio_utils/_audio_utils.py#L66)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L85)
- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L15)

### `Behaviors` — mayatk, pythontk

- `mayatk` — [`Behaviors`](mayatk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L144)
- `pythontk` — [`Behaviors`](pythontk/core_utils/engines/shots/manifest/behaviors/_behaviors.py#L83)

### `CoreUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`CoreUtils`](blendertk/core_utils/_core_utils.py#L231)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L171)
- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L14)

### `Parameters` — blendertk, mayatk, uitk

- `blendertk` — [`Parameters`](blendertk/env_utils/maya_bridge/parameters.py#L101)
- `blendertk` — [`Parameters`](blendertk/env_utils/unity_bridge/parameters.py#L160)
- `blendertk` — [`Parameters`](blendertk/mat_utils/marmoset_bridge/parameters.py#L230)
- `blendertk` — [`Parameters`](blendertk/mat_utils/substance_bridge/parameters.py#L168)
- `blendertk` — [`Parameters`](blendertk/uv_utils/rizom_bridge/parameters.py#L437)
- `mayatk` — [`Parameters`](mayatk/env_utils/blender_bridge/parameters.py#L100)
- `mayatk` — [`Parameters`](mayatk/env_utils/unity_bridge/parameters.py#L162)
- `mayatk` — [`Parameters`](mayatk/mat_utils/marmoset_bridge/parameters.py#L230)
- `mayatk` — [`Parameters`](mayatk/mat_utils/substance_bridge/parameters.py#L168)
- `mayatk` — [`Parameters`](mayatk/uv_utils/rizom_bridge/parameters.py#L432)
- `uitk` — [`Parameters`](uitk/bridge/parameters.py#L38)

### `RangeResolver` — mayatk, pythontk

- `mayatk` — [`RangeResolver`](mayatk/anim_utils/shots/shot_manifest/range_resolver.py#L28)
- `pythontk` — [`RangeResolver`](pythontk/core_utils/engines/shots/manifest/range_resolver.py#L19)

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

### `launch` — mayatk, tentacle

- `mayatk` — [`launch`](mayatk/node_utils/attributes/channels/__init__.py#L14)
- `tentacle` — [`launch`](tentacle/tcl_blender.py#L1780)

### `register` — blendertk, mayatk, tentacle

- `blendertk` — [`register`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L21)
- `blendertk` — [`register`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/registry.py#L26)
- `mayatk` — [`register`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L21)
- `mayatk` — [`register`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/registry.py#L26)
- `tentacle` — [`register`](tentacle/tcl_blender.py#L1785)

---

## Intentional mayatk↔blendertk port parity (193)

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
- `SceneDataSidecar`
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
- `TemplateParams`
- `TextureBaker`
- `TexturePathEditorSlots`
- `ToolbagHelpers`
- `ToolbagLog`
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
- `all_ops`
- `apply_manifest`
- `autostart`
- `clear`
- `close_plugin`
- `describe`
- `describe_op`
- `eval_python`
- `export_usd`
- `get`
- `import_fbx`
- `is_main_thread_marshalling_active`
- `is_running`
- `js_evaluate`
- `list_materials`
- `list_ops`
- `main`
- `mesh_reload`
- `mesh_reload_status`
- `ping`
- `project_info`
- `run_on_main_thread`
- `start_plugin`
- `start_server`
- `stop_server`
- `summary`
- `version`
