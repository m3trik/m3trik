"""Comprehensive validation test for Maya - uses ModuleResolverValidator."""

import socket
import sys
import time
import os
import tempfile

# Test script using the comprehensive validator
test_script = """
import sys, os, tempfile
output_file = os.path.join(tempfile.gettempdir(), 'maya_validation_output.txt')

with open(output_file, 'w', encoding='utf-8') as f:
    # Clear modules
    to_remove = [k for k in sys.modules.keys() if k.startswith('mayatk') or k.startswith('pythontk')]
    for k in to_remove: del sys.modules[k]
    f.write(f'Cleared {len(to_remove)} cached modules\\n')
    f.write('='*70 + '\\n\\n')
    
    # Run pythontk validation
    try:
        from test.test_module_resolver import validate_package
        
        f.write('PYTHONTK VALIDATION\\n')
        f.write('='*70 + '\\n')
        
        # Capture stdout temporarily
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        
        success_pythontk = validate_package('pythontk', verbose=True)
        
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        f.write(output)
        
        f.write('\\n' + '='*70 + '\\n\\n')
        
    except Exception as e:
        f.write(f'ERROR in pythontk validation: {e}\\n\\n')
        import traceback
        f.write(traceback.format_exc())
        success_pythontk = False
    
    # Run mayatk validation
    try:
        f.write('MAYATK VALIDATION\\n')
        f.write('='*70 + '\\n')
        
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        
        success_mayatk = validate_package('mayatk', verbose=True)
        
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        f.write(output)
        
        f.write('\\n' + '='*70 + '\\n\\n')
        
    except Exception as e:
        f.write(f'ERROR in mayatk validation: {e}\\n\\n')
        import traceback
        f.write(traceback.format_exc())
        success_mayatk = False
    
    # Summary
    f.write('\\n' + '='*70 + '\\n')
    f.write('FINAL RESULTS\\n')
    f.write('='*70 + '\\n')
    f.write(f'pythontk: {"PASS" if success_pythontk else "FAIL"}\\n')
    f.write(f'mayatk: {"PASS" if success_mayatk else "FAIL"}\\n')
    if success_pythontk and success_mayatk:
        f.write('\\n[OK] ALL PACKAGES VALIDATED SUCCESSFULLY\\n')
    else:
        f.write('\\n[X] SOME VALIDATIONS FAILED - SEE ABOVE\\n')
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

            # Wait for Maya to run validation (takes longer)
            print("⏳ Running comprehensive validation (this may take 5-10 seconds)...")
            time.sleep(5)

            # Read output from temp file
            temp_file = os.path.join(
                tempfile.gettempdir(), "maya_validation_output.txt"
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
