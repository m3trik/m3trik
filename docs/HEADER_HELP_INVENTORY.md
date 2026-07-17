# Header Help Button — Migration Inventory

Documents the rollout of the new `Header.set_help_text(...)` API across the
ecosystem (replacing the old "Instructions" pushbutton buried in the header
menu of every tool).

## API

```python
def header_init(self, widget):
    widget.set_help_text(
        "Tool Name — short summary.\n\n"
        "• Bullet 1\n• Bullet 2\n• ..."
    )
```

The help button (`?` icon) is auto-inserted at the leftmost slot of the
header. Hovering shows the tooltip; clicking pops the tooltip up at the
button anchor via `QToolTip.showText`. The text accepts the same rich-text
HTML that `setToolTip` accepts (build with
`uitk.widgets.mixins.tooltip_mixin.fmt`).

Source: [`uitk/uitk/widgets/header.py`](../../uitk/uitk/widgets/header.py)
(see `set_help_text`, `help_text`, `show_help`, and the `help` entry in
`button_definitions`).

## Migrated (39 files)

All previously used the old pattern:

```python
widget.menu.add("Separator", setTitle="About")
widget.menu.add(
    "QPushButton",
    setText="Instructions",
    setObjectName="btn_instructions",
    setToolTip="...",
)
```

| Package | File |
|:---|:---|
| extapps | [`photogrammetry/_panel_slots.py`](../../extapps/extapps/photogrammetry/_panel_slots.py) |
| mayatk · anim_utils | [`blendshape_animator/blendshape_animator_slots.py`](../../mayatk/mayatk/anim_utils/blendshape_animator/blendshape_animator_slots.py) |
| mayatk · anim_utils | [`shots/shots_slots.py`](../../mayatk/mayatk/anim_utils/shots/shots_slots.py) |
| mayatk · anim_utils | [`shots/shot_manifest/shot_manifest_slots.py`](../../mayatk/mayatk/anim_utils/shots/shot_manifest/shot_manifest_slots.py) |
| mayatk · anim_utils | [`shots/shot_sequencer/shot_sequencer_slots.py`](../../mayatk/mayatk/anim_utils/shots/shot_sequencer/shot_sequencer_slots.py) |
| mayatk · audio_utils | [`audio_clips/audio_clips_slots.py`](../../mayatk/mayatk/audio_utils/audio_clips/audio_clips_slots.py) |
| mayatk · display_utils | [`color_id.py`](../../mayatk/mayatk/display_utils/color_id.py) |
| mayatk · display_utils | [`exploded_view.py`](../../mayatk/mayatk/display_utils/exploded_view.py) |
| mayatk · edit_utils | [`bevel.py`](../../mayatk/mayatk/edit_utils/bevel.py) |
| mayatk · edit_utils | [`bridge.py`](../../mayatk/mayatk/edit_utils/bridge.py) |
| mayatk · edit_utils | [`cut_on_axis.py`](../../mayatk/mayatk/edit_utils/cut_on_axis.py) |
| mayatk · edit_utils | [`duplicate_grid.py`](../../mayatk/mayatk/edit_utils/duplicate_grid.py) |
| mayatk · edit_utils | [`duplicate_linear.py`](../../mayatk/mayatk/edit_utils/duplicate_linear.py) |
| mayatk · edit_utils | [`duplicate_radial.py`](../../mayatk/mayatk/edit_utils/duplicate_radial.py) |
| mayatk · edit_utils | [`dynamic_pipe.py`](../../mayatk/mayatk/edit_utils/dynamic_pipe.py) |
| mayatk · edit_utils | [`mirror.py`](../../mayatk/mayatk/edit_utils/mirror.py) |
| mayatk · edit_utils | [`naming/naming_slots.py`](../../mayatk/mayatk/edit_utils/naming/naming_slots.py) |
| mayatk · edit_utils | [`snap.py`](../../mayatk/mayatk/edit_utils/snap.py) |
| mayatk · env_utils | [`hierarchy_sync/hierarchy_sync_slots.py`](../../mayatk/mayatk/env_utils/hierarchy_sync/hierarchy_sync_slots.py) |
| mayatk · env_utils | [`reference_manager.py`](../../mayatk/mayatk/env_utils/reference_manager.py) |
| mayatk · env_utils | [`scene_exporter/_scene_exporter.py`](../../mayatk/mayatk/env_utils/scene_exporter/_scene_exporter.py) |
| mayatk · env_utils | [`workspace_map.py`](../../mayatk/mayatk/env_utils/workspace_map.py) |
| mayatk · light_utils | [`hdr_manager.py`](../../mayatk/mayatk/light_utils/hdr_manager.py) |
| mayatk · mat_utils | [`game_shader.py`](../../mayatk/mayatk/mat_utils/game_shader.py) |
| mayatk · mat_utils | [`image_to_plane/image_to_plane_slots.py`](../../mayatk/mayatk/mat_utils/image_to_plane/image_to_plane_slots.py) |
| mayatk · mat_utils | [`marmoset_bridge/marmoset_bridge_slots.py`](../../mayatk/mayatk/mat_utils/marmoset_bridge/marmoset_bridge_slots.py) |
| mayatk · mat_utils | [`mat_updater.py`](../../mayatk/mayatk/mat_utils/mat_updater.py) |
| mayatk · mat_utils | [`render_opacity/render_opacity_slots.py`](../../mayatk/mayatk/mat_utils/render_opacity/render_opacity_slots.py) |
| mayatk · mat_utils | [`shader_templates/_shader_templates.py`](../../mayatk/mayatk/mat_utils/shader_templates/_shader_templates.py) |
| mayatk · mat_utils | [`substance_bridge/substance_bridge_slots.py`](../../mayatk/mayatk/mat_utils/substance_bridge/substance_bridge_slots.py) |
| mayatk · mat_utils | [`texture_path_editor.py`](../../mayatk/mayatk/mat_utils/texture_path_editor.py) |
| mayatk · node_utils | [`attributes/channels/channels_slots.py`](../../mayatk/mayatk/node_utils/attributes/channels/channels_slots.py) |
| mayatk · nurbs_utils | [`image_tracer.py`](../../mayatk/mayatk/nurbs_utils/image_tracer.py) |
| mayatk · rig_utils | [`shadow_rig.py`](../../mayatk/mayatk/rig_utils/shadow_rig.py) |
| mayatk · rig_utils | [`telescope_rig.py`](../../mayatk/mayatk/rig_utils/telescope_rig.py) |
| mayatk · rig_utils | [`tube_rig.py`](../../mayatk/mayatk/rig_utils/tube_rig.py) |
| mayatk · rig_utils | [`wheel_rig.py`](../../mayatk/mayatk/rig_utils/wheel_rig.py) |
| mayatk · ui_utils | [`calculator.py`](../../mayatk/mayatk/ui_utils/calculator.py) |
| mayatk · uv_utils | [`rizom_bridge/rizom_bridge_slots.py`](../../mayatk/mayatk/uv_utils/rizom_bridge/rizom_bridge_slots.py) |

### Excluded from migration

- [`.archive/metashape_workflow/.../metashape_workflow_slots.py`](../../.archive/metashape_workflow/metashape_workflow/metashape_workflow_slots.py) — archived, do not touch.

## Candidates — standalone tools that still lack help text

Tools with a `header_init` but no help text yet. Adding
`widget.set_help_text(...)` is straightforward and recommended:

| Package | File | Notes |
|:---|:---|:---|
| extapps | [`texture_maps/compositor/slots.py`](../../extapps/extapps/texture_maps/compositor/slots.py) | Standalone tool — add a short workflow summary. |
| extapps | [`mesh_convert/slots.py`](../../extapps/extapps/mesh_convert/slots.py) | Standalone tool — header_init currently adds a single checkbox; help text would help discoverability. |
| extapps | [`texture_maps/packer/slots.py`](../../extapps/extapps/texture_maps/packer/slots.py) | Standalone tool — explains the per-channel preset workflow. |

## Out of scope — tentacle hub panels

These `header_init` methods exist in [tentacle/tentacle/slots/maya/](../../tentacle/tentacle/slots/maya/) but
serve as **launchers / utility menus** for the tentacle marking-menu hub
(materials, scene, edit, polygons, rigging, animation, uv, transform,
duplicate, settings). They aren't standalone tool windows, so the help
button doesn't fit the UI model. Leave as-is.

## Mechanics

1. The `Header` widget now declares a `help` entry in `button_definitions`
   with the icon `uitk/icons/help.svg`.
2. `set_help_text(text)` lazily creates the `help` button at the leftmost
   slot (right of the layout stretch) and stores `text` as its tooltip.
3. Clicking the button calls `show_help`, which forces `QToolTip.showText`
   to display the same text at the button's anchor.
4. The button is also configurable explicitly: e.g.
   `Header(config_buttons=["help", "hide"])`.

## Tests

[`uitk/test/test_header.py`](../../uitk/test/test_header.py) →
`TestHeaderHelpButton` covers:

- Help button is absent by default.
- `set_help_text(...)` auto-adds the button.
- Tooltip text round-trips via `set_help_text` → `help_text`.
- Repeated `set_help_text` updates the existing button rather than creating a duplicate.
- Help button is inserted at the leftmost slot.
- `'help'` is accepted in `config_buttons`.
- `show_help()` with no help button is a no-op.
