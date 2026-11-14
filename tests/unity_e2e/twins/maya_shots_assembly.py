"""The Shots sample exported from a Maya assembly: stray carriers before and after the scene's own.

The Maya recipe's scene (``unity_samples/shots.py``) as an assembly ships it
(``_assembly.py``): a referenced module's ``MOD:data_export`` ahead of the
scene's own carrier in the file, an imported module's ``data_export1`` and a
grouped module's ``Module|data_export`` after it, each holding the
``animation`` record with every shot's description and section stale. The
Shots importer reads the user properties Unity hands it
(``CarrierImport.Collect``), so ``ShotsSampleTests`` passing on this delivery
proves that reader's precedence on what Maya's FBX writer really writes.
"""

NAME = "MayaShotsAssembly"
SAMPLE = "Shots"
PRODUCER = "maya"


def stale(record: dict) -> dict:
    """*record* (``animation``) with every shot described otherwise."""
    for shot in record["shots"]:
        shot["description"] = "stale"
        shot["metadata"] = {key: "stale" for key in shot.get("metadata", {})}
    return record


def build(out_dir: str) -> list:
    """The Shots scene as an assembly, exported into *out_dir*: ``["Shots.fbx"]``."""
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _assembly
    from unity_samples import shots as recipe

    return _assembly.export(recipe, out_dir, "animation", stale)
