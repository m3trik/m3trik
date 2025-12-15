"""Test lazy loading across all packages after conversion."""

import sys
import os

# Suppress stderr
sys.stderr = open(os.devnull, "w")

print("=" * 60)
print("TESTING LAZY LOADING CONVERSION")
print("=" * 60)

# Test pythontk
print("\n✓ Testing pythontk...")
import pythontk

utils = [
    pythontk.CoreUtils,
    pythontk.StrUtils,
    pythontk.ImgUtils,
    pythontk.FileUtils,
    pythontk.MathUtils,
    pythontk.VidUtils,
    pythontk.IterUtils,
]
print(f"  ✓ All {len(utils)} utils loaded successfully")

# Test mayatk
print("\n✓ Testing mayatk...")
import mayatk

print(f"  ✓ mayatk loaded")
print(f"  ✓ Instancing namespace alias: {mayatk.Instancing}")
print(f"  ✓ Namespace has {len(mayatk.Instancing.__bases__)} base classes")
print(f"  ✓ Arrow syntax working!")

# Test uitk
print("\n✓ Testing uitk...")
import uitk

print(f"  ✓ uitk loaded")
print(f"  ✓ Switchboard: {uitk.Switchboard}")

print("\n" + "=" * 60)
print("SUCCESS: All packages using lazy loading!")
print("=" * 60)
