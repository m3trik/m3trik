# Debug script to run in Maya - check namespace alias setup

import mayatk

print("=" * 60)
print("DEBUGGING NAMESPACE ALIAS SETUP")
print("=" * 60)

# Access the PackageResolver
if hasattr(mayatk, "PACKAGE_RESOLVER"):
    pr = mayatk.PACKAGE_RESOLVER
    print("\nFound PACKAGE_RESOLVER")
    print("  namespace_aliases:", pr.resolver.namespace_aliases)

    if pr.resolver.namespace_aliases:
        print("\nnamespace_aliases dict is populated:")
        for alias_name, (module_key, classes) in pr.resolver.namespace_aliases.items():
            print("  " + alias_name + ":")
            print("    module:", module_key)
            print("    classes:", classes)
    else:
        print("\nnamespace_aliases dict is EMPTY")

    # Check if Instancing is in module_globals
    if "Instancing" in pr.module_globals:
        print("\nInstancing found in module_globals:", pr.module_globals["Instancing"])
    else:
        print("\nInstancing NOT in module_globals")
        available = [k for k in pr.module_globals.keys() if not k.startswith("_")][:20]
        print("  Available globals:", available)

else:
    print("\nNo PACKAGE_RESOLVER found")

print("\n" + "=" * 60)
