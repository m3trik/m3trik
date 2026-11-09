"""The Materials sample: four spheres, one material each, stated as literal glTF.

The scene a person makes with Maya's own shaders and the Scene Exporter: a
Standard Surface with colour, metalness, roughness and normal maps; one that
glows at four times its colour (emission above 1, which glTF carries as
``KHR_materials_emissive_strength``); a Surface Shader (unlit:
``KHR_materials_unlit``); and one whose colour map is tiled and offset by its
``place2dTexture`` (``KHR_texture_transform``), exported with the data node
on. The exporter packs the metalness and roughness maps into one image in
glTF's layout and embeds every image the ``materials`` record names; unitytk's
MaterialsImporter writes each material through the pipeline's own Lit,
repacking that image into Unity's mask. Its Edit Mode tests
(``Features/Materials/Tests/MaterialsSampleTests.cs``) state the same
materials. The textures are tiny and synthetic, written with the standard
library alone (``_images.write_png``).
"""

from unity_samples._images import write_png


NAME = "Materials"
DESCRIPTION = (
    "Four spheres, one glTF material each, written onto the render pipeline's own Lit: "
    "colour, metal / roughness (repacked into Unity's mask) and normal maps; an emission "
    "four times its colour; an unlit colour; and a tiled, offset colour map. The demo "
    "scene lines them up under a light."
)
#: The records the Materials feature reads (its MaterialsImporter): the sample
#: is described, and held to its recipe, by these and the delivery's structure.
RECORDS = ("materials",)
#: The exported file's stem (``Materials.fbx``).
MODEL = "Materials"
#: The spheres' radius and spacing (centimetres).
RADIUS, SPACING = 40.0, 120.0
#: The textures' size (texels a side).
SIZE = 16
#: The glow's colour and its strength (emission above 1).
GLOW = ((1.0, 0.5, 0.2), 4.0)
#: The unlit sphere's colour.
FLAT = (0.2, 0.6, 1.0)
#: The tiled map's ``place2dTexture``: repeat and offset (Maya's UV space).
TILING = ((3.0, 2.0), (0.25, 0.5))


def write_textures(folder: str) -> dict:
    """The sample's textures in *folder*, by role: a two-colour checker, a metal
    map (metal on the left half), a roughness ramp (smooth at the top), a normal
    map with one bevelled band, and the tiled sphere's stripes.

    Returns:
        ``{role: path}``.
    """
    import os

    half = SIZE // 2

    def checker(x, y):
        return (230, 180, 60, 255) if (x // 4 + y // 4) % 2 else (60, 90, 200, 255)

    def metal(x, y):
        v = 255 if x < half else 0
        return (v, v, v, 255)

    def rough(x, y):
        v = int(round(255 * y / (SIZE - 1)))
        return (v, v, v, 255)

    def normal(x, y):
        # A band across the middle tilted toward +X: tangent space, +Y up.
        return (180, 128, 230, 255) if half - 2 <= y < half + 2 else (128, 128, 255, 255)

    def stripes(x, y):
        return (240, 240, 240, 255) if x % 4 < 2 else (200, 30, 30, 255)

    paths = {
        "base": "Metal_BaseColor.png", "metal": "Metal_Metallic.png", "rough": "Metal_Roughness.png",
        "normal": "Metal_Normal.png", "tiled": "Tiled_BaseColor.png",
    }
    pixels = {"base": checker, "metal": metal, "rough": rough, "normal": normal, "tiled": stripes}
    return {role: write_png(os.path.join(folder, name), pixels[role], SIZE) for role, name in paths.items()}


def build(out_dir: str, surface: str = "standardSurface") -> list:
    """Make the scene and export it into *out_dir* through the Scene Exporter.

    Parameters:
        out_dir: Where the export goes.
        surface: The node type of the three PBR materials: the sample's
            ``standardSurface``, or a twin's (the workspace's end-to-end
            suite delivers it again with Arnold's ``aiStandardSurface``,
            which shares its attributes).

    Returns:
        The names of the files written: ``["Materials.fbx"]`` (its images ride
        inside it).

    Raises:
        RuntimeError: The export reported a failure (its log says why).
    """
    import os

    import maya.cmds as cmds
    import mayatk as mtk

    # The textures' sources live in the project's sourceimages, outside the
    # delivery, as a person's do: the export embeds them from there, and the
    # metal / roughness image it packs from them -- a delivery file of the
    # pack store, written nowhere in the project -- with them.
    project = os.path.join(out_dir, "_project")
    mtk.EnvUtils.create_workspace(project, rules={"sourceImages": "sourceimages", "scene": "scenes"})
    mtk.EnvUtils.set_current_workspace(project)
    sources = os.path.join(project, "sourceimages")
    os.makedirs(sources, exist_ok=True)
    maps = write_textures(sources)

    def sphere(name, index):
        node = cmds.polySphere(name=name, radius=RADIUS, subdivisionsX=24, subdivisionsY=16)[0]
        cmds.move((index - 1.5) * SPACING, RADIUS, 0, node)
        return node

    def material(node, kind, name):
        shader = cmds.shadingNode(kind, asShader=True, name=name)
        group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
        cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
        cmds.sets(node, edit=True, forceElement=group)
        return shader

    def texture(path, name, raw, repeat=(1.0, 1.0), offset=(0.0, 0.0)):
        node = cmds.shadingNode("file", asTexture=True, isColorManaged=True, name=name)
        place = cmds.shadingNode("place2dTexture", asUtility=True, name=name + "_place")
        for attr in ("coverage", "translateFrame", "rotateFrame", "mirrorU", "mirrorV", "stagger", "wrapU",
                     "wrapV", "repeatUV", "offset", "rotateUV", "noiseUV", "vertexUvOne", "vertexUvTwo",
                     "vertexUvThree", "vertexCameraOne"):
            cmds.connectAttr(f"{place}.{attr}", f"{node}.{attr}")
        cmds.connectAttr(place + ".outUV", node + ".uvCoord")
        cmds.connectAttr(place + ".outUvFilterSize", node + ".uvFilterSize")
        cmds.setAttr(node + ".fileTextureName", path, type="string")
        if raw:
            cmds.setAttr(node + ".ignoreColorSpaceFileRules", 1)
            cmds.setAttr(node + ".colorSpace", "Raw", type="string")
        cmds.setAttr(place + ".repeatUV", *repeat, type="double2")
        cmds.setAttr(place + ".offset", *offset, type="double2")
        return node

    spheres = [sphere(name, i) for i, name in enumerate(("Metal", "Glow", "Flat", "Tiled"))]

    metal = material(spheres[0], surface, "Metal_MAT")
    cmds.connectAttr(texture(maps["base"], "Metal_base", False) + ".outColor", metal + ".baseColor")
    cmds.connectAttr(texture(maps["metal"], "Metal_metal", True) + ".outColorR", metal + ".metalness")
    cmds.connectAttr(texture(maps["rough"], "Metal_rough", True) + ".outColorR", metal + ".specularRoughness")
    bump = cmds.shadingNode("bump2d", asUtility=True, name="Metal_bump")
    cmds.setAttr(bump + ".bumpInterp", 1)  # tangent-space normals
    cmds.connectAttr(texture(maps["normal"], "Metal_normal", True) + ".outAlpha", bump + ".bumpValue")
    cmds.connectAttr(bump + ".outNormal", metal + ".normalCamera")

    glow = material(spheres[1], surface, "Glow_MAT")
    (r, g, b), strength = GLOW
    cmds.setAttr(glow + ".baseColor", 0.05, 0.05, 0.05, type="double3")
    cmds.setAttr(glow + ".emissionColor", r, g, b, type="double3")
    cmds.setAttr(glow + ".emission", strength)

    flat = material(spheres[2], "surfaceShader", "Flat_MAT")
    cmds.setAttr(flat + ".outColor", *FLAT, type="double3")

    tiled = material(spheres[3], surface, "Tiled_MAT")
    repeat, offset = TILING
    cmds.connectAttr(texture(maps["tiled"], "Tiled_base", False, repeat, offset) + ".outColor", tiled + ".baseColor")
    cmds.setAttr(tiled + ".specularRoughness", 0.6)

    exporter = mtk.SceneExporter(log_level="WARNING")
    exporter.confirm = lambda question: False
    if not exporter.perform_export(
        export_dir=out_dir,
        objects=spheres,
        output_name=MODEL,
        tasks={"export_data_node": True},
    ):
        raise RuntimeError(f"the Scene Exporter wrote no {MODEL}.fbx; its log above says why")
    return [f"{MODEL}.fbx"]
