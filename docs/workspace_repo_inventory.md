# Workspace Repository Inventory

Generated from `O:/Cloud/Code/_scripts` on 2026-05-18 02:50 UTC.

Scope: direct child git repositories under the workspace root. Line counts cover tracked code/config files and exclude common generated folders such as `.venv`, `build`, `dist`, `output`, `node_modules`, and `__pycache__`.

## Summary

- Repositories: 12
- Tracked code/config files: 1105
- Total lines: 504090
- Non-empty lines: 443653

## Repository Index

| Repo | Domain | Kind | Package roots | Code roots | Docs | Tests | Files | Total lines | Non-empty |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| androidtk | - | Python package | androidtk | examples<br>test | Yes | Yes | 15 | 746 | 605 |
| comfyui | - | Operations / scripts | - | comfyui<br>config<br>patches<br>scripts<br>test<br>workflows | Yes | Yes | 87 | 17001 | 15994 |
| m3trik | - | Operations / scripts | - | docs<br>scripts<br>test | Yes | Yes | 9 | 4485 | 3975 |
| map_compositor | - | Python package | map_compositor | test | Yes | Yes | 7 | 2250 | 1929 |
| mayatk | - | Python package | mayatk<br>test | - | Yes | Yes | 367 | 208243 | 180681 |
| metashape_workflow | - | Python package | metashape_workflow | test | Yes | Yes | 9 | 2055 | 1771 |
| pythontk | - | Python package | pythontk<br>test | examples | Yes | Yes | 117 | 50960 | 43619 |
| server | - | Operations / scripts | - | scripts<br>server<br>test | Yes | Yes | 59 | 6533 | 5606 |
| tentacle | - | Python package | tentacle | tentacletk-0.9.34<br>test | Yes | Yes | 219 | 54940 | 51658 |
| uitk | - | Python package | test<br>uitk | - | Yes | Yes | 167 | 87565 | 74813 |
| unitytk | - | Python package | test<br>unitytk | - | Yes | Yes | 21 | 7818 | 6625 |
| www | - | Operations / scripts | - | test<br>www | Yes | Yes | 28 | 61494 | 56377 |

## Repository Details

### androidtk

- Path: `androidtk`
- Domain: Unclassified
- Kind: Python package
- Summary: A Python toolkit for Android device management and modification.
- Manifests: pyproject.toml
- Root entry scripts: push_creds_to_phone.ps1, root_pixel7.py, run_tests.py
- Support folders: docs=Yes, tests=Yes, examples=Yes
- Tracked code surface: 15 files, 746 total lines, 605 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| androidtk | `androidtk` | core<br>devices<br>utils | - | 5 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| examples | `examples` | 1 | .py (1) |
| test | `test` | 1 | .py (1) |

### comfyui

- Path: `comfyui`
- Domain: Unclassified
- Kind: Operations / scripts
- Summary: ComfyUI environment for m3trik-desktop -- single venv, uv-resolved, lockfile-pinned.
- Manifests: pyproject.toml
- Root entry scripts: connect.ps1, pull_outputs.ps1, remote_cmd.ps1, update.ps1
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 87 files, 17001 total lines, 15994 non-empty lines

#### Package Roots

No top-level Python package roots detected.

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| comfyui | `comfyui` | 39 | .ps1 (19)<br>.py (15)<br>.sh (4)<br>.psm1 (1) |
| config | `config` | 1 | .yaml (1) |
| patches | `patches` | 1 | .py (1) |
| scripts | `scripts` | 9 | .py (5)<br>.ps1 (4) |
| test | `test` | 10 | .ps1 (8)<br>.sh (1)<br>.py (1) |
| workflows | `workflows` | 22 | .json (22) |

### m3trik

- Path: `m3trik`
- Domain: Unclassified
- Kind: Operations / scripts
- Summary: Workspace repository.
- Manifests: -
- Root entry scripts: common.ps1, push.ps1
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 9 files, 4485 total lines, 3975 non-empty lines

#### Package Roots

No top-level Python package roots detected.

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| docs | `docs` | 1 | .json (1) |
| scripts | `scripts` | 5 | .py (3)<br>.ps1 (2) |
| test | `test` | 1 | .py (1) |

### map_compositor

- Path: `map_compositor`
- Domain: Unclassified
- Kind: Python package
- Summary: Workspace repository.
- Manifests: requirements.txt, setup.py
- Root entry scripts: setup.py
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 7 files, 2250 total lines, 1929 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| map_compositor | `map_compositor` | - | _map_compositor<br>compositor<br>slots | 3 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| test | `test` | 1 | .py (1) |

### mayatk

- Path: `mayatk`
- Domain: Unclassified
- Kind: Python package
- Summary: A comprehensive toolkit for Autodesk Maya providing utilities for modeling, animation, rigging, and UI management.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 367 files, 208243 total lines, 180681 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| mayatk | `mayatk` | anim_utils<br>audio_utils<br>cam_utils<br>core_utils<br>display_utils<br>edit_utils<br>env_utils<br>light_utils<br>mat_utils<br>node_utils<br>nurbs_utils<br>rig_utils<br>ui_utils<br>uv_utils<br>xform_utils | - | 150 |
| test | `test` | - | _run_hm_tests<br>base_test<br>check_cmds_naming<br>check_cmds_syntax<br>conftest<br>run_tests<br>test_anim_utils<br>test_audio_clips<br>test_audio_internals<br>test_audio_utils_batch<br>test_audio_utils_compositor<br>test_audio_utils_discovery<br>test_audio_utils_events<br>test_audio_utils_phase2f<br>test_audio_utils_schema<br>test_auto_instancer<br>test_auto_instancer_scene<br>test_blendshape_animator<br>test_calculator<br>test_cam_utils<br>test_channel_box<br>test_channels<br>test_components<br>test_compute_plan<br>test_controls<br>test_core_utils<br>test_data_nodes<br>test_devtools<br>test_diagnostics<br>test_display_extras<br>test_display_utils<br>test_dynamic_pipe<br>test_edit_tools_duplicate<br>test_edit_tools_geometry<br>test_edit_tools_misc<br>test_edit_utils<br>test_env_utils<br>test_event_triggers<br>test_fbx_utils<br>test_freeze_restore_locator_rig<br>test_game_shader<br>test_game_shader_config<br>test_group_combine<br>test_hdr_manager<br>test_hierarchy_manager<br>test_hierarchy_sidecar<br>test_hotkey_collisions<br>test_image_to_plane<br>test_image_tracer<br>test_instancing_extras<br>test_light_utils<br>test_macros<br>test_mash<br>test_mat_manifest<br>test_mat_marmoset_bridge<br>test_mat_snapshot<br>test_mat_transfer<br>test_mat_utils<br>test_mat_utils_extended<br>test_mat_utils_resolve_path<br>test_material_updater<br>test_material_updater_diagnostics<br>test_material_updater_workflow<br>test_maya_connection<br>test_maya_menu_handler<br>test_mayapy_package_manager<br>test_msao_fbx_export<br>test_namespace_alias_edge_cases<br>test_namespace_sandbox<br>test_naming<br>test_native_menu_window<br>test_node_utils<br>test_nurbs_utils<br>test_original_mesh_separated<br>test_pivot_rot_place<br>test_pivot_transfer_scenarios<br>test_pivot_watcher<br>test_playblast_exporter<br>test_preview<br>test_reference_manager<br>test_remaining<br>test_render_opacity<br>test_render_opacity_export<br>test_rig_utils<br>test_scale_keys<br>test_scene_audit<br>test_scene_exporter<br>test_script_output<br>test_segment_keys<br>test_separate_objects<br>test_sequencer<br>test_sequencer_audio_shift<br>test_sequencer_gui<br>test_shader_attribute_map<br>test_shader_remapper<br>test_shader_templates<br>test_shot_manifest<br>test_shot_manifest_audio_integration<br>test_shot_plan<br>test_smart_bake<br>test_stagger_keys<br>test_static_analysis<br>test_tentacle_editors<br>test_texture_path_editor<br>test_tube_rig_cleanliness<br>test_ui_utils<br>test_unbake_keys<br>test_uv_cleanup_actions<br>test_uv_diagnostics<br>test_uv_rizom_bridge<br>test_uv_snapshot<br>test_uv_utils<br>test_wheel_rig<br>test_workspace<br>test_xform_matrices<br>test_xform_utils | 126 |

#### Non-package Code Roots

No additional top-level code roots detected.

### metashape_workflow

- Path: `metashape_workflow`
- Domain: Unclassified
- Kind: Python package
- Summary: Automate Agisoft Metashape photogrammetry workflows with a Qt GUI.
- Manifests: pyproject.toml, requirements.txt
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 9 files, 2055 total lines, 1771 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| metashape_workflow | `metashape_workflow` | - | _metashape_workflow<br>extract_frames_from_video<br>metashape_workflow_slots<br>metashape_workflow_ui | 4 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| test | `test` | 1 | .py (1) |

### pythontk

- Path: `pythontk`
- Domain: Unclassified
- Kind: Python package
- Summary: A modular Python toolkit providing utilities for file handling, string processing, iteration, math operations, and more.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=Yes
- Tracked code surface: 117 files, 50960 total lines, 43619 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| pythontk | `pythontk` | audio_utils<br>color_utils<br>core_utils<br>file_utils<br>img_utils<br>iter_utils<br>math_utils<br>net_utils<br>str_utils<br>vid_utils | - | 45 |
| test | `test` | - | conftest<br>manual_test_execution_monitor_integration<br>run_tests<br>temp_smoke_img_utils<br>test_affix_hardening<br>test_all_packages_namespace_aliases<br>test_app_installer<br>test_app_launcher<br>test_atomic_write<br>test_audio_utils<br>test_class_property<br>test_cli<br>test_color_utils<br>test_core<br>test_execution_monitor<br>test_execution_monitor_comprehensive<br>test_execution_monitor_maya<br>test_execution_monitor_refactor<br>test_file<br>test_file_transfer<br>test_fuzzy_matcher<br>test_help_mixin<br>test_hierarchy_diff<br>test_hierarchy_utils<br>test_html_presets<br>test_img<br>test_iter<br>test_logging_mixin<br>test_map_converter<br>test_map_factory<br>test_map_factory_grouping<br>test_map_registry_ambiguity<br>test_map_registry_resolution<br>test_map_registry_resolve<br>test_math<br>test_mesh_convert<br>test_module_reloader<br>test_module_resolver<br>test_namedtuple_container<br>test_namespace_handler<br>test_net_utils<br>test_package_manager<br>test_progression<br>test_singleton_mixin<br>test_str<br>test_texture_factory_non_greedy<br>test_vid | 48 |

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
- Root entry scripts: connect.ps1, credential-manager.ps1, diagnose.ps1, manage_db_secrets.py
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 59 files, 6533 total lines, 5606 non-empty lines

#### Package Roots

No top-level Python package roots detected.

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| scripts | `scripts` | 1 | .sh (1) |
| server | `server` | 45 | .sh (13)<br>.yml (10)<br>.py (8)<br>.ps1 (7)<br>.conf (4) |
| test | `test` | 8 | .ps1 (8) |

### tentacle

- Path: `tentacle`
- Domain: Unclassified
- Kind: Python package
- Summary: A multi-application marking menu and UI framework for Maya, 3ds Max, and Blender.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 219 files, 54940 total lines, 51658 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| tentacle | `tentacle` | slots<br>ui | tcl_blender<br>tcl_max<br>tcl_maya | 64 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| tentacletk-0.9.34 | `tentacletk-0.9.34` | 1 | .py (1) |
| test | `test` | 55 | .py (50)<br>.json (5) |

### uitk

- Path: `uitk`
- Domain: Unclassified
- Kind: Python package
- Summary: A comprehensive UI toolkit extending Qt Designer workflows with dynamic loading, custom widgets, and automatic signal-slot management.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 167 files, 87565 total lines, 74813 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| test | `test` | bench | conftest<br>run_tests<br>test_color_mapping_editor<br>test_color_swatch<br>test_combobox<br>test_compile<br>test_compiled_loader<br>test_dismiss_on_move<br>test_double_spin_box<br>test_dynamic_slot_init<br>test_events<br>test_expandable_list<br>test_external_tool_handler<br>test_file_manager<br>test_footer<br>test_header<br>test_hotkey_editor<br>test_hotkeys<br>test_line_edit_validator<br>test_main_window_resize<br>test_mainwindow<br>test_marking_menu<br>test_marking_menu_integration<br>test_marking_menu_resolver<br>test_menu<br>test_optionBox<br>test_runtime_loader<br>test_sequencer<br>test_signals<br>test_spinbox<br>test_style_editor<br>test_style_sheet<br>test_switchboard<br>test_switchboard_browser<br>test_switchboard_editors_mixin<br>test_switchboard_sources<br>test_switchboard_style_mixin<br>test_switchboard_tag_persistence<br>test_text_edit_log_handler<br>test_tree_column_config<br>test_tree_header_actions<br>test_tree_selection<br>test_widget_combobox<br>test_widgets | 49 |
| uitk | `uitk` | examples<br>loaders<br>switchboard<br>widgets | compile<br>events<br>file_manager | 100 |

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
- Tracked code surface: 21 files, 7818 total lines, 6625 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| test | `test` | - | base_test<br>run_tests<br>test_audio_events_integration<br>test_audio_trigger_roundtrip<br>test_bool_to_fade_curve<br>test_c130_fcr_integration<br>test_c5m_visibility<br>test_fade_window_preservation<br>test_launcher<br>test_render_opacity_controller<br>test_render_opacity_integration<br>test_shared_material_standalone<br>test_standalone_enduser | 13 |
| unitytk | `unitytk` | templates | launcher<br>scene_builder | 2 |

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
- Tracked code surface: 28 files, 61494 total lines, 56377 non-empty lines

#### Package Roots

No top-level Python package roots detected.

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| test | `test` | 3 | .py (2)<br>.sh (1) |
| www | `www` | 23 | .js (18)<br>.html (3)<br>.css (2) |

## Non-repository Code Folders

These top-level folders contain code or manifests but are not standalone git repositories.

| Folder | Path | Manifests | Package roots | Root scripts | Code files |
| --- | --- | --- | --- | --- | ---: |
| substancetk | `substancetk` | pyproject.toml | substancetk<br>test | - | 28 |
