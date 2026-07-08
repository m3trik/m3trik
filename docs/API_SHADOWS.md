# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

_Generated: 2026-07-08_

## Genuine cross-layer collisions (14)

_Touch `pythontk` or span 3+ packages — the real DRY review surface._

### `AudioUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`AudioUtils`](blendertk/audio_utils/_audio_utils.py#L66)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L81)
- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L15)

### `CoreUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`CoreUtils`](blendertk/core_utils/_core_utils.py#L619)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L219)
- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L14)

### `Selection` — blendertk, mayatk, tentacle

- `blendertk` — [`Selection`](blendertk/edit_utils/selection.py#L30)
- `mayatk` — [`Selection`](mayatk/edit_utils/selection.py#L19)
- `tentacle` — [`Selection`](tentacle/slots/blender/selection.py#L9)
- `tentacle` — [`Selection`](tentacle/slots/maya/selection.py#L10)

### `defaults` — blendertk, mayatk, uitk

- `blendertk` — [`defaults`](blendertk/env_utils/maya_bridge/parameters.py#L111)
- `blendertk` — [`defaults`](blendertk/env_utils/unity_bridge/parameters.py#L145)
- `blendertk` — [`defaults`](blendertk/uv_utils/rizom_bridge/parameters.py#L91)
- `mayatk` — [`defaults`](mayatk/env_utils/blender_bridge/parameters.py#L110)
- `mayatk` — [`defaults`](mayatk/env_utils/unity_bridge/parameters.py#L147)
- `mayatk` — [`defaults`](mayatk/mat_utils/marmoset_bridge/parameters.py#L240)
- `mayatk` — [`defaults`](mayatk/mat_utils/marmoset_bridge/template_params.py#L60)
- `mayatk` — [`defaults`](mayatk/mat_utils/substance_bridge/parameters.py#L179)
- `mayatk` — [`defaults`](mayatk/uv_utils/rizom_bridge/parameters.py#L301)
- `uitk` — [`defaults`](uitk/bridge/parameters.py#L48)

### `launch` — mayatk, tentacle

- `mayatk` — [`launch`](mayatk/node_utils/attributes/channels/__init__.py#L14)
- `tentacle` — [`launch`](tentacle/tcl_blender.py#L1385)

### `list_template_modes` — blendertk, mayatk, pythontk

- `blendertk` — [`list_template_modes`](blendertk/env_utils/maya_bridge/_maya_bridge.py#L81)
- `mayatk` — [`list_template_modes`](mayatk/env_utils/blender_bridge/_blender_bridge.py#L73)
- `mayatk` — [`list_template_modes`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L73)
- `mayatk` — [`list_template_modes`](mayatk/mat_utils/substance_bridge/_substance_bridge.py#L206)
- `pythontk` — [`list_template_modes`](pythontk/core_utils/script_template.py#L81)

### `list_templates` — blendertk, mayatk, pythontk

- `blendertk` — [`list_templates`](blendertk/env_utils/maya_bridge/_maya_bridge.py#L71)
- `blendertk` — [`list_templates`](blendertk/ui_utils/style_setter/_style_setter.py#L99)
- `mayatk` — [`list_templates`](mayatk/env_utils/blender_bridge/_blender_bridge.py#L63)
- `mayatk` — [`list_templates`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L59)
- `mayatk` — [`list_templates`](mayatk/mat_utils/substance_bridge/_substance_bridge.py#L126)
- `mayatk` — [`list_templates`](mayatk/ui_utils/style_setter/_style_setter.py#L111)
- `pythontk` — [`list_templates`](pythontk/core_utils/script_template.py#L47)

### `main` — blendertk, mayatk, uitk

- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/import.py#L26)
- `mayatk` — [`main`](mayatk/env_utils/blender_bridge/templates/import.py#L28)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/bake.py#L123)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/import.py#L32)
- `mayatk` — [`main`](mayatk/mat_utils/marmoset_bridge/templates/lookdev.py#L41)
- `uitk` — [`main`](uitk/compile.py#L526)

### `python_literal` — mayatk, uitk

- `mayatk` — [`python_literal`](mayatk/mat_utils/marmoset_bridge/template_params.py#L49)
- `uitk` — [`python_literal`](uitk/bridge/formatters.py#L29)

### `referenced_keys` — blendertk, mayatk, uitk

- `blendertk` — [`referenced_keys`](blendertk/env_utils/maya_bridge/parameters.py#L106)
- `blendertk` — [`referenced_keys`](blendertk/env_utils/unity_bridge/parameters.py#L140)
- `blendertk` — [`referenced_keys`](blendertk/uv_utils/rizom_bridge/parameters.py#L86)
- `mayatk` — [`referenced_keys`](mayatk/env_utils/blender_bridge/parameters.py#L105)
- `mayatk` — [`referenced_keys`](mayatk/env_utils/unity_bridge/parameters.py#L142)
- `mayatk` — [`referenced_keys`](mayatk/mat_utils/marmoset_bridge/parameters.py#L235)
- `mayatk` — [`referenced_keys`](mayatk/mat_utils/substance_bridge/parameters.py#L174)
- `mayatk` — [`referenced_keys`](mayatk/uv_utils/rizom_bridge/parameters.py#L296)
- `uitk` — [`referenced_keys`](uitk/bridge/parameters.py#L34)

### `register` — mayatk, tentacle

- `mayatk` — [`register`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/registry.py#L21)
- `tentacle` — [`register`](tentacle/tcl_blender.py#L1390)

### `render_context` — blendertk, mayatk, uitk

- `blendertk` — [`render_context`](blendertk/env_utils/maya_bridge/parameters.py#L116)
- `blendertk` — [`render_context`](blendertk/env_utils/unity_bridge/parameters.py#L150)
- `blendertk` — [`render_context`](blendertk/uv_utils/rizom_bridge/parameters.py#L96)
- `mayatk` — [`render_context`](mayatk/env_utils/blender_bridge/parameters.py#L115)
- `mayatk` — [`render_context`](mayatk/env_utils/unity_bridge/parameters.py#L152)
- `mayatk` — [`render_context`](mayatk/mat_utils/marmoset_bridge/parameters.py#L245)
- `mayatk` — [`render_context`](mayatk/uv_utils/rizom_bridge/parameters.py#L306)
- `uitk` — [`render_context`](uitk/bridge/parameters.py#L53)

### `run_batch` — mayatk, pythontk

- `mayatk` — [`run_batch`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/job.py#L30)
- `pythontk` — [`run_batch`](pythontk/net_utils/rpc/job.py#L55)

### `template_modes` — blendertk, mayatk, pythontk

- `blendertk` — [`template_modes`](blendertk/env_utils/maya_bridge/_maya_bridge.py#L76)
- `mayatk` — [`template_modes`](mayatk/env_utils/blender_bridge/_blender_bridge.py#L68)
- `mayatk` — [`template_modes`](mayatk/mat_utils/marmoset_bridge/_marmoset_engine.py#L64)
- `pythontk` — [`template_modes`](pythontk/core_utils/script_template.py#L56)

---

## Intentional mayatk↔blendertk port parity (143)

_blendertk deliberately mirrors mayatk's public names (branch-free tentacle slots). Expected — not DRY violations. Names only:_

- `AnchorStrategy`
- `AnimUtils`
- `AnimationMacros`
- `Applicator`
- `ApplyStatus`
- `ArnoldBridge`
- `ArnoldBridgeSlots`
- `AudioClipsSlots`
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
- `Keyframes`
- `LightUtils`
- `LightmapBaker`
- `LightmapBakerSlots`
- `MacroManager`
- `MacroManagerSlots`
- `Macros`
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
- `StyleSetter`
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
- `UvUtils`
- `Validator`
- `Weights`
- `WheelRig`
- `WheelRigSlots`
- `XformUtils`
- `apply_template`
- `build_hierarchy_structure`
- `find_tree_item_by_name`
- `get_bounding_box`
- `get_selected_object_names`
- `get_selected_tree_items`
- `install`
- `is_installed`
- `list_delivery_modes`
- `list_styles`
- `node_ref`
- `resolve_ref`
- `restore_session`
- `set_style`
- `should_keep_node_by_type`
- `show`
- `toggle`
