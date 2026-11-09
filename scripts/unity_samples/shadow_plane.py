"""The ShadowPlane sample: three objects on a ground, each with a shadow plane, under a lamp that moves.

The scene a person makes with Maya's Shadow Rig and the Scene Exporter,
exported with the data node on. Three objects stand on a ground:

- ``Box``, a plain box: the simplest footprint;
- ``Chair``, a seat on four legs with a back: seen from above, its horizon
  map holds spans and gaps (each leg, the air under the seat, the seat);
- ``Awning``, a slab on one post, cantilevered past it: an overhang, whose
  shadow lands away from its foot.

Each is given one shadow plane by ``ShadowRig.create``, the rig types and
the sources between them covering both of each: the box's plane follows the
point light ``Lamp`` and is a Projected rig (its silhouette drawn, ``draw:
true``); the chair's follows the directional light ``Sun`` and the awning's
the lamp, both Horizon rigs (their silhouette the fallback, ``draw:
false``). Every plane carries its horizon map (shadows v3), baked by the rig
at create and checked again by the export. The lamp is keyed over three
seconds, sweeping low across the scene and over it, so the planes it casts
move, lengthen and fade as it goes. The take keys the lamp's sweep and each
plane's placement (the Scene Exporter bakes the rig's driven transform
channels, ShadowRig's documented FBX export; a reader following the source,
``follow_source``, places a plane itself), and never a fade: every reader
fades a plane every frame from the record's fade terms, and the rig's
preview fade lives on its material, which no take keys.

What the delivery holds and who reads it:

- **Unity reads** the planes (``planes``: each plane's name, its source and
  contact nodes, the bounding cylinder's ``radius`` and ``height``, the
  ``ground``, ``max_stretch``, ``follow_source`` and the source's size), each
  plane's horizon map (``horizon``: the PNG the FBX embeds and its layout),
  and the fade's terms (``intensity``, ``falloff_power``, ``fade_height``,
  with ``unit_scale``). unitytk's ShadowPlaneImporter gives each plane a
  Shadow Plane bound by reference to its target, its source Light and its
  contact, its delivered horizon map bound; the component places and fades
  it every frame from the model (``ShadowPlaneModel``). Its Edit Mode tests
  (``Features/ShadowPlane/Tests/ShadowPlaneSampleTests.cs``) state the same,
  and rebake each map in Unity with the ported baker to hold it to the
  producer's.
- **Unity ignores** ``silhouette`` (the image, its canvas and the draw
  choice): the WebXR viewer's extension. Unity marches the horizon map
  alone, so the box's Projected rig draws there as the others do.
"""

NAME = "ShadowPlane"
DESCRIPTION = (
    "Three objects on a ground, a box, a chair on four legs and an awning cantilevered past its "
    "post, each with a shadow plane bound by reference to its target, its source Light and its "
    "contact, marching the horizon map delivered with it: two follow a lamp keyed to sweep across "
    "the scene, so they move, lengthen and fade as it goes, and one follows the sun. The demo scene "
    "plays the lamp's sweep."
)
#: The record the ShadowPlane feature reads (its ShadowPlaneImporter): the
#: sample is described, and held to its recipe, by it and the delivery's
#: structure (the lamp's take among it).
RECORDS = ("shadows",)
#: The exported file's stem (``ShadowPlane.fbx``).
MODEL = "ShadowPlane"
#: The scene's rate: Maya's ``film`` (24 fps).
TIME_UNIT = "film"
#: The lamp's sweep, first and last frame: three seconds.
FRAMES = (1, 72)
#: The ground's side (centimetres, Y up, centred on the origin).
GROUND = 800.0
#: The box: its side and where it stands (``(x, z)``, centimetres).
BOX = (60.0, (-180.0, 40.0))
#: The chair: where it stands, its seat (side, height of its top, thickness),
#: its legs' side, and its back's height above the seat (centimetres).
CHAIR_AT = (0.0, -40.0)
SEAT = (50.0, 45.0, 6.0)
LEG = 5.0
BACK = 45.0
#: The awning: where its post stands, the post's side and height, and the
#: slab on it (width, depth, thickness), reaching ``REACH`` past the post
#: along +X (centimetres).
AWNING_AT = (180.0, 20.0)
POST = (12.0, 110.0)
SLAB = (110.0, 60.0, 8.0)
REACH = 40.0
#: The lamp: its keys, ``(frame, (x, y, z))`` in centimetres, linear: from low
#: on the left, over the scene, to low on the right.
LAMP_KEYS = (
    (1, (-380.0, 150.0, 220.0)),
    (36, (0.0, 340.0, 160.0)),
    (72, (380.0, 150.0, 220.0)),
)
#: The sun's rotation (degrees, XYZ): it shines along its -Z, down and away.
SUN_ROTATION = (-50.0, 35.0, 0.0)
#: The silhouette's size (texels a side): only the WebXR viewer reads it.
SILHOUETTE = 64
#: Each plane: ``(target, source, rig type)``.
RIGS = (
    ("Box", "Lamp", "projected"),
    ("Chair", "Sun", "horizon"),
    ("Awning", "Lamp", "horizon"),
)


def _box(cmds, name, size, centre):
    """A polyCube of *size* ``(x, y, z)`` centred at *centre*."""
    node = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    cmds.move(*centre, node)
    return node


def _united(cmds, name, parts):
    """*parts* united into one mesh *name*, history gone, its pivot at its
    footprint's centre on the ground."""
    node = cmds.polyUnite(*parts, name=name, constructionHistory=False)[0]
    for part in parts:
        if cmds.objExists(part):
            cmds.delete(part)
    box = cmds.exactWorldBoundingBox(node)
    cmds.xform(node, pivots=((box[0] + box[3]) / 2.0, 0.0, (box[2] + box[5]) / 2.0), worldSpace=True)
    return node


def build(out_dir: str) -> list:
    """Make the scene and export it into *out_dir* through the Scene Exporter.

    Returns:
        The names of the files written: ``["ShadowPlane.fbx"]`` (its horizon
        maps and silhouettes ride inside it).

    Raises:
        RuntimeError: The export reported a failure (its log says why), or a
            plane carries no horizon map.
    """
    import os

    import maya.cmds as cmds
    import mayatk as mtk

    cmds.currentUnit(time=TIME_UNIT)
    cmds.playbackOptions(
        minTime=FRAMES[0], maxTime=FRAMES[1], animationStartTime=FRAMES[0], animationEndTime=FRAMES[1]
    )
    cmds.currentTime(FRAMES[0])

    # The rigs write their maps into the project's sourceimages, outside the
    # delivery, as a person's do: the export embeds them from there.
    project = os.path.join(out_dir, "_project")
    mtk.EnvUtils.create_workspace(project, rules={"sourceImages": "sourceimages", "scene": "scenes"})
    mtk.EnvUtils.set_current_workspace(project)
    os.makedirs(os.path.join(project, "sourceimages"), exist_ok=True)

    def surface(name, base):
        shader = cmds.shadingNode("standardSurface", asShader=True, name=name)
        cmds.setAttr(shader + ".baseColor", *base, type="double3")
        cmds.setAttr(shader + ".specularRoughness", 0.6)
        return shader

    ground = cmds.polyPlane(name="Ground", width=GROUND, height=GROUND, subdivisionsX=1, subdivisionsY=1)[0]
    mtk.MatUtils.assign_mat([ground], surface("Ground_MAT", (0.7, 0.7, 0.68)))

    side, (bx, bz) = BOX
    box = _box(cmds, "Box", (side, side, side), (bx, side / 2.0, bz))

    cx, cz = CHAIR_AT
    seat, top, thick = SEAT
    under = top - thick
    half = seat / 2.0 - LEG / 2.0
    parts = [_box(cmds, "Chair_seat", (seat, thick, seat), (cx, top - thick / 2.0, cz))]
    for i, (sx, sz) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1))):
        parts.append(_box(cmds, f"Chair_leg{i}", (LEG, under, LEG), (cx + sx * half, under / 2.0, cz + sz * half)))
    parts.append(_box(cmds, "Chair_back", (seat, BACK, LEG), (cx, top + BACK / 2.0, cz - half)))
    chair = _united(cmds, "Chair", parts)

    ax, az = AWNING_AT
    post, tall = POST
    width, depth, slab = SLAB
    parts = [
        _box(cmds, "Awning_post", (post, tall, post), (ax, tall / 2.0, az)),
        _box(cmds, "Awning_slab", (width, slab, depth), (ax + REACH, tall + slab / 2.0, az)),
    ]
    awning = _united(cmds, "Awning", parts)

    objects = [box, chair, awning]
    mtk.MatUtils.assign_mat(objects, surface("Prop_MAT", (0.55, 0.35, 0.22)))
    cmds.delete(objects + [ground], constructionHistory=True)

    lamp = cmds.rename(cmds.listRelatives(cmds.pointLight(intensity=1.0), parent=True)[0], "Lamp")
    for frame, at in LAMP_KEYS:
        for axis, value in zip("XYZ", at):
            cmds.setKeyframe(lamp, attribute=f"translate{axis}", time=frame, value=value)
    cmds.keyTangent(lamp, inTangentType="linear", outTangentType="linear")
    sun = cmds.rename(cmds.listRelatives(cmds.directionalLight(intensity=1.0), parent=True)[0], "Sun")
    cmds.xform(sun, rotation=SUN_ROTATION, translation=(0.0, 400.0, 0.0))
    cmds.currentTime(FRAMES[0])

    nodes = {"Box": box, "Chair": chair, "Awning": awning}
    rigs = [
        mtk.ShadowRig.create([nodes[target]], source_name=source, texture_res=SILHOUETTE, rig_type=kind)
        for target, source, kind in RIGS
    ]
    unbaked = [r.shadow_plane for r in rigs if not (r.horizon_path and os.path.isfile(r.horizon_path))]
    if unbaked:
        raise RuntimeError(f"no horizon map baked for {unbaked}")

    exporter = mtk.SceneExporter(log_level="WARNING")
    exporter.confirm = lambda question: False
    if not exporter.perform_export(
        export_dir=out_dir,
        objects=[ground, *objects, lamp, sun, *(r.group for r in rigs)],
        output_name=MODEL,
        tasks={"export_data_node": True},
    ):
        raise RuntimeError(f"the Scene Exporter wrote no {MODEL}.fbx; its log above says why")
    return [f"{MODEL}.fbx"]
