# API Shadows — Cross-Package Name Collisions

_Symbols whose simple name is defined in more than one ecosystem package. Review for DRY violations: a downstream wrapper that just re-exposes upstream behavior should be deleted; if it adds value, name it differently or document why._

## Genuine cross-layer collisions (54)

_Touch `pythontk` or span 3+ packages — the real DRY review surface._

### `AudioUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`AudioUtils`](blendertk/audio_utils/_audio_utils.py#L75)
- `mayatk` — [`AudioUtils`](mayatk/audio_utils/_audio_utils.py#L88)
- `pythontk` — [`AudioUtils`](pythontk/audio_utils/_audio_utils.py#L24)

### `Behaviors` — blendertk, mayatk, pythontk

- `blendertk` — [`Behaviors`](blendertk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L241)
- `mayatk` — [`Behaviors`](mayatk/anim_utils/shots/shot_manifest/behaviors/_behaviors.py#L157)
- `pythontk` — [`Behaviors`](pythontk/core_utils/engines/shots/manifest/behaviors/_behaviors.py#L110)

### `CompositorSlots` — extapps, tentacle

- `extapps` — [`CompositorSlots`](extapps/texture_maps/compositor/slots.py#L108)
- `tentacle` — [`CompositorSlots`](tentacle/slots/tools/compositor.py#L109)

### `CompositorUI` — extapps, tentacle

- `extapps` — [`CompositorUI`](extapps/texture_maps/compositor/launcher.py#L15)
- `tentacle` — [`CompositorUI`](tentacle/tcl_standalone.py#L138)

### `ConverterSlots` — extapps, tentacle

- `extapps` — [`ConverterSlots`](extapps/texture_maps/converter/slots.py#L38)
- `tentacle` — [`ConverterSlots`](tentacle/slots/tools/converter.py#L39)

### `ConverterUI` — extapps, tentacle

- `extapps` — [`ConverterUI`](extapps/texture_maps/converter/launcher.py#L15)
- `tentacle` — [`ConverterUI`](tentacle/tcl_standalone.py#L142)

### `CoreUtils` — blendertk, mayatk, pythontk

- `blendertk` — [`CoreUtils`](blendertk/core_utils/_core_utils.py#L479)
- `mayatk` — [`CoreUtils`](mayatk/core_utils/_core_utils.py#L291)
- `pythontk` — [`CoreUtils`](pythontk/core_utils/_core_utils.py#L16)

### `Finding` — mayatk, pythontk

- `mayatk` — [`Finding`](mayatk/core_utils/diagnostics/audit_records.py#L111)
- `pythontk` — [`Finding`](pythontk/file_utils/mesh_convert/export_verify.py#L43)

### `FramesSourceMixin` — extapps, tentacle

- `extapps` — [`FramesSourceMixin`](extapps/photogrammetry/_panel_slots.py#L386)
- `tentacle` — [`FramesSourceMixin`](tentacle/slots/tools/_photogrammetry/panel_slots.py#L385)

### `GaussianSplatWorkflowSlots` — extapps, tentacle

- `extapps` — [`GaussianSplatWorkflowSlots`](extapps/photogrammetry/gaussian_splat_workflow/slots.py#L37)
- `tentacle` — [`GaussianSplatWorkflowSlots`](tentacle/slots/tools/gaussian_splat_workflow.py#L36)

### `GaussianSplatWorkflowUI` — extapps, tentacle

- `extapps` — [`GaussianSplatWorkflowUI`](extapps/photogrammetry/gaussian_splat_workflow/launcher.py#L13)
- `tentacle` — [`GaussianSplatWorkflowUI`](tentacle/tcl_standalone.py#L162)

### `HierarchyBaseline` — blendertk, mayatk, pythontk

- `blendertk` — [`HierarchyBaseline`](blendertk/env_utils/hierarchy_sync/hierarchy_baseline.py#L43)
- `mayatk` — [`HierarchyBaseline`](mayatk/env_utils/hierarchy_sync/hierarchy_baseline.py#L48)
- `pythontk` — [`HierarchyBaseline`](pythontk/core_utils/engines/scene_export/hierarchy_baseline.py#L53)

### `KeyStash` — blendertk, mayatk, pythontk

- `blendertk` — [`KeyStash`](blendertk/anim_utils/key_stash/_key_stash.py#L304)
- `mayatk` — [`KeyStash`](mayatk/anim_utils/key_stash/_key_stash.py#L323)
- `pythontk` — [`KeyStash`](pythontk/core_utils/engines/key_stash/key_stash_model.py#L309)

### `LookMatchSlots` — extapps, tentacle

- `extapps` — [`LookMatchSlots`](extapps/look_match/slots.py#L92)
- `tentacle` — [`LookMatchSlots`](tentacle/slots/tools/look_match.py#L94)

### `LookMatchUI` — extapps, tentacle

- `extapps` — [`LookMatchUI`](extapps/look_match/launcher.py#L14)
- `tentacle` — [`LookMatchUI`](tentacle/tcl_standalone.py#L182)

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

### `MarmosetWorkflowSlots` — extapps, tentacle

- `extapps` — [`MarmosetWorkflowSlots`](extapps/marmoset_workflow/slots.py#L48)
- `tentacle` — [`MarmosetWorkflowSlots`](tentacle/slots/tools/marmoset_workflow.py#L49)

### `MarmosetWorkflowUI` — extapps, tentacle

- `extapps` — [`MarmosetWorkflowUI`](extapps/marmoset_workflow/launcher.py#L16)
- `tentacle` — [`MarmosetWorkflowUI`](tentacle/tcl_standalone.py#L170)

### `MaterialRecord` — mayatk, pythontk

- `mayatk` — [`MaterialRecord`](mayatk/core_utils/diagnostics/audit_records.py#L83)
- `pythontk` — [`MaterialRecord`](pythontk/core_utils/engines/scene_export/material_record.py#L120)

### `MeshConvertSlots` — extapps, tentacle

- `extapps` — [`MeshConvertSlots`](extapps/mesh_convert/slots.py#L16)
- `tentacle` — [`MeshConvertSlots`](tentacle/slots/tools/mesh_convert.py#L18)

### `MeshConvertUI` — extapps, tentacle

- `extapps` — [`MeshConvertUI`](extapps/mesh_convert/launcher.py#L14)
- `tentacle` — [`MeshConvertUI`](tentacle/tcl_standalone.py#L150)

### `MetashapeWorkflowSlots` — extapps, tentacle

- `extapps` — [`MetashapeWorkflowSlots`](extapps/photogrammetry/metashape_workflow/slots.py#L42)
- `tentacle` — [`MetashapeWorkflowSlots`](tentacle/slots/tools/metashape_workflow.py#L40)

### `MetashapeWorkflowUI` — extapps, tentacle

- `extapps` — [`MetashapeWorkflowUI`](extapps/photogrammetry/metashape_workflow/launcher.py#L15)
- `tentacle` — [`MetashapeWorkflowUI`](tentacle/tcl_standalone.py#L154)

### `OpRegistry` — blendertk, mayatk, pythontk

- `blendertk` — [`OpRegistry`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L84)
- `blendertk` — [`OpRegistry`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L84)
- `mayatk` — [`OpRegistry`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L84)
- `mayatk` — [`OpRegistry`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L84)
- `pythontk` — [`OpRegistry`](pythontk/net_utils/rpc/plugin_core.py#L84)

### `PackerSlots` — extapps, tentacle

- `extapps` — [`PackerSlots`](extapps/texture_maps/packer/slots.py#L16)
- `tentacle` — [`PackerSlots`](tentacle/slots/tools/packer.py#L18)

### `PackerUI` — extapps, tentacle

- `extapps` — [`PackerUI`](extapps/texture_maps/packer/launcher.py#L13)
- `tentacle` — [`PackerUI`](tentacle/tcl_standalone.py#L146)

### `PanelLauncher` — extapps, tentacle

- `extapps` — [`PanelLauncher`](extapps/_panel_launcher.py#L70)
- `tentacle` — [`PanelLauncher`](tentacle/tcl_standalone.py#L74)

### `Parameters` — blendertk, extapps, mayatk, tentacle, uitk

- `blendertk` — [`Parameters`](blendertk/env_utils/maya_bridge/parameters.py#L149)
- `blendertk` — [`Parameters`](blendertk/env_utils/unity_bridge/parameters.py#L61)
- `blendertk` — [`Parameters`](blendertk/mat_utils/marmoset_bridge/parameters.py#L418)
- `blendertk` — [`Parameters`](blendertk/mat_utils/substance_bridge/parameters.py#L266)
- `blendertk` — [`Parameters`](blendertk/uv_utils/rizom_bridge/parameters.py#L532)
- `extapps` — [`Parameters`](extapps/marmoset_workflow/parameters.py#L49)
- `extapps` — [`Parameters`](extapps/photogrammetry/gaussian_splat_workflow/parameters.py#L117)
- `extapps` — [`Parameters`](extapps/photogrammetry/metashape_workflow/parameters.py#L372)
- `extapps` — [`Parameters`](extapps/photogrammetry/realityscan_workflow/parameters.py#L164)
- `extapps` — [`Parameters`](extapps/unity_workflow/parameters.py#L157)
- `extapps` — [`Parameters`](extapps/webxr_preview/parameters.py#L360)
- `mayatk` — [`Parameters`](mayatk/env_utils/blender_bridge/parameters.py#L508)
- `mayatk` — [`Parameters`](mayatk/env_utils/unity_bridge/parameters.py#L63)
- `mayatk` — [`Parameters`](mayatk/mat_utils/marmoset_bridge/parameters.py#L418)
- `mayatk` — [`Parameters`](mayatk/mat_utils/substance_bridge/parameters.py#L266)
- `mayatk` — [`Parameters`](mayatk/uv_utils/rizom_bridge/parameters.py#L527)
- `tentacle` — [`Parameters`](tentacle/slots/tools/_marmoset_workflow/parameters.py#L52)
- `tentacle` — [`Parameters`](tentacle/slots/tools/_photogrammetry/gaussian_splat_parameters.py#L119)
- `tentacle` — [`Parameters`](tentacle/slots/tools/_photogrammetry/metashape_parameters.py#L374)
- `tentacle` — [`Parameters`](tentacle/slots/tools/_photogrammetry/realityscan_parameters.py#L166)
- `tentacle` — [`Parameters`](tentacle/slots/tools/_unity_workflow/parameters.py#L127)
- `tentacle` — [`Parameters`](tentacle/slots/tools/_webxr_preview/parameters.py#L363)
- `uitk` — [`Parameters`](uitk/bridge/parameters.py#L39)

### `PhotogrammetryPanelSlots` — extapps, tentacle

- `extapps` — [`PhotogrammetryPanelSlots`](extapps/photogrammetry/_panel_slots.py#L45)
- `tentacle` — [`PhotogrammetryPanelSlots`](tentacle/slots/tools/_photogrammetry/panel_slots.py#L44)

### `ProbePlacement` — blendertk, mayatk, pythontk

- `blendertk` — [`ProbePlacement`](blendertk/light_utils/lightmap_baker/_probe_placement.py#L184)
- `mayatk` — [`ProbePlacement`](mayatk/light_utils/lightmap_baker/_probe_placement.py#L178)
- `pythontk` — [`ProbePlacement`](pythontk/geo_utils/probe_placement.py#L283)

### `QtPlatformUnavailable` — blendertk, tentacle

- `blendertk` — [`QtPlatformUnavailable`](blendertk/ui_utils/qt_runtime.py#L56)
- `tentacle` — [`QtPlatformUnavailable`](tentacle/tcl.py#L39)

### `RangeResolver` — blendertk, mayatk, pythontk

- `blendertk` — [`RangeResolver`](blendertk/anim_utils/shots/shot_manifest/range_resolver.py#L29)
- `mayatk` — [`RangeResolver`](mayatk/anim_utils/shots/shot_manifest/range_resolver.py#L28)
- `pythontk` — [`RangeResolver`](pythontk/core_utils/engines/shots/manifest/range_resolver.py#L19)

### `RealityScanWorkflowUI` — extapps, tentacle

- `extapps` — [`RealityScanWorkflowUI`](extapps/photogrammetry/realityscan_workflow/launcher.py#L13)
- `tentacle` — [`RealityScanWorkflowUI`](tentacle/tcl_standalone.py#L158)

### `RealityscanWorkflowSlots` — extapps, tentacle

- `extapps` — [`RealityscanWorkflowSlots`](extapps/photogrammetry/realityscan_workflow/slots.py#L36)
- `tentacle` — [`RealityscanWorkflowSlots`](tentacle/slots/tools/realityscan_workflow.py#L36)

### `RpcPlugin` — blendertk, mayatk, pythontk

- `blendertk` — [`RpcPlugin`](blendertk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L451)
- `blendertk` — [`RpcPlugin`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L451)
- `mayatk` — [`RpcPlugin`](mayatk/mat_utils/marmoset_bridge/marmoset_rpc/plugin_src/marmoset_rpc/_rpc_core.py#L451)
- `mayatk` — [`RpcPlugin`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/_rpc_core.py#L451)
- `pythontk` — [`RpcPlugin`](pythontk/net_utils/rpc/plugin_core.py#L451)

### `SharedParams` — extapps, tentacle

- `extapps` — [`SharedParams`](extapps/photogrammetry/_shared_params.py#L151)
- `tentacle` — [`SharedParams`](tentacle/slots/tools/_photogrammetry/shared_parameters.py#L153)

### `ShotApply` — mayatk, pythontk

- `mayatk` — [`ShotApply`](mayatk/anim_utils/shots/_shot_apply.py#L329)
- `pythontk` — [`ShotApply`](pythontk/core_utils/engines/shots/shot_apply.py#L55)

### `ShotManifest` — mayatk, pythontk

- `mayatk` — [`ShotManifest`](mayatk/anim_utils/shots/shot_manifest/_shot_manifest.py#L118)
- `pythontk` — [`ShotManifest`](pythontk/core_utils/engines/shots/manifest/manifest_engine.py#L103)

### `ShotSequencer` — blendertk, mayatk, pythontk

- `blendertk` — [`ShotSequencer`](blendertk/anim_utils/shots/shot_sequencer/_shot_sequencer.py#L248)
- `mayatk` — [`ShotSequencer`](mayatk/anim_utils/shots/shot_sequencer/_shot_sequencer.py#L67)
- `pythontk` — [`ShotSequencer`](pythontk/core_utils/engines/shots/shot_sequencer.py#L375)

### `SubstanceWorkflowSlots` — extapps, tentacle

- `extapps` — [`SubstanceWorkflowSlots`](extapps/substance_workflow/slots.py#L235)
- `tentacle` — [`SubstanceWorkflowSlots`](tentacle/slots/tools/substance_workflow.py#L234)

### `SubstanceWorkflowUI` — extapps, tentacle

- `extapps` — [`SubstanceWorkflowUI`](extapps/substance_workflow/launcher.py#L15)
- `tentacle` — [`SubstanceWorkflowUI`](tentacle/tcl_standalone.py#L166)

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

### `UnityWorkflowSlots` — extapps, tentacle

- `extapps` — [`UnityWorkflowSlots`](extapps/unity_workflow/slots.py#L61)
- `tentacle` — [`UnityWorkflowSlots`](tentacle/slots/tools/unity_workflow.py#L56)

### `UnityWorkflowUI` — extapps, tentacle

- `extapps` — [`UnityWorkflowUI`](extapps/unity_workflow/launcher.py#L15)
- `tentacle` — [`UnityWorkflowUI`](tentacle/tcl_standalone.py#L174)

### `WebXrPreviewSlots` — extapps, tentacle

- `extapps` — [`WebXrPreviewSlots`](extapps/webxr_preview/slots.py#L116)
- `tentacle` — [`WebXrPreviewSlots`](tentacle/slots/tools/webxr_preview.py#L117)

### `WebXrPreviewUI` — extapps, tentacle

- `extapps` — [`WebXrPreviewUI`](extapps/webxr_preview/launcher.py#L15)
- `tentacle` — [`WebXrPreviewUI`](tentacle/tcl_standalone.py#L178)

### `close_plugin` — blendertk, extapps, mayatk

- `blendertk` — [`close_plugin`](blendertk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L81)
- `extapps` — [`close_plugin`](extapps/substance_workflow/plugins/startup/substance_workflow_bridge/__init__.py#L126)
- `mayatk` — [`close_plugin`](mayatk/mat_utils/substance_bridge/substance_rpc/plugin_src/substance_rpc/__init__.py#L81)

### `main` — blendertk, extapps, mayatk, pythontk

- `blendertk` — [`main`](blendertk/env_utils/hierarchy_sync/_fbx_stage_worker.py#L42)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/_bake_scene.py#L64)
- `blendertk` — [`main`](blendertk/env_utils/maya_bridge/templates/_import_scene.py#L1298)
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

## Intentional mayatk↔blendertk port parity (181)

_blendertk deliberately mirrors mayatk's public names (branch-free tentacle slots). Expected — not DRY violations. Names only:_

- `AnchorStrategy`
- `AnimUtils`
- `AnimationMacros`
- `Applicator`
- `ApplyStatus`
- `ArnoldBridge`
- `ArticulatedRig`
- `ArticulatedRigGrab`
- `AssemblyReconstructor`
- `AudioClips`
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
- `BlendshapeAnimator`
- `Bridge`
- `BridgeHost`
- `CalculatorController`
- `CamUtils`
- `CameraVisibility`
- `Channels`
- `ColorId`
- `CombineInputs`
- `Components`
- `ControlNodes`
- `Controls`
- `Creator`
- `Curtain`
- `CurtainMesh`
- `CurtainRig`
- `CurveToTube`
- `CutOnAxis`
- `DataNodes`
- `Detection`
- `DisplayMacros`
- `DisplayUtils`
- `DuplicateGrid`
- `DuplicateLinear`
- `DuplicateRadial`
- `DynamicPipe`
- `EditMacros`
- `EditUtils`
- `EmissiveGroups`
- `EnvUtils`
- `ExplodedView`
- `FKChainStrategy`
- `FbxUtils`
- `GameShader`
- `GeometryMatcher`
- `GraphSync`
- `HdrManager`
- `HierarchyMapBuilder`
- `HierarchySync`
- `HierarchySyncSession`
- `ImageToPlane`
- `ImageTracer`
- `Installer`
- `InstanceCandidate`
- `InstanceGroup`
- `Keyframes`
- `LightUtils`
- `LightmapBakeResult`
- `LightmapBaker`
- `LightmapExcludeSet`
- `LightmapIsolateSet`
- `LightmapRecords`
- `MacroManager`
- `Macros`
- `ManifestHost`
- `MarmosetBridge`
- `MarmosetConnection`
- `MatManifest`
- `MatUpdater`
- `MatUtils`
- `MaterialRecords`
- `Matrices`
- `MeshDiagnostics`
- `Naming`
- `NodeIcons`
- `NodeUtils`
- `NurbsUtils`
- `ObjectSwapper`
- `PackUvsResult`
- `PainterRpcClient`
- `PlayblastExporter`
- `Preview`
- `Primitives`
- `Rail`
- `ReferenceManager`
- `RenderEffects`
- `RenderUtils`
- `RestoreResult`
- `RigGraphBuilder`
- `RigGraphExtractor`
- `RigModeConfig`
- `RigUtils`
- `RizomUVBridge`
- `ScaleKeys`
- `SceneAnalyzer`
- `SceneDataSidecar`
- `SceneDiagnostics`
- `SceneExporter`
- `SceneInfoSection`
- `ScriptConsole`
- `ScriptJobManager`
- `SegmentCollector`
- `SegmentKeys`
- `Selection`
- `SelectionMacros`
- `SequencerHost`
- `ShaderTemplates`
- `ShadowPreview`
- `ShadowRig`
- `SmartBake`
- `Snap`
- `SplineIKStrategy`
- `StaggerKeys`
- `StyleSetter`
- `SubstanceBridge`
- `SubstanceConnection`
- `SubstanceEngine`
- `Target`
- `TargetWeld`
- `Targets`
- `TaskManager`
- `TelescopeRig`
- `TelescopeRigBundle`
- `TextureBaker`
- `TextureCombine`
- `TexturePathEditor`
- `TextureTransfer`
- `TransformDiagnostics`
- `TubePath`
- `TubeRig`
- `TubeRigBundle`
- `TubeStrategy`
- `UiMacros`
- `UiUtils`
- `UnfoldResult`
- `Units`
- `UnityBridge`
- `UsdUtils`
- `UvDiagnostics`
- `UvSetCleanupResult`
- `UvUtils`
- `Validator`
- `WebXrPreview`
- `WheelRig`
- `WorkspaceMap`
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
