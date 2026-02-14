"""Reload mayatk in Maya and test."""

import socket

code = """
# Reload mayatk completely
import sys
if 'mayatk' in sys.modules:
    # Remove all mayatk submodules
    to_remove = [k for k in sys.modules.keys() if k.startswith('mayatk')]
    for k in to_remove:
        del sys.modules[k]
    print(f"Removed {len(to_remove)} mayatk modules from cache")

# Fresh import
import mayatk
print("mayatk reloaded")
print("Has Instancing:", 'Instancing' in dir(mayatk))
if 'Instancing' in dir(mayatk):
    print("SUCCESS! Instancing:", mayatk.Instancing)
    print("Bases:", [b.__name__ for b in mayatk.Instancing.__bases__])
else:
    print("Instancing NOT FOUND")
    print("Available:", [x for x in dir(mayatk) if not x.startswith('_')][:10])
"""

sock = socket.socket()
sock.connect(("127.0.0.1", 7002))
sock.send(code.encode("utf-8"))

import time

time.sleep(1.0)

try:
    response = sock.recv(16384).decode("utf-8", errors="replace")
    if response:
        print(response)
    else:
        print("(No response)")
except:
    print("(No response)")

sock.close()
