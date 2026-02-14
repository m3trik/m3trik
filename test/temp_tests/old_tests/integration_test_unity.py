import pymel.core as pm
import os
import sys

# Ensure module is in path (modify if needed for your environment)
# sys.path.append(r"O:\Cloud\Code\_scripts")

try:
    from mayatk.mat_utils.material_fade._material_fade import MaterialFade
    from mayatk.env_utils._env_utils import EnvUtils
except ImportError as e:
    print(f"Error importing wrappers: {e}")
    print("Please run this script within the Maya environment with 'mayatk' accessible.")
    sys.exit(1)

def setup_test_scene():
    print("-" * 50)
    print("STARTING UNITY INTEGRATION TEST")
    print("-" * 50)

    # 1. Clean Scene
    pm.newFile(force=True)
    
    # 2. Setup Resources
    # Load Stingray/ShaderFX if needed
    if not pm.pluginInfo("shaderFXPlugin", query=True, loaded=True):
        pm.loadPlugin("shaderFXPlugin")

    # 3. scenario A: Attribute Mode (Game Engine Standard)
    # ---------------------------------------------------------
    print("\n[Scenario A] Attribute Mode")
    sphere_attr = pm.polySphere(name="Test_AttributeMode")[0]
    sphere_attr.translate.set(-5, 0, 0)
    
    print(f"Applying Attribute Mode to {sphere_attr}...")
    MaterialFade.create([sphere_attr], mode="attribute")
    
    # Animate Opacity (Full -> Invisible)
    pm.setKeyframe(sphere_attr, attribute="opacity", t=1, v=1.0)
    pm.setKeyframe(sphere_attr, attribute="opacity", t=30, v=0.0)
    
    # Verify
    has_keys = pm.keyframe(sphere_attr, attr="opacity", query=True, keyframeCount=True) > 0
    vis_driven = len(sphere_attr.visibility.inputs()) > 0
    print(f"  - Has 'opacity' keys: {has_keys}")
    print(f"  - Visibility is driven: {vis_driven}")
    
    # 4. Scenario B: Material Mode (Shared Material Conflict)
    # ---------------------------------------------------------
    print("\n[Scenario B] Material Mode (Shared Handling)")
    sphere_mat_1 = pm.polySphere(name="Test_MatMode_1")[0]
    sphere_mat_2 = pm.polySphere(name="Test_MatMode_2")[0]
    sphere_mat_1.translate.set(0, 0, 0)
    sphere_mat_2.translate.set(5, 0, 0)
    
    # Assign Shared Material
    mat_name = "Shared_Stingray"
    mat = pm.shadingNode("StingrayPBS", asShader=True, name=mat_name)
    sg = pm.sets(renderable=True, noSurfaceShader=True, empty=True, name=f"{mat_name}SG")
    pm.connectAttr(mat.outColor, sg.surfaceShader)
    pm.sets(sg, forceElement=[sphere_mat_1, sphere_mat_2])
    
    print(f"Applying Material Mode to {sphere_mat_1} and {sphere_mat_2}...")
    # Select both so they initially 'share' the intent, but the script should split them
    # because Material Mode logic now enforces unique drivers for visual feedback.
    MaterialFade.create([sphere_mat_1, sphere_mat_2], mode="material")
    
    # Animate Opacity Separately
    # Sphere 1: 0 -> 1
    pm.setKeyframe(sphere_mat_1, attribute="opacity", t=1, v=0.0)
    pm.setKeyframe(sphere_mat_1, attribute="opacity", t=30, v=1.0)
    
    # Sphere 2: 1 -> 0
    pm.setKeyframe(sphere_mat_2, attribute="opacity", t=1, v=1.0)
    pm.setKeyframe(sphere_mat_2, attribute="opacity", t=30, v=0.0)
    
    # Verify Materials were split
    sg1 = sphere_mat_1.getShape().listConnections(type="shadingEngine")[0]
    m1 = sg1.surfaceShader.inputs()[0]
    
    sg2 = sphere_mat_2.getShape().listConnections(type="shadingEngine")[0]
    m2 = sg2.surfaceShader.inputs()[0]
    
    print(f"  - {sphere_mat_1} Material: {m1.name()}")
    print(f"  - {sphere_mat_2} Material: {m2.name()}")
    
    if m1 == m2:
        print("  [FAIL] Materials should have been split to allow independent fading!")
    else:
        print("  [PASS] Materials correctly split.")

    # Verify Connections
    conn1 = pm.isConnected(sphere_mat_1.opacity, m1.opacity)
    conn2 = pm.isConnected(sphere_mat_2.opacity, m2.opacity)
    print(f"  - Connection {sphere_mat_1}.opacity -> {m1}.opacity: {conn1}")
    print(f"  - Connection {sphere_mat_2}.opacity -> {m2}.opacity: {conn2}")
    
    # 5. Conclusion
    print("-" * 50)
    print("TEST COMPLETE")
    print("READY FOR EXPORT TO UNITY")
    print("1. Select all sphere objects.")
    print("2. File > Export Selection (FBX).")
    print("3. Validations in Unity:")
    print("   [Attribute Mode Object]: Add 'MaterialFadeController.cs' component (or ensure FadeCurveFixer runs).")
    print("   [Material Mode Objects]: Should fade independently. Check Materials in Inspector.")
    print("-" * 50)

if __name__ == "__main__":
    setup_test_scene()
