"""Debug wildcard namespace alias."""

import socket
import os
import tempfile
import time

test_script = """
import sys, os, tempfile
output_file = os.path.join(tempfile.gettempdir(), 'diagnostics_debug_output.txt')

with open(output_file, 'w', encoding='utf-8') as f:
    # Clear modules
    to_remove = [k for k in sys.modules.keys() if k.startswith('mayatk')]
    for k in to_remove: del sys.modules[k]
    
    import mayatk
    
    f.write('Namespace aliases in resolver:\\n')
    if hasattr(mayatk, 'PACKAGE_RESOLVER'):
        resolver = mayatk.PACKAGE_RESOLVER
        f.write(f'  resolver.namespace_aliases: {resolver.namespace_aliases}\\n\\n')
    
    f.write('Available attributes in mayatk:\\n')
    attrs = [a for a in dir(mayatk) if not a.startswith('_')]
    f.write(f'  {attrs[:20]}\\n\\n')
    
    f.write('Checking if Diagnostics in CLASS_TO_MODULE:\\n')
    if hasattr(mayatk, 'CLASS_TO_MODULE'):
        f.write(f'  "Diagnostics" in CLASS_TO_MODULE: {"Diagnostics" in mayatk.CLASS_TO_MODULE}\\n')
        f.write(f'  Available classes: {list(mayatk.CLASS_TO_MODULE.keys())[:10]}\\n')

print('Debug complete.')
"""


def send_to_maya(code, port=7002):
    ports_to_try = [port, 7002, 7003]

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
                tempfile.gettempdir(), "diagnostics_debug_output.txt"
            )
            if os.path.exists(temp_file):
                with open(temp_file, "r", encoding="utf-8") as f:
                    output = f.read()
                os.remove(temp_file)

                print("\\n" + "=" * 60)
                print(output)
                print("=" * 60)

            return True

        except Exception as e:
            if try_port == ports_to_try[-1]:
                print(f"\\n✗ Could not connect: {e}")
                return False
            continue

    return False


if __name__ == "__main__":
    send_to_maya(test_script)
