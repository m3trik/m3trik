"""Test namespace alias detection directly."""

import sys

sys.path.insert(0, r"o:\Cloud\Code\_scripts")

# Test parsing the include dict
from pythontk.core_utils.module_resolver import ModuleAttributeResolver

test_include = {
    "core_utils.diagnostics->Diagnostics": "*",
    "core_utils.mash->Mash": ["MashToolkit", "MashNetworkNodes"],
}

resolver = ModuleAttributeResolver("test_package")
resolver._set_include(test_include)

print("Namespace aliases detected:")
for alias, (module_key, classes) in resolver.namespace_aliases.items():
    print(f"  {alias}: {module_key} -> {classes}")

print("\nDirect include:")
print(f"  {resolver._direct_include}")

print("\nAbsolute include:")
print(f"  {resolver._absolute_include}")
