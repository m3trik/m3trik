"""Test by checking what mayatk actually has."""

import sys

sys.path.insert(0, r"o:\Cloud\Code\_scripts")

# Import mayatk __init__ to see the DEFAULT_INCLUDE
import mayatk

print("Keys with arrows in DEFAULT_INCLUDE:")
for key in mayatk.DEFAULT_INCLUDE.keys():
    if "->" in key:
        value = mayatk.DEFAULT_INCLUDE[key]
        print(f"  {key}: {value}")

print("\nChecking PACKAGE_RESOLVER:")
if hasattr(mayatk, "PACKAGE_RESOLVER"):
    resolver = mayatk.PACKAGE_RESOLVER
    print(f"  Has resolver: Yes")
    print(f"  resolver.namespace_aliases: {resolver.namespace_aliases}")
else:
    print("  No PACKAGE_RESOLVER found")

print("\nChecking for Diagnostics:")
try:
    diag = mayatk.Diagnostics
    print(f"  Found: {diag}")
except AttributeError as e:
    print(f"  Not found: {e}")
