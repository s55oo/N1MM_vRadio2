"""Acts like logging software: sends read-only TS-2000 queries to the emulated port.
Usage: python test_client.py [COM2] [38400]
"""
import sys
import time
import serial

port = sys.argv[1] if len(sys.argv) > 1 else "COM2"
baud = int(sys.argv[2]) if len(sys.argv) > 2 else 38400
QUERIES = ["ID;", "AI;", "FA;", "FB;", "MD;", "IF;", "FT;", "FR;", "SM0;", "AG0;", "RG;",
           "PC;", "KS;", "NB;", "NR;", "PA;", "RA;", "RT;", "XT;", "PS;", "ZZ;"]

with serial.Serial(port, baud, timeout=1.5) as s:
    s.reset_input_buffer()
    for q in QUERIES:
        s.write(q.encode())
        buf = b""
        t0 = time.time()
        while time.time() - t0 < 1.5 and not buf.endswith(b";"):
            buf += s.read(1)
        print(f"{q:<5} -> {buf.decode(errors='replace') or '(no answer)'}")
