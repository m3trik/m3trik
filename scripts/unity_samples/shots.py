"""The Shots sample: a box moving through three shots, one take each.

The scene a person makes with the Shot Sequencer and the Scene Exporter: a
keyed box, three shots over its motion, each with a description and the one
manifest key the sample ships (``section``), exported with the data node on.
Unity's model importer makes one clip per shot, named after it; unitytk's
ShotsImporter writes the ShotList that joins each clip to its description and
metadata. Its Edit Mode tests (``Features/Shots/Tests/ShotsSampleTests.cs``)
state the same shots.
"""

NAME = "Shots"
DESCRIPTION = (
    "A box moving through three shots: one clip per shot, named after it, and the "
    "ShotList that gives each clip its description and section; the demo scene "
    "plays the shots in order and shows the playing shot's description."
)
#: The records the Shots feature reads (its ShotsImporter): the sample is
#: described, and held to its recipe, by these and the delivery's structure.
RECORDS = ("animation",)
#: The exported file's stem (``Shots.fbx``).
MODEL = "Shots"
#: The scene's rate: Maya's ``film``.
TIME_UNIT = "film"
#: ``(name, first frame, last frame, description, section)`` per shot.
SHOTS = (
    ("Approach", 1, 24, "The box slides in from the left.", "intro"),
    ("Turn", 25, 48, "The box turns half way round.", "middle"),
    ("Exit", 49, 72, "The box slides out to the right.", "outro"),
)
#: ``(frame, attribute, value)``: the motion the shots cut (centimetres, degrees).
KEYS = (
    (1, "translateX", -300.0),
    (24, "translateX", 0.0),
    (25, "rotateY", 0.0),
    (48, "rotateY", 180.0),
    (49, "translateX", 0.0),
    (72, "translateX", 300.0),
)


def build(out_dir: str) -> list:
    """Make the scene and export it into *out_dir* through the Scene Exporter.

    Returns:
        The names of the files written: ``["Shots.fbx"]``.

    Raises:
        RuntimeError: The export reported a failure (its log says why).
    """
    import maya.cmds as cmds
    import mayatk as mtk

    cmds.currentUnit(time=TIME_UNIT)
    cmds.playbackOptions(minTime=SHOTS[0][1], maxTime=SHOTS[-1][2])
    box = cmds.polyCube(name="Box", width=100, height=100, depth=100)[0]
    for frame, attribute, value in KEYS:
        cmds.setKeyframe(box, attribute=attribute, time=frame, value=value)

    store = mtk.ShotStore()
    mtk.ShotStore.set_active(store)
    for name, start, end, description, section in SHOTS:
        store.define_shot(
            name, start, end, objects=[box], description=description, metadata={"section": section}
        )
    # What the Shot Manifest's Build hands the store: the keys an export ships.
    store.set_shipped_metadata(["section"])

    exporter = mtk.SceneExporter(log_level="WARNING")
    exporter.confirm = lambda question: False
    # The rows a headless caller names (perform_export runs only those): the
    # data node, which carries the records.
    if not exporter.perform_export(
        export_dir=out_dir,
        objects=[box],
        output_name=MODEL,
        tasks={"export_data_node": True},
    ):
        raise RuntimeError("the Scene Exporter wrote no Shots.fbx; its log above says why")
    return [f"{MODEL}.fbx"]
