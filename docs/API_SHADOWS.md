# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

_Generated: 2026-07-09_

## Genuine cross-layer collisions (35)

_Touch `pythontk` or span 3+ packages — the real DRY review surface._

### `AudioUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`AudioUtils`](blendertk/audio_utils/_audio_utils.py#L66)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L84)
- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L15)

### `Call` — extapps, pythontk

- `extapps` — [`Call`](extapps/substance_workflow/job.py#L18)
- `pythontk` — [`Call`](pythontk/net_utils/rpc/job.py#L30)

### `CoreUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`CoreUtils`](blendertk/core_utils/_core_utils.py#L678)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L219)
- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L14)

### `MarmosetEngine` — blendertk, extapps, mayatk

- `blendertk` — [`MarmosetEngine`](blendertk/mat_utils/marmoset_bridge/_marmoset_engine.py#L83)
- `extapps` — [`MarmosetEngine`](extapps/marmoset_workflow/_marmoset_engine.py#L83)
- `mayatk` — [`MarmosetEngine`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L83)

### `Result` — extapps, pythontk

- `extapps` — [`Result`](extapps/substance_workflow/job.py#L27)
- `pythontk` — [`Result`](pythontk/net_utils/rpc/job.py#L42)

### `Selection` — blendertk, mayatk, tentacle

- `blendertk` — [`Selection`](blendertk/edit_utils/selection.py#L30)
- `mayatk` — [`Selection`](mayatk/edit_utils/selection.py#L19)
- `tentacle` — [`Selection`](tentacle/slots/blender/selection.py#L9)
- `tentacle` — [`Selection`](tentacle/slots/maya/selection.py#L10)

### `all_ops` — blendertk, extapps, mayatk

- `blendertk` — [`all_ops`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L41)
- `extapps` — [`all_ops`](extapps/substance_workflow/registry.py#L43)
- `mayatk` — [`all_ops`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L41)

### `apply_sky_preset` — blendertk, extapps, mayatk

- `blendertk` — [`apply_sky_preset`](blendertk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L431)
- `extapps` — [`apply_sky_preset`](extapps/marmoset_workflow/_toolbag_helpers.py#L431)
- `mayatk` — [`apply_sky_preset`](mayatk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L431)

### `begin_log` — blendertk, extapps, mayatk

- `blendertk` — [`begin_log`](blendertk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L55)
- `extapps` — [`begin_log`](extapps/marmoset_workflow/_toolbag_helpers.py#L55)
- `mayatk` — [`begin_log`](mayatk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L55)

### `classify_log_line` — blendertk, extapps, mayatk

- `blendertk` — [`classify_log_line`](blendertk/mat_utils/marmoset_bridge/toolbag_log.py#L83)
- `extapps` — [`classify_log_line`](extapps/marmoset_workflow/toolbag_log.py#L83)
- `mayatk` — [`classify_log_line`](mayatk/mat_utils/marmoset_bridge/toolbag_log.py#L83)

### `collect_mesh_objects` — blendertk, extapps, mayatk

- `blendertk` — [`collect_mesh_objects`](blendertk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L391)
- `extapps` — [`collect_mesh_objects`](extapps/marmoset_workflow/_toolbag_helpers.py#L391)
- `mayatk` — [`collect_mesh_objects`](mayatk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L391)

### `defaults` — blendertk, extapps, mayatk, uitk

- `blendertk` — [`defaults`](blendertk/env_utils/maya_bridge/parameters.py#L111)
- `blendertk` — [`defaults`](blendertk/env_utils/unity_bridge/parameters.py#L145)
- `blendertk` — [`defaults`](blendertk/mat_utils/marmoset_bridge/parameters.py#L240)
- `blendertk` — [`defaults`](blendertk/mat_utils/marmoset_bridge/template_params.py#L60)
- `blendertk` — [`defaults`](blendertk/mat_utils/substance_bridge/parameters.py#L179)
- `blendertk` — [`defaults`](blendertk/uv_utils/rizom_bridge/parameters.py#L91)
- `extapps` — [`defaults`](extapps/marmoset_workflow/parameters.py#L68)
- `extapps` — [`defaults`](extapps/marmoset_workflow/template_params.py#L60)
- `extapps` — [`defaults`](extapps/photogrammetry/gaussian_splat_workflow/parameters.py#L108)
- `extapps` — [`defaults`](extapps/photogrammetry/metashape_workflow/parameters.py#L250)
- `extapps` — [`defaults`](extapps/photogrammetry/realityscan_workflow/parameters.py#L118)
- `extapps` — [`defaults`](extapps/unity_workflow/parameters.py#L96)
- `mayatk` — [`defaults`](mayatk/env_utils/blender_bridge/parameters.py#L110)
- `mayatk` — [`defaults`](mayatk/env_utils/unity_bridge/parameters.py#L147)
- `mayatk` — [`defaults`](mayatk/mat_utils/marmoset_bridge/parameters.py#L240)
- `mayatk` — [`defaults`](mayatk/mat_utils/marmoset_bridge/template_params.py#L60)
- `mayatk` — [`defaults`](mayatk/mat_utils/substance_bridge/parameters.py#L179)
- `mayatk` — [`defaults`](mayatk/uv_utils/rizom_bridge/parameters.py#L301)
- `uitk` — [`defaults`](uitk/bridge/parameters.py#L48)

### `derive_per_run_log_path` — blendertk, extapps, mayatk

- `blendertk` — [`derive_per_run_log_path`](blendertk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L41)
- `extapps` — [`derive_per_run_log_path`](extapps/marmoset_workflow/_toolbag_helpers.py#L41)
- `mayatk` — [`derive_per_run_log_path`](mayatk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L41)

### `describe` — blendertk, extapps, mayatk

- `blendertk` — [`describe`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L46)
- `extapps` — [`describe`](extapps/substance_workflow/registry.py#L47)
- `mayatk` — [`describe`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L46)

### `dispatch_log_lines` — blendertk, extapps, mayatk

- `blendertk` — [`dispatch_log_lines`](blendertk/mat_utils/marmoset_bridge/toolbag_log.py#L134)
- `extapps` — [`dispatch_log_lines`](extapps/marmoset_workflow/toolbag_log.py#L134)
- `mayatk` — [`dispatch_log_lines`](mayatk/mat_utils/marmoset_bridge/toolbag_log.py#L134)

### `find_material` — blendertk, extapps, mayatk

- `blendertk` — [`find_material`](blendertk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L153)
- `extapps` — [`find_material`](extapps/marmoset_workflow/_toolbag_helpers.py#L153)
- `mayatk` — [`find_material`](mayatk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L153)

### `frame_in_viewport` — blendertk, extapps, mayatk

- `blendertk` — [`frame_in_viewport`](blendertk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L455)
- `extapps` — [`frame_in_viewport`](extapps/marmoset_workflow/_toolbag_helpers.py#L455)
- `mayatk` — [`frame_in_viewport`](mayatk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L455)

### `get` — blendertk, extapps, mayatk

- `blendertk` — [`get`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L36)
- `extapps` — [`get`](extapps/substance_workflow/registry.py#L39)
- `mayatk` — [`get`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L36)

### `launch` — mayatk, tentacle

- `mayatk` — [`launch`](mayatk/node_utils/attributes/channels/__init__.py#L14)
- `tentacle` — [`launch`](tentacle/tcl_blender.py#L1385)

### `list_template_modes` — blendertk, extapps, mayatk, pythontk

- `blendertk` — [`list_template_modes`](blendertk/env_utils/maya_bridge/_maya_bridge.py#L81)
- `blendertk` — [`list_template_modes`](blendertk/mat_utils/marmoset_bridge/_marmoset_engine.py#L73)
- `blendertk` — [`list_template_modes`](blendertk/mat_utils/substance_bridge/_substance_bridge.py#L186)
- `extapps` — [`list_template_modes`](extapps/marmoset_workflow/_marmoset_engine.py#L73)
- `mayatk` — [`list_template_modes`](mayatk/env_utils/blender_bridge/_blender_bridge.py#L73)
- `mayatk` — [`list_template_modes`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L73)
- `mayatk` — [`list_template_modes`](mayatk/mat_utils/substance_bridge/_substance_bridge.py#L206)
- `pythontk` — [`list_template_modes`](pythontk/core_utils/script_template.py#L81)

### `list_templates` — blendertk, extapps, mayatk, pythontk

- `blendertk` — [`list_templates`](blendertk/env_utils/maya_bridge/_maya_bridge.py#L71)
- `blendertk` — [`list_templates`](blendertk/mat_utils/marmoset_bridge/_marmoset_engine.py#L59)
- `blendertk` — [`list_templates`](blendertk/mat_utils/substance_bridge/_substance_bridge.py#L106)
- `blendertk` — [`list_templates`](blendertk/ui_utils/style_setter/_style_setter.py#L99)
- `extapps` — [`list_templates`](extapps/marmoset_workflow/_marmoset_engine.py#L59)
- `mayatk` — [`list_templates`](mayatk/env_utils/blender_bridge/_blender_bridge.py#L63)
- `mayatk` — [`list_templates`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L59)
- `mayatk` — [`list_templates`](mayatk/mat_utils/substance_bridge/_substance_bridge.py#L126)
- `mayatk` — [`list_templates`](mayatk/ui_utils/style_setter/_style_setter.py#L111)
- `pythontk` — [`list_templates`](pythontk/core_utils/script_template.py#L47)

### `load_manifest` — blendertk, extapps, mayatk

- `blendertk` — [`load_manifest`](blendertk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L168)
- `extapps` — [`load_manifest`](extapps/marmoset_workflow/_toolbag_helpers.py#L168)
- `mayatk` — [`load_manifest`](mayatk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L168)

### `log` — blendertk, extapps, mayatk

- `blendertk` — [`log`](blendertk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L75)
- `extapps` — [`log`](extapps/marmoset_workflow/_toolbag_helpers.py#L75)
- `mayatk` — [`log`](mayatk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L75)

### `main` — blendertk, extapps, mayatk, uitk

- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/import.py#L26)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/bake.py#L123)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/import.py#L32)
- `blendertk` — [`main`](blendertk/mat_utils/marmoset_bridge/templates/lookdev.py#L41)
- `extapps` — [`main`](extapps/marmoset_workflow/templates/import.py#L32)
- `extapps` — [`main`](extapps/marmoset_workflow/templates/lookdev.py#L41)
- `extapps` — [`main`](extapps/photogrammetry/gaussian_splat_workflow/_install_brush.py#L19)
- `extapps` — [`main`](extapps/photogrammetry/gaussian_splat_workflow/run_combined.py#L46)
- `extapps` — [`main`](extapps/photogrammetry/metashape_workflow/run_combined.py#L91)
- `extapps` — [`main`](extapps/photogrammetry/realityscan_workflow/run_combined.py#L117)
- `extapps` — [`main`](extapps/photogrammetry/sugar_mesh_workflow/run_combined.py#L37)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/import.py#L28)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/bake.py#L123)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/import.py#L32)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/lookdev.py#L41)
- `uitk` — [`main`](uitk/compile.py#L526)

### `python_literal` — blendertk, extapps, mayatk, uitk

- `blendertk` — [`python_literal`](blendertk/mat_utils/marmoset_bridge/template_params.py#L49)
- `extapps` — [`python_literal`](extapps/marmoset_workflow/template_params.py#L49)
- `mayatk` — [`python_literal`](mayatk/mat_utils/marmoset_bridge/template_params.py#L49)
- `uitk` — [`python_literal`](uitk/bridge/formatters.py#L29)

### `referenced_keys` — blendertk, extapps, mayatk, uitk

- `blendertk` — [`referenced_keys`](blendertk/env_utils/maya_bridge/parameters.py#L106)
- `blendertk` — [`referenced_keys`](blendertk/env_utils/unity_bridge/parameters.py#L140)
- `blendertk` — [`referenced_keys`](blendertk/mat_utils/marmoset_bridge/parameters.py#L235)
- `blendertk` — [`referenced_keys`](blendertk/mat_utils/substance_bridge/parameters.py#L174)
- `blendertk` — [`referenced_keys`](blendertk/uv_utils/rizom_bridge/parameters.py#L86)
- `extapps` — [`referenced_keys`](extapps/marmoset_workflow/parameters.py#L63)
- `extapps` — [`referenced_keys`](extapps/photogrammetry/gaussian_splat_workflow/parameters.py#L98)
- `extapps` — [`referenced_keys`](extapps/photogrammetry/metashape_workflow/parameters.py#L233)
- `extapps` — [`referenced_keys`](extapps/photogrammetry/realityscan_workflow/parameters.py#L107)
- `extapps` — [`referenced_keys`](extapps/unity_workflow/parameters.py#L91)
- `mayatk` — [`referenced_keys`](mayatk/env_utils/blender_bridge/parameters.py#L105)
- `mayatk` — [`referenced_keys`](mayatk/env_utils/unity_bridge/parameters.py#L142)
- `mayatk` — [`referenced_keys`](mayatk/mat_utils/marmoset_bridge/parameters.py#L235)
- `mayatk` — [`referenced_keys`](mayatk/mat_utils/substance_bridge/parameters.py#L174)
- `mayatk` — [`referenced_keys`](mayatk/uv_utils/rizom_bridge/parameters.py#L296)
- `uitk` — [`referenced_keys`](uitk/bridge/parameters.py#L34)

### `register` — blendertk, extapps, mayatk, tentacle

- `blendertk` — [`register`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L21)
- `extapps` — [`register`](extapps/substance_workflow/registry.py#L19)
- `mayatk` — [`register`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L21)
- `tentacle` — [`register`](tentacle/tcl_blender.py#L1390)

### `render_context` — blendertk, extapps, mayatk, uitk

- `blendertk` — [`render_context`](blendertk/env_utils/maya_bridge/parameters.py#L116)
- `blendertk` — [`render_context`](blendertk/env_utils/unity_bridge/parameters.py#L150)
- `blendertk` — [`render_context`](blendertk/mat_utils/marmoset_bridge/parameters.py#L245)
- `blendertk` — [`render_context`](blendertk/uv_utils/rizom_bridge/parameters.py#L96)
- `extapps` — [`render_context`](extapps/marmoset_workflow/parameters.py#L73)
- `extapps` — [`render_context`](extapps/unity_workflow/parameters.py#L101)
- `mayatk` — [`render_context`](mayatk/env_utils/blender_bridge/parameters.py#L115)
- `mayatk` — [`render_context`](mayatk/env_utils/unity_bridge/parameters.py#L152)
- `mayatk` — [`render_context`](mayatk/mat_utils/marmoset_bridge/parameters.py#L245)
- `mayatk` — [`render_context`](mayatk/uv_utils/rizom_bridge/parameters.py#L306)
- `uitk` — [`render_context`](uitk/bridge/parameters.py#L53)

### `resolve_toolbag_log_path` — blendertk, extapps, mayatk

- `blendertk` — [`resolve_toolbag_log_path`](blendertk/mat_utils/marmoset_bridge/toolbag_log.py#L29)
- `extapps` — [`resolve_toolbag_log_path`](extapps/marmoset_workflow/toolbag_log.py#L29)
- `mayatk` — [`resolve_toolbag_log_path`](mayatk/mat_utils/marmoset_bridge/toolbag_log.py#L29)

### `run_batch` — blendertk, extapps, mayatk, pythontk

- `blendertk` — [`run_batch`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/job.py#L30)
- `extapps` — [`run_batch`](extapps/substance_workflow/job.py#L49)
- `mayatk` — [`run_batch`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/job.py#L30)
- `pythontk` — [`run_batch`](pythontk/net_utils/rpc/job.py#L55)

### `split_high_low` — blendertk, extapps, mayatk

- `blendertk` — [`split_high_low`](blendertk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L309)
- `extapps` — [`split_high_low`](extapps/marmoset_workflow/_toolbag_helpers.py#L309)
- `mayatk` — [`split_high_low`](mayatk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L309)

### `start_toolbag_log_tail` — blendertk, extapps, mayatk

- `blendertk` — [`start_toolbag_log_tail`](blendertk/mat_utils/marmoset_bridge/toolbag_log.py#L148)
- `extapps` — [`start_toolbag_log_tail`](extapps/marmoset_workflow/toolbag_log.py#L148)
- `mayatk` — [`start_toolbag_log_tail`](mayatk/mat_utils/marmoset_bridge/toolbag_log.py#L148)

### `template_modes` — blendertk, extapps, mayatk, pythontk

- `blendertk` — [`template_modes`](blendertk/env_utils/maya_bridge/_maya_bridge.py#L76)
- `blendertk` — [`template_modes`](blendertk/mat_utils/marmoset_bridge/_marmoset_engine.py#L64)
- `extapps` — [`template_modes`](extapps/marmoset_workflow/_marmoset_engine.py#L64)
- `mayatk` — [`template_modes`](mayatk/env_utils/blender_bridge/_blender_bridge.py#L68)
- `mayatk` — [`template_modes`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L64)
- `pythontk` — [`template_modes`](pythontk/core_utils/script_template.py#L56)

### `to_context` — blendertk, extapps, mayatk

- `blendertk` — [`to_context`](blendertk/mat_utils/marmoset_bridge/template_params.py#L65)
- `extapps` — [`to_context`](extapps/marmoset_workflow/template_params.py#L65)
- `mayatk` — [`to_context`](mayatk/mat_utils/marmoset_bridge/template_params.py#L65)

### `wire_materials_from_manifest` — blendertk, extapps, mayatk

- `blendertk` — [`wire_materials_from_manifest`](blendertk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L185)
- `extapps` — [`wire_materials_from_manifest`](extapps/marmoset_workflow/_toolbag_helpers.py#L185)
- `mayatk` — [`wire_materials_from_manifest`](mayatk/mat_utils/marmoset_bridge/_toolbag_helpers.py#L185)

---

## Intentional mayatk↔blendertk port parity (184)

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
- `OutputStream`
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
- `TaskFactory`
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
- `UvTransformSlots`
- `UvUtils`
- `Validator`
- `Weights`
- `WheelRig`
- `WheelRigSlots`
- `XformUtils`
- `apply_template`
- `auto_instance`
- `autostart`
- `build_bake_pairs_manifest`
- `build_hierarchy_structure`
- `clear`
- `default_log_path`
- `describe_op`
- `find_painter_exe`
- `find_tree_item_by_name`
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
- `node_ref`
- `parse_template`
- `ping`
- `render_cli_context`
- `render_js_context`
- `resolve_painter_log_path`
- `resolve_ref`
- `restore_session`
- `run_on_main_thread`
- `set_style`
- `should_keep_node_by_type`
- `show`
- `start_server`
- `stop_server`
- `summary`
- `toggle`
- `uninstall`
- `user_plugin_dir`
- `version`
