"""The RenderEffects sample made in Blender: fade, pulse, a keyed blink and a lamp group.

The Maya recipe's scene (``unity_samples/render_effects.py``: its shots,
fades, pulses, blink, lamp group and emission map) built with bpy and
blendertk -- Principled BSDF materials, the panel's blink keyed on
``hide_viewport`` and ``hide_render`` -- and exported through blendertk's
Scene Exporter, so ``RenderEffectsSampleTests`` passing on this delivery
proves Blender's channels: the box's Fade and the sphere's Highlight on their
curve proxies, the blink as the panel's own stepped active state, the lamp
group's weight as an Emission Track on its copy material, and the emission
map embedded and bound.
"""

NAME = "BlenderRenderEffects"
SAMPLE = "RenderEffects"
PRODUCER = "blender"


def build(out_dir: str) -> list:
    """Make the RenderEffects scene in Blender and export it into *out_dir*.

    Returns:
        ``["RenderEffects.fbx"]`` (its image rides inside it).

    Raises:
        RuntimeError: The export reported a failure (its log says why).
    """
    import os

    import bmesh
    import bpy

    import blendertk as btk
    from unity_samples import render_effects as recipe

    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = 24, 1.0
    scene.frame_start, scene.frame_end = recipe.SHOTS[0][1], recipe.SHOTS[-1][2]
    # The map's source lives outside the delivery, as a person's does: the export embeds it.
    sources = os.path.join(out_dir, "_project", "sourceimages")
    os.makedirs(sources, exist_ok=True)
    emission_map = recipe.write_emission_map(os.path.join(sources, "Sphere_Emission.png"))

    def surface(name, base, emission=0.0, glow=(1.0, 1.0, 1.0), image=None):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*base, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.5
        bsdf.inputs["Emission Strength"].default_value = emission
        bsdf.inputs["Emission Color"].default_value = (*glow, 1.0)
        if image is not None:
            node = mat.node_tree.nodes.new("ShaderNodeTexImage")
            node.image = bpy.data.images.load(image)
            mat.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Emission Color"])
        return mat

    def mesh(name, make, at):
        data = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bm.loops.layers.uv.new("UVMap")  # each primitive lays its UVs out, as Maya's do
        make(bm)
        bm.to_mesh(data)
        bm.free()
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = at
        return obj

    # Maya's centimetres, Y up, in Blender's metres, Z up: Maya (x, y, z) is Blender (x, -z, y).
    size, spacing, up = recipe.SIZE / 100.0, recipe.SPACING / 100.0, recipe.SIZE / 200.0
    box = mesh("Box", lambda bm: bmesh.ops.create_cube(bm, size=size, calc_uvs=True), (-spacing, 0.0, up))
    box.data.materials.append(surface("Box_MAT", (0.8, 0.3, 0.2)))
    sphere = mesh(
        "Sphere",
        lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=size / 2.0, calc_uvs=True),
        (0.0, 0.0, up),
    )
    sphere.data.materials.append(surface("Sphere_MAT", (0.05, 0.05, 0.05), emission=1.0, image=emission_map))

    def slab(bm):
        bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)
        bmesh.ops.scale(bm, vec=(size, size / 4.0, size), verts=bm.verts)

    panel = mesh("Panel", slab, (spacing, 0.0, up))
    panel.data.materials.append(surface("Panel_MAT", (0.35, 0.35, 0.4)))
    panel.data.materials.append(surface("Lamp_MAT", (0.1, 0.1, 0.1), emission=1.0, glow=recipe.LAMP))
    # The lamp: the front face, Maya's +Z, which is Blender's -Y.
    front = min(panel.data.polygons, key=lambda p: p.normal.y).index
    panel.data.polygons[front].material_index = 1

    for start, end, direction in recipe.FADES:
        btk.RenderEffects.key_fade([box], start=start, end=end, direction=direction)
    bright, dim = recipe.HIGHLIGHT
    for start, end in recipe.PULSES:
        btk.RenderEffects.key_pulse(
            [sphere], start=start, end=end, period=recipe.PULSE_PERIOD, color=bright, dim_color=dim
        )
    for frame, visible in recipe.BLINK:
        for path in ("hide_viewport", "hide_render"):
            setattr(panel, path, not visible)
            panel.keyframe_insert(path, frame=frame)
    btk.EmissiveGroups.add_group(recipe.GROUP, {panel.name: [front]}, weight=0.0)
    for frame, weight in recipe.LAMP_KEYS:
        btk.EmissiveGroups.key_weight(recipe.GROUP, weight, frame=frame)
    # The rest state the export writes: the first frame (the box opaque, the
    # sphere and the lamp dark, the panel shown).
    scene.frame_set(recipe.SHOTS[0][1])

    objects = [box, sphere, panel]
    store = btk.ShotStore()
    btk.ShotStore.set_active(store)
    for name, start, end in recipe.SHOTS:
        store.define_shot(name, start, end, objects=[o.name for o in objects])

    exporter = btk.SceneExporter(log_level="WARNING")
    exporter.confirm = lambda question: False
    if not exporter.perform_export(
        export_dir=out_dir, objects=objects, output_name=recipe.MODEL, tasks={"export_data_node": True}
    ):
        raise RuntimeError(f"the Scene Exporter wrote no {recipe.MODEL}.fbx; its log above says why")
    return [f"{recipe.MODEL}.fbx"]
