"""The Lightmaps sample: three boxes on a floor, lit by a lightmap set baked elsewhere, with its reflection probe.

The scene a person makes with Maya's Lightmap Baker and the Scene Exporter,
exported with the data node on: a floor and three boxes, each given a
lightmap UV set at index 1 (``UvUtils.create_lightmap_uvs``), lit by a bake
committed as the Lightmap Baker commits one made elsewhere
(``LightmapBaker.commit_lightmap``): the floor by a map of its own, the three
boxes by one atlas, each its own rect in it (``scaleOffset``). The room's
reflection probe, a panorama seen from one point in the room's box, is
recorded as the baker records its own (``LightmapRecords.commit_probe``), and
one point light hangs over the floor: the light the bake is lit by, which the
record's ``lights`` carry and the export draws into the probe. The maps and
the probe are tiny synthetic EXRs (linear light, written with OpenCV through
``ptk.ImgUtils.cv2_write``): a real Arnold bake would make the sample hang
on a renderer and its licence.

What the delivery holds and who reads it:

- **Unity reads** the maps (``objects``: each object's map and rect, read
  through its second UV set, applied as stored) and the probe (``probe``: its
  map, position and box). The probe's map is the one the export delivers,
  ``Lightmaps_Probe_Lights.hdr``: the panorama with the light drawn in as the
  capture point sees it, so a reader of the probe alone still sees its
  highlight. unitytk's LightmapsImporter gives the model's root a Lightmap
  Set holding each renderer with its map and rect, and the probe as a native
  box-projected ReflectionProbe; its Edit Mode tests
  (``Features/Lightmaps/Tests/LightmapsSampleTests.cs``) state the same.
- **Unity ignores** ``lights`` and ``probe.highlights`` (the complete copies
  of the probe per group of receivers): the WebXR viewer's extensions. Unity
  picks a reflection probe by volume, not per renderer, and has no light that
  adds its specular alone; the light itself is not exported, so it lights
  nothing in Unity a second time.
"""

NAME = "Lightmaps"
DESCRIPTION = (
    "Three boxes on a floor lit by a lightmap set baked elsewhere: the floor's own map and the boxes' "
    "shared atlas, each box its own rect, read through the second UV set and bound by a Lightmap Set "
    "through Unity's native lightmap fields; and the bake's reflection probe, a box-projected Reflection "
    "Probe whose panorama holds the bake's light. The demo scene shows them lit by the set alone."
)
#: The record the Lightmaps feature reads (its LightmapsImporter): the sample
#: is described, and held to its recipe, by it and the delivery's structure.
RECORDS = ("lightmaps",)
#: The exported file's stem (``Lightmaps.fbx``); the probe is named after the
#: scene, as the baker names it (``<scene>_Probe.exr``).
MODEL = "Lightmaps"
#: The floor's side (centimetres, Y up, centred on the origin).
FLOOR = 400.0
#: Each box: ``(name, size, (x, z), material)``, standing on the floor.
BOXES = (
    ("Box_A", 60.0, (-100.0, -40.0), "Box_MAT"),
    ("Box_B", 40.0, (80.0, -70.0), "Box_MAT"),
    ("Box_C", 80.0, (30.0, 100.0), "Metal_MAT"),
)
#: Each box's rect in the atlas, ``[scaleX, scaleY, offsetX, offsetY]``
#: (Unity's ``lightmapScaleOffset``: uv2 * scale + offset, v up): a quarter each.
RECTS = {
    "Box_A": [0.5, 0.5, 0.0, 0.0],
    "Box_B": [0.5, 0.5, 0.5, 0.0],
    "Box_C": [0.5, 0.5, 0.0, 0.5],
}
#: The map files: the floor's own and the boxes' atlas.
FLOOR_MAP, BOX_ATLAS = "Floor_Lightmap.exr", "Boxes_Lightmap.exr"
#: The maps' size (texels a side).
MAP_SIZE = 64
#: The probe: its file (the baker's name for a scene called ``Lightmaps``),
#: where it was captured and the room's box it projects onto (centimetres).
PROBE = "Lightmaps_Probe.exr"
PROBE_AT = (40.0, 100.0, -30.0)
PROBE_BOX = ((-250.0, 0.0, -200.0), (200.0, 300.0, 220.0))
#: The panorama's width (twice its height: equirectangular).
PROBE_WIDTH = 64
#: The light over the floor: its position (centimetres), intensity (Arnold's
#: quadratic falloff: the irradiance at one centimetre, so 1.0 on the floor
#: under it, as the maps hold it) and colour.
LAMP_AT = (0.0, 220.0, 0.0)
LAMP_INTENSITY = LAMP_AT[1] ** 2
LAMP_COLOR = (1.0, 0.92, 0.8)
#: The light the maps hold beside the lamp's: the room's bounce, flat.
AMBIENT = 0.12


def _irradiance(distance: float, height: float) -> float:
    """The lamp's irradiance on a level surface *distance* (centimetres,
    along the surface) from the point under it, *height* below it, in the
    maps' units (1.0 under it at :data:`LAMP_AT`'s height over the floor)."""
    return LAMP_AT[1] ** 2 * height / (height**2 + distance**2) ** 1.5


def lightmap_pixels() -> dict:
    """Each map's linear RGB texels, rows top-down, ``MAP_SIZE`` a side:
    ``{file name: float32 array (MAP_SIZE, MAP_SIZE, 3)}``.

    - :data:`FLOOR_MAP`: the lamp's falloff over the floor (the floor's
      lightmap UVs span its square) and the room's bounce;
    - :data:`BOX_ATLAS`: each box's quarter (:data:`RECTS`, v up) at the
      lamp's irradiance over its top, softened toward the quarter's edges
      (its faces' contact with the floor), the fourth quarter empty.
    """
    import numpy as np

    n = MAP_SIZE
    colour = np.asarray(LAMP_COLOR, np.float32)
    # Texel centres in UV (v up: row 0 is the map's top).
    u = (np.arange(n, dtype=np.float64) + 0.5) / n
    uu, vv = np.meshgrid(u, 1.0 - u)

    x, z = (uu - 0.5) * FLOOR, (vv - 0.5) * FLOOR
    floor = AMBIENT + _irradiance(np.hypot(x - LAMP_AT[0], z - LAMP_AT[2]), LAMP_AT[1])
    atlas = np.zeros((n, n), np.float64)
    for name, size, (bx, bz), _material in BOXES:
        sx, sy, ox, oy = RECTS[name]
        inside = (uu >= ox) & (uu < ox + sx) & (vv >= oy) & (vv < oy + sy)
        top = _irradiance(float(np.hypot(bx - LAMP_AT[0], bz - LAMP_AT[2])), LAMP_AT[1] - size)
        # 1 at the quarter's middle, 0.6 at its rim.
        cu, cv = (uu - ox) / sx - 0.5, (vv - oy) / sy - 0.5
        soft = 1.0 - 0.4 * np.clip(np.maximum(abs(cu), abs(cv)) * 2.0, 0.0, 1.0) ** 2
        atlas = np.where(inside, AMBIENT + top * soft, atlas)
    return {
        FLOOR_MAP: (floor[:, :, None] * colour).astype(np.float32),
        BOX_ATLAS: (atlas[:, :, None] * colour).astype(np.float32),
    }


def probe_pixels():
    """The room seen from :data:`PROBE_AT`, equirectangular (rows top-down,
    ``PROBE_WIDTH`` x half of it, linear RGB float32): a dim ceiling, warm
    walls brightest at the horizon, a grey floor, and a bright window in
    one wall. The lamp is not in it: the export draws it in."""
    import numpy as np

    w, h = PROBE_WIDTH, PROBE_WIDTH // 2
    elevation = (0.5 - (np.arange(h) + 0.5) / h) * np.pi  # +pi/2 at the top row
    azimuth = ((np.arange(w) + 0.5) / w) * 2.0 * np.pi - np.pi
    el, az = np.meshgrid(elevation, azimuth, indexing="ij")
    up = np.sin(el)[:, :, None]
    ceiling = np.asarray((0.25, 0.25, 0.27), np.float32)
    walls = np.asarray((0.55, 0.48, 0.40), np.float32)
    floor = np.asarray((0.30, 0.30, 0.30), np.float32)
    sky = np.where(up > 0, ceiling * up + walls * (1.0 - up), floor * -up + walls * (1.0 + up))
    window = (np.abs(az) < 0.35) & (el > 0.1) & (el < 0.6)
    sky = np.where(window[:, :, None], np.asarray((2.0, 2.1, 2.3), np.float32), sky)
    return sky.astype(np.float32)


def write_exr(path: str, pixels) -> str:
    """*pixels* (linear RGB float32, rows top-down) as a half-float EXR at
    *path* (``ptk.ImgUtils.cv2_write``: OpenCV's EXR codec, which pythontk
    enables on import).

    Returns:
        *path*.

    Raises:
        OSError: OpenCV wrote nothing.
    """
    import pythontk as ptk  # first: it enables OpenCV's EXR codec
    import cv2

    bgr = pixels[:, :, ::-1].copy()
    if not ptk.ImgUtils.cv2_write(path, bgr, [cv2.IMWRITE_EXR_TYPE, cv2.IMWRITE_EXR_TYPE_HALF]):
        raise OSError(f"no EXR written at {path}")
    return path


def build(out_dir: str) -> list:
    """Make the scene and export it into *out_dir* through the Scene Exporter.

    Returns:
        The names of the files written: ``["Lightmaps.fbx"]`` (its maps and
        probe ride inside it).

    Raises:
        RuntimeError: The export reported a failure (its log says why), or
            a commit recorded less than it was given.
    """
    import os

    import maya.cmds as cmds
    import mayatk as mtk

    # The bake's files live in the project's sourceimages/lightmaps, outside
    # the delivery, where the Lightmap Baker writes its own: the export embeds
    # them from there.
    project = os.path.join(out_dir, "_project")
    mtk.EnvUtils.create_workspace(project, rules={"sourceImages": "sourceimages", "scene": "scenes"})
    mtk.EnvUtils.set_current_workspace(project)
    folder = os.path.join(project, "sourceimages", "lightmaps")
    os.makedirs(folder, exist_ok=True)
    maps = {name: write_exr(os.path.join(folder, name), pixels) for name, pixels in lightmap_pixels().items()}
    probe = write_exr(os.path.join(folder, PROBE), probe_pixels())

    def surface(name, base, roughness, metalness=0.0):
        shader = cmds.shadingNode("standardSurface", asShader=True, name=name)
        cmds.setAttr(shader + ".baseColor", *base, type="double3")
        cmds.setAttr(shader + ".specularRoughness", roughness)
        cmds.setAttr(shader + ".metalness", metalness)
        return shader

    materials = {
        "Floor_MAT": surface("Floor_MAT", (0.6, 0.6, 0.6), 0.8),
        "Box_MAT": surface("Box_MAT", (0.8, 0.45, 0.25), 0.5),
        "Metal_MAT": surface("Metal_MAT", (0.9, 0.9, 0.92), 0.25, metalness=1.0),
    }
    floor = cmds.polyPlane(name="Floor", width=FLOOR, height=FLOOR, subdivisionsX=1, subdivisionsY=1)[0]
    mtk.MatUtils.assign_mat([floor], materials["Floor_MAT"])
    boxes = []
    for name, size, (x, z), material in BOXES:
        box = cmds.polyCube(name=name, width=size, height=size, depth=size)[0]
        cmds.move(x, size / 2, z, box)
        mtk.MatUtils.assign_mat([box], materials[material])
        boxes.append(box)
    objects = [floor] + boxes
    cmds.delete(objects, constructionHistory=True)

    # The lightmap UVs: a packed set at index 1, where Unity and three.js read them.
    mtk.UvUtils.create_lightmap_uvs(objects, freeze_history=True, quiet=True)

    # The lamp the bake is lit by: the record's ``lights`` carry it, the
    # export draws it into the probe. Not exported itself.
    shape = cmds.pointLight(intensity=LAMP_INTENSITY, rgb=LAMP_COLOR)
    lamp = cmds.rename(cmds.listRelatives(shape, parent=True)[0], "Lamp")
    cmds.move(*LAMP_AT, lamp)

    # The bake, committed as the Lightmap Baker commits one made elsewhere,
    # and its probe as the baker records its own.
    mapping = {floor: maps[FLOOR_MAP]}
    mapping.update({box: maps[BOX_ATLAS] for box in boxes})
    recorded = mtk.LightmapBaker().commit_lightmap(mapping, scale_offsets=RECTS)
    if len(recorded) != len(mapping):
        raise RuntimeError(f"the commit recorded {sorted(recorded)} of {sorted(mapping)}")
    mtk.LightmapRecords.commit_probe(probe, PROBE_AT, [list(c) for c in PROBE_BOX])

    exporter = mtk.SceneExporter(log_level="WARNING")
    exporter.confirm = lambda question: False
    if not exporter.perform_export(
        export_dir=out_dir,
        objects=objects,
        output_name=MODEL,
        tasks={"export_data_node": True},
    ):
        raise RuntimeError(f"the Scene Exporter wrote no {MODEL}.fbx; its log above says why")
    return [f"{MODEL}.fbx"]
