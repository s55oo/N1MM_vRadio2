"""Read-only probe: sends query commands to the FTDX101D and prints the raw answers.
Usage: python probe_yaesu.py [COM14] [38400]
"""
import sys
import time
import serial

port = sys.argv[1] if len(sys.argv) > 1 else "COM14"
baud = int(sys.argv[2]) if len(sys.argv) > 2 else 38400

QUERIES = ["ID;", "AI;", "FA;", "FB;", "MD0;", "MD1;", "IF;", "OI;", "TX;", "FT;", "FR;", "VS;",
           "ST;", "SM0;", "AG0;", "RG0;", "SQ0;", "PC;", "KS;", "MG;", "VX;", "NB0;", "NR0;",
           "PA0;", "RA0;", "LK;", "BY;", "RT;", "RT0;", "XT;", "XT0;", "CF;", "CF0;", "SH0;",
           "NA0;", "PS;"]

with serial.Serial(port, baud, bytesize=8, parity="N", stopbits=1, timeout=0.4) as s:
    s.reset_input_buffer()
    for q in QUERIES:
        s.write(q.encode("ascii"))
        buf = b""
        t0 = time.time()
        while time.time() - t0 < 0.5:
            c = s.read(1)
            if not c:
                break
            buf += c
            if c == b";":
                break
        print(f"{q:<6} -> {buf.decode('ascii', 'replace') or '(no answer)'}")
        time.sleep(0.03)
