# Workspace Repository Inventory

Generated from `O:/Cloud/Code/_scripts` on 2026-11-01 03:21 UTC.

Scope: direct child git repositories under the workspace root. Line counts cover tracked code/config files and exclude common generated folders such as `.venv`, `build`, `dist`, `output`, `node_modules`, and `__pycache__`.

## Summary

- Repositories: 12
- Tracked code/config files: 2905
- Total lines: 1765055
- Non-empty lines: 1576200

## Repository Index

| Repo | Domain | Kind | Package roots | Code roots | Docs | Tests | Files | Total lines | Non-empty |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| androidtk | Android device toolkit (satellite) | Python package | androidtk | examples<br>test | Yes | Yes | 21 | 1814 | 1492 |
| blendertk | Blender 4.x+ host library, mirrors mayatk; each tool's Blender API half | Python package | blendertk | test | Yes | Yes | 398 | 254707 | 232899 |
| comfyui | ComfyUI custom nodes | Operations / scripts | - | comfyui<br>config<br>examples<br>patches<br>scripts<br>test<br>workflows | Yes | Yes | 99 | 18609 | 17381 |
| extapps | Standalone apps: each host-free app's engine, panel and Slots class | Python package | extapps | test | Yes | Yes | 177 | 53360 | 47566 |
| m3trik | PowerShell DevOps, release automation | Operations / scripts | - | docs<br>scripts<br>test | Yes | Yes | 65 | 39308 | 35251 |
| mayatk | Maya 2025+ host library; each tool's Maya API half | Python package | mayatk<br>test | - | Yes | Yes | 526 | 441885 | 389451 |
| pythontk | Core utils — DCC-agnostic, zero-dep | Python package | pythontk<br>test | examples<br>typings | Yes | Yes | 540 | 369986 | 329910 |
| server | Linux infra, zero-trust secrets | Operations / scripts | - | plugins<br>scripts<br>server<br>test | Yes | Yes | 115 | 18377 | 16441 |
| tentacle | The product: the launcher, every tool's panel and Slots class | Python package | tentacle | docs<br>test | Yes | Yes | 483 | 232173 | 212666 |
| uitk | Generic Qt UI library; no DCC/app logic | Python package | test<br>uitk | - | Yes | Yes | 407 | 240768 | 208016 |
| unitytk | Unity integration | Python package | test<br>unitytk | - | Yes | Yes | 45 | 32131 | 28383 |
| www | Web | Operations / scripts | - | test<br>www | Yes | Yes | 29 | 61937 | 56744 |

## Repository Details

### androidtk

- Path: `androidtk`
- Domain: Android device toolkit (satellite)
- Kind: Python package
- Summary: A Python toolkit for Android device management and modification.
- Manifests: pyproject.toml
- Root entry scripts: push_creds_to_phone.ps1, root_pixel7.py, run_tests.py
- Support folders: docs=Yes, tests=Yes, examples=Yes
- Tracked code surface: 21 files, 1814 total lines, 1492 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| androidtk | `androidtk` | core<br>devices<br>utils | - | 5 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| examples | `examples` | 2 | .py (2) |
| test | `test` | 5 | .py (5) |

### blendertk

- Path: `blendertk`
- Domain: Blender 4.x+ host library, mirrors mayatk; each tool's Blender API half
- Kind: Python package
- Summary: Python toolkit for Blender mirroring mayatk's API: modeling, UV, materials, animation, rigging and export utilities.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 398 files, 254707 total lines, 232899 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| blendertk | `blendertk` | anim_utils<br>audio_utils<br>cam_utils<br>core_utils<br>display_utils<br>edit_utils<br>env_utils<br>light_utils<br>mat_utils<br>node_utils<br>nurbs_utils<br>render_utils<br>rig_utils<br>ui_utils<br>uv_utils<br>xform_utils | - | 187 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| test | `test` | 140 | .py (132)<br>.json (7)<br>.ps1 (1) |

### comfyui

- Path: `comfyui`
- Domain: ComfyUI custom nodes
- Kind: Operations / scripts
- Summary: ComfyUI environment for m3trik-desktop -- single venv, uv-resolved, lockfile-pinned.
- Manifests: pyproject.toml
- Root entry scripts: connect.ps1, pull_outputs.ps1, remote_cmd.ps1, update.ps1
- Support folders: docs=Yes, tests=Yes, examples=Yes
- Tracked code surface: 99 files, 18609 total lines, 17381 non-empty lines

#### Package Roots

No top-level Python package roots detected.

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| comfyui | `comfyui` | 39 | .ps1 (19)<br>.py (15)<br>.sh (4)<br>.psm1 (1) |
| config | `config` | 1 | .yaml (1) |
| examples | `examples` | 1 | .json (1) |
| patches | `patches` | 1 | .py (1) |
| scripts | `scripts` | 10 | .py (6)<br>.ps1 (4) |
| test | `test` | 18 | .py (9)<br>.ps1 (8)<br>.sh (1) |
| workflows | `workflows` | 24 | .json (24) |

### extapps

- Path: `extapps`
- Domain: Standalone apps: each host-free app's engine, panel and Slots class
- Kind: Python package
- Summary: Standalone Qt tools for content pipelines: texture map compositing and conversion, photogrammetry, Substance Painter and Marmoset Toolbag automation, Unity and WebXR hand-off, and mesh conversion.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 177 files, 53360 total lines, 47566 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| extapps | `extapps` | look_match<br>marmoset_workflow<br>mesh_convert<br>photogrammetry<br>substance_workflow<br>texture_maps<br>unity_workflow<br>webxr_preview | __main__<br>_panel_launcher | 77 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| test | `test` | 49 | .py (49) |

### m3trik

- Path: `m3trik`
- Domain: PowerShell DevOps, release automation
- Kind: Operations / scripts
- Summary: Tech-art tooling for game-art and DCC pipelines: one product of tools that behaves the same in Maya and Blender, built on general libraries that are each useful on their own.
- Manifests: -
- Root entry scripts: common.ps1, package-manager.bat, pm_doctor.py, push.ps1
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 65 files, 39308 total lines, 35251 non-empty lines

#### Package Roots

No top-level Python package roots detected.

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| docs | `docs` | 1 | .json (1) |
| scripts | `scripts` | 33 | .py (27)<br>.ps1 (3)<br>.json (3) |
| test | `test` | 26 | .py (26) |

### mayatk

- Path: `mayatk`
- Domain: Maya 2025+ host library; each tool's Maya API half
- Kind: Python package
- Summary: Python toolkit for Autodesk Maya: modeling, UV, materials, animation, rigging, lighting and scene-export utilities.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 526 files, 441885 total lines, 389451 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| mayatk | `mayatk` | anim_utils<br>audio_utils<br>cam_utils<br>core_utils<br>display_utils<br>edit_utils<br>env_utils<br>light_utils<br>mat_utils<br>node_utils<br>nurbs_utils<br>render_utils<br>rig_utils<br>ui_utils<br>uv_utils<br>xform_utils | - | 234 |
| test | `test` | - | _run_hm_tests<br>_suite_driver<br>articulated_rig_live_check<br>base_test<br>check_cmds_naming<br>check_cmds_syntax<br>conftest<br>dump_runtime_surface<br>rig_metrics<br>rizom_headless_probe<br>run_tests<br>scene_import_live_e2e<br>scene_roundtrip_live_e2e<br>shadow_preview_device_check<br>test_anim_utils<br>test_arnold_bridge<br>test_articulated_rig<br>test_audio_clips<br>test_audio_clips_export<br>test_audio_internals<br>test_audio_utils_batch<br>test_audio_utils_compositor<br>test_audio_utils_discovery<br>test_audio_utils_events<br>test_audio_utils_phase2f<br>test_audio_utils_schema<br>test_auto_instancer<br>test_auto_instancer_scene<br>test_base_test<br>test_blender_bridge<br>test_blendshape_animator<br>test_calculator<br>test_cam_utils<br>test_cancel_provider<br>test_channel_box<br>test_channels<br>test_color_id<br>test_components<br>test_compute_plan<br>test_connect_switch_to_constraint<br>test_controls<br>test_core_utils<br>test_create_locator_naming<br>test_curtain<br>test_curve_to_tube<br>test_data_nodes<br>test_devtools<br>test_diagnostics<br>test_display_extras<br>test_display_utils<br>test_duplicate_radial<br>test_dynamic_pipe<br>test_edit_bridge<br>test_edit_tools_duplicate<br>test_edit_tools_geometry<br>test_edit_tools_misc<br>test_edit_utils<br>test_emissive_groups<br>test_env_utils<br>test_export_baselines<br>test_fbx_export_preparers<br>test_fbx_utils<br>test_freeze_restore_locator_rig<br>test_game_shader<br>test_game_shader_config<br>test_group_combine<br>test_hdr_manager<br>test_hierarchy_sync<br>test_hotkey_collisions<br>test_image_to_plane<br>test_image_tracer<br>test_instancing_extras<br>test_key_stash<br>test_light_layer_baker<br>test_light_rig<br>test_light_utils<br>test_lightmap_baker<br>test_macros<br>test_mash<br>test_mat_bake_sets<br>test_mat_manifest<br>test_mat_marmoset_bridge<br>test_mat_snapshot<br>test_mat_updater<br>test_mat_utils<br>test_mat_utils_extended<br>test_mat_utils_resolve_path<br>test_material_records<br>test_material_updater<br>test_material_updater_diagnostics<br>test_material_updater_workflow<br>test_maya_connection<br>test_maya_marking_menu_host<br>test_maya_menu_handler<br>test_maya_ui_handler<br>test_mayapy_package_manager<br>test_msao_fbx_export<br>test_namespace_alias_edge_cases<br>test_namespace_sandbox<br>test_naming<br>test_native_menu_window<br>test_node_utils<br>test_nurbs_utils<br>test_original_mesh_separated<br>test_pivot_transfer_scenarios<br>test_pivot_watcher<br>test_playblast_exporter<br>test_plugins<br>test_preview<br>test_rack_builder<br>test_reference_manager<br>test_remaining<br>test_render_opacity<br>test_render_opacity_export<br>test_render_utils<br>test_rig_graph_build<br>test_rig_graph_extract<br>test_rig_utils<br>test_run_tests<br>test_scale_keys<br>test_scene_audit<br>test_scene_data_sidecar<br>test_scene_exporter<br>test_scene_exporter_dependencies<br>test_scene_import<br>test_script_output<br>test_segment_keys<br>test_selection<br>test_separate_objects<br>test_sequencer<br>test_sequencer_audio_shift<br>test_sequencer_gui<br>test_shader_attribute_map<br>test_shader_converter<br>test_shader_templates<br>test_shadow_preview<br>test_shadow_rig<br>test_shot_export_view<br>test_shot_manifest<br>test_shot_manifest_audio_integration<br>test_shot_manifest_behaviors<br>test_shot_plan<br>test_shot_sequencer_hooks<br>test_shot_transfer<br>test_skinning<br>test_smart_bake<br>test_snap<br>test_stagger_keys<br>test_static_analysis<br>test_style_setter<br>test_substance_bridge<br>test_substance_bridge_scene<br>test_substance_connection<br>test_substance_rpc_plugin<br>test_suite_driver<br>test_texture_baker<br>test_texture_combine<br>test_texture_path_editor<br>test_tube_rig<br>test_ui_utils<br>test_undo_recorder<br>test_units<br>test_unity_bridge<br>test_usd<br>test_uv_budget<br>test_uv_cleanup_actions<br>test_uv_diagnostics<br>test_uv_rizom_bridge<br>test_uv_snapshot<br>test_uv_texture_transfer<br>test_uv_utils<br>test_wheel_rig<br>test_workspace<br>test_workspace_mel<br>test_world_fit_bake<br>test_xform_matrices<br>test_xform_utils<br>tube_rig_export_live_check | 199 |

#### Non-package Code Roots

No additional top-level code roots detected.

### pythontk

- Path: `pythontk`
- Domain: Core utils — DCC-agnostic, zero-dep
- Kind: Python package
- Summary: Python toolkit for DCC pipelines: files, math, geometry, images, video and audio, plus PBR texture, glTF/USD export and shot-timeline engines.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=Yes
- Tracked code surface: 540 files, 369986 total lines, 329910 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| pythontk | `pythontk` | audio_utils<br>core_utils<br>file_utils<br>geo_utils<br>img_utils<br>iter_utils<br>math_utils<br>net_utils<br>str_utils<br>vid_utils | __main__ | 250 |
| test | `test` | - | conftest<br>run_tests<br>test_affix_hardening<br>test_all_packages_namespace_aliases<br>test_animation_record_shape<br>test_app_installer<br>test_app_launcher<br>test_articulated_rig_web<br>test_articulation<br>test_articulation_plan<br>test_assembly_sorter<br>test_atomic_write<br>test_audio_record_shape<br>test_audio_utils<br>test_bake_baseline<br>test_bake_cache<br>test_bridge<br>test_cancel_scope<br>test_class_property<br>test_cli<br>test_color<br>test_conformance<br>test_core<br>test_core_utils<br>test_curtain_drape<br>test_cylinder_seams<br>test_deprecation<br>test_doc_audit<br>test_effect_recipe<br>test_emissive_groups<br>test_execution_monitor<br>test_export_profile<br>test_export_snapshot<br>test_export_verify<br>test_fbx_media<br>test_fbx_writer<br>test_file<br>test_file_collect<br>test_file_dependencies<br>test_file_naming<br>test_file_transfer<br>test_frame_extractor<br>test_fuzzy_matcher<br>test_glb_key_reduction<br>test_glb_pipeline<br>test_glb_skin_weights<br>test_glb_tangents<br>test_gltf2fbx<br>test_handlers<br>test_handoff_manifest<br>test_handoff_record<br>test_handoff_scope<br>test_help_mixin<br>test_hierarchy_baseline<br>test_hierarchy_diff<br>test_hierarchy_indexer<br>test_hierarchy_matching<br>test_hierarchy_path<br>test_hierarchy_utils<br>test_hotkey_utils<br>test_html_presets<br>test_img<br>test_instance_grouping<br>test_instancing_strategy<br>test_iter<br>test_job_queue<br>test_key_curve<br>test_key_stash_core<br>test_ktx2_encoder<br>test_light_layers<br>test_light_predictor<br>test_light_rig_payload<br>test_lightmap_record<br>test_lightmap_record_shape<br>test_logging_mixin<br>test_look_capture<br>test_look_fit<br>test_look_loop<br>test_look_match<br>test_look_measures<br>test_look_session<br>test_look_sheet<br>test_look_target<br>test_main_cli<br>test_manifest_edits<br>test_manifest_export<br>test_manifest_tags<br>test_map_compositor<br>test_map_factory<br>test_map_factory_grouping<br>test_map_optimizer<br>test_map_registry_ambiguity<br>test_map_registry_duplicate_token<br>test_map_registry_register<br>test_map_registry_resolution<br>test_map_registry_resolve<br>test_map_registry_short_alias_boundary<br>test_mask_generator<br>test_mat_report<br>test_material_record<br>test_math<br>test_mesh_convert<br>test_mesh_ops<br>test_metadata<br>test_module_reloader<br>test_module_resolver<br>test_namedtuple_container<br>test_namespace_handler<br>test_naming_convention<br>test_net_utils<br>test_noise<br>test_output_template<br>test_package_manager<br>test_package_requirement<br>test_packaging_metadata<br>test_pending_files<br>test_plate_emitter<br>test_plugin_core<br>test_pointcloud<br>test_polyline<br>test_polyline_transport_frames<br>test_preset_library<br>test_preset_store<br>test_preview_playblast<br>test_preview_server<br>test_preview_viewer_live<br>test_probe_placement<br>test_process_exit<br>test_process_stream<br>test_progression<br>test_py39_compat<br>test_quaternion<br>test_rail_surface<br>test_ramp_keys<br>test_rect_packer<br>test_region_masks<br>test_remote_file<br>test_render_effects_record<br>test_report_doc<br>test_rig_graph<br>test_rpc<br>test_run_tests<br>test_scene_data_sidecar<br>test_scene_exporter<br>test_scene_listing<br>test_scene_notes<br>test_scene_record_rows<br>test_scene_records<br>test_schema_spec<br>test_script_run<br>test_sequence_exporter<br>test_shadow_atlas<br>test_shadow_horizon<br>test_shadow_projection<br>test_shadow_record_shape<br>test_shadow_web<br>test_share_tunnel<br>test_shot_report<br>test_shot_sequencer<br>test_shot_transfer<br>test_shots_core<br>test_shots_manifest_core<br>test_singleton_mixin<br>test_ssh_client<br>test_status_badge<br>test_step_toggle<br>test_str<br>test_surface_snapshot<br>test_symbol_record<br>test_sync_rpc_core<br>test_sync_shadow_shaders<br>test_task_factory<br>test_temp_artifacts<br>test_template_set<br>test_test_sandbox<br>test_text_layout<br>test_texture_factory_non_greedy<br>test_tiled_path<br>test_tooltip_format<br>test_upstream_patch<br>test_usd<br>test_user_config<br>test_uv_budget<br>test_uv_combine<br>test_uv_pack<br>test_uv_transfer<br>test_uv_unwrap<br>test_vid<br>test_weights<br>test_workspace<br>test_workspace_map<br>test_x11 | 193 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| examples | `examples` | 2 | .py (2) |
| typings | `typings` | 1 | .ts (1) |

### server

- Path: `server`
- Domain: Linux infra, zero-trust secrets
- Kind: Operations / scripts
- Summary: Workspace repo aligned with the Linux infra, zero-trust secrets domain.
- Manifests: -
- Root entry scripts: connect.ps1, credential-manager.ps1, diagnose.ps1, manage_db_secrets.py, update-samba-creds.ps1
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 115 files, 18377 total lines, 16441 non-empty lines

#### Package Roots

No top-level Python package roots detected.

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| plugins | `plugins` | 12 | .sh (5)<br>.py (3)<br>.json (2)<br>.html (1)<br>.js (1) |
| scripts | `scripts` | 2 | .py (1)<br>.sh (1) |
| server | `server` | 69 | .sh (29)<br>.py (13)<br>.yml (12)<br>.conf (9)<br>.ps1 (2) |
| test | `test` | 26 | .ps1 (14)<br>.sh (7)<br>.py (5) |

### tentacle

- Path: `tentacle`
- Domain: The product: the launcher, every tool's panel and Slots class
- Kind: Python package
- Summary: Marking menus (pie menus) and tool panels for Maya and Blender: one hotkey-driven Qt interface for modeling, UV, animation and export.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 483 files, 232173 total lines, 212666 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| tentacle | `tentacle` | slots<br>ui | tcl<br>tcl_blender<br>tentacle_installer | 125 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| docs | `docs` | 2 | .json (1)<br>.py (1) |
| test | `test` | 171 | .py (166)<br>.json (5) |

### uitk

- Path: `uitk`
- Domain: Generic Qt UI library; no DCC/app logic
- Kind: Python package
- Summary: Convention-driven Qt UI toolkit for Python (PySide6 via qtpy): Designer .ui files or code-built UIs, signal-slot wiring by widget name, state persistence, custom widgets and presets.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 407 files, 240768 total lines, 208016 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| test | `test` | bench | conftest<br>native_trace<br>run_tests<br>test_affix_option<br>test_attribute_spec<br>test_attribute_window<br>test_attributes<br>test_background_task<br>test_bootstrap<br>test_bridge_slots<br>test_bridge_slots_header<br>test_bridge_template_description<br>test_cancel_manager<br>test_centered_icon<br>test_choice_capture<br>test_choice_option<br>test_collapsable_group<br>test_color_editor<br>test_color_mapping_editor<br>test_color_swatch<br>test_column_config<br>test_combobox<br>test_compare_view<br>test_compile<br>test_compiled_loader<br>test_conftest_qsettings_sandbox<br>test_conftest_teardown_backstop<br>test_context_menu<br>test_convert<br>test_cursor_manager<br>test_designer_plugin<br>test_dismiss_on_move<br>test_double_spin_box<br>test_dynamic_slot_init<br>test_editor_handler<br>test_embedded_menu<br>test_events<br>test_expandable_list<br>test_external_app_handler<br>test_external_app_hub<br>test_field_visibility<br>test_filter_option<br>test_first_paint_stability<br>test_footer<br>test_form_panel<br>test_form_rows<br>test_header<br>test_host_exit_guard<br>test_icon_states<br>test_icons<br>test_image_view<br>test_layout_items<br>test_lazy_subpackage_exports<br>test_line_edit_validator<br>test_list_input_dialog<br>test_main_window_resize<br>test_mainwindow<br>test_mainwindow_menus<br>test_marking_menu<br>test_marking_menu_anchor_pairing<br>test_marking_menu_chord_release<br>test_marking_menu_double_click<br>test_marking_menu_host<br>test_marking_menu_instance_retirement<br>test_marking_menu_integration<br>test_marking_menu_leaf_click<br>test_marking_menu_multiscreen<br>test_marking_menu_position_stability<br>test_marking_menu_preload<br>test_marking_menu_present_order<br>test_marking_menu_pressed_state<br>test_marking_menu_resolver<br>test_marking_menu_shortcuts<br>test_menu<br>test_menu_button<br>test_message_box<br>test_naming_convention_editor<br>test_optionBox<br>test_optional_package_manager<br>test_overflow_indicator<br>test_overlay_clone_positioning<br>test_package_exports<br>test_panel_renames<br>test_persistence_full_chain<br>test_persistence_hardening<br>test_popup_kit<br>test_preset_editor<br>test_preset_manager<br>test_preview_controller<br>test_progress_adapter<br>test_progress_bar<br>test_qt_wait<br>test_recent_values_store<br>test_region<br>test_registry_manager<br>test_reset_gesture<br>test_rich_text<br>test_rich_text_formatter<br>test_row_tags<br>test_run_tests<br>test_runtime_loader<br>test_script_output<br>test_separator<br>test_sequencer<br>test_settings_manager<br>test_shortcut_capture<br>test_shortcut_commands<br>test_shortcut_editor<br>test_shortcut_guard<br>test_shortcuts<br>test_signals<br>test_size_grip<br>test_slider<br>test_spinbox<br>test_state_manager<br>test_style_editor<br>test_style_sheet<br>test_switchboard<br>test_switchboard_browser<br>test_switchboard_editors_mixin<br>test_switchboard_history<br>test_switchboard_namespace<br>test_switchboard_sources<br>test_switchboard_style_mixin<br>test_switchboard_tag_persistence<br>test_switchboard_toggle<br>test_table_actions<br>test_table_formatting<br>test_table_widget<br>test_table_widget_add<br>test_table_widget_autofit<br>test_table_widget_click_forward<br>test_table_widget_edit_as<br>test_table_widget_truncation<br>test_table_widget_wheel<br>test_testing<br>test_text_edit_log_handler<br>test_text_view_box<br>test_tooltip_mixin<br>test_tree_column_config<br>test_tree_formatting<br>test_tree_header_actions<br>test_tree_selection<br>test_ui_handler<br>test_value_bar<br>test_value_manager<br>test_value_option<br>test_visibility_policy<br>test_widget_combobox<br>test_widgets<br>test_window_auto_hide<br>test_window_blur<br>test_window_height<br>test_window_panel<br>test_window_shadow | 161 |
| uitk | `uitk` | bridge<br>designer<br>examples<br>handlers<br>loaders<br>managers<br>switchboard<br>themes<br>widgets | _bootstrap<br>_facade<br>_window_blur<br>_window_shadow<br>compile<br>events<br>testing | 214 |

#### Non-package Code Roots

No additional top-level code roots detected.

### unitytk

- Path: `unitytk`
- Domain: Unity integration
- Kind: Python package
- Summary: A modular Python toolkit for Unity interaction.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 45 files, 32131 total lines, 28383 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| test | `test` | - | base_test<br>conftest<br>run_tests<br>test_articulated_rig_runtime<br>test_asset_delivery<br>test_audio_events_integration<br>test_base_test<br>test_blender_render_effects_e2e<br>test_blender_shadow_plane_integration<br>test_blender_shot_metadata_integration<br>test_bool_to_fade_curve<br>test_clip_name_contract_integration<br>test_controller_runtime_integration<br>test_deploy_templates<br>test_embedded_dependencies_integration<br>test_emissive_groups_integration<br>test_fade_window_preservation<br>test_keyed_visibility<br>test_launcher<br>test_lightmap_metadata_integration<br>test_maya_surface_materials_integration<br>test_multi_section_audio_integration<br>test_package<br>test_render_effects_e2e<br>test_render_opacity_controller<br>test_render_opacity_e2e<br>test_render_opacity_integration<br>test_run_tests<br>test_scene_builder<br>test_shadow_plane_integration<br>test_shadow_plane_runtime_integration<br>test_shared_material_standalone<br>test_shot_metadata_integration<br>test_shots_audio_sidebyside_integration<br>test_standalone_enduser<br>test_temp_projects | 36 |
| unitytk | `unitytk` | templates | asset_delivery<br>launcher<br>scene_builder<br>template_deployer | 4 |

#### Non-package Code Roots

No additional top-level code roots detected.

### www

- Path: `www`
- Domain: Web
- Kind: Operations / scripts
- Summary: Workspace repo aligned with the Web domain.
- Manifests: -
- Root entry scripts: connect.ps1
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 29 files, 61937 total lines, 56744 non-empty lines

#### Package Roots

No top-level Python package roots detected.

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| test | `test` | 4 | .py (3)<br>.sh (1) |
| www | `www` | 23 | .js (18)<br>.html (3)<br>.css (2) |
