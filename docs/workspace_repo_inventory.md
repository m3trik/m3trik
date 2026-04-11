# Workspace Repository Inventory

Generated from `O:/Cloud/Code/_scripts` on 2026-04-08 19:39 UTC.

Scope: direct child git repositories under the workspace root. Line counts cover tracked code/config files and exclude common generated folders such as `.venv`, `build`, `dist`, `output`, `node_modules`, and `__pycache__`.

## Summary

- Repositories: 11
- Tracked code/config files: 940
- Total lines: 405013
- Non-empty lines: 352310

## Repository Index

| Repo | Domain | Kind | Package roots | Code roots | Docs | Tests | Files | Total lines | Non-empty |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| comfyui | AI Custom Nodes | Operations / scripts | - | comfyui<br>config<br>docker<br>test<br>workflows | Yes | Yes | 80 | 15284 | 14520 |
| m3trik | DevOps & Powershell | Operations / scripts | - | projects<br>test<br>update_wheel | Yes | Yes | 35 | 12773 | 10671 |
| map_compositor | Image Processing | Python package | map_compositor | - | Yes | No | 4 | 953 | 854 |
| mayatk | Maya Utils | Python package | mayatk<br>test | - | Yes | Yes | 315 | 165228 | 140831 |
| metashape_workflow | Photogrammetry | Python package | metashape_workflow | - | Yes | No | 6 | 1543 | 1334 |
| pythontk | Core Utils (No Dependencies) | Python package | pythontk<br>test | examples | Yes | Yes | 108 | 39628 | 32990 |
| server | Infrastructure & Config | Operations / scripts | - | scripts<br>server<br>test | Yes | Yes | 54 | 5286 | 4556 |
| tentacle | Desktop App | Python package | tentacle | tentacletk-0.9.34<br>test | Yes | Yes | 171 | 39923 | 38200 |
| uitk | UI Library (Qt) | Python package | test<br>uitk | - | Yes | Yes | 121 | 55810 | 45974 |
| unitytk | - | Python package | test<br>unitytk | - | Yes | Yes | 18 | 7091 | 6003 |
| www | Web | Operations / scripts | - | test<br>www | Yes | Yes | 28 | 61494 | 56377 |

## Repository Details

### comfyui

- Path: `comfyui`
- Domain: AI Custom Nodes
- Kind: Operations / scripts
- Summary: Workspace repo aligned with the AI Custom Nodes domain.
- Manifests: -
- Root entry scripts: connect.ps1, remote_cmd.ps1, update.ps1
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 80 files, 15284 total lines, 14520 non-empty lines

#### Package Roots

No top-level Python package roots detected.

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| comfyui | `comfyui` | 43 | .ps1 (20)<br>.py (14)<br>.sh (8)<br>.psm1 (1) |
| config | `config` | 2 | .yaml (2) |
| docker | `docker` | 1 | .yml (1) |
| test | `test` | 10 | .ps1 (8)<br>.sh (1)<br>.py (1) |
| workflows | `workflows` | 21 | .json (21) |

### m3trik

- Path: `m3trik`
- Domain: DevOps & Powershell
- Kind: Operations / scripts
- Summary: Workspace repo aligned with the DevOps & Powershell domain.
- Manifests: -
- Root entry scripts: common.ps1, Generate-WorkspaceInventory.ps1, push.ps1, push_creds_to_phone.ps1, update_samba_creds.ps1
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 35 files, 12773 total lines, 10671 non-empty lines

#### Package Roots

No top-level Python package roots detected.

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| projects | `projects` | 5 | .py (5) |
| test | `test` | 22 | .py (20)<br>.ps1 (2) |
| update_wheel | `update_wheel` | 4 | .py (2)<br>.ps1 (1)<br>.cmd (1) |

### map_compositor

- Path: `map_compositor`
- Domain: Image Processing
- Kind: Python package
- Summary: Workspace repo aligned with the Image Processing domain.
- Manifests: requirements.txt, setup.py
- Root entry scripts: setup.py
- Support folders: docs=Yes, tests=No, examples=No
- Tracked code surface: 4 files, 953 total lines, 854 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| map_compositor | `map_compositor` | - | _map_compositor | 1 |

#### Non-package Code Roots

No additional top-level code roots detected.

### mayatk

- Path: `mayatk`
- Domain: Maya Utils
- Kind: Python package
- Summary: A comprehensive toolkit for Autodesk Maya providing utilities for modeling, animation, rigging, and UI management.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 315 files, 165228 total lines, 140831 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| mayatk | `mayatk` | anim_utils<br>cam_utils<br>core_utils<br>display_utils<br>edit_utils<br>env_utils<br>light_utils<br>mat_utils<br>node_utils<br>nurbs_utils<br>rig_utils<br>ui_utils<br>uv_utils<br>xform_utils | - | 130 |
| test | `test` | - | _run_hm_tests<br>_run_sequencer_tests<br>base_test<br>conftest<br>run_tests<br>test_anim_utils<br>test_attribute_manager<br>test_audio_events<br>test_auto_instancer<br>test_auto_instancer_scene<br>test_calculator<br>test_cam_utils<br>test_channel_box<br>test_components<br>test_controls<br>test_core_utils<br>test_display_utils<br>test_edit_utils<br>test_env_utils<br>test_game_shader<br>test_game_shader_config<br>test_group_combine<br>test_hierarchy_manager<br>test_image_to_plane<br>test_image_tracer<br>test_light_utils<br>test_marmoset_bridge<br>test_mat_utils<br>test_mat_utils_extended<br>test_material_updater<br>test_material_updater_diagnostics<br>test_maya_connection<br>test_maya_menu_handler<br>test_msao_fbx_export<br>test_namespace_alias_edge_cases<br>test_naming<br>test_node_utils<br>test_nurbs_utils<br>test_original_mesh_separated<br>test_pivot_rot_place<br>test_pivot_transfer_scenarios<br>test_playblast_exporter<br>test_preview<br>test_reference_manager<br>test_render_opacity<br>test_render_opacity_export<br>test_retro_alignment<br>test_rig_utils<br>test_scale_keys<br>test_scene_audit<br>test_scene_exporter<br>test_script_output<br>test_segment_keys<br>test_sequencer<br>test_sequencer_controller<br>test_sequencer_gui<br>test_sequencer_perf<br>test_sequencer_real_scene<br>test_shader_templates<br>test_shot_manifest<br>test_stagger_keys<br>test_telescope_rig<br>test_tentacle_editors<br>test_tube_rig_cleanliness<br>test_ui_utils<br>test_uv_cleanup_actions<br>test_uv_diagnostics<br>test_uv_utils<br>test_wheel_rig<br>test_xform_utils | 105 |

#### Non-package Code Roots

No additional top-level code roots detected.

### metashape_workflow

- Path: `metashape_workflow`
- Domain: Photogrammetry
- Kind: Python package
- Summary: Workspace repo aligned with the Photogrammetry domain.
- Manifests: requirements.txt
- Root entry scripts: -
- Support folders: docs=Yes, tests=No, examples=No
- Tracked code surface: 6 files, 1543 total lines, 1334 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| metashape_workflow | `metashape_workflow` | - | _metashape_workflow<br>extract_frames_from_video<br>metashape_workflow_slots | 3 |

#### Non-package Code Roots

No additional top-level code roots detected.

### pythontk

- Path: `pythontk`
- Domain: Core Utils (No Dependencies)
- Kind: Python package
- Summary: A modular Python toolkit providing utilities for file handling, string processing, iteration, math operations, and more.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=Yes
- Tracked code surface: 108 files, 39628 total lines, 32990 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| pythontk | `pythontk` | audio_utils<br>color_utils<br>core_utils<br>file_utils<br>img_utils<br>iter_utils<br>math_utils<br>net_utils<br>str_utils<br>vid_utils | - | 42 |
| test | `test` | - | conftest<br>manual_test_execution_monitor_integration<br>run_tests<br>test_all_packages_namespace_aliases<br>test_app_launcher<br>test_audio_utils<br>test_class_property<br>test_cli<br>test_color_utils<br>test_core<br>test_execution_monitor<br>test_execution_monitor_comprehensive<br>test_execution_monitor_maya<br>test_execution_monitor_refactor<br>test_file<br>test_fuzzy_matcher<br>test_help_mixin<br>test_hierarchy_diff<br>test_hierarchy_utils<br>test_html_presets<br>test_img<br>test_iter<br>test_logging_mixin<br>test_map_converter<br>test_map_factory<br>test_map_registry_ambiguity<br>test_math<br>test_module_reloader<br>test_module_resolver<br>test_namedtuple_container<br>test_namespace_handler<br>test_net_utils<br>test_package_manager<br>test_progression<br>test_singleton_mixin<br>test_str<br>test_texture_factory_non_greedy<br>test_vid | 45 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| examples | `examples` | 2 | .py (2) |

### server

- Path: `server`
- Domain: Infrastructure & Config
- Kind: Operations / scripts
- Summary: Workspace repo aligned with the Infrastructure & Config domain.
- Manifests: -
- Root entry scripts: connect.ps1, credential-manager.ps1, diagnose.ps1, manage_db_secrets.py
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 54 files, 5286 total lines, 4556 non-empty lines

#### Package Roots

No top-level Python package roots detected.

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| scripts | `scripts` | 1 | .sh (1) |
| server | `server` | 40 | .sh (13)<br>.yml (10)<br>.ps1 (7)<br>.conf (4)<br>.py (3) |
| test | `test` | 8 | .ps1 (8) |

### tentacle

- Path: `tentacle`
- Domain: Desktop App
- Kind: Python package
- Summary: A multi-application marking menu and UI framework for Maya, 3ds Max, and Blender.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 171 files, 39923 total lines, 38200 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| tentacle | `tentacle` | slots<br>ui | tcl_blender<br>tcl_max<br>tcl_maya | 63 |

#### Non-package Code Roots

| Root | Path | Code files | Dominant suffixes |
| --- | --- | ---: | --- |
| tentacletk-0.9.34 | `tentacletk-0.9.34` | 1 | .py (1) |
| test | `test` | 9 | .py (9) |

### uitk

- Path: `uitk`
- Domain: UI Library (Qt)
- Kind: Python package
- Summary: A comprehensive UI toolkit extending Qt Designer workflows with dynamic loading, custom widgets, and automatic signal-slot management.
- Manifests: pyproject.toml
- Root entry scripts: -
- Support folders: docs=Yes, tests=Yes, examples=No
- Tracked code surface: 121 files, 55810 total lines, 45974 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| test | `test` | - | conftest<br>run_tests<br>test_color_swatch<br>test_events<br>test_expandable_list<br>test_file_manager<br>test_footer<br>test_header<br>test_hotkey_editor<br>test_hotkeys<br>test_mainwindow<br>test_marking_menu<br>test_menu<br>test_optionBox<br>test_sequencer<br>test_signals<br>test_spinbox<br>test_style_editor<br>test_style_sheet<br>test_switchboard<br>test_switchboard_sources<br>test_tree_column_config<br>test_widget_combobox<br>test_widgets | 34 |
| uitk | `uitk` | examples<br>widgets | events<br>file_manager<br>switchboard | 74 |

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
- Tracked code surface: 18 files, 7091 total lines, 6003 non-empty lines

#### Package Roots

| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |
| --- | --- | --- | --- | ---: |
| test | `test` | - | base_test<br>run_tests<br>test_audio_events_integration<br>test_audio_trigger_roundtrip<br>test_c130_fcr_integration<br>test_c5m_visibility<br>test_launcher<br>test_render_opacity_controller<br>test_render_opacity_integration<br>test_shared_material_standalone<br>test_standalone_enduser | 11 |
| unitytk | `unitytk` | templates | launcher<br>scene_builder | 2 |

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
| androidtk | `androidtk` | pyproject.toml | androidtk | root_pixel7.py<br>run_tests.py | 16 |
| media_sorter | `media_sorter` | - | - | fix_srts.py | 1 |
| test | `test` | - | - | - | 405 |
