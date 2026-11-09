"""The Render Effects sample: a fade, a highlight over a mapped emission, a lamp group and a blink over two shots.

The scene a person makes with Maya's Render Effects, Emissive Groups, the Shot
Sequencer and the Scene Exporter, exported with the data node on. Over two
shots, one take each:

- ``Box`` fades out in the first shot and back in over the second
  (``opacity``);
- ``Sphere``, whose emission is mapped (a tiny synthetic emission map), pulses a
  blue highlight once in each shot (``highlight``): while it glows the map is
  set aside, at rest it is back;
- ``Panel``, a two-material object (its body, and its front face's lamp),
  blinks off for a moment in the first shot (its keyed ``visibility``) and its
  lamp switches on in the second: the front face is the emissive group
  ``Signal``, so it wears ``Lamp_MAT_Signal``, the group's copy of its lamp
  material, whose emission the group's weight keys (a material ``emission``
  channel).

Every channel the ``render_effects`` record holds rides it, each curve on its
proxy in each take. unitytk's RenderEffectsImporter gives the box a Fade and
the sphere a Highlight, binds the lamp copy's weight to an Emission Track,
the blink to the panel's active state, and makes the twins into the model; its
Edit Mode tests (``Features/RenderEffects/Tests/RenderEffectsSampleTests.cs``)
state the same. The emission map is written here with the standard library
alone (the Materials recipe's writer).
"""

from unity_samples._images import write_png


NAME = "RenderEffects"
DESCRIPTION = (
    "Render effects over two shots: a box that fades out and back (Fade), a sphere "
    "that pulses a highlight over its mapped emission (Highlight), and a two-material "
    "panel that blinks off for a moment and whose lamp group switches on (its active "
    "state, and an Emission Track on the group's material); the twins they wear are "
    "made into the model. The demo scene plays the two shots in order."
)
#: The records the sample is held to: ``render_effects``, which the Render
#: Effects feature reads, and ``materials``, which gives the sphere its mapped
#: emission and the lamp group its copy -- what the effects are drawn over.
RECORDS = ("render_effects", "materials")
#: The exported file's stem (``RenderEffects.fbx``).
MODEL = "RenderEffects"
#: The scene's rate: Maya's ``film`` (24 fps).
TIME_UNIT = "film"
#: ``(name, first frame, last frame)`` per shot.
SHOTS = (("FadeOut", 1, 24), ("FadeIn", 25, 48))
#: The objects' size and spacing (centimetres).
SIZE, SPACING = 80.0, 150.0
#: The box's fades: ``(first frame, last frame, direction)``.
FADES = ((4, 16, "out"), (28, 40, "in"))
#: The sphere's highlight: one pulse per shot (``(first frame, last frame)``),
#: its period, its colour at 1 and at 0 (linear).
PULSES = ((1, 24), (25, 48))
PULSE_PERIOD = 24
HIGHLIGHT = ((0.2, 0.6, 1.0), (0.0, 0.0, 0.0))
#: The panel's blink: ``(frame, visible)``, stepped.
BLINK = ((1, 1), (8, 0), (12, 1))
#: The lamp group: its name and its weight keys ``(frame, weight)``.
GROUP = "Signal"
LAMP_KEYS = ((1, 0.0), (28, 0.0), (34, 1.0), (48, 1.0))
#: The lamp's emission colour (linear) at weight 1.
LAMP = (1.0, 0.8, 0.3)
#: The emission map's size (texels a side).
MAP_SIZE = 16


def write_emission_map(path: str) -> str:
    """The sphere's emission map at *path*: warm bands across a dark ground,
    ``MAP_SIZE`` texels a side.

    Returns:
        *path*.
    """

    def bands(x, y):
        return (255, 140, 40, 255) if (y // 2) % 4 == 0 else (20, 10, 5, 255)

    return write_png(path, bands, MAP_SIZE)


def build(out_dir: str) -> list:
    """Make the scene and export it into *out_dir* through the Scene Exporter.

    Returns:
        The names of the files written: ``["RenderEffects.fbx"]`` (its image
        rides inside it).

    Raises:
        RuntimeError: The export reported a failure (its log says why).
    """
    import os

    import maya.cmds as cmds
    import mayatk as mtk

    cmds.currentUnit(time=TIME_UNIT)
    cmds.playbackOptions(minTime=SHOTS[0][1], maxTime=SHOTS[-1][2])

    # The map's source lives in the project's sourceimages, outside the
    # delivery, as a person's does: the export embeds it from there.
    project = os.path.join(out_dir, "_project")
    mtk.EnvUtils.create_workspace(project, rules={"sourceImages": "sourceimages", "scene": "scenes"})
    mtk.EnvUtils.set_current_workspace(project)
    sources = os.path.join(project, "sourceimages")
    os.makedirs(sources, exist_ok=True)
    emission_map = write_emission_map(os.path.join(sources, "Sphere_Emission.png"))

    def surface(name, base, emission=0.0, glow=None):
        shader = cmds.shadingNode("standardSurface", asShader=True, name=name)
        cmds.setAttr(shader + ".baseColor", *base, type="double3")
        cmds.setAttr(shader + ".specularRoughness", 0.5)
        cmds.setAttr(shader + ".emission", emission)
        if glow is not None:
            cmds.setAttr(shader + ".emissionColor", *glow, type="double3")
        return shader

    def texture(path, name):
        node = cmds.shadingNode("file", asTexture=True, isColorManaged=True, name=name)
        place = cmds.shadingNode("place2dTexture", asUtility=True, name=name + "_place")
        cmds.defaultNavigation(connectToExisting=True, source=place, destination=node)
        cmds.setAttr(node + ".fileTextureName", path, type="string")
        return node

    box = cmds.polyCube(name="Box", width=SIZE, height=SIZE, depth=SIZE)[0]
    cmds.move(-SPACING, SIZE / 2, 0, box)
    mtk.MatUtils.assign_mat([box], surface("Box_MAT", (0.8, 0.3, 0.2)))

    sphere = cmds.polySphere(name="Sphere", radius=SIZE / 2, subdivisionsX=24, subdivisionsY=16)[0]
    cmds.move(0, SIZE / 2, 0, sphere)
    glow = surface("Sphere_MAT", (0.05, 0.05, 0.05), emission=1.0)
    cmds.connectAttr(texture(emission_map, "Sphere_emission") + ".outColor", glow + ".emissionColor")
    mtk.MatUtils.assign_mat([sphere], glow)

    panel = cmds.polyCube(name="Panel", width=SIZE, height=SIZE, depth=SIZE / 4)[0]
    cmds.move(SPACING, SIZE / 2, 0, panel)
    mtk.MatUtils.assign_mat([panel], surface("Panel_MAT", (0.35, 0.35, 0.4)))
    # The lamp: the front face (+Z), its material glowing at full weight.
    front = f"{panel}.f[0]"
    mtk.MatUtils.assign_mat([front], surface("Lamp_MAT", (0.1, 0.1, 0.1), emission=1.0, glow=LAMP))

    for start, end, direction in FADES:
        mtk.RenderEffects.key_fade([box], start=start, end=end, direction=direction)
    bright, dim = HIGHLIGHT
    for start, end in PULSES:
        mtk.RenderEffects.key_pulse(
            [sphere], start=start, end=end, period=PULSE_PERIOD, color=bright, dim_color=dim
        )
    for frame, visible in BLINK:
        cmds.setKeyframe(panel, attribute="visibility", time=frame, value=visible)
    cmds.keyTangent(panel, attribute="visibility", outTangentType="step")
    mtk.EmissiveGroups.add_group(GROUP, [front], weight=0.0)
    for frame, weight in LAMP_KEYS:
        mtk.EmissiveGroups.key_weight(GROUP, weight, frame=frame)
    # The rest state the export writes (each node's and material's static value): the
    # first frame, where the box is opaque, the sphere and the lamp dark, the panel shown.
    cmds.currentTime(SHOTS[0][1])

    store = mtk.ShotStore()
    mtk.ShotStore.set_active(store)
    for name, start, end in SHOTS:
        store.define_shot(name, start, end, objects=[box, sphere, panel])

    exporter = mtk.SceneExporter(log_level="WARNING")
    exporter.confirm = lambda question: False
    if not exporter.perform_export(
        export_dir=out_dir,
        objects=[box, sphere, panel],
        output_name=MODEL,
        tasks={"export_data_node": True},
    ):
        raise RuntimeError(f"the Scene Exporter wrote no {MODEL}.fbx; its log above says why")
    return [f"{MODEL}.fbx"]
