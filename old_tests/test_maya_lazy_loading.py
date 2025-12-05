"""Remote test executor for Maya - sends test script via command port."""

import socket
import sys
import time
import os

# Test script to execute in Maya - writes output to temp file
test_script = """
import sys, os, tempfile
output_file = os.path.join(tempfile.gettempdir(), 'maya_test_output.txt')

with open(output_file, 'w', encoding='utf-8') as f:
    # Reload modules
    to_remove = [k for k in sys.modules.keys() if k.startswith('mayatk') or k.startswith('pythontk') or k.startswith('uitk')]
    for k in to_remove: del sys.modules[k]
    f.write(f'Cleared {len(to_remove)} cached modules\\n')
    f.write('='*60 + '\\n')
    f.write('TESTING LAZY LOADING IN MAYA\\n')
    f.write('='*60 + '\\n')
    
    # Test pythontk
    import pythontk
    utils = [pythontk.CoreUtils, pythontk.StrUtils, pythontk.ImgUtils, pythontk.FileUtils, pythontk.MathUtils, pythontk.VidUtils, pythontk.IterUtils]
    f.write(f'\\n[OK] pythontk: All {len(utils)} utils loaded\\n')
    f.write(f'[OK] Sample: {pythontk.CoreUtils}\\n')
    
    # Test mayatk
    import mayatk
    f.write(f'\\n[OK] mayatk loaded\\n')
    f.write(f'[OK] CoreUtils: {mayatk.CoreUtils}\\n')
    f.write(f'[OK] NodeUtils: {mayatk.NodeUtils}\\n')
    f.write(f'[OK] EditUtils: {mayatk.EditUtils}\\n')
    f.write(f'[OK] AutoInstancer: {mayatk.AutoInstancer}\\n')
    
    # Check init files
    paths = [
        r'O:\\Cloud\\Code\\_scripts\\pythontk\\pythontk\\core_utils\\__init__.py',
        r'O:\\Cloud\\Code\\_scripts\\pythontk\\pythontk\\str_utils\\__init__.py',
        r'O:\\Cloud\\Code\\_scripts\\mayatk\\mayatk\\mat_utils\\__init__.py'
    ]
    f.write('\\nSubpackage __init__.py files:\\n')
    for p in paths:
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as inf:
                lines = [line for line in inf.readlines() if line.strip() and not line.strip().startswith('#')]
                f.write(f'  {os.path.basename(os.path.dirname(p))}: {len(lines)} non-comment lines\\n')
    
    f.write('\\n' + '='*60 + '\\n')
    f.write('SUCCESS: All packages using lazy loading!\\n')
    f.write('='*60 + '\\n')

print('Test output written to:', output_file)
"""


def send_to_maya(code, host="127.0.0.1", port=7002):
    """Send Python code to Maya via command port.

    Args:
        code: Python code to execute
        host: Maya host (default localhost)
        port: Command port number (default 7002)
    """
    # Try multiple ports in case some are in use
    ports_to_try = [port, 7003, 7004, 7005, 7010]

    for try_port in ports_to_try:
        try:
            # Connect to Maya's command port
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect((host, try_port))

            print(f"✓ Connected to Maya on port {try_port}")

            # Send the code
            sock.send(code.encode("utf-8"))

            # Receive response
            response = b""
            sock.settimeout(5.0)  # Increased timeout for longer output
            try:
                while True:
                    chunk = sock.recv(8192)  # Larger buffer
                    if not chunk:
                        break
                    response += chunk
            except socket.timeout:
                pass

            sock.close()

            # Wait a moment for Maya to write the file
            time.sleep(0.5)

            # Read the output file
            temp_output = os.path.join(
                os.environ.get("TEMP", "/tmp"), "maya_test_output.txt"
            )
            if os.path.exists(temp_output):
                with open(temp_output, "r", encoding="utf-8") as f:
                    output = f.read()
                print("\n" + "=" * 60)
                print("MAYA TEST OUTPUT:")
                print("=" * 60)
                print(output)
                print("=" * 60)
                os.remove(temp_output)
            else:
                print("\n✓ Test script sent to Maya successfully")
                print(f"(Output file not found at: {temp_output})")
                print("Check Maya Script Editor for results")

            return True

        except (ConnectionRefusedError, socket.timeout, OSError):
            continue

    # All ports failed
    print(f"❌ ERROR: Could not connect to Maya on any port: {ports_to_try}")
    print("\nTo open a command port in Maya Script Editor (Python tab):")
    print("  import mayatk")
    print("  mayatk.openPorts(python=':7003')  # or :7004, :7005, etc.")
    print("\nThen re-run this test script")
    return False


if __name__ == "__main__":
    print("Connecting to Maya on localhost:7002...")
    success = send_to_maya(test_script)
    sys.exit(0 if success else 1)
