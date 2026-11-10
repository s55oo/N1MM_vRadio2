"""Acts like N1MM over TCP: sends read-only TS-2000 queries.
Usage: python test_tcp.py [127.0.0.1] [4532]
"""
import socket
import sys
import time

host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 4532
QUERIES = ["ID;", "AI;", "FA;", "FB;", "MD;", "IF;", "FT;", "SM0;", "PS;"]

with socket.create_connection((host, port), timeout=2) as s:
    for q in QUERIES:
        s.sendall(q.encode())
        buf = b""
        t0 = time.time()
        while time.time() - t0 < 2 and not buf.endswith(b";"):
            buf += s.recv(1)
        print(f"{q:<5} -> {buf.decode(errors='replace')}")
