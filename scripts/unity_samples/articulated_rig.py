"""The ArticulatedRig sample: a desk lamp on two hinged arms, a telescoping section and a hinged head.

The scene a person makes with Maya's Articulated Rig and the Scene Exporter,
exported with the data node on. A desk lamp stands in the XY plane (Y up,
centimetres) under one group, ``Lamp``:

- ``Base``, a disc on the ground: the root link, which stays put;
- ``LowerArm``, a post on the base: a universal joint, swivelling about its
  own length (``rx``) and tilting in the lamp's plane (``rz``);
- ``UpperArm``, a tube from the post's top, hinged there (``rz``);
- ``Extension``, a thinner tube telescoping out of the upper arm's end: a
  slide along it (``tx``);
- ``Head``, a shade hanging off the extension's tip, hinged there (``rz``).

``ArticulatedRig.analyze`` reads the parts (the base the lowest, the root),
the joints are stated as a person sets them in the panel's table (each one's
type, pivot and axes: the sample does not hang on how the analysis reads a
few primitives), and
``ArticulatedRig.create`` builds the rig without an end control (the take
keys the FK controls, which an end control's solve would pin). Every limit is
taken from a pose (``set_limit_from_pose``): each channel posed to where it
stops, its side's limit set there, then the rig back to rest. Every moving
part is a grab part (the rig's record lists each link's parts), the head
among them. A two-second take keys every channel (frames 1, 24 and 48, the
last the first again), one shot (``Reach``) spans it, so the export bakes
the joints the controls drive into one clip, and the file is written at
frame 1, so its own pose is not the rest pose.

What the delivery holds and who reads it:

- **Unity reads** the record's rig: its joints (``name``, each the node the
  rig built, ``lamp_<part>_jnt``), their ``parent`` links (an earlier joint's
  index), their rests (``t``, ``q``, in metres and the parent joint's frame),
  their anchors (``anchor``: the identity, as every Maya rig's: it nests each
  joint on its pivot), ``rotate_order`` and channels (``channel``, ``min``,
  ``max``, ``weight``: degrees, and metres for the slide), and ``grab`` (each
  part a hand takes, by name under its joint, and the joint it rides).
  unitytk's ArticulatedRigImporter gives ``lamp_RIG`` an Articulated Rig and
  each joint's node an Articulated Joint, by reference, mirrored to Unity's
  axes; the take's clip animates the joints and the rig follows it. Its Edit
  Mode tests (``Features/ArticulatedRig/Tests/ArticulatedRigSampleTests.cs``)
  state the same.
- **Unity ignores** nothing of the record; the rig's controls are not in the
  file (the export's Exclude Rig Helpers drops them).

No flat variant: a flat model (every part a child of one group, chained only
by the record's parent links) holds its hinges in its anchors, and a Maya rig
nests each joint on its pivot, so its producer writes the identity anchor
alone and refuses any other (``ArticulationPlan.refuse_anchors``); a flat
rig is one made in Unity (``ArticulatedRigActions``), as the feature's own
tests make one.
"""

NAME = "ArticulatedRig"
DESCRIPTION = (
    "A desk lamp of rigid parts on joints, delivered with its articulation record: a post swivelling and tilting on its base, "
    "an upper arm hinged on the post, a section telescoping out of the arm and a shade hinged at its tip, "
    "each joint an Articulated Joint bound by reference with its limits, and the parts grabbable. The "
    "demo scene plays the take and lets the mouse grab any part, the shade's drag solving the chain."
)
#: The record the ArticulatedRig feature reads (its ArticulatedRigImporter):
#: the sample is described, and held to its recipe, by it and the delivery's
#: structure (the take among it).
RECORDS = ("articulation",)
#: The exported file's stem (``ArticulatedRig.fbx``).
MODEL = "ArticulatedRig"
#: The scene's rate: Maya's ``film`` (24 fps).
TIME_UNIT = "film"
#: The take's first and last frame: two seconds.
FRAMES = (1, 48)
#: ``(name, first frame, last frame)`` per shot: one over the take, and so
#: its clip's name.
SHOTS = (("Reach", FRAMES[0], FRAMES[1]),)
#: The lamp's group, and the rig's name (the group's, lowercase).
GROUP = "Lamp"
#: The parts: ``(name, kind, size, centre)`` -- a ``cylinder`` is ``(radius,
#: length, axis)``, a ``cube`` ``(x, y, z)``, a ``cone`` ``(radius, height)``
#: (centimetres; the root first).
PARTS = (
    ("Base", "cylinder", (10.0, 3.0, "y"), (0.0, 1.5, 0.0)),
    ("LowerArm", "cube", (3.0, 31.0, 3.0), (0.0, 18.5, 0.0)),
    ("UpperArm", "cylinder", (1.6, 24.0, "x"), (13.0, 34.0, 0.0)),
    ("Extension", "cylinder", (1.1, 16.0, "x"), (22.0, 34.0, 0.0)),
    ("Head", "cone", (5.0, 8.0), (30.0, 29.0, 0.0)),
)
#: Each joint as the panel's table states it: ``(part, parent part, type,
#: pivot, aim, normal)`` -- world space, X down the link, Z a hinge's axis.
JOINTS = (
    ("LowerArm", "Base", "universal", (0.0, 3.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    ("UpperArm", "LowerArm", "hinge", (0.0, 34.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ("Extension", "UpperArm", "slide", (14.0, 34.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ("Head", "Extension", "hinge", (30.0, 34.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
)
#: Where each channel stops, ``{(part, channel): (min, max)}``: degrees, and
#: centimetres for the slide (it retracts 4 and runs out 8, 3 still inside).
STOPS = {
    ("LowerArm", "rx"): (-90.0, 90.0),
    ("LowerArm", "rz"): (-35.0, 35.0),
    ("UpperArm", "rz"): (-60.0, 45.0),
    ("Extension", "tx"): (-4.0, 8.0),
    ("Head", "rz"): (-50.0, 70.0),
}
#: The take: ``(frame, {(part, channel): value})``; the file is written at
#: the first.
KEYS = (
    (1, {("LowerArm", "rx"): 20.0, ("LowerArm", "rz"): -10.0, ("UpperArm", "rz"): -20.0,
         ("Extension", "tx"): 2.0, ("Head", "rz"): 15.0}),
    (24, {("LowerArm", "rx"): -30.0, ("LowerArm", "rz"): 15.0, ("UpperArm", "rz"): 25.0,
          ("Extension", "tx"): 6.0, ("Head", "rz"): -30.0}),
    (48, {("LowerArm", "rx"): 20.0, ("LowerArm", "rz"): -10.0, ("UpperArm", "rz"): -20.0,
          ("Extension", "tx"): 2.0, ("Head", "rz"): 15.0}),
)


def _part(cmds, name, kind, size, centre):
    """One part's mesh, history gone, its pivot at its centre."""
    if kind == "cylinder":
        radius, length, axis = size
        node = cmds.polyCylinder(
            name=name, radius=radius, height=length, subdivisionsAxis=16,
            axis=(1, 0, 0) if axis == "x" else (0, 1, 0),
        )[0]
    elif kind == "cone":
        radius, height = size
        node = cmds.polyCone(name=name, radius=radius, height=height, subdivisionsAxis=16)[0]
    else:
        node = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    cmds.move(*centre, node)
    cmds.delete(node, constructionHistory=True)
    return node


def build(out_dir: str) -> list:
    """Make the lamp, rig it, key its take and export it into *out_dir*
    through the Scene Exporter.

    Returns:
        The names of the files written: ``["ArticulatedRig.fbx"]``.

    Raises:
        RuntimeError: The analysis did not take the base for the root, or the
            export reported a failure (its log says why).
    """
    import maya.cmds as cmds
    import mayatk as mtk
    import pythontk as ptk

    cmds.currentUnit(time=TIME_UNIT)
    cmds.playbackOptions(
        minTime=FRAMES[0], maxTime=FRAMES[1], animationStartTime=FRAMES[0], animationEndTime=FRAMES[1]
    )
    cmds.currentTime(FRAMES[0])

    shader = cmds.shadingNode("standardSurface", asShader=True, name="Lamp_MAT")
    cmds.setAttr(shader + ".baseColor", 0.62, 0.64, 0.68, type="double3")
    cmds.setAttr(shader + ".metalness", 0.6)
    parts = {name: _part(cmds, name, kind, size, centre) for name, kind, size, centre in PARTS}
    mtk.MatUtils.assign_mat(list(parts.values()), shader)
    group = cmds.group(*parts.values(), name=GROUP)

    plan = mtk.ArticulatedRig.analyze(group)
    links = [[cmds.ls(n, long=True)[0] for n in link] for link in plan["links"]]
    leaves = [link[0].split("|")[-1] for link in links]
    if leaves[0] != PARTS[0][0]:
        raise RuntimeError(f"the analysis took {leaves[0]} for the root, not {PARTS[0][0]}")
    joints = [
        {
            "link": leaves.index(part),
            "parent": leaves.index(parent),
            "type": kind,
            "position": list(position),
            "aim": list(aim),
            "normal": list(normal),
            "limits": {},
            "size": 4.0,
        }
        for part, parent, kind, position, aim, normal in JOINTS
    ]
    rig = mtk.ArticulatedRig.create(links, joints, end_control=False)

    slots = ptk.ArticulationPlan.slots(rig.spec)
    rest = [0.0] * len(slots)
    for (part, channel), stops in STOPS.items():
        for side, value in zip(("min", "max"), stops):
            pose = list(rest)
            pose[slots.index((part, channel))] = value
            rig.set_state(pose, key=False)
            rig.set_limit_from_pose(part, channel, side)
    rig.reset_pose(key=False)

    for frame, values in KEYS:
        cmds.currentTime(frame)
        rig.set_state([values[slot] for slot in slots], key=True)
    cmds.currentTime(FRAMES[0])
    # One shot over the take, as the Shot Sequencer makes one: the export's
    # take split bakes it, so the joints the controls drive carry its keys.
    store = mtk.ShotStore()
    mtk.ShotStore.set_active(store)
    for name, start, end in SHOTS:
        store.define_shot(name, start, end, objects=[group])

    exporter = mtk.SceneExporter(log_level="WARNING")
    exporter.confirm = lambda question: False
    if not exporter.perform_export(
        export_dir=out_dir,
        objects=[group],
        output_name=MODEL,
        tasks={"export_data_node": True, "drop_rig_apparatus": True},
    ):
        raise RuntimeError(f"the Scene Exporter wrote no {MODEL}.fbx; its log above says why")
    return [f"{MODEL}.fbx"]
