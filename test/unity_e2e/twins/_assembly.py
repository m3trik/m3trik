"""A sample exported from a Maya assembly: stray carriers around the scene's own.

A helper the assembly twins import (its name starts with ``_``), never a twin.
An assembly ships more than the scene's carrier: a referenced module's
``MOD:data_export``, an imported module's ``data_export1``, a grouped module's
own-named ``Module|data_export``. :func:`export` builds a sample's scene as its
recipe does, gives each stray a stale copy of the record the sample's feature
reads, puts them all ahead of the scene's own in the file -- the grouped
module's own-named one first of the two of that name -- and exports through
the Scene Exporter, which makes the scene's carrier at the root when its
records are all made at the write (a scene holding one keeps it last). The
scene's own is the root-level ``data_export``
(``ptk.SceneStoreBase.is_scene_carrier``), and every reader takes it and no
other's record, so the sample's tests pass on the
delivery only by that rule: a reader taking the first carrier, the last, or
the first one named ``data_export`` reads a stale copy; a writer adopting the
grouped one as the scene's writes over it and deletes it.
"""

#: The carriers the file must hold, in file order, each with the Models above it.
ORDER = ["MOD:data_export", "Module|data_export", "data_export1", "data_export"]


def export(recipe, out_dir: str, key: str, stale) -> list:
    """*recipe*'s scene, its strays carrying ``stale(record)`` for the
    record *key* the recipe's export wrote, exported into *out_dir*.

    Returns:
        The recipe's files (its one FBX).

    Raises:
        RuntimeError: An export failed, or the file does not hold the
            carriers in :data:`ORDER`.
    """
    import json
    import os

    import maya.cmds as cmds
    import mayatk as mtk
    import pythontk as ptk

    # The sample's scene, exported once as its recipe does: the record it reads is the real one.
    sample = os.path.join(out_dir, "_sample")
    os.makedirs(sample)
    files = recipe.build(sample)
    record = ptk.FbxMedia.record(os.path.join(sample, files[0]), key)
    if not record:
        raise RuntimeError(f"the {recipe.NAME} recipe's export carries no {key} record")
    text = json.dumps(stale(record))
    roots = [n for n in cmds.ls(assemblies=True, long=True) if not cmds.listRelatives(n, shapes=True, type="camera")]
    roots = [n for n in roots if not n.lstrip("|").startswith("data_")]

    def stray(name, parent=None):
        node = cmds.createNode("transform", name=name, parent=parent, skipSelect=True)
        cmds.addAttr(node, longName=key, dataType="string")
        cmds.setAttr(f"{node}.{key}", text, type="string")
        return cmds.ls(node, long=True)[0]

    # A scene whose records all live on the export has no carrier until the write
    # makes one at the root, after every stray; one it holds already goes after them.
    own = mtk.DataNodes.get_export_node(create=False)
    own = cmds.ls(own, long=True)[0] if own else None  # before a stray shares its name
    cmds.namespace(add="MOD")
    module = stray("MOD:data_export")
    imported = stray("data_export1")
    group = cmds.createNode("transform", name="Module", skipSelect=True)
    nested = stray("data_export", parent=group)
    cmds.reorder(group, front=True)
    cmds.reorder(module, front=True)
    cmds.reorder(imported, back=True)
    if own:
        cmds.reorder(own, back=True)

    exporter = mtk.SceneExporter(log_level="WARNING")
    exporter.confirm = lambda question: False
    if not exporter.perform_export(
        export_dir=out_dir,
        objects=[*roots, module, imported, group],
        output_name=os.path.splitext(files[0])[0],
        tasks={"export_data_node": True},
    ):
        raise RuntimeError(f"the Scene Exporter wrote no {files[0]}; its log above says why")
    fbx = ptk.FbxFile.load(os.path.join(out_dir, files[0]))
    owners = [owner for owner, _ in fbx.user_properties(key, named=True, paths=True)]
    if owners != ORDER:
        raise RuntimeError(f"the file's {key} carriers are {owners}, not {ORDER} in that order")
    if not cmds.objExists(nested) or cmds.getAttr(f"{nested}.{key}") != text:
        raise RuntimeError(f"the export wrote over or deleted the grouped module's {nested}")
    return files
