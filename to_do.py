# to-do notes:

# mayatk: components: get shortest edge not working

# file: sort recent files by timestamps.

# Add: mayatk.mat_utils.stingray_arnold_shader: option to omit arnold network from result.

# toggle explode:  this should be wrapped in a undo chunk. check why this seems not to be the case.

# Add: Bridge: support for triangle edges.

# Traceback (most recent call last):
#   File "C:\Program Files\Autodesk\Maya2023\Python\lib\site-packages\pymel\internal\pmcmds.py", line 217, in parent_wrapped
#     res = new_cmd(*new_args, **new_kwargs)
# ValueError: No object matches name: |INTERACTIVES|TANK_BLADDER_ROLLED_GRP|STRAPS
# #
# During handling of the above exception, another exception occurred:

# Traceback (most recent call last):
#   File "O:\Cloud\Code\_scripts\uitk\uitk\switchboard.py", line 814, in wrapper
#     return slot(widget)
#   File "O:\Cloud\Code\_scripts\tentacle\tentacle\slots\maya\polygons.py", line 174, in tb002
#     pm.parent(newObjRenamed, objParent[0])
#   File "C:\Program Files\Autodesk\Maya2023\Python\lib\site-packages\pymel\core\general.py", line 1553, in parent
#     result = cmds.parent(*args, **kwargs)
#   File "C:\Program Files\Autodesk\Maya2023\Python\lib\site-packages\pymel\internal\pmcmds.py", line 224, in parent_wrapped
#     raise pymel.core.general._objectError(obj)
# pymel.core.general.MayaNodeError: Maya Node does not exist (or is not unique):: '|INTERACTIVES|TANK_BLADDER_ROLLED_GRP|STRAPS'
