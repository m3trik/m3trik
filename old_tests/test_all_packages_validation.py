"""Comprehensive validation test for all packages - uses ModuleResolverValidator."""

import socket
import sys
import time
import os
import tempfile

# Test script using the comprehensive validator for all packages
test_script = """
import sys, os, tempfile
output_file = os.path.join(tempfile.gettempdir(), 'all_packages_validation_output.txt')

with open(output_file, 'w', encoding='utf-8') as f:
    # Clear modules
    to_remove = [k for k in sys.modules.keys() if k.startswith(('mayatk', 'pythontk', 'uitk', 'tentacle'))]
    for k in to_remove: del sys.modules[k]
    f.write(f'Cleared {len(to_remove)} cached modules\\n')
    f.write('='*70 + '\\n\\n')
    
    packages = ['pythontk', 'mayatk', 'uitk', 'tentacle']
    results = {}
    
    for pkg_name in packages:
        try:
            f.write(f'{pkg_name.upper()} VALIDATION\\n')
            f.write('='*70 + '\\n')
            
            from test.test_module_resolver import validate_package
            
            # Capture stdout temporarily
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            
            success = validate_package(pkg_name, verbose=True)
            
            output = sys.stdout.getvalue()
            sys.stdout = old_stdout
            f.write(output)
            
            results[pkg_name] = success
            
            f.write('\\n' + '='*70 + '\\n\\n')
            
        except Exception as e:
            f.write(f'ERROR in {pkg_name} validation: {e}\\n\\n')
            import traceback
            f.write(traceback.format_exc())
            results[pkg_name] = False
            f.write('\\n' + '='*70 + '\\n\\n')
    
    # Summary
    f.write('\\n' + '='*70 + '\\n')
    f.write('FINAL RESULTS\\n')
    f.write('='*70 + '\\n')
    for pkg_name, success in results.items():
        f.write(f'{pkg_name:12s}: {"PASS" if success else "FAIL"}\\n')
    
    all_pass = all(results.values())
    f.write('\\n')
    if all_pass:
        f.write('[OK] ALL PACKAGES VALIDATED SUCCESSFULLY\\n')
    else:
        failed = [k for k, v in results.items() if not v]
        f.write(f'[X] FAILED: {", ".join(failed)}\\n')
    f.write('='*70 + '\\n')

print('Validation complete. Output written to:', output_file)
"""


def send_to_maya(code, host="127.0.0.1", port=7002):
    """Send Python code to Maya via command port."""
    ports_to_try = [port, 7003, 7004, 7005, 7010]

    for try_port in ports_to_try:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((host, try_port))

            print(f"✓ Connected to Maya on port {try_port}")

            # Send the code
            sock.send(code.encode("utf-8"))
            sock.close()

            # Wait for Maya to run validation (takes longer with 4 packages)
            print(
                "⏳ Running comprehensive validation on 4 packages (this may take 10-15 seconds)..."
            )
            time.sleep(8)

            # Read output from temp file
            temp_file = os.path.join(
                tempfile.gettempdir(), "all_packages_validation_output.txt"
            )
            if os.path.exists(temp_file):
                with open(temp_file, "r", encoding="utf-8") as f:
                    output = f.read()
                os.remove(temp_file)

                print("\n" + "=" * 70)
                print("MAYA VALIDATION OUTPUT:")
                print("=" * 70)
                print(output)
                print("=" * 70)
            else:
                print("⚠️  No output file found. Check Maya Script Editor for results.")

            return True

        except Exception as e:
            if try_port == ports_to_try[-1]:
                print(f"\n✗ Could not connect to Maya on any port: {ports_to_try}")
                print(f"Last error: {e}")
                print("\nMake sure Maya is running with command port open:")
                print("  import mayatk")
                print("  mayatk.openPorts(python=':7002')")
                return False
            continue

    return False


if __name__ == "__main__":
    print("Connecting to Maya on localhost:7002...")
    send_to_maya(test_script)
