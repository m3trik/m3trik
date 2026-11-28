"""The Tasks sample: a cabinet task, its sheet, its delivery and its plan, made with no DCC.

A small task in the Interactive build-sheet format, written in cells (pythontk's
``docs/build_sheets.md``: a step's own row, ``IN_01`` / ``A01`` / ``B03A`` step IDs, ``SECTION X:``
rows, then one row per action: its word and the cells it takes, each name the node's own as the
delivery spells it): ``cabinet.csv``, read with the ``interactive`` template and held to the strict
check; the delivery its steps play, at life size (a cabinet with a hinged door, two latches on its
frame, a bolt, a lid and a button at its back, and a table with a key and a wrench on it; two
viewpoints, front and back), one take per row that plays a clip, named as the Shot Manifest names
a step's takes: ``cabinet.fbx``; and the plan unitytk reads them into: ``cabinet.plan.json``.

Unlike the other samples, nothing here runs in a DCC (:data:`PRODUCER`): the
delivery is written by pythontk's ``FbxWriter`` and the plan by unitytk's own
reader, both in this interpreter, so every byte is reproducible. The Tasks
kit's Edit Mode tests (``Kits/Tasks/Tests/TaskSampleTests.cs``) build the
sample's demo scene and play it through, step by step; the demo recipe
(``Samples~/Tasks/Editor``) is the same build a person plays.

Weighed for the document (:func:`fbx`): pythontk's glTF converter writes the
same sections around its objects (``GlobalSettings``, ``Documents``,
``Definitions``, ``Takes``), but as one conversion's private builder
(``_GltfToFbx.records``): it holds one take, its objects come from a glTF it
reads, and a script reaches pythontk only through its root. A glTF converted
by ``ptk.MeshConvert.gltf_to_fbx`` would carry one take of the five. So the
recipe writes the sections with ``ptk.FbxWriter``'s public nodes itself, the
fields an FBX SDK reader needs, as the converter does; a public document
builder in pythontk, when a second writer needs it, would replace both.
"""

import struct
from pathlib import Path
from typing import Dict, List, Tuple

NAME = "Tasks"
DESCRIPTION = (
    "A cabinet task from a studio's sequence sheet and its delivery: unlock two latches "
    "with a key, open the door, take a bolt out with a wrench, press a button and answer a "
    "question, each step built by the Tasks kit from the sheet's rows (highlights, "
    "pointers, viewpoints, selections, clips, choices). The demo scene puts a desktop rig "
    "in it, a camera that looks about with the right mouse button and clicks to select, "
    "and plays it."
)
#: No scene record: the kit reads the sheet and the plan, and the delivery's
#: takes and nodes, which every sample's description holds anyway.
RECORDS = ()
#: Written in this interpreter, not a DCC's (``sync_unity_samples.py``).
PRODUCER = "python"

SHEET = """Step,Step Name,Voice,Placard,Audio,Action,Target,With,Clip,Members,Label,To,Settings,Notes
INTRO,,,,,,,,,,,,,
IN_01,Welcome,Welcome to the cabinet service task.,,,,,,,,,,,
,,,,,note,,,,,,,,The cabinet stands in front of you with its tools on the table.
IN_02,Begin,Select 'Begin' to start.,,,,,,,,,,,
,,,,,button,,,,,Begin,next,,
SECTION A: Open the cabinet,,,,,,,,,,,,,
A01,Unlock the latches,Unlock both latches with the key.,,,,,,,,,,,
,,,,,travel,CABINET,,,,,,where=VIEW_FRONT,
,,,,,highlight,CABINET_LATCHES_GRP,,,,,,,
,,,,,indicate,KEY_GRP,,,,,,,
,,,,,take,KEY_GRP,,,,,,,
,,,,,use,LATCH_UPPER_GRP,KEY_GRP,A01_1,LATCH_UPPER_GRP,,,,
,,,,,use,LATCH_LOWER_GRP,KEY_GRP,A01_2,LATCH_LOWER_GRP,,,,
,,,,,return,KEY_GRP,,,,,,,
A02,Open the door,Now open the door.,Select the door to open it,,,,,,,,,,
,,,,,highlight,DOOR_GRP,,,,,,,
,,,,,use,DOOR_GRP,,A02,,,,,
SECTION B: Replace the bolt,,,,,,,,,,,,,
B01,Remove the bolt,Remove the bolt with the wrench.,,,,,,,,,,,
,,,,,travel,CABINET,,,,,,where=VIEW_BACK,
,,,,,highlight,BOLT_GRP,,,,,,,
,,,,,indicate,WRENCH_GRP,,,,,,,
,,,,,take,WRENCH_GRP,,,,,,,
,,,,,use,BOLT_GRP,WRENCH_GRP,B01_1,BOLT_GRP,,,,
,,,,,play,,,B01_2,LID_GRP,,,after=B01_1,
,,,,,hide,BOLT_GRP,,,,,,,
,,,,,return,WRENCH_GRP,,,,,,,
B02,Test the lamp,Press the button.,,,,,,,,,,,
,,,,,select,BUTTON_GRP,,,,,,,
B03,Did it light?,Did the lamp light?,Did the lamp light?,,,,,,,,,,
,,,,,button,,,,,YES,B04,,
,,,,,button,,,,,NO,B03A,,
B03A,Wrong answer,That is not right. Try again.,,,,,,,,,,,
,,,,,button,,,,,Try Again,B03,,
B04,Done,Well done.,,,,,,,,,,,
,,,,,button,,,,,Exit,exit,,
"""

#: The delivery's nodes, parents first: ``(path, kind, local position in cm)``, Y up,
#: the cabinet's front facing +Z. A ``Mesh`` is a box, sized by :data:`SIZES`.
NODES: Tuple[Tuple[str, str, Tuple[float, float, float]], ...] = (
    ("CABINET", "Mesh", (0, 50, 0)),
    # The door hangs on the front's left edge and stops short of the right, where
    # the latches sit on the frame that holds it shut.
    ("CABINET|DOOR_GRP", "Null", (-30, 0, 20)),
    ("CABINET|DOOR_GRP|DOOR_GEO", "Mesh", (24, 0, 1)),
    ("CABINET|CABINET_LATCHES_GRP", "Null", (24, 0, 21)),
    ("CABINET|CABINET_LATCHES_GRP|LATCH_UPPER_GRP", "Null", (0, 30, 0)),
    ("CABINET|CABINET_LATCHES_GRP|LATCH_UPPER_GRP|LATCH_UPPER_GEO", "Mesh", (0, 0, 0)),
    ("CABINET|CABINET_LATCHES_GRP|LATCH_LOWER_GRP", "Null", (0, -30, 0)),
    ("CABINET|CABINET_LATCHES_GRP|LATCH_LOWER_GRP|LATCH_LOWER_GEO", "Mesh", (0, 0, 0)),
    ("CABINET|BOLT_GRP", "Null", (0, 0, -21)),
    ("CABINET|BOLT_GRP|BOLT_GEO", "Mesh", (0, 0, 0)),
    # The lid hinges on the top's back edge.
    ("CABINET|LID_GRP", "Null", (0, 50, -20)),
    ("CABINET|LID_GRP|LID_GEO", "Mesh", (0, 1, 20)),
    ("CABINET|BUTTON_GRP", "Null", (15, 25, -21)),
    ("CABINET|BUTTON_GRP|BUTTON_GEO", "Mesh", (0, 0, 0)),
    ("TABLE", "Mesh", (100, 37.5, 0)),
    ("TABLE|KEY_GRP", "Null", (-30, 39, 15)),
    ("TABLE|KEY_GRP|KEY_GEO", "Mesh", (0, 0, 0)),
    ("TABLE|WRENCH_GRP", "Null", (-30, 39, -15)),
    ("TABLE|WRENCH_GRP|WRENCH_GEO", "Mesh", (0, 0, 0)),
    ("VIEW_FRONT", "Null", (0, 0, 110)),
    ("VIEW_BACK", "Null", (0, 0, -110)),
)

#: Each mesh's box: ``{path: (width, height, depth) in cm}``.
SIZES: Dict[str, Tuple[float, float, float]] = {
    "CABINET": (60, 100, 40),
    "CABINET|DOOR_GRP|DOOR_GEO": (48, 92, 2),
    "CABINET|CABINET_LATCHES_GRP|LATCH_UPPER_GRP|LATCH_UPPER_GEO": (4, 8, 2),
    "CABINET|CABINET_LATCHES_GRP|LATCH_LOWER_GRP|LATCH_LOWER_GEO": (4, 8, 2),
    "CABINET|BOLT_GRP|BOLT_GEO": (4, 4, 6),
    "CABINET|LID_GRP|LID_GEO": (60, 2, 40),
    "CABINET|BUTTON_GRP|BUTTON_GEO": (6, 6, 3),
    "TABLE": (100, 75, 60),
    "TABLE|KEY_GRP|KEY_GEO": (3, 2, 10),
    "TABLE|WRENCH_GRP|WRENCH_GEO": (4, 2, 22),
}

#: The nodes turned from their parent's axes: ``{path: (x, y, z) degrees}``. A viewpoint
#: faces its +Z, so the front one turns to face the cabinet.
ROTATIONS: Dict[str, Tuple[float, float, float]] = {"VIEW_FRONT": (0, 180, 0)}

#: The takes, each one second on the scene's timeline: ``(name, description, curves)``,
#: a curve ``(node path, "T" or "R", ((axis, value at the start, value at the end), ...))``
#: in the node's parent's axes (cm, degrees). Each starts where the scene holds its
#: part (an importer poses the model from the first take's start) and moves the
#: cabinet alone: the tool used stays in the user's hand.
TAKES = (
    ("A01_1", "Selecting the top latch triggers Top Latch Open Animation and returns the key to hand",
     (("CABINET|CABINET_LATCHES_GRP|LATCH_UPPER_GRP", "R", (("Z", 0.0, 90.0),)),)),
    ("A01_2", "Selecting the bottom latch triggers Bottom Latch Open Animation and returns the key to hand",
     (("CABINET|CABINET_LATCHES_GRP|LATCH_LOWER_GRP", "R", (("Z", 0.0, -90.0),)),)),
    ("A02", "Selecting the door triggers Door Open Animation",
     (("CABINET|DOOR_GRP", "R", (("Y", 0.0, -100.0),)),)),
    ("B01_1", "Selecting the bolt with wrench in hand triggers Bolt Removal Animation",
     (("CABINET|BOLT_GRP", "T", (("Z", -21.0, -36.0),)),)),
    ("B01_2", "Trigger Lid Open Animation",
     (("CABINET|LID_GRP", "R", (("X", 0.0, -80.0),)),)),
)
#: The scene's frame rate: the delivery's time mode (6) and its record's ``fps``.
FPS = 30.0

#: FBX time units in a second, and the scene's rate (TimeMode 6: 30 frames a second).
SECOND = 46186158000
#: The interpolation flags and data of a linear key, as Unity's importer reads them.
_KEY_FLAGS = 24836
_KEY_DATA = (0.0, 0.0, struct.unpack("<f", struct.pack("<i", 218434821))[0], 0.0)


def _box(size: Tuple[float, float, float]) -> Tuple[List[float], List[int], List[float]]:
    """A box of *size* (width, height, depth) about its node: its vertices,
    polygon indices (the last of each face negated, as FBX ends a polygon) and
    a normal per polygon vertex (each face's own, so its edges stay hard)."""
    w, h, d = (s / 2 for s in size)
    corners = [(x, y, z) for x in (-w, w) for y in (-h, h) for z in (-d, d)]
    faces = (((0, 1, 3, 2), (-1, 0, 0)), ((4, 6, 7, 5), (1, 0, 0)), ((0, 4, 5, 1), (0, -1, 0)),
             ((2, 3, 7, 6), (0, 1, 0)), ((0, 2, 6, 4), (0, 0, -1)), ((1, 5, 7, 3), (0, 0, 1)))
    indices: List[int] = []
    normals: List[float] = []
    for face, normal in faces:
        indices += [face[0], face[1], face[2], -face[3] - 1]
        normals += [float(n) for n in normal] * 4
    return [c for corner in corners for c in corner], indices, normals


def fbx(path: Path) -> Path:
    """Write the delivery: the nodes, a box per mesh, one take per entry of
    :data:`TAKES`, and the carrier's ``animation`` record naming each take's
    description (the shots' as an exporter writes them)."""
    import pythontk as ptk

    FbxNode, FbxWriter = ptk.FbxNode, ptk.FbxWriter
    i64 = FbxWriter.i64
    ids: Dict[str, int] = {}
    objects, links = FbxNode("Objects"), FbxNode("Connections")
    next_id = [1000]

    def new_id() -> int:
        next_id[0] += 1
        return next_id[0]

    def model(path_: str, kind: str, at, extra=None) -> None:
        ids[path_] = new_id()
        name = path_.rsplit("|", 1)[-1]
        node = objects.add("Model", i64(ids[path_]), f"{name}\x00\x01Model", kind)
        node.add("Version", 232)
        props = node.add("Properties70")
        props.p("Lcl Translation", "Lcl Translation", "", "A", float(at[0]), float(at[1]), float(at[2]))
        if path_ in ROTATIONS:
            turn = ROTATIONS[path_]
            props.p("Lcl Rotation", "Lcl Rotation", "", "A", float(turn[0]), float(turn[1]), float(turn[2]))
        if extra:
            for key, value in extra.items():
                props.p(key, "KString", "", "U", value)
        node.add("Shading", True)
        node.add("Culling", "CullingOff")
        parent = ids[path_.rsplit("|", 1)[0]] if "|" in path_ else 0
        links.add("C", "OO", i64(ids[path_]), i64(parent))
        if kind == "Mesh":
            vertices, indices, normals = _box(SIZES[path_])
            geometry_id = new_id()
            geometry = objects.add("Geometry", i64(geometry_id), "\x00\x01Geometry", "Mesh")
            geometry.add("Vertices", FbxWriter.array("d", vertices))
            geometry.add("PolygonVertexIndex", FbxWriter.array("i", indices))
            geometry.add("GeometryVersion", 124)
            layer = geometry.add("LayerElementNormal", 0)
            layer.add("Version", 101)
            layer.add("Name", "")
            layer.add("MappingInformationType", "ByPolygonVertex")
            layer.add("ReferenceInformationType", "Direct")
            layer.add("Normals", FbxWriter.array("d", normals))
            element = geometry.add("Layer", 0)
            element.add("Version", 100)
            element = element.add("LayerElement")
            element.add("Type", "LayerElementNormal")
            element.add("TypedIndex", 0)
            links.add("C", "OO", i64(geometry_id), i64(ids[path_]))

    for path_, kind, at in NODES:
        model(path_, kind, at)
    shots = [{"clip": name, "description": text} for name, text, _ in TAKES]
    record = ptk.SceneRecords.SHOTS.make({"shots": shots, "fps": FPS})  # the record's own version, stamped
    model("data_export", "Null", (0, 0, 0), {"animation": record.text})

    takes = FbxNode("Takes")
    takes.add("Current", "")
    for index, (name, _, curves) in enumerate(TAKES):
        start, stop = i64(index * SECOND), i64((index + 1) * SECOND)
        stack_id, layer_id = new_id(), new_id()
        stack = objects.add("AnimationStack", i64(stack_id), f"{name}\x00\x01AnimStack", "")
        sp = stack.add("Properties70")
        for key in ("LocalStart", "ReferenceStart"):
            sp.p(key, "KTime", "Time", "", start)
        for key in ("LocalStop", "ReferenceStop"):
            sp.p(key, "KTime", "Time", "", stop)
        objects.add("AnimationLayer", i64(layer_id), "BaseLayer\x00\x01AnimLayer", "")
        links.add("C", "OO", i64(layer_id), i64(stack_id))
        for node, channel, keyed in curves:
            # One curve node per property, its unkeyed axes held at the node's rest.
            rest = dict(zip("XYZ", (0.0, 0.0, 0.0)))
            if channel == "T":
                rest = dict(zip("XYZ", (float(v) for v in next(n[2] for n in NODES if n[0] == node))))
            elif node in ROTATIONS:
                rest = dict(zip("XYZ", (float(v) for v in ROTATIONS[node])))
            for axis, a, _ in keyed:
                rest[axis] = a
            curve_node_id = new_id()
            curve_node = objects.add("AnimationCurveNode", i64(curve_node_id), f"{channel}\x00\x01AnimCurveNode", "")
            cp = curve_node.add("Properties70")
            for ax in "XYZ":
                cp.p(f"d|{ax}", "Number", "", "A", float(rest[ax]))
            property_name = "Lcl Translation" if channel == "T" else "Lcl Rotation"
            links.add("C", "OO", i64(curve_node_id), i64(layer_id))
            links.add("C", "OP", i64(curve_node_id), i64(ids[node]), property_name)
            for axis, a, b in keyed:
                curve_id = new_id()
                curve = objects.add("AnimationCurve", i64(curve_id), "\x00\x01AnimCurve", "")
                curve.add("Default", float(a))
                curve.add("KeyVer", 4009)
                curve.add("KeyTime", FbxWriter.array("l", [index * SECOND, (index + 1) * SECOND]))
                curve.add("KeyValueFloat", FbxWriter.array("f", [float(a), float(b)]))
                curve.add("KeyAttrFlags", FbxWriter.array("i", [_KEY_FLAGS]))
                curve.add("KeyAttrDataFloat", FbxWriter.array("f", list(_KEY_DATA)))
                curve.add("KeyAttrRefCount", FbxWriter.array("i", [2]))
                links.add("C", "OP", i64(curve_id), i64(curve_node_id), f"d|{axis}")
        take = takes.add("Take", name)
        take.add("FileName", f"{name}.tak")
        take.add("LocalTime", start, stop)
        take.add("ReferenceTime", start, stop)

    settings = FbxNode("GlobalSettings")
    settings.add("Version", 1000)
    gp = settings.add("Properties70")
    for key, value in (("UpAxis", 1), ("UpAxisSign", 1), ("FrontAxis", 2), ("FrontAxisSign", 1),
                       ("CoordAxis", 0), ("CoordAxisSign", 1)):
        gp.p(key, "int", "Integer", "", value)
    gp.p("UnitScaleFactor", "double", "Number", "", 1.0)
    gp.p("TimeMode", "enum", "", "", 6)  # 30 frames a second: FPS
    gp.p("TimeSpanStart", "KTime", "Time", "", i64(0))
    gp.p("TimeSpanStop", "KTime", "Time", "", i64(len(TAKES) * SECOND))
    # The sections an FBX reader asks for beside the objects, as pythontk's glTF
    # converter writes them (FBX SDK readers import nothing without them).
    documents = FbxNode("Documents")
    documents.add("Count", 1)
    document = documents.add("Document", i64(new_id()), "Scene", "Scene")
    document.add("Properties70").p("ActiveAnimStackName", "KString", "", "", TAKES[0][0])
    document.add("RootNode", i64(0))
    counts: Dict[str, int] = {}
    for record in objects.children:
        counts[record.name] = counts.get(record.name, 0) + 1
    definitions = FbxNode("Definitions")
    definitions.add("Version", 100)
    definitions.add("Count", 1 + sum(counts.values()))
    definitions.add("ObjectType", "GlobalSettings").add("Count", 1)
    for kind, count in counts.items():
        definitions.add("ObjectType", kind).add("Count", count)
    records = FbxWriter.header_records("unitytk tasks sample") + [
        settings, documents, FbxNode("References"), definitions, objects, links, takes,
    ]
    return Path(FbxWriter.write(str(path), records))


def build(out_dir) -> List[str]:
    """Write ``cabinet.csv``, ``cabinet.fbx`` and ``cabinet.plan.json`` into
    *out_dir*; the plan is read from the other two, as a user reads theirs,
    by the workspace's unitytk checkout (``sync_unity_contracts.CHECKOUTS``)."""
    # Puts pythontk's and unitytk's checkouts on sys.path (unitytk imports
    # pythontk), as for the script's own reads of unitytk's declarations.
    import sync_unity_contracts  # noqa: F401
    from unitytk.sheets import SheetPlan

    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    sheet = folder / "cabinet.csv"
    sheet.write_bytes(SHEET.encode("utf-8"))
    model = fbx(folder / "cabinet.fbx")
    plan = folder / "cabinet.plan.json"
    SheetPlan.from_sheet(str(sheet), str(model), mapping="interactive").write(plan)
    return [sheet.name, model.name, plan.name]
