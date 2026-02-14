"""Debug namespace alias creation in Maya."""

import socket

code = """
import mayatk
print("Checking namespace aliases...")
print("Dir mayatk:", [x for x in dir(mayatk) if not x.startswith('_')])
print("Has Instancing:", 'Instancing' in dir(mayatk))
print("Trying to access Instancing...")
try:
    print("mayatk.Instancing:", mayatk.Instancing)
except AttributeError as e:
    print("ERROR:", e)
"""

sock = socket.socket()
sock.connect(("127.0.0.1", 7002))
sock.send(code.encode("utf-8"))

import time

time.sleep(0.5)

response = sock.recv(8192).decode("utf-8", errors="replace")
print(response)
sock.close()
