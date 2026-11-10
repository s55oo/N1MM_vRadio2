"""vRadio - virtual radio translator.

Connects to a Yaesu FTDX101D (new-style Yaesu CAT) and presents it to other
software as a Kenwood TS-2000 on a (virtual) serial port.

    Yaesu FTDX101D  <-- COM14 38400 8N1 -->  vRadio  <-- COM1 -->  logger / WSJT-X / ...
                                                                  (select "Kenwood TS-2000")

Usage:
    python vradio.py                       # defaults: radio COM14@38400, app side COM1@38400
    python vradio.py --radio COM14 --cat COM1 --cat-baud 9600 -v
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

import serial

log = logging.getLogger("vradio")

__version__ = "1.0.1"
GITHUB_REPO = "s55oo/N1MM_vRadio2"

# vRadioTray.exe is built without a console: then sys.stderr is None and we run in the tray.
WINDOWED = sys.stderr is None
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))

# ---------------------------------------------------------------------------
# Mode tables
# Yaesu FTDX101D MD codes: 1 LSB, 2 USB, 3 CW-U, 4 FM, 5 AM, 6 RTTY-L, 7 CW-L,
#   8 DATA-L, 9 RTTY-U, A DATA-FM, B FM-N, C DATA-U, D AM-N, E PSK, F DATA-FM-N
# Kenwood TS-2000 MD codes: 1 LSB, 2 USB, 3 CW, 4 FM, 5 AM, 6 FSK, 7 CW-R, 9 FSK-R
# ---------------------------------------------------------------------------
Y2K_MODE = {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7",
            "8": "1", "9": "9", "A": "4", "B": "4", "C": "2", "D": "5", "E": "2", "F": "4"}
K2Y_MODE = {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7", "9": "9"}


BANDS = [(1_800_000, 2_000_000, "160m"), (3_500_000, 4_000_000, "80m"), (5_250_000, 5_450_000, "60m"),
         (7_000_000, 7_300_000, "40m"), (10_100_000, 10_150_000, "30m"), (14_000_000, 14_350_000, "20m"),
         (18_068_000, 18_168_000, "17m"), (21_000_000, 21_450_000, "15m"), (24_890_000, 24_990_000, "12m"),
         (28_000_000, 29_700_000, "10m"), (50_000_000, 54_000_000, "6m"), (70_000_000, 70_500_000, "4m")]


def band_of(hz: int) -> str | None:
    for lo, hi, name in BANDS:
        if lo <= hz <= hi:
            return name
    return None


def smeter_y2k(v: int) -> int:
    """Yaesu 0-255 (S9 ~ 130) -> TS-2000 0-30 (S9 = 15)."""
    if v <= 130:
        return round(v * 15 / 130)
    return min(30, 15 + round((v - 130) * 15 / 125))


class RadioError(Exception):
    pass


# ---------------------------------------------------------------------------
# Radio side (Yaesu)
# ---------------------------------------------------------------------------
class YaesuRadio:
    def __init__(self, port: str, baud: int):
        self.port, self.baud = port, baud
        self.ser: serial.Serial | None = None
        self.lock = threading.RLock()
        self.ok: bool | None = None          # last radio exchange OK? (for the tray icon)

    def open(self):
        self.ser = serial.Serial(self.port, self.baud, bytesize=8, parity="N", stopbits=1,
                                 timeout=0.3, write_timeout=1)
        self.ser.reset_input_buffer()
        log.info("Radio port %s open @ %d 8N1", self.port, self.baud)

    def close(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    def _read_answer(self, timeout: float = 0.6) -> str:
        buf = bytearray()
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            c = self.ser.read(1)
            if not c:
                continue
            buf += c
            if c == b";":
                return buf.decode("ascii", "replace")
        raise RadioError(f"timeout (partial: {buf!r})")

    def query(self, cmd: str, expect: str | None = None) -> str:
        """Send a query like 'FA;' and return the answer (e.g. 'FA014074000;')."""
        expect = expect or cmd[:2]
        with self.lock:
            for attempt in range(2):
                try:
                    if self.ser is None:
                        self.open()
                    self.ser.reset_input_buffer()
                    self.ser.write(cmd.encode("ascii"))
                    ans = self._read_answer()
                    # skip any unsolicited data that is not our answer
                    for _ in range(3):
                        if ans.startswith(expect) or ans == "?;":
                            break
                        ans = self._read_answer()
                    log.debug("  radio %-8s -> %s", cmd, ans)
                    self.ok = True
                    if ans == "?;":
                        raise RadioError(f"radio rejected {cmd}")
                    return ans
                except serial.SerialException as e:
                    log.warning("Radio port error: %s - reopening", e)
                    self.ok = False
                    self.close()
                    time.sleep(0.5)
                except RadioError as e:
                    if attempt:
                        if "rejected" not in str(e):
                            self.ok = False
                        raise
                    time.sleep(0.05)
            self.ok = False
            raise RadioError(f"no answer to {cmd}")

    def send(self, cmd: str):
        """Send a set command (no answer expected)."""
        with self.lock:
            try:
                if self.ser is None:
                    self.open()
                self.ser.write(cmd.encode("ascii"))
                log.debug("  radio %-8s (set)", cmd)
                time.sleep(0.02)
            except serial.SerialException as e:
                log.warning("Radio port error: %s", e)
                self.ok = False
                self.close()
                raise RadioError(str(e))


# ---------------------------------------------------------------------------
# Translator: Kenwood TS-2000 command in -> Kenwood answer out
# ---------------------------------------------------------------------------
class TS2000Emulator:
    def __init__(self, radio: YaesuRadio, usb_data: bool = False, lsb_data: bool = False,
                 vfo: str = "B", auto_split: bool = False):
        self.r = radio
        self.auto_split = auto_split
        self.want_own: bool | None = None   # N1MM TX focus on our radio? None = unknown
        self.udp_error: str | None = None   # N1MM UDP port busy?
        self.transmitting = False
        self.ai = 0
        self.usb_data = usb_data
        self.lsb_data = lsb_data
        self.lock = threading.Lock()
        # vfo="B": the software's VFO-A is the radio's VFO-B (SUB band) and vice versa.
        self.swap = vfo.upper() == "B"
        self.band = "1" if self.swap else "0"      # Yaesu P1 for MD/SM/RG/...: 0 main, 1 sub
        self.ymap = {"A": "B", "B": "A"} if self.swap else {"A": "A", "B": "B"}

    # --- helpers ---------------------------------------------------------
    def _val(self, ycmd: str, strip: int) -> str:
        """Query radio and return the answer payload after `strip` chars, without ';'."""
        return self.r.query(ycmd)[strip:-1]

    def _freq(self, vfo: str) -> str:
        y = self.ymap[vfo]
        return f"F{vfo}{int(self._val(f'F{y};', 2)):011d};"

    def _set_freq(self, vfo: str, p: str):
        self.r.send(f"F{self.ymap[vfo]}{int(p):09d};")

    def _mode(self) -> str:
        return Y2K_MODE.get(self._val(f"MD{self.band};", 3), "2")

    def _split(self) -> bool:
        """Kenwood split = TX on the other VFO than the one we receive on."""
        if self.auto_split:
            return False      # vRadio moves TX itself; N1MM should see a plain, non-split radio
        tx_sub = self._val("FT;", 2) == "1"
        return tx_sub != self.swap

    def build_if(self) -> str:
        # OI = information for the SUB band, same layout as IF
        y = self.r.query("OI;" if self.swap else "IF;", "OI" if self.swap else "IF")
        if len(y) < 28:
            raise RadioError(f"short IF: {y}")
        mem, freq, clar = y[2:5], y[5:14], y[14:19]
        rx_clar, tx_clar, ymode, vfomem = y[19], y[20], y[21], y[22]
        tx = "1" if self._val("TX;", 2) != "0" else "0"
        split = "1" if self._split() else "0"
        kvfo = "0" if vfomem == "0" else "2"
        kmode = Y2K_MODE.get(ymode, "2")
        return ("IF" + f"{int(freq):011d}" + "00000" + clar + rx_clar + tx_clar +
                mem + tx + kmode + kvfo + "0" + split + "0" + "00" + "0" + ";")

    # --- TX VFO selection (Yaesu ST1 = TX on SUB, ST0 = TX on MAIN) --------
    def tx_on_own(self):
        self.r.send("ST1;" if self.swap else "ST0;")

    def tx_on_other(self):
        self.r.send("ST0;" if self.swap else "ST1;")

    def apply_idle_tx(self, why: str):
        """Set the TX VFO for the next transmission: our VFO if N1MM's TX focus is on our
        radio, otherwise the other VFO (split off)."""
        if self.want_own:
            self.tx_on_own()
            log.info("%s: TX on VFO-%s (N1MM radio with TX focus)", why, "B" if self.swap else "A")
        else:
            self.tx_on_other()
            log.info("%s: split off, TX on VFO-%s", why, "A" if self.swap else "B")

    def set_focus(self, own: bool):
        """Called when N1MM's ActiveRadioNr (TX focus) changes."""
        with self.lock:
            if own == self.want_own:
                return
            self.want_own = own
            if not self.transmitting:            # never switch VFO in the middle of a transmission
                self.apply_idle_tx("N1MM TX focus -> radio %s" % ("ours" if own else "other"))

    def tx_watch_loop(self, stop: threading.Event, interval: float = 0.15):
        """Whatever keyed the radio (CAT, WinKeyer, PTT line, VOX): as soon as it goes from
        TX back to RX, put TX back where N1MM's focus says (no focus info: split off)."""
        while not stop.is_set():
            try:
                with self.lock:
                    is_tx = self._val("TX;", 2) != "0"
                    if self.transmitting and not is_tx:
                        self.transmitting = False
                        self.apply_idle_tx("TX -> RX")
                    self.transmitting = is_tx
            except (RadioError, ValueError) as e:
                log.debug("tx-watch: %s", e)
            stop.wait(interval)

    def n1mm_udp_loop(self, stop: threading.Event, port: int, my_radio: int):
        """Listen to N1MM RadioInfo broadcasts and follow ActiveRadioNr (TX focus)."""
        import re
        # No SO_REUSEADDR: on Windows a shared UDP port silently hands each packet
        # to only one listener. Take the port exclusively and complain loudly if busy.
        while not stop.is_set():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                sock.bind(("", port))
                self.udp_error = None
                break
            except OSError as e:
                sock.close()
                if self.udp_error is None:
                    log.error("UDP %d is used by another program (%s) - TX focus NOT followed. "
                              "Close it or pick another --n1mm-udp port; retrying every 5 s", port, e)
                self.udp_error = f"UDP {port} busy"
                stop.wait(5)
        else:
            return
        sock.settimeout(0.5)
        log.info("Listening for N1MM RadioInfo on UDP %d (we are N1MM radio %d)", port, my_radio)
        rx = re.compile(rb"<ActiveRadioNr>(\d+)</ActiveRadioNr>")
        while not stop.is_set():
            try:
                data, _ = sock.recvfrom(16384)
            except socket.timeout:
                continue
            except OSError as e:
                log.debug("udp: %s", e)
                continue
            m = rx.search(data)
            if m:
                self.set_focus(int(m.group(1)) == my_radio)

    # --- dual receive keeper -------------------------------------------------
    def dual_rx_loop(self, stop: threading.Event, cmd: str, interval: float = 2.0):
        """Keep dual receive (MAIN + SUB) switched on: re-send `cmd` whenever the radio drifts off it."""
        want = cmd.rstrip(";")
        while not stop.is_set():
            try:
                with self.lock:
                    cur = self.r.query("FR;")[:-1]
                    if cur != want:
                        self.r.send(cmd)
                        log.info("Dual RX: radio reported %s, sent %s", cur, cmd)
            except RadioError as e:
                log.debug("dual-rx: %s", e)
            stop.wait(interval)

    # --- same band (N1MM refuses to put both radios on one band itself) ----
    def other_and_own_freq(self) -> tuple[int, int]:
        other, own = ("FA", "FB") if self.swap else ("FB", "FA")
        return int(self._val(f"{other};", 2)), int(self._val(f"{own};", 2))

    def copy_to_own(self, reason: str = ""):
        """Copy the other radio VFO (freq + mode) onto the VFO this software controls."""
        self.r.send("AB;" if self.swap else "BA;")     # AB = MAIN->SUB, BA = SUB->MAIN
        log.info("Copied radio VFO-%s -> VFO-%s %s", "A" if self.swap else "B",
                 "B" if self.swap else "A", reason)

    def follow_band_loop(self, stop: threading.Event, interval: float = 1.0):
        """When the other VFO (N1MM radio A) changes band, bring our VFO onto that band."""
        last = None
        while not stop.is_set():
            try:
                with self.lock:
                    other, own = self.other_and_own_freq()
                    ob = band_of(other)
                    if ob and ob != last:
                        if band_of(own) != ob:
                            self.copy_to_own(f"(follow band {ob})")
                        last = ob
            except (RadioError, ValueError) as e:
                log.debug("follow-band: %s", e)
            stop.wait(interval)

    # --- dispatcher --------------------------------------------------------
    def handle(self, cmd: str) -> str:
        """cmd without trailing ';'. Returns the reply to send to the app ('' for none)."""
        with self.lock:
            try:
                return self._handle(cmd.upper(), cmd[2:])
            except (RadioError, ValueError, IndexError) as e:
                log.warning("%s; -> error: %s", cmd, e)
                return "?;"

    def _handle(self, cmd: str, p: str) -> str:
        c = cmd[:2]
        p = cmd[2:]
        r = self.r

        # vRadio's own commands, for N1MM macros, e.g. {CAT2ASC VRAB;}
        if cmd == "VRAB":
            self.copy_to_own("(VRAB macro)")
            return ""

        if c == "ID":
            return "ID019;"
        if c == "TY":
            return "TYK 00;"
        if c == "AI":
            if p:
                self.ai = int(p[0])
                return ""
            return f"AI{self.ai};"
        if c == "PS":
            if p:
                if p == "1":
                    r.send("PS1;")
                    time.sleep(1.2)
                    r.send("PS1;")
                else:
                    r.send("PS0;")
                return ""
            return r.query("PS;")

        # Frequency
        if c in ("FA", "FB"):
            vfo = c[1]
            if p:
                self._set_freq(vfo, p)
                return ""
            return self._freq(vfo)
        if c == "IF":
            return self.build_if()

        # Mode
        if c == "MD":
            if p:
                ymode = K2Y_MODE.get(p[0])
                if ymode is None:
                    return "?;"
                if p[0] == "2" and self.usb_data:
                    ymode = "C"
                elif p[0] == "1" and self.lsb_data:
                    ymode = "8"
                cur = self._val(f"MD{self.band};", 3)
                # keep e.g. DATA-U if the app asks for USB and radio is already in DATA-U
                if cur == ymode or (Y2K_MODE.get(cur) == p[0] and not (self.usb_data or self.lsb_data)):
                    return ""
                r.send(f"MD{self.band}{ymode};")
                return ""
            return f"MD{self._mode()};"

        # PTT
        if c == "TX":
            if self.auto_split:
                self.tx_on_own()          # transmit on the VFO this software controls
                time.sleep(0.05)
            r.send("TX1;")
            return ""
        if c == "RX":
            r.send("TX0;")
            if self.auto_split:
                time.sleep(0.05)
                self.apply_idle_tx("CAT RX")    # focus-aware; no focus info -> split off
            return ""

        # VFO / split
        if c == "FT":
            if p:
                if self.auto_split:
                    return ""      # --auto-split decides the TX VFO itself
                # Kenwood FT1 = transmit on the other VFO. Yaesu ST1 = TX on SUB, ST0 = TX on MAIN.
                want_split = p[0] == "1"
                tx_sub = want_split != self.swap
                r.send("ST1;" if tx_sub else "ST0;")
                return ""
            return "FT1;" if self._split() else "FT0;"
        if c == "FR":
            if p:
                return ""          # we always receive on the selected radio VFO
            return "FR0;"
        if c == "VV":
            r.send("BA;" if self.swap else "AB;")
            return ""

        # Meter / levels (Kenwood band 0 = our VFO, band 1 = the other one)
        yb = {"0": self.band, "1": "0" if self.band == "1" else "1"}
        if c == "SM":
            band = p[:1] or "0"
            v = int(self._val(f"SM{yb.get(band, self.band)};", 3))
            return f"SM{band}{smeter_y2k(v):04d};"
        if c == "AG":
            band = p[:1] or "0"
            y = yb.get(band, self.band)
            if len(p) > 1:
                r.send(f"AG{y}{int(p[1:]):03d};")
                return ""
            return f"AG{band}{int(self._val(f'AG{y};', 3)):03d};"
        if c == "RG":
            if p:
                r.send(f"RG{self.band}{int(p):03d};")
                return ""
            return f"RG{int(self._val(f'RG{self.band};', 3)):03d};"
        if c == "SQ":
            band = p[:1] or "0"
            y = yb.get(band, self.band)
            if len(p) > 1:
                r.send(f"SQ{y}{int(p[1:]):03d};")
                return ""
            return f"SQ{band}{int(self._val(f'SQ{y};', 3)):03d};"
        if c == "PC":
            if p:
                r.send(f"PC{max(5, min(100, int(p))):03d};")
                return ""
            return f"PC{int(self._val('PC;', 2)):03d};"
        if c == "KS":
            if p:
                r.send(f"KS{max(4, min(60, int(p))):03d};")
                return ""
            return f"KS{int(self._val('KS;', 2)):03d};"
        if c == "VX":
            if p:
                r.send(f"VX{p[0]};")
                return ""
            return r.query("VX;")
        b = self.band
        if c == "NB":
            if p:
                r.send(f"NB{b}{'1' if p[0] != '0' else '0'};")
                return ""
            return f"NB{self._val(f'NB{b};', 3)};"
        if c == "NR":
            if p:
                r.send(f"NR{b}{'1' if p[0] != '0' else '0'};")
                return ""
            return f"NR{self._val(f'NR{b};', 3)};"
        if c == "PA":
            if p:
                r.send(f"PA{b}{'1' if p[0] != '0' else '0'};")
                return ""
            return f"PA{'1' if self._val(f'PA{b};', 3) != '0' else '0'}0;"
        if c == "RA":
            if p:
                r.send(f"RA{b}{'1' if int(p) else '0'};")
                return ""
            return f"RA{'01' if self._val(f'RA{b};', 3) != '0' else '00'};"

        # RIT / XIT (Yaesu clarifier)
        if c in ("RT", "XT"):
            if p:
                r.send(f"{c}{p[0]};")
                return ""
            return r.query(f"{c};")
        if c == "RC":
            r.send("RC;")
            return ""
        if c in ("RU", "RD"):
            step = int(p) if p else 10
            r.send(f"{c}{max(0, min(9999, step)):04d};")
            return ""

        # misc pass-through
        if c == "BY":
            return r.query("BY;")
        if c in ("UP", "DN"):
            r.send(f"{c};")
            return ""

        log.info("Unsupported TS-2000 command: %s;", cmd)
        return "?;"


# ---------------------------------------------------------------------------
# App side (virtual COM port)
# ---------------------------------------------------------------------------
class CatServer:
    def __init__(self, port: str, baud: int, emu: TS2000Emulator, poll: float):
        self.port, self.baud, self.emu, self.poll = port, baud, emu, poll
        self.ser: serial.Serial | None = None
        self.wlock = threading.Lock()
        self.stop = threading.Event()

    def write(self, s: str):
        if s and self.ser:
            with self.wlock:
                self.ser.write(s.encode("ascii"))

    def auto_info_loop(self):
        """Emulate Kenwood AI (auto information): push IF; when the radio state changes."""
        last = None
        while not self.stop.is_set():
            time.sleep(self.poll)
            if not self.emu.ai or not self.ser:
                last = None
                continue
            ans = self.emu.handle("IF")
            if ans != "?;" and ans != last:
                last = ans
                log.debug("AI push %s", ans)
                try:
                    self.write(ans)
                except serial.SerialException:
                    pass

    def run(self):
        threading.Thread(target=self.auto_info_loop, daemon=True).start()
        while not self.stop.is_set():
            try:
                self.ser = serial.Serial(self.port, self.baud, bytesize=8, parity="N",
                                         stopbits=1, timeout=0.1, write_timeout=1)
                log.info("TS-2000 emulation on %s @ %d 8N1 - point your software here",
                         self.port, self.baud)
                buf = ""
                while not self.stop.is_set():
                    data = self.ser.read(256)
                    if not data:
                        continue
                    buf += data.decode("ascii", "ignore")
                    while ";" in buf:
                        raw, buf = buf.split(";", 1)
                        cmd = raw.strip()
                        if not cmd:
                            continue
                        reply = self.emu.handle(cmd)
                        log.debug("app %-16s -> %s", cmd + ";", reply or "(none)")
                        self.write(reply)
                    if len(buf) > 512:
                        buf = ""
            except serial.SerialException as e:
                log.warning("CAT port %s error: %s - retrying in 2 s", self.port, e)
                self.ser = None
                time.sleep(2)


class TcpCatServer:
    """TS-2000 emulation over TCP (e.g. N1MM Logger+ Configurer: Port = TCP)."""

    def __init__(self, host: str, port: int, emu: TS2000Emulator, poll: float):
        self.host, self.port, self.emu, self.poll = host, port, emu, poll
        self.clients: list[socket.socket] = []
        self.clock = threading.Lock()
        self.stop = threading.Event()

    def _send(self, conn: socket.socket, s: str):
        if s:
            conn.sendall(s.encode("ascii"))

    def auto_info_loop(self):
        last = None
        while not self.stop.is_set():
            time.sleep(self.poll)
            with self.clock:
                clients = list(self.clients)
            if not self.emu.ai or not clients:
                last = None
                continue
            ans = self.emu.handle("IF")
            if ans != "?;" and ans != last:
                last = ans
                log.debug("AI push %s", ans)
                for c in clients:
                    try:
                        self._send(c, ans)
                    except OSError:
                        pass

    def client_loop(self, conn: socket.socket, addr):
        log.info("TCP client connected: %s:%d", *addr)
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with self.clock:
            self.clients.append(conn)
        buf = ""
        try:
            while not self.stop.is_set():
                data = conn.recv(1024)
                if not data:
                    break
                buf += data.decode("ascii", "ignore")
                while ";" in buf:
                    raw, buf = buf.split(";", 1)
                    cmd = raw.strip()
                    if not cmd:
                        continue
                    reply = self.emu.handle(cmd)
                    log.debug("tcp %-16s -> %s", cmd + ";", reply or "(none)")
                    self._send(conn, reply)
                if len(buf) > 512:
                    buf = ""
        except OSError as e:
            log.debug("TCP client %s:%d error: %s", *addr, e)
        finally:
            with self.clock:
                if conn in self.clients:
                    self.clients.remove(conn)
            conn.close()
            log.info("TCP client disconnected: %s:%d", *addr)

    def run(self):
        threading.Thread(target=self.auto_info_loop, daemon=True).start()
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.port))
        srv.listen(5)
        srv.settimeout(0.5)
        log.info("TS-2000 emulation on TCP %s:%d - in N1MM set Port=TCP, Radio=TS-2000",
                 self.host, self.port)
        try:
            while not self.stop.is_set():
                try:
                    conn, addr = srv.accept()
                except socket.timeout:
                    continue
                threading.Thread(target=self.client_loop, args=(conn, addr), daemon=True).start()
        finally:
            srv.close()


def main():
    ap = Parser(
        description="Yaesu FTDX101D -> Kenwood TS-2000 CAT translator",
        usage="vRadio.exe [RADIO_PORT] [RADIO_BAUD] [options]   e.g. vRadio.exe COM5 38400 --tcp 4532")
    ap.add_argument("port", nargs="?", metavar="RADIO_PORT",
                    help="radio COM port, same as --radio (e.g. COM14)")
    ap.add_argument("baud", nargs="?", type=int, metavar="RADIO_BAUD",
                    help="radio baud, same as --radio-baud (e.g. 38400)")
    ap.add_argument("--radio", default="COM14", help="radio port (default COM14)")
    ap.add_argument("--radio-baud", type=int, default=38400, help="radio baud (default 38400)")
    ap.add_argument("--cat", default="COM1", help="TS-2000 emulation port (default COM1)")
    ap.add_argument("--cat-baud", type=int, default=38400, help="emulation port baud (default 38400)")
    ap.add_argument("--tcp", type=int, metavar="PORT",
                    help="serve TS-2000 CAT over TCP on this port instead of a COM port (e.g. 4532)")
    ap.add_argument("--tcp-host", default="127.0.0.1",
                    help="TCP listen address (default 127.0.0.1; use 0.0.0.0 for other PCs)")
    ap.add_argument("--usb-data", action="store_true",
                    help="when software selects USB, put the radio in DATA-U (good for WSJT-X/FT8)")
    ap.add_argument("--lsb-data", action="store_true", help="when software selects LSB, use DATA-L")
    ap.add_argument("--vfo", choices=["A", "B", "a", "b"], default="B",
                    help="radio VFO the software controls as its VFO-A (default B = SUB band)")
    ap.add_argument("--tx-follow", action="store_true",
                    help="at startup set the radio to transmit on the same VFO as --vfo (no split)")
    ap.add_argument("--same-band", action="store_true",
                    help="at startup copy the other radio VFO onto ours (A->B), so both are on one band")
    ap.add_argument("--follow-band", action="store_true",
                    help="whenever the other VFO (N1MM radio A) changes band, move our VFO to that band")
    ap.add_argument("--auto-split", action="store_true",
                    help="CAT TX from this software transmits on our VFO (ST1), RX gives TX back "
                         "to the other VFO (ST0)")
    ap.add_argument("--n1mm-udp", type=int, metavar="PORT",
                    help="with --auto-split: follow N1MM TX focus from its RadioInfo UDP broadcast "
                         "(N1MM Configurer > Broadcast Data > Radio, e.g. 12064; avoid 12060-12063, "
                         "used by Callbooker/QSOrouter/POUNCer/PingPong)")
    ap.add_argument("--n1mm-radio", type=int, default=2,
                    help="which N1MM radio number vRadio is (default 2)")
    ap.add_argument("--dual-rx", action="store_true",
                    help="keep dual receive (MAIN + SUB) on all the time")
    ap.add_argument("--dual-rx-cmd", default="FR00;",
                    help="radio command for dual receive (default FR00; - verify on site)")
    ap.add_argument("--poll", type=float, default=0.3, help="AI auto-info poll interval, seconds")
    ap.add_argument("-v", "--verbose", action="store_true", help="log every command")
    ap.add_argument("--log", metavar="FILE", help="also write the log to this file")
    ap.add_argument("--tray", action="store_true",
                    help="run as a system tray icon (vRadioTray.exe always does)")
    ap.add_argument("--update", action="store_true",
                    help="download and install the latest release from GitHub, then exit")
    ap.add_argument("--auto-update", action="store_true",
                    help="at start, install a newer GitHub release (if any) and restart with it")
    ap.add_argument("--no-update-check", action="store_true",
                    help="do not check GitHub for new versions")
    ap.add_argument("--updated", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--version", action="version", version=f"vRadio {__version__}")
    a = ap.parse_args()

    if a.port:
        a.radio = a.port.upper()
    if a.baud:
        a.radio_baud = a.baud
    a.dual_rx_cmd = a.dual_rx_cmd.strip().upper().rstrip(";") + ";"
    tray = a.tray or WINDOWED
    if tray and not a.log:
        a.log = os.path.join(APP_DIR, "vradio_log.txt")
    handlers: list[logging.Handler] = []
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    if a.log:
        handlers.append(RotatingFileHandler(a.log, maxBytes=2_000_000, backupCount=3, encoding="utf-8"))
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")

    log.info("vRadio %s", __version__)
    cleanup_old_exe()
    state = {"radio": None, "emu": None, "server": None, "error": None, "args": a,
             "update": None, "relaunch": None}
    stop = threading.Event()

    if a.update or (a.auto_update and not a.updated):     # --updated: just restarted, no loop
        if not getattr(sys, "frozen", False):
            log.error("Updating works only for the exe, not for vradio.py")
            if a.update:
                return
        else:
            try:
                info = check_update()
                if info is None:
                    log.info("vRadio %s is the latest version", __version__)
                    if a.update:
                        if WINDOWED:
                            message_box(f"vRadio {__version__} is the latest version.")
                        return
                else:
                    exe = install_update(info)
                    if a.update:
                        msg = f"vRadio updated to {info['version']}. Start it again."
                        message_box(msg) if WINDOWED else print(msg)
                        return
                    relaunch(exe)
                    return
            except Exception as e:
                log.error("Update failed: %s - starting this version", e)
                if a.update:
                    if WINDOWED:
                        message_box(f"vRadio update failed: {e}")
                    return

    if tray:
        if not single_instance(wait=20 if a.updated else 0):
            message_box("vRadio is already running (see the tray icon).")
            return
        t = threading.Thread(target=run_core, args=(a, stop, state), daemon=True)
        t.start()
        run_tray(a, stop, state)
        stop.set()
        t.join(8)
        if state["radio"]:
            state["radio"].close()
        if state["relaunch"]:
            relaunch(state["relaunch"])
        return

    if not a.no_update_check:
        threading.Thread(target=update_check_loop, args=(stop, state), daemon=True).start()
    try:
        run_core(a, stop, state)
    except KeyboardInterrupt:
        log.info("Stopped.")
    finally:
        stop.set()
        if state["radio"]:
            state["radio"].close()


def run_core(a, stop: threading.Event, state: dict):
    """Connect to the radio, set everything up and serve until `stop` is set."""
    try:
        _run_core(a, stop, state)
    except Exception as e:          # shown in the tray tooltip
        state["error"] = str(e)
        log.exception("vRadio stopped with an error: %s", e)
        if not (a.tray or WINDOWED):
            raise


def _run_core(a, stop: threading.Event, state: dict):
    radio = YaesuRadio(a.radio, a.radio_baud)
    state["radio"] = radio
    while not stop.is_set():
        try:
            radio.open()
            rid = radio.query("ID;")
            log.info("Radio ID: %s %s", rid, "(FTDX101D)" if rid == "ID0681;" else "")
            break
        except (serial.SerialException, RadioError) as e:
            log.error("Cannot talk to radio on %s: %s - retrying in 3 s", a.radio, e)
            radio.ok = False
            radio.close()
            stop.wait(3)
    if stop.is_set():
        return

    emu = TS2000Emulator(radio, usb_data=a.usb_data, lsb_data=a.lsb_data, vfo=a.vfo,
                         auto_split=a.auto_split)
    state["emu"] = emu
    log.info("Software VFO-A -> radio VFO-%s", a.vfo.upper())
    if a.auto_split:
        try:
            emu.tx_on_other()
            log.info("Auto-split on: CAT TX from software -> TX on VFO-%s, idle -> TX on VFO-%s",
                     "B" if emu.swap else "A", "A" if emu.swap else "B")
        except RadioError as e:
            log.warning("Could not set TX VFO: %s", e)
        if a.tx_follow:
            log.warning("--tx-follow ignored: --auto-split controls the TX VFO")
            a.tx_follow = False
    if a.tx_follow:
        try:
            radio.send("ST1;" if emu.swap else "ST0;")    # ST1 = TX on SUB, ST0 = TX on MAIN
            time.sleep(0.2)
            tx_sub = radio.query("FT;") == "FT1;"
            want = "B" if emu.swap else "A"
            got = "B" if tx_sub else "A"
            if got == want:
                log.info("TX set to radio VFO-%s", got)
            else:
                log.warning("Tried to set TX to VFO-%s but radio reports TX on VFO-%s", want, got)
        except RadioError as e:
            log.warning("Could not set TX VFO: %s", e)
    if a.same_band and not a.follow_band:
        try:
            emu.copy_to_own("(--same-band)")
        except RadioError as e:
            log.warning("Could not copy VFO: %s", e)

    if a.tcp:
        server = TcpCatServer(a.tcp_host, a.tcp, emu, a.poll)
    else:
        server = CatServer(a.cat, a.cat_baud, emu, a.poll)
    server.stop = stop
    state["server"] = server
    if a.follow_band:
        threading.Thread(target=emu.follow_band_loop, args=(server.stop,), daemon=True).start()
        log.info("Follow-band on: our VFO follows the other VFO's band")
    if a.dual_rx:
        threading.Thread(target=emu.dual_rx_loop, args=(server.stop, a.dual_rx_cmd),
                         daemon=True).start()
        log.info("Dual RX keeper on (%s)", a.dual_rx_cmd)
    if a.auto_split:
        threading.Thread(target=emu.tx_watch_loop, args=(server.stop,), daemon=True).start()
        log.info("TX watcher on: split off as soon as the radio returns to RX")
        if a.n1mm_udp:
            threading.Thread(target=emu.n1mm_udp_loop,
                             args=(server.stop, a.n1mm_udp, a.n1mm_radio), daemon=True).start()
    elif a.n1mm_udp:
        log.warning("--n1mm-udp needs --auto-split; ignored")
    server.run()


# ---------------------------------------------------------------------------
# Auto-update from GitHub Releases
# ---------------------------------------------------------------------------
def _ver(s: str) -> tuple:
    import re
    return tuple(int(x) for x in re.findall(r"\d+", s)[:3])


def check_update(timeout: float = 8.0) -> dict | None:
    """Return info about a newer release that has an asset for this exe, else None."""
    import json
    import urllib.request
    if not getattr(sys, "frozen", False):
        return None
    req = urllib.request.Request(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                                 headers={"User-Agent": f"vRadio/{__version__}",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        rel = json.load(r)
    tag = rel.get("tag_name", "")
    if not tag or _ver(tag) <= _ver(__version__):
        return None
    name = os.path.basename(sys.executable).lower()
    for asset in rel.get("assets", []):
        if asset.get("name", "").lower() == name:
            return {"version": tag, "url": asset["browser_download_url"], "size": asset["size"],
                    "page": rel.get("html_url", "")}
    log.info("Release %s has no %s - not updating", tag, name)
    return None


def install_update(info: dict) -> str:
    """Download the new exe next to the running one and swap them. Returns the exe path."""
    import urllib.request
    exe = sys.executable
    new, old = exe + ".new", exe + ".old"
    log.info("Downloading vRadio %s (%d bytes) ...", info["version"], info["size"])
    req = urllib.request.Request(info["url"], headers={"User-Agent": f"vRadio/{__version__}"})
    with urllib.request.urlopen(req, timeout=60) as r, open(new, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
    with open(new, "rb") as f:
        head = f.read(2)
    if os.path.getsize(new) != info["size"] or head != b"MZ":
        os.remove(new)
        raise RuntimeError("downloaded file is incomplete or not an exe")
    if os.path.exists(old):
        os.remove(old)
    os.replace(exe, old)            # a running exe can be renamed, not overwritten
    os.replace(new, exe)
    log.info("Updated to %s (previous version kept as %s)", info["version"], os.path.basename(old))
    return exe


def relaunch(exe: str):
    """Start the (new) exe with the same options; the caller then exits."""
    import subprocess
    args = [x for x in sys.argv[1:] if x not in ("--update", "--updated")] + ["--updated"]
    flags = 0x00000008 | 0x00000200 if WINDOWED else 0x00000010   # DETACHED|NEW_GROUP / NEW_CONSOLE
    subprocess.Popen([exe] + args, creationflags=flags, close_fds=True)


def cleanup_old_exe():
    old = sys.executable + ".old"
    if getattr(sys, "frozen", False) and os.path.exists(old):
        try:
            os.remove(old)
        except OSError:
            pass                      # previous version still closing; next start removes it


def update_check_loop(stop: threading.Event, state: dict, notify=None, every: float = 6 * 3600):
    """Check for a new release now and every few hours; never installs by itself."""
    while not stop.is_set():
        try:
            info = check_update()
            if info and (state.get("update") or {}).get("version") != info["version"]:
                state["update"] = info
                log.warning("vRadio %s is available (this is %s). %s", info["version"], __version__,
                            "Tray menu: Install update." if notify else "Run: vRadio.exe --update")
                if notify:
                    notify(f"vRadio {info['version']} is available - right-click the tray icon to update.")
        except Exception as e:
            log.debug("update check failed: %s", e)
        stop.wait(every)


# ---------------------------------------------------------------------------
# System tray
# ---------------------------------------------------------------------------
def single_instance(wait: float = 0.0) -> bool:
    """Only one tray vRadio at a time (two would fight over COM14).
    After an update the old copy may still be closing, so the new one waits `wait` seconds."""
    import ctypes
    k32 = ctypes.windll.kernel32
    end = time.time() + wait
    while True:
        h = k32.CreateMutexW(None, False, "Local\\vRadioTray")
        if k32.GetLastError() != 183:                    # ERROR_ALREADY_EXISTS
            single_instance.handle = h
            return True
        k32.CloseHandle(h)
        if time.time() >= end:
            return False
        time.sleep(0.5)


def message_box(text: str, title: str = "vRadio"):
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)


def make_icon(color: str):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 62, 62), fill=color, outline="white", width=3)
    try:
        font = ImageFont.truetype("arialbd.ttf", 30)
    except OSError:
        font = ImageFont.load_default()
    d.text((32, 33), "vR", fill="white", font=font, anchor="mm")
    return img


def status_lines(a, state: dict) -> tuple[list[str], str]:
    """Return (menu lines, icon color)."""
    radio, emu, server = state["radio"], state["emu"], state["server"]
    if state["error"]:
        return [f"Error: {state['error']}"[:120]], "#c0392b"
    if radio is None or radio.ok is None:
        r, color = f"Radio {a.radio}: connecting...", "#7f8c8d"
    elif radio.ok:
        r, color = f"Radio {a.radio}: OK", "#1e8449"
    else:
        r, color = f"Radio {a.radio}: no answer", "#c0392b"
    if isinstance(server, TcpCatServer):
        n = len(server.clients)
        cat = f"N1MM TCP {a.tcp}: " + (f"{n} connected" if n else "waiting")
    elif isinstance(server, CatServer):
        cat = f"CAT {a.cat}: " + ("open" if server.ser else "not open")
    else:
        cat = "CAT: starting"
    lines = [r, cat]
    if emu is not None and emu.auto_split:
        own = "B" if emu.swap else "A"
        other = "A" if emu.swap else "B"
        if emu.want_own is None:
            f = "TX focus: unknown (split off)"
        elif emu.want_own:
            f = f"TX focus: radio {a.n1mm_radio} (VFO-{own})"
        else:
            f = f"TX focus: other radio (VFO-{other})"
        lines.append(f)
    if emu is not None and emu.udp_error:
        lines.append(f"{emu.udp_error} - TX focus not followed")
        color = "#c0392b"
    if state.get("update"):
        lines.append(f"Update {state['update']['version']} available")
    if emu is not None and emu.transmitting and radio and radio.ok:
        lines.append("TRANSMITTING")
        color = "#d35400"
    return lines, color


def run_tray(a, stop: threading.Event, state: dict):
    import pystray

    icons = {}

    def icon_for(color):
        if color not in icons:
            icons[color] = make_icon(color)
        return icons[color]

    def line(i):
        return lambda item: (status_lines(a, state)[0] + [""] * 6)[i]

    def visible(i):
        return lambda item: len(status_lines(a, state)[0]) > i

    def copy_ab(icon, item):
        emu = state["emu"]
        if emu is not None:
            try:
                with emu.lock:
                    emu.copy_to_own("(tray menu)")
            except RadioError as e:
                log.warning("Copy failed: %s", e)

    def open_log(icon, item):
        if a.log and os.path.exists(a.log):
            os.startfile(a.log)

    def open_folder(icon, item):
        os.startfile(APP_DIR)

    def quit_app(icon, item):
        log.info("Exit from tray menu")
        stop.set()
        icon.stop()

    def notify(text):
        try:
            icon.notify(text, "vRadio")
        except Exception:
            pass

    def do_update(icon, item):
        info = state.get("update")
        emu = state["emu"]
        if not info:
            return
        if emu is not None and emu.transmitting:
            notify("Not now - the radio is transmitting.")
            return

        def work():
            try:
                state["relaunch"] = install_update(info)
            except Exception as e:
                log.error("Update failed: %s", e)
                notify(f"Update failed: {e}")
                return
            log.info("Restarting with %s", info["version"])
            stop.set()                  # main() closes COM14 and starts the new exe
            icon.stop()
        threading.Thread(target=work, daemon=True).start()

    def check_now(icon, item):
        def work():
            try:
                info = check_update()
            except Exception as e:
                notify(f"Update check failed: {e}")
                return
            if info:
                state["update"] = info
                icon.update_menu()
                notify(f"vRadio {info['version']} is available - right-click > Install update.")
            else:
                notify(f"vRadio {__version__} is the latest version.")
        threading.Thread(target=work, daemon=True).start()

    def update_label(item):
        info = state.get("update")
        return f"Install update {info['version']} (restarts vRadio)" if info else "Install update"

    own = "B" if a.vfo.upper() == "B" else "A"
    other = "A" if own == "B" else "B"
    menu = pystray.Menu(
        pystray.MenuItem(line(0), None, enabled=False),
        pystray.MenuItem(line(1), None, enabled=False, visible=visible(1)),
        pystray.MenuItem(line(2), None, enabled=False, visible=visible(2)),
        pystray.MenuItem(line(3), None, enabled=False, visible=visible(3)),
        pystray.MenuItem(line(4), None, enabled=False, visible=visible(4)),
        pystray.MenuItem(line(5), None, enabled=False, visible=visible(5)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"Copy VFO-{other} -> VFO-{own} (same band)", copy_ab),
        pystray.MenuItem("Open log", open_log),
        pystray.MenuItem("Open vRadio folder", open_folder),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(update_label, do_update, visible=lambda item: bool(state.get("update"))),
        pystray.MenuItem(f"Check for updates (v{__version__})", check_now),
        pystray.MenuItem("Exit vRadio", quit_app),
    )
    icon = pystray.Icon("vRadio", icon_for("#7f8c8d"), "vRadio - starting", menu)

    def updater(icon):
        icon.visible = True
        if not a.no_update_check:
            threading.Thread(target=update_check_loop, args=(stop, state, notify), daemon=True).start()
        last = None
        while not stop.is_set():
            lines, color = status_lines(a, state)
            title = ("vRadio - " + " | ".join(lines))[:127]
            if (title, color) != last:
                icon.icon = icon_for(color)
                icon.title = title
                icon.update_menu()
                last = (title, color)
            stop.wait(1.0)
        icon.stop()

    log.info("vRadio running in the system tray")
    icon.run(setup=updater)


class Parser(argparse.ArgumentParser):
    """Shows --help / argument errors in a message box when there is no console."""

    def _print_message(self, message, file=None):
        if message and (sys.stderr is None or sys.stdout is None):
            message_box(message)
        else:
            super()._print_message(message, file)


if __name__ == "__main__":
    main()
