# Workspace Repository Inventory

Generated from `O:/Cloud/Code/_scripts` on 2026-09-15 20:24 UTC.

Scope: direct child git repositories under the workspace root. Line counts cover tracked code/config files and exclude common generated folders such as `.venv`, `build`, `dist`, `output`, `node_modules`, and `__pycache__`.

## Summary

- Repositories: 12
- Tracked code/config files: 2349
- Total lines: 1291600
- Non-empty lines: 1147607

## Repository Index

| Repo | Domain | Kind | Package roots | Code roots | Docs | Tests | Files | Total lines | Non-empty |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| androidtk | - | Python package | androidtk | examples<br>test | Yes | Yes | 21 | 1814 | 1492 |
| blendertk | - | Python package | blendertk | test | Yes | Yes | 413 | 214545 | 195998 |
| comfyui | - | Operations / scripts | - | comfyui<br>config<br>examples<br>patches<br>scripts<br>test<br>workflows | Yes | Yes | 99 | 18609 | 17381 |
| extapps | - | Python package | extapps | test | Yes | Yes | 157 | 42787 | 38020 |
| m3trik | - | Operations / scripts | - | docs<br>scripts<br>test | Yes | Yes | 36 | 17651 | 15652 |
| mayatk | - | Python package | mayatk<br>test | - | Yes | Yes | 532 | 412303 | 362598 |
| pythontk | - | Python package | pythontk<br>test | examples | Yes | Yes | 289 | 186924 | 164576 |
| server | - | Operations / scripts | - | scripts<br>server<br>test | Yes | Yes | 98 | 15119 | 13402 |
| tentacle | - | Python package | tentacle | docs<br>test | Yes | Yes | 351 | 117928 | 107713 |
| uitk | - | Python package | test<br>uitk | - | Yes | Yes | 287 | 184863 | 159296 |
| unitytk | - | Python package | test<br>unitytk | - | Yes | Yes | 37 | 17120 | 14735 |
| www | - | Operations / scripts | - | test<br>www | Yes | Yes | 29 | 61937 | 56744 |

## Repository Details

### androidtk

- Path: `androidtk`
- Domain: Unclassified
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
- Domain: Unclassified
- Kind: Python package
- Summary: A toolkit for Blender mirroring the mayatk public API, backing the tentacle Blender slots.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 413 files, 214545 total lines, 195998 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| blendertk | `blendertk` | anim_utils<br>audio_utils<br>cam_utils<br>core_utils<br>display_utils<br>edit_utils<br>env_utils<br>light_utils<br>mat_utils<br>node_utils<br>nurbs_utils<br>rig_utils<br>ui_utils<br>uv_utils<br>xform_utils | - | 184 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| test | `test` | 117 | .py (116)<br>.ps1 (1) |

### comfyui

- Path: `comfyui`
- Domain: Unclassified
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
- Domain: Unclassified
- Kind: Python package
- Summary: Standalone Switchboard panels for content-pipeline workflows (map compositing, photogrammetry, Substance Painter automation, texture conversion, mesh conversion).
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 157 files, 42787 total lines, 38020 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| extapps | `extapps` | marmoset_workflow<br>mesh_convert<br>photogrammetry<br>substance_workflow<br>texture_maps<br>unity_workflow<br>webxr_preview | - | 71 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| test | `test` | 45 | .py (45) |

### m3trik

- Path: `m3trik`
- Domain: Unclassified
- Kind: Operations / scripts
- Summary: Tech-art tooling for game-art and DCC pipelines — one ecosystem, built in layers:
- Manifests: -
- Root entry scripts: common.ps1, package-manager.bat, pm_doctor.py, push.ps1
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 36 files, 17651 total lines, 15652 non-empty lines

#### Package Roots

No top-level Python package roots detected.

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| docs | `docs` | 1 | .json (1) |
| scripts | `scripts` | 19 | .py (16)<br>.ps1 (3) |
| test | `test` | 12 | .py (12) |

### mayatk

- Path: `mayatk`
- Domain: Unclassified
- Kind: Python package
- Summary: A comprehensive toolkit for Autodesk Maya providing utilities for modeling, animation, rigging, and UI management.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 532 files, 412303 total lines, 362598 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| mayatk | `mayatk` | anim_utils<br>audio_utils<br>cam_utils<br>core_utils<br>display_utils<br>edit_utils<br>env_utils<br>light_utils<br>mat_utils<br>node_utils<br>nurbs_utils<br>render_utils<br>rig_utils<br>ui_utils<br>uv_utils<br>xform_utils | - | 220 |
| test | `test` | - | _run_hm_tests<br>_suite_driver<br>base_test<br>check_cmds_naming<br>check_cmds_syntax<br>conftest<br>dump_runtime_surface<br>rig_metrics<br>rizom_headless_probe<br>run_tests<br>scene_import_live_e2e<br>shadow_preview_device_check<br>shell_xform_ui_check<br>test_anim_utils<br>test_arnold_bridge<br>test_audio_clips<br>test_audio_clips_export<br>test_audio_internals<br>test_audio_utils_batch<br>test_audio_utils_compositor<br>test_audio_utils_discovery<br>test_audio_utils_events<br>test_audio_utils_phase2f<br>test_audio_utils_schema<br>test_auto_instancer<br>test_auto_instancer_scene<br>test_blender_bridge<br>test_blendshape_animator<br>test_calculator<br>test_cam_utils<br>test_cancel_provider<br>test_channel_box<br>test_channels<br>test_color_id<br>test_components<br>test_compute_plan<br>test_connect_switch_to_constraint<br>test_controls<br>test_core_utils<br>test_create_locator_naming<br>test_curtain<br>test_curtain_drape<br>test_curve_to_tube<br>test_data_nodes<br>test_devtools<br>test_diagnostics<br>test_display_extras<br>test_display_utils<br>test_duplicate_radial<br>test_dynamic_pipe<br>test_edit_bridge<br>test_edit_tools_duplicate<br>test_edit_tools_geometry<br>test_edit_tools_misc<br>test_edit_utils<br>test_emissive_groups<br>test_emissive_groups_panel<br>test_env_utils<br>test_fbx_export_preparers<br>test_fbx_utils<br>test_freeze_restore_locator_rig<br>test_game_shader<br>test_game_shader_config<br>test_group_combine<br>test_hdr_manager<br>test_hierarchy_sync<br>test_hotkey_collisions<br>test_image_to_plane<br>test_image_tracer<br>test_instancing_extras<br>test_key_stash<br>test_key_stash_panel<br>test_light_utils<br>test_lightmap_baker<br>test_macros<br>test_mash<br>test_mat_bake_sets<br>test_mat_manifest<br>test_mat_marmoset_bridge<br>test_mat_snapshot<br>test_mat_updater<br>test_mat_utils<br>test_mat_utils_extended<br>test_mat_utils_resolve_path<br>test_material_updater<br>test_material_updater_diagnostics<br>test_material_updater_workflow<br>test_maya_connection<br>test_maya_menu_handler<br>test_maya_ui_handler<br>test_mayapy_package_manager<br>test_msao_fbx_export<br>test_namespace_alias_edge_cases<br>test_namespace_sandbox<br>test_naming<br>test_native_menu_window<br>test_node_utils<br>test_nurbs_utils<br>test_original_mesh_separated<br>test_pivot_transfer_scenarios<br>test_pivot_watcher<br>test_playblast_exporter<br>test_preview<br>test_rack_builder<br>test_reference_manager<br>test_remaining<br>test_render_opacity<br>test_render_opacity_export<br>test_render_utils<br>test_rig_utils<br>test_run_tests<br>test_scale_keys<br>test_scene_audit<br>test_scene_data_sidecar<br>test_scene_exporter<br>test_scene_import<br>test_scene_state<br>test_script_output<br>test_segment_keys<br>test_separate_objects<br>test_sequencer<br>test_sequencer_audio_shift<br>test_sequencer_gui<br>test_shader_attribute_map<br>test_shader_converter<br>test_shader_templates<br>test_shadow_preview<br>test_shadow_rig<br>test_shadow_rig_panel<br>test_shell_xform<br>test_shot_export_view<br>test_shot_manifest<br>test_shot_manifest_audio_integration<br>test_shot_manifest_behaviors<br>test_shot_manifest_csv_load<br>test_shot_manifest_mapping<br>test_shot_plan<br>test_shots_panel<br>test_skinning<br>test_smart_bake<br>test_smart_bake_slots<br>test_snap<br>test_stagger_keys<br>test_static_analysis<br>test_style_setter<br>test_substance_bridge<br>test_substance_bridge_scene<br>test_substance_connection<br>test_substance_rpc_plugin<br>test_suite_driver<br>test_tentacle_editors<br>test_texture_baker<br>test_texture_path_editor<br>test_tube_rig<br>test_ui_utils<br>test_unity_bridge<br>test_usd<br>test_uv_budget<br>test_uv_cleanup_actions<br>test_uv_diagnostics<br>test_uv_rizom_bridge<br>test_uv_snapshot<br>test_uv_texture_transfer<br>test_uv_utils<br>test_wheel_rig<br>test_workspace<br>test_workspace_mel<br>test_xform_matrices<br>test_xform_utils<br>tube_rig_export_live_check<br>unity_bridge_ui_check | 189 |

#### Non-package Code Roots

No additional top-level code roots detected.

### pythontk

- Path: `pythontk`
- Domain: Unclassified
- Kind: Python package
- Summary: Foundation layer of a DCC-tooling ecosystem: composable primitives for files, strings, iteration, math, geometry, images, video, audio and networking, the host-agnostic engines built on them (PBR texture conversion, shot timeline, instancing), plus shared class mixins and package infrastructure.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=Yes
- Tracked code surface: 289 files, 186924 total lines, 164576 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| pythontk | `pythontk` | audio_utils<br>core_utils<br>file_utils<br>geo_utils<br>img_utils<br>iter_utils<br>math_utils<br>net_utils<br>str_utils<br>vid_utils | __main__ | 124 |
| test | `test` | - | conftest<br>run_tests<br>test_affix_hardening<br>test_all_packages_namespace_aliases<br>test_app_installer<br>test_app_launcher<br>test_assembly_sorter<br>test_atomic_write<br>test_audio_utils<br>test_bridge<br>test_cancel_scope<br>test_class_property<br>test_cli<br>test_color<br>test_core<br>test_core_utils<br>test_doc_audit<br>test_execution_monitor<br>test_export_profile<br>test_export_verify<br>test_fbx_media<br>test_file<br>test_file_naming<br>test_file_transfer<br>test_frame_extractor<br>test_fuzzy_matcher<br>test_glb_key_reduction<br>test_glb_pipeline<br>test_handlers<br>test_help_mixin<br>test_hierarchy_diff<br>test_hierarchy_indexer<br>test_hierarchy_matching<br>test_hierarchy_path<br>test_hierarchy_utils<br>test_hotkey_utils<br>test_html_presets<br>test_img<br>test_iter<br>test_key_stash_core<br>test_ktx2_encoder<br>test_logging_mixin<br>test_main_cli<br>test_map_compositor<br>test_map_factory<br>test_map_factory_grouping<br>test_map_optimizer<br>test_map_registry_ambiguity<br>test_map_registry_duplicate_token<br>test_map_registry_register<br>test_map_registry_resolution<br>test_map_registry_resolve<br>test_map_registry_short_alias_boundary<br>test_mask_generator<br>test_mat_report<br>test_math<br>test_mesh_convert<br>test_mesh_ops<br>test_metadata<br>test_module_reloader<br>test_module_resolver<br>test_namedtuple_container<br>test_namespace_handler<br>test_naming_convention<br>test_net_utils<br>test_noise<br>test_output_template<br>test_package_manager<br>test_packaging_metadata<br>test_plate_emitter<br>test_plugin_core<br>test_pointcloud<br>test_polyline<br>test_polyline_transport_frames<br>test_preset_store<br>test_preview_playblast<br>test_preview_server<br>test_preview_viewer_live<br>test_process_exit<br>test_process_stream<br>test_progression<br>test_py39_compat<br>test_rail_surface<br>test_ramp_keys<br>test_region_masks<br>test_remote_file<br>test_rpc<br>test_run_tests<br>test_schema_spec<br>test_script_run<br>test_sequence_exporter<br>test_shadow_atlas<br>test_shadow_horizon<br>test_shadow_projection<br>test_shadow_web<br>test_shots_core<br>test_shots_manifest_core<br>test_singleton_mixin<br>test_ssh_client<br>test_status_badge<br>test_step_toggle<br>test_str<br>test_surface_snapshot<br>test_symbol_record<br>test_sync_rpc_core<br>test_sync_shadow_shaders<br>test_task_factory<br>test_temp_artifacts<br>test_template_set<br>test_test_sandbox<br>test_texture_factory_non_greedy<br>test_usd<br>test_user_config<br>test_uv_budget<br>test_uv_pack<br>test_uv_transfer<br>test_uv_unwrap<br>test_vid<br>test_weights<br>test_workspace | 121 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| examples | `examples` | 2 | .py (2) |

### server

- Path: `server`
- Domain: Unclassified
- Kind: Operations / scripts
- Summary: Workspace repository.
- Manifests: -
- Root entry scripts: connect.ps1, credential-manager.ps1, diagnose.ps1, manage_db_secrets.py, update-samba-creds.ps1
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 98 files, 15119 total lines, 13402 non-empty lines

#### Package Roots

No top-level Python package roots detected.

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| scripts | `scripts` | 2 | .py (1)<br>.sh (1) |
| server | `server` | 66 | .sh (28)<br>.py (13)<br>.yml (11)<br>.conf (8)<br>.ps1 (2) |
| test | `test` | 24 | .ps1 (14)<br>.sh (5)<br>.py (5) |

### tentacle

- Path: `tentacle`
- Domain: Unclassified
- Kind: Python package
- Summary: A multi-application marking menu and UI framework for Maya, 3ds Max, and Blender.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 351 files, 117928 total lines, 107713 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| tentacle | `tentacle` | slots<br>ui | tcl<br>tcl_blender<br>tcl_max<br>tcl_maya<br>tentacle_installer | 108 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| docs | `docs` | 2 | .json (1)<br>.py (1) |
| test | `test` | 116 | .py (111)<br>.json (5) |

### uitk

- Path: `uitk`
- Domain: Unclassified
- Kind: Python package
- Summary: A comprehensive UI toolkit extending Qt Designer workflows with dynamic loading, custom widgets, and automatic signal-slot management.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 287 files, 184863 total lines, 159296 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| test | `test` | bench | conftest<br>native_trace<br>run_tests<br>test_affix_option<br>test_attribute_window<br>test_attributes<br>test_bridge_slots<br>test_bridge_slots_header<br>test_bridge_template_description<br>test_cancel_manager<br>test_centered_icon<br>test_choice_capture<br>test_collapsable_group<br>test_color_mapping_editor<br>test_color_swatch<br>test_combobox<br>test_compile<br>test_compiled_loader<br>test_conftest_qsettings_sandbox<br>test_conftest_teardown_backstop<br>test_context_menu<br>test_convert<br>test_cursor_manager<br>test_designer_plugin<br>test_dismiss_on_move<br>test_double_spin_box<br>test_dynamic_slot_init<br>test_embedded_menu<br>test_events<br>test_expandable_list<br>test_external_app_handler<br>test_filter_option<br>test_first_paint_stability<br>test_footer<br>test_form_panel<br>test_header<br>test_icon_states<br>test_icons<br>test_lazy_subpackage_exports<br>test_line_edit_validator<br>test_list_input_dialog<br>test_main_window_resize<br>test_mainwindow<br>test_mainwindow_menus<br>test_marking_menu<br>test_marking_menu_anchor_pairing<br>test_marking_menu_chord_release<br>test_marking_menu_double_click<br>test_marking_menu_instance_retirement<br>test_marking_menu_integration<br>test_marking_menu_leaf_click<br>test_marking_menu_multiscreen<br>test_marking_menu_position_stability<br>test_marking_menu_preload<br>test_marking_menu_present_order<br>test_marking_menu_pressed_state<br>test_marking_menu_resolver<br>test_marking_menu_shortcuts<br>test_menu<br>test_menu_button<br>test_message_box<br>test_optionBox<br>test_overlay_clone_positioning<br>test_package_exports<br>test_persistence_full_chain<br>test_persistence_hardening<br>test_preset_manager<br>test_progress_adapter<br>test_progress_bar<br>test_qt_wait<br>test_recent_values_store<br>test_region<br>test_registry_manager<br>test_rich_text<br>test_rich_text_formatter<br>test_run_tests<br>test_runtime_loader<br>test_script_output<br>test_separator<br>test_sequencer<br>test_settings_manager<br>test_shortcut_capture<br>test_shortcut_commands<br>test_shortcut_editor<br>test_shortcut_guard<br>test_shortcuts<br>test_signals<br>test_size_grip<br>test_slider<br>test_spinbox<br>test_state_manager<br>test_style_editor<br>test_style_sheet<br>test_switchboard<br>test_switchboard_browser<br>test_switchboard_editors_mixin<br>test_switchboard_history<br>test_switchboard_namespace<br>test_switchboard_sources<br>test_switchboard_style_mixin<br>test_switchboard_tag_persistence<br>test_switchboard_toggle<br>test_table_actions<br>test_table_widget_add<br>test_table_widget_autofit<br>test_table_widget_click_forward<br>test_table_widget_truncation<br>test_table_widget_wheel<br>test_text_edit_log_handler<br>test_tooltip_mixin<br>test_tree_column_config<br>test_tree_formatting<br>test_tree_header_actions<br>test_tree_selection<br>test_ui_handler<br>test_value_manager<br>test_value_option<br>test_visibility_policy<br>test_widget_combobox<br>test_widgets<br>test_window_panel | 126 |
| uitk | `uitk` | bridge<br>designer<br>examples<br>handlers<br>loaders<br>managers<br>switchboard<br>themes<br>widgets | _bootstrap<br>compile<br>events<br>file_manager<br>testing | 133 |

#### Non-package Code Roots

No additional top-level code roots detected.

### unitytk

- Path: `unitytk`
- Domain: Unclassified
- Kind: Python package
- Summary: A modular Python toolkit for Unity interaction.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 37 files, 17120 total lines, 14735 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| test | `test` | - | base_test<br>run_tests<br>test_asset_delivery<br>test_audio_events_integration<br>test_base_test<br>test_bool_to_fade_curve<br>test_clip_name_contract_integration<br>test_controller_runtime_integration<br>test_deploy_templates<br>test_emissive_groups_integration<br>test_fade_window_preservation<br>test_keyed_visibility<br>test_launcher<br>test_lightmap_metadata_integration<br>test_multi_section_audio_integration<br>test_render_effects_e2e<br>test_render_opacity_controller<br>test_render_opacity_e2e<br>test_render_opacity_integration<br>test_run_tests<br>test_scene_builder<br>test_shadow_plane_integration<br>test_shadow_plane_runtime_integration<br>test_shared_material_standalone<br>test_shot_metadata_integration<br>test_shots_audio_sidebyside_integration<br>test_standalone_enduser<br>test_temp_projects | 28 |
| unitytk | `unitytk` | templates | asset_delivery<br>launcher<br>scene_builder<br>template_deployer | 4 |

#### Non-package Code Roots

No additional top-level code roots detected.

### www

- Path: `www`
- Domain: Unclassified
- Kind: Operations / scripts
- Summary: Workspace repository.
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
