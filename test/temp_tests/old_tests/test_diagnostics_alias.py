"""Test wildcard namespace alias in Maya."""

import socket
import os
import tempfile
import time

test_script = """
import sys, os, tempfile
output_file = os.path.join(tempfile.gettempdir(), 'diagnostics_test_output.txt')

with open(output_file, 'w', encoding='utf-8') as f:
    # Clear modules
    to_remove = [k for k in sys.modules.keys() if k.startswith('mayatk')]
    for k in to_remove: del sys.modules[k]
    f.write(f'Cleared {len(to_remove)} cached modules\\n\\n')
    
    # Test the Diagnostics alias
    import mayatk
    
    f.write('Testing wildcard namespace alias: core_utils.diagnostics->Diagnostics\\n')
    f.write('='*60 + '\\n')
    
    try:
        # Check if Diagnostics exists
        diag = mayatk.Diagnostics
        f.write(f'[OK] mayatk.Diagnostics exists: {diag}\\n')
        
        # List methods
        methods = [m for m in dir(diag) if not m.startswith('_')][:10]
        f.write(f'[OK] Sample methods: {", ".join(methods)}\\n')
        
        # Check base classes
        bases = diag.__bases__
        f.write(f'[OK] Base classes: {[b.__name__ for b in bases]}\\n')
        
        f.write('\\n[OK] WILDCARD NAMESPACE ALIAS WORKS!\\n')
    except AttributeError as e:
        f.write(f'[X] FAILED: {e}\\n')
    except Exception as e:
        f.write(f'[X] ERROR: {e}\\n')
        import traceback
        f.write(traceback.format_exc())

print('Test complete. Output written to:', output_file)
"""


def send_to_maya(code, port=7002):
    ports_to_try = [port, 7003, 7004, 7005, 7010]

    for try_port in ports_to_try:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect(("localhost", try_port))

            print(f"✓ Connected to Maya on port {try_port}")

            sock.send(code.encode("utf-8"))
            sock.close()

            time.sleep(1)

            temp_file = os.path.join(
                tempfile.gettempdir(), "diagnostics_test_output.txt"
            )
            if os.path.exists(temp_file):
                with open(temp_file, "r", encoding="utf-8") as f:
                    output = f.read()
                os.remove(temp_file)

                print("\\n" + "=" * 60)
                print("MAYA TEST OUTPUT:")
                print("=" * 60)
                print(output)
                print("=" * 60)
            else:
                print("No output file found. Check Maya Script Editor.")

            return True

        except Exception as e:
            if try_port == ports_to_try[-1]:
                print(f"\\n✗ Could not connect to Maya on any port: {ports_to_try}")
                print(f"Last error: {e}")
                return False
            continue

    return False


if __name__ == "__main__":
    print("Testing wildcard namespace alias in Maya...")
    send_to_maya(test_script)
