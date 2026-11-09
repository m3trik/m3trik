"""The Shots sample made in Blender: one scene-range action, split into a take per shot.

The Maya recipe's scene (``unity_samples/shots.py``: its shots, keys and rate)
built with bpy and blendertk and exported through blendertk's Scene Exporter.
Blender writes one AnimStack for the scene's range and blendertk splits it into
the declared takes afterwards, so ``ShotsSampleTests`` passing on this delivery
proves the split: one clip per shot, named after it, as long as the shot and
in its place on the timeline, each joined to its description and section.
"""

NAME = "BlenderShots"
SAMPLE = "Shots"
PRODUCER = "blender"


def build(out_dir: str) -> list:
    """Make the Shots scene in Blender and export it into *out_dir*.

    Returns:
        ``["Shots.fbx"]``.

    Raises:
        RuntimeError: The export reported a failure (its log says why).
    """
    import math

    import bpy

    import blendertk as btk
    from unity_samples import shots as recipe

    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = 24, 1.0
    scene.frame_start, scene.frame_end = recipe.SHOTS[0][1], recipe.SHOTS[-1][2]
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    box = bpy.context.active_object
    box.name = box.data.name = "Box"
    # Maya's centimetres, Y up, in Blender's metres, Z up: translateX is
    # location.x, rotateY (about the up axis) is rotation_euler.z.
    for frame, attribute, value in recipe.KEYS:
        if attribute == "translateX":
            box.location.x = value / 100.0
            box.keyframe_insert("location", index=0, frame=frame)
        else:
            box.rotation_euler.z = math.radians(value)
            box.keyframe_insert("rotation_euler", index=2, frame=frame)

    store = btk.ShotStore()
    btk.ShotStore.set_active(store)
    for name, start, end, description, section in recipe.SHOTS:
        store.define_shot(name, start, end, objects=[box.name], description=description, metadata={"section": section})
    store.set_shipped_metadata(["section"])

    exporter = btk.SceneExporter(log_level="WARNING")
    exporter.confirm = lambda question: False
    if not exporter.perform_export(
        export_dir=out_dir, objects=[box], output_name=recipe.MODEL, tasks={"export_data_node": True}
    ):
        raise RuntimeError("the Scene Exporter wrote no Shots.fbx; its log above says why")
    return [f"{recipe.MODEL}.fbx"]
