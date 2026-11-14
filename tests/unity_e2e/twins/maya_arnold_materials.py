"""The Materials sample made with Arnold's aiStandardSurface through Maya's FBX writer.

The Maya recipe's scene (``unity_samples/materials.py``) with its three PBR
materials on ``aiStandardSurface`` instead of ``standardSurface``, MtoA
loaded as an Arnold user's Maya has it. The ``materials`` record is read
from the shading network, so ``MaterialsSampleTests`` passing on this
delivery proves mayatk states an Arnold surface as it states a Standard
Surface, and that Maya's FBX writer, with MtoA loaded, embeds every map the
record names.
"""

NAME = "MayaArnoldMaterials"
SAMPLE = "Materials"
PRODUCER = "maya"


def build(out_dir: str) -> list:
    """Make the Materials scene on aiStandardSurface and export it into *out_dir*.

    Returns:
        ``["Materials.fbx"]``.

    Raises:
        RuntimeError: MtoA cannot load, or the export reported a failure.
    """
    import maya.cmds as cmds

    from unity_samples import materials as recipe

    cmds.loadPlugin("mtoa", quiet=True)
    if not cmds.pluginInfo("mtoa", query=True, loaded=True):
        raise RuntimeError("MtoA did not load: this twin needs Arnold for Maya")
    return recipe.build(out_dir, surface="aiStandardSurface")
