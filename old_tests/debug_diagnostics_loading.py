"""Debug script to check what modules are loaded after accessing Diagnostics."""

import sys

# Clear diagnostics modules
for key in list(sys.modules.keys()):
    if "mayatk.core_utils.diagnostics" in key:
        del sys.modules[key]

print("Modules before accessing Diagnostics:")
diagnostics_before = [k for k in sys.modules.keys() if "diagnostics" in k.lower()]
print(f"  Found {len(diagnostics_before)}: {diagnostics_before}")

import mayatk

print("\nAccessing mayatk.Diagnostics...")
try:
    diag = mayatk.Diagnostics
    print(f"  Success: {diag}")
except Exception as e:
    print(f"  Error: {e}")

print("\nModules after accessing Diagnostics:")
diagnostics_after = [
    k for k in sys.modules.keys() if "mayatk" in k and "diagnostics" in k.lower()
]
print(f"  Found {len(diagnostics_after)}:")
for mod in sorted(diagnostics_after):
    print(f"    - {mod}")

print("\nAll mayatk.core_utils modules loaded:")
core_utils_modules = [
    k for k in sys.modules.keys() if k.startswith("mayatk.core_utils")
]
for mod in sorted(core_utils_modules):
    print(f"  - {mod}")
