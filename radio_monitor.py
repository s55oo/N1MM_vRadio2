"""vRadio test tool - watches the FTDX101D and prints every change (read-only).

Use it on site: start it, then press buttons on the radio or in N1MM (e.g. Ctrl+Alt+D dual RX,
split, VFO swap) and see which CAT values change.

Usage:
    radio_monitor.exe [COM14] [38400]            watch FR / FT / ST / VS / TX / FA / FB / MD
    radio_monitor.exe COM14 38400 FR00;          send one command first, then watch
Stop with Ctrl+C. While it runs, nothing else can use COM14 (stop vRadio first).
"""
import sys
import time
import serial

sys.stdout.reconfigure(line_buffering=True)

port = sys.argv[1] if len(sys.argv) > 1 else "COM14"
baud = int(sys.argv[2]) if len(sys.argv) > 2 else 38400
send_first = sys.argv[3] if len(sys.argv) > 3 else None

WATCH = {
    "FR;": "dual/single RX",
    "FT;": "TX VFO (0=A/MAIN 1=B/SUB)",
    "ST;": "split",
    "VS;": "VFO select",
    "TX;": "TX state",
    "FA;": "VFO-A",
    "FB;": "VFO-B",
    "MD0;": "mode MAIN",
    "MD1;": "mode SUB",
}


def ask(s, cmd):
    s.reset_input_buffer()
    s.write(cmd.encode("ascii"))
    buf = b""
    t_end = time.time() + 0.5
    while time.time() < t_end:
        c = s.read(1)
        if not c:
            continue
        buf += c
        if c == b";":
            break
    return buf.decode("ascii", "replace") or "(no answer)"


def main():
    print(f"vRadio radio monitor - {port} @ {baud} 8N1   (Ctrl+C to stop)")
    try:
        s = serial.Serial(port, baud, bytesize=8, parity="N", stopbits=1, timeout=0.2)
    except serial.SerialException as e:
        print(f"Cannot open {port}: {e}\nIs vRadio or another program using it?")
        input("Press Enter to close...")
        return
    with s:
        print("Radio ID:", ask(s, "ID;"))
        if send_first:
            cmd = send_first if send_first.endswith(";") else send_first + ";"
            s.write(cmd.encode("ascii"))
            print(f"Sent {cmd}")
            time.sleep(0.3)
        last = {}
        while True:
            for cmd, label in WATCH.items():
                ans = ask(s, cmd)
                if last.get(cmd) != ans:
                    mark = "" if cmd not in last else "  <-- changed"
                    print(f"{time.strftime('%H:%M:%S')}  {cmd:<5} {ans:<16} {label}{mark}")
                    last[cmd] = ans
            time.sleep(0.3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")

