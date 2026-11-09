"""The Materials sample exported from a Maya assembly: stray carriers before and after the scene's own.

The Maya recipe's scene (``unity_samples/materials.py``) as an assembly ships
it (``_assembly.py``), each stray holding the ``materials`` record with every
colour, emission and factor stale. The Materials importer reads the record
off the file itself before Unity builds the materials (``CarrierFile``, in
``OnPreprocessModel``), a reader of its own beside the user-property one the
Shots twin holds, so ``MaterialsSampleTests`` passing on this delivery proves
the file reader's precedence on what Maya's FBX writer really writes.
"""

NAME = "MayaMaterialsAssembly"
SAMPLE = "Materials"
PRODUCER = "maya"

#: The strays' colour: what no material of the sample is.
STALE = [1.0, 0.0, 1.0, 1.0]


def stale(record: dict) -> dict:
    """*record* (``materials``) with every material's colour magenta, its
    emission off, and its metal and roughness factors 0.5."""
    for material in record["materials"]:
        pbr = material.setdefault("pbrMetallicRoughness", {})
        pbr["baseColorFactor"] = list(STALE)
        pbr["metallicFactor"] = pbr["roughnessFactor"] = 0.5
        material["emissiveFactor"] = [0.0, 0.0, 0.0]
    return record


def build(out_dir: str) -> list:
    """The Materials scene as an assembly, exported into *out_dir*: ``["Materials.fbx"]``."""
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _assembly
    from unity_samples import materials as recipe

    return _assembly.export(recipe, out_dir, "materials", stale)
