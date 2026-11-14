"""The ShadowPlane sample made in Blender: Z up, its FBX writer turning only the roots upright.

The Maya recipe's scene (``unity_samples/shadow_plane.py``: the ground, the
box, the chair and the awning, the lamp's sweep, the sun, one rig each) built
with bpy and blendertk's Shadow Rig and exported through blendertk's Scene
Exporter. The scene's unit is the recipe's centimetre (``scale_length``
0.01), so the record states the sample's lengths. Blender is Z up and its
FBX writer turns only the root nodes upright, so every plane and contact
below them reaches Unity in its Blender-local frame: ``ShadowPlaneSampleTests``
passing on this delivery proves the importer and the component read that
frame -- each plane bound to its target, light, contact and delivered map,
placed and faded where the model puts it, at the file's own pose where Blender
put it, the sun shining as it did, the demo's planes drawing, and Unity's
rebake of each map equal to the delivered one -- the awning's post and slab,
which Unity's import of this file puts a float apart, one span.
"""

NAME = "BlenderShadowPlane"
SAMPLE = "ShadowPlane"
PRODUCER = "blender"


def build(out_dir: str) -> list:
    """Make the ShadowPlane scene in Blender and export it into *out_dir*.

    Returns:
        ``["ShadowPlane.fbx"]`` (its horizon maps and silhouettes ride inside it).

    Raises:
        RuntimeError: The export reported a failure, or a plane carries no horizon map.
    """
    import math
    import os

    import bmesh
    import bpy
    from mathutils import Euler, Matrix

    import blendertk as btk
    from unity_samples import shadow_plane as recipe

    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = 24, 1.0
    scene.frame_start, scene.frame_end = recipe.FRAMES
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 0.01  # one unit is the recipe's centimetre
    scene.frame_set(recipe.FRAMES[0])
    # The rigs write their maps into the file's project, outside the delivery,
    # as a person's do: the export embeds them from there.
    project = os.path.join(out_dir, "_project")
    os.makedirs(project, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(project, f"{recipe.MODEL}.blend"))

    def at(x, y, z):
        """Maya's (x, y, z), Y up, as Blender's, Z up."""
        return (x, -z, y)

    def surface(name, base):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*base, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.6
        return mat

    def solid(name, boxes, origin):
        """One mesh object of *boxes* (``(size, centre)``, Maya's terms), its
        origin at *origin* (Maya's terms), as the recipe's ``_united`` leaves it."""
        data = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bm.loops.layers.uv.new("UVMap")
        pivot = at(*origin)
        for (sx, sy, sz), centre in boxes:
            made = bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)["verts"]
            bmesh.ops.scale(bm, vec=(sx, sz, sy), verts=made)
            c = at(*centre)
            bmesh.ops.translate(bm, vec=tuple(c[i] - pivot[i] for i in range(3)), verts=made)
        bm.to_mesh(data)
        bm.free()
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = pivot
        return obj

    data = bpy.data.meshes.new("Ground")
    bm = bmesh.new()
    bm.loops.layers.uv.new("UVMap")
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=recipe.GROUND / 2.0, calc_uvs=True)
    bm.to_mesh(data)
    bm.free()
    ground = bpy.data.objects.new("Ground", data)
    scene.collection.objects.link(ground)
    ground.data.materials.append(surface("Ground_MAT", (0.7, 0.7, 0.68)))

    side, (bx, bz) = recipe.BOX
    box = solid("Box", [((side, side, side), (bx, side / 2.0, bz))], (bx, side / 2.0, bz))

    cx, cz = recipe.CHAIR_AT
    seat, top, thick = recipe.SEAT
    under = top - thick
    reach = seat / 2.0 - recipe.LEG / 2.0
    parts = [((seat, thick, seat), (cx, top - thick / 2.0, cz))]
    for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        parts.append(((recipe.LEG, under, recipe.LEG), (cx + sx * reach, under / 2.0, cz + sz * reach)))
    parts.append(((seat, recipe.BACK, recipe.LEG), (cx, top + recipe.BACK / 2.0, cz - reach)))
    chair = solid("Chair", parts, (cx, 0.0, cz))

    ax, az = recipe.AWNING_AT
    post, tall = recipe.POST
    width, depth, slab = recipe.SLAB
    parts = [
        ((post, tall, post), (ax, tall / 2.0, az)),
        ((width, slab, depth), (ax + recipe.REACH, tall + slab / 2.0, az)),
    ]
    # The footprint's centre, as the recipe's _united pivots it.
    xs = [ax - post / 2.0, ax + post / 2.0, ax + recipe.REACH - width / 2.0, ax + recipe.REACH + width / 2.0]
    zs = [az - post / 2.0, az + post / 2.0, az - depth / 2.0, az + depth / 2.0]
    awning = solid("Awning", parts, ((min(xs) + max(xs)) / 2.0, 0.0, (min(zs) + max(zs)) / 2.0))

    objects = [box, chair, awning]
    prop = surface("Prop_MAT", (0.55, 0.35, 0.22))
    for obj in objects:
        obj.data.materials.append(prop)

    lamp_data = bpy.data.lights.new("Lamp", "POINT")
    lamp_data.shadow_soft_size = 0.0  # Maya's point light: a point
    lamp = bpy.data.objects.new("Lamp", lamp_data)
    scene.collection.objects.link(lamp)
    for frame, where in recipe.LAMP_KEYS:
        lamp.location = at(*where)
        lamp.keyframe_insert("location", frame=frame)
    for fcurve in btk.AnimUtils.get_fcurves([lamp]):
        for key in fcurve.keyframe_points:
            key.interpolation = "LINEAR"
    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.angle = 0.0  # Maya's directional light: parallel rays
    sun = bpy.data.objects.new("Sun", sun_data)
    scene.collection.objects.link(sun)
    # Both lights shine along their own -Z: Maya's turn, seen from Z up.
    turn = Matrix.Rotation(math.radians(90.0), 4, "X") @ Euler(
        [math.radians(a) for a in recipe.SUN_ROTATION], "XYZ"
    ).to_matrix().to_4x4()
    sun.matrix_world = Matrix.Translation(at(0.0, 400.0, 0.0)) @ turn
    scene.frame_set(recipe.FRAMES[0])

    nodes = {"Box": box, "Chair": chair, "Awning": awning}
    rigs = [
        btk.ShadowRig.create([nodes[target]], source_name=source, texture_res=recipe.SILHOUETTE, rig_type=kind)
        for target, source, kind in recipe.RIGS
    ]
    unbaked = [r.shadow_plane.name for r in rigs if not (r.horizon_path and os.path.isfile(r.horizon_path))]
    if unbaked:
        raise RuntimeError(f"no horizon map baked for {unbaked}")
    exporter = btk.SceneExporter(log_level="WARNING")
    exporter.confirm = lambda question: False
    # The recipe's export set: each node ships its hierarchy, as Maya's does.
    if not exporter.perform_export(
        export_dir=out_dir,
        objects=[ground, *objects, lamp, sun, *(r.group for r in rigs)],
        output_name=recipe.MODEL,
        tasks={"export_data_node": True},
    ):
        raise RuntimeError(f"the Scene Exporter wrote no {recipe.MODEL}.fbx; its log above says why")
    return [f"{recipe.MODEL}.fbx"]
