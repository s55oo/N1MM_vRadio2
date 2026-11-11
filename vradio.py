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


class TrafficMonitor:
    """Live traffic for the Monitor window. Each kind is off until its tick is set, so it
    costs nothing in normal operation."""
    POLLS = {"IF", "FA", "FB", "MD", "SM", "TX", "FT", "FR", "AI", "PS", "ID", "TY", "OI", "ST",
             "AG", "RG", "SQ", "PC", "RA", "PA", "NB", "NR", "BC", "RT", "XT", "RU", "RD", "KS", "SH", "SL"}

    def __init__(self):
        import collections
        self.on = {"cat": False, "radio": False}
        self.hide_polls = True
        self.lines = collections.deque(maxlen=5000)
        self.lock = threading.Lock()

    def add(self, kind: str, text: str):
        if self.on.get(kind):
            stamp = time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
            with self.lock:
                self.lines.append(f"{stamp} {text}")

    def take(self) -> list[str]:
        with self.lock:
            out = list(self.lines)
            self.lines.clear()
        return out

    def is_poll(self, cmd: str) -> bool:
        """A plain query without arguments (N1MM asks these all the time)."""
        c = cmd.strip().rstrip(";").upper()
        return c[:2] in self.POLLS and len(c) <= 3

    def cat(self, who: str, cmd: str, reply: str):
        # TS-2000 "TX;" is PTT, not a query: always show it
        ptt = cmd.strip().upper()[:2] in ("TX", "RX")
        if self.on["cat"] and (ptt or not (self.hide_polls and self.is_poll(cmd))):
            self.add("cat", f"CAT {who:<15} {cmd + ';':<18} -> {reply or '(none)'}")

    def radio(self, cmd: str, ans: str | None):
        if self.on["radio"] and not (self.hide_polls and ans is not None and self.is_poll(cmd)):
            self.add("radio", f"RIG {cmd:<18} " + ("(set)" if ans is None else f"-> {ans}"))


MON = TrafficMonitor()

__version__ = "1.0.7"
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
                    # The microHAM router can also deliver answers meant for another program
                    # (or the radio's auto-information): only accept the answer to OUR question.
                    t_end = time.monotonic() + 0.8
                    skipped = []
                    while True:
                        ans = self._read_answer(max(0.05, t_end - time.monotonic()))
                        if ans.startswith(expect) or ans == "?;":
                            break
                        skipped.append(ans)
                        if time.monotonic() >= t_end or len(skipped) > 20:
                            raise RadioError(f"no {expect} answer (only {', '.join(skipped[:3])})")
                    if skipped:
                        log.debug("  radio %-8s skipped %s", cmd, " ".join(skipped))
                    log.debug("  radio %-8s -> %s", cmd, ans)
                    MON.radio(cmd, ans)
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
                MON.radio(cmd, None)
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
        self.udp_listening = False          # N1MM UDP socket bound
        self.udp_last = 0.0                 # time of the last N1MM RadioInfo packet
        self.transmitting = False
        self.cat_tx = False                 # between CAT TX; and RX; from N1MM radio 2
        self.freq_gen = 0                   # +1 whenever N1MM or follow-band sets our VFO
        self.split_off_idle = False         # split on only during radio 2's CAT TX
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
        self.freq_gen += 1          # tells the DJ wheel to re-read the frequency

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

    def idle_own(self) -> bool:
        """Should the radio sit with TX on our VFO while nobody transmits?"""
        if self.split_off_idle:
            return False      # split only during radio 2's own CAT TX; off after every TX
        return bool(self.want_own)

    def apply_idle_tx(self, why: str):
        """Set the TX VFO for the next transmission. Normally our VFO if N1MM's TX focus is
        on our radio, otherwise the other VFO (split off). With split_off_idle: always split off."""
        if self.idle_own():
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
            if self.split_off_idle:
                log.info("N1MM TX focus -> radio %s", "ours" if own else "other")
            elif not self.transmitting and not self.cat_tx:  # never mid-TX
                self.apply_idle_tx("N1MM TX focus -> radio %s" % ("ours" if own else "other"))

    def tx_vfo_ok(self) -> bool:
        """Is the radio's TX VFO where it should be right now?"""
        tx_sub = self._val("FT;", 2) == "1"
        own = self.cat_tx or self.idle_own()
        want_sub = self.swap if own else not self.swap
        return tx_sub == want_sub

    def tx_watch_loop(self, stop: threading.Event, interval: float = 0.15):
        """Whatever keyed the radio (CAT, WinKeyer, PTT line, VOX): as soon as it goes from
        TX back to RX, put TX back where it belongs (split_off_idle or no focus info: split off).
        While receiving it also keeps checking the TX VFO and corrects it, so a lost ST
        command or a manual split never survives until the next transmission."""
        fixes, quiet_until = 0, 0.0
        while not stop.is_set():
            try:
                with self.lock:
                    is_tx = self._val("TX;", 2) != "0"
                    known = self.want_own is not None or self.split_off_idle
                    if self.transmitting and not is_tx:
                        self.transmitting = False
                        self.cat_tx = False
                        self.apply_idle_tx("TX -> RX")
                    elif is_tx and not self.transmitting:
                        if known and not self.tx_vfo_ok():
                            log.warning("TX started on the wrong VFO - keyed before vRadio could "
                                        "correct it")
                        if self.split_off_idle and self.want_own and not self.cat_tx:
                            log.warning("Radio 2 has TX focus but keyed without CAT TX; it transmits "
                                        "on VFO-%s. In N1MM enable PTT via radio command for radio 2",
                                        "A" if self.swap else "B")
                    elif (not is_tx and not self.cat_tx and known
                          and time.time() >= quiet_until):
                        if self.tx_vfo_ok():
                            fixes = 0
                        else:
                            fixes += 1
                            if fixes <= 3:
                                self.apply_idle_tx("Split keeper (TX VFO was wrong)")
                            else:       # the radio refuses ST: don't flood it, look again in 5 s
                                log.warning("TX VFO stays wrong after 3 corrections, retrying in 5 s")
                                fixes, quiet_until = 0, time.time() + 5
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
                self.udp_listening = True
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
                self.udp_last = time.time()
            except socket.timeout:
                continue
            except OSError as e:
                log.debug("udp: %s", e)
                continue
            m = rx.search(data)
            if m:
                self.set_focus(int(m.group(1)) == my_radio)

    # --- dual receive keeper -------------------------------------------------
    def dual_rx_loop(self, stop: threading.Event, cmd: str, interval: float = 0.25):
        """Keep dual receive (MAIN + SUB) switched on: re-send `cmd` whenever the radio drifts off it.
        Checked 4x a second: N1MM radio 1 (FTDX101D) switches dual RX off when it jumps to a spot
        (Ctrl+Up/Down), and VFO-B must come back before the operator notices."""
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
        self.freq_gen += 1
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
                self.cat_tx = True
                self.tx_on_own()          # transmit on the VFO this software controls
                time.sleep(0.05)
            r.send("TX1;")
            # "TX0;" (with a parameter) is answered by a real TS-2000; DXLog waits for that
            # answer and reconnects without it. Plain "TX;" (N1MM) gets no answer.
            return f"TX{p[0]};" if p else ""
        if c == "RX":
            r.send("TX0;")
            if self.auto_split:
                self.cat_tx = False
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
                        MON.cat(self.port, cmd, reply)
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

    def peers(self) -> list[str]:
        """IP addresses of the connected clients."""
        out = []
        with self.clock:
            for c in self.clients:
                try:
                    out.append(c.getpeername()[0])
                except OSError:
                    pass
        return out

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
        keyed = False                  # this client keyed the radio by CAT and hasn't sent RX; yet
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
                    MON.cat(addr[0], cmd, reply)
                    c2 = cmd[:2].upper()
                    if c2 == "TX":
                        keyed = True
                    elif c2 == "RX":
                        keyed = False
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
            if keyed and self.emu.cat_tx:
                # it keyed the radio and left without RX;: never leave the radio transmitting
                log.warning("TCP client %s left while keying the radio - PTT released", addr[0])
                self.emu.handle("RX")

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


# ---------------------------------------------------------------------------
# DJ controller jog wheel (MIDI) -> tune our VFO (radio 2)
# Uses Windows winmm directly, no extra Python packages.
# ---------------------------------------------------------------------------
class MidiIn:
    """Minimal Windows MIDI input: open a device by (part of) its name, queue (status, d1, d2)."""
    MIM_DATA = 0x3C3
    CALLBACK_FUNCTION = 0x30000

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct = ctypes
        self.mm = ctypes.windll.winmm

        class CAPS(ctypes.Structure):
            _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD),
                        ("vDriverVersion", wintypes.UINT), ("szPname", wintypes.WCHAR * 32),
                        ("dwSupport", wintypes.DWORD)]
        self.CAPS = CAPS
        self.PROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t,
                                       ctypes.c_size_t, ctypes.c_size_t)
        self.handle = None
        self.name = None
        self.events = None
        self._cb = None

    def devices(self) -> list[str]:
        out = []
        for i in range(self.mm.midiInGetNumDevs()):
            caps = self.CAPS()
            if self.mm.midiInGetDevCapsW(i, self.ct.byref(caps), self.ct.sizeof(caps)) == 0:
                out.append(caps.szPname)
        return out

    def open(self, want: str, events) -> bool:
        """Open the first MIDI input whose name contains `want` (case-insensitive)."""
        for i, name in enumerate(self.devices()):
            if want.lower() in name.lower():
                def cb(h, msg, inst, p1, p2):
                    if msg == self.MIM_DATA:
                        events.put((p1 & 0xFF, (p1 >> 8) & 0x7F, (p1 >> 16) & 0x7F))
                self._cb = self.PROC(cb)
                h = self.ct.c_void_p()
                if self.mm.midiInOpen(self.ct.byref(h), i, self._cb, 0, self.CALLBACK_FUNCTION) != 0:
                    raise OSError(f"MIDI device '{name}' is in use by another program")
                self.mm.midiInStart(h)
                self.handle, self.name = h, name
                return True
        return False

    def close(self):
        if self.handle is not None:
            try:
                self.mm.midiInStop(self.handle)
                self.mm.midiInReset(self.handle)
                self.mm.midiInClose(self.handle)
            except OSError:
                pass
        self.handle, self.name = None, None


def jog_delta(v: int) -> int:
    """Relative jog value: 1..63 = clockwise steps, 65..127 = counter-clockwise (127 = -1)."""
    return v if v < 64 else v - 128


def parse_cc_list(s: str | None) -> set[int]:
    """'48,49' or '0x30,0x31' -> {48, 49}; empty -> set() = any controller."""
    out = set()
    for x in (s or "").replace(";", ",").split(","):
        x = x.strip()
        if x:
            out.add(int(x, 0))
    return out


class JogTuner:
    """Turns jog wheel ticks into frequency changes on the VFO vRadio controls."""

    def __init__(self, emu: "TS2000Emulator", step: int = 10, ccs: set[int] | None = None,
                 accel: bool = True, learn: bool = False):
        import queue
        self.emu, self.step, self.ccs, self.accel, self.learn = emu, step, ccs or set(), accel, learn
        self.events = queue.Queue()
        self.device: str | None = None     # connected MIDI device name
        self.error: str | None = None
        self.last_move = 0.0
        self.freq: int | None = None        # cached frequency while turning
        self.gen = -1                       # emu.freq_gen when self.freq was read
        self.target = f"VFO-{emu.ymap['A']}" if emu is not None else "VFO"

    def ticks_from(self, status: int, d1: int, d2: int) -> int:
        if self.learn:
            log.info("MIDI %02X %02X %02X  (status, controller/note, value)", status, d1, d2)
        if status & 0xF0 != 0xB0:            # control change only
            return 0
        if self.ccs and d1 not in self.ccs:
            return 0
        if not self.ccs and d2 in (0, 64):     # absolute knobs/faders rest at 0/64: ignore
            return 0
        return jog_delta(d2)

    def multiplier(self, ticks: int) -> int:
        """Fast spin = bigger steps. `ticks` is the sum over one 40 ms batch."""
        if not self.accel:
            return 1
        n = abs(ticks)
        return 1 if n < 5 else 2 if n < 10 else 5

    def apply(self, ticks: int):
        """Move our VFO by ticks * step (never while transmitting)."""
        emu = self.emu
        if not ticks or emu.transmitting or emu.cat_tx:
            return
        y = emu.ymap["A"]                    # radio VFO letter vRadio controls (B = SUB)
        with emu.lock:
            now = time.time()
            if self.freq is None or now - self.last_move > 1.0 or self.gen != emu.freq_gen:
                # re-read after a pause (radio knob) or when N1MM / follow-band set the VFO
                self.freq, self.gen = int(emu._val(f"F{y};", 2)), emu.freq_gen
            f = self.freq + ticks * self.step * self.multiplier(ticks)
            f = max(30_000, min(f, 75_000_000))
            f -= f % self.step                              # stay on the step grid
            emu.r.send(f"F{y}{f:09d};")
            self.freq, self.last_move = f, now
        log.debug("Jog %+d -> VFO-%s %d Hz", ticks, y, f)

    def skip_connect_dump(self, stop: threading.Event, wait: float = 6.0):
        """About 4 s after opening, the MP3 e2 reports every fader position (CC 0x34-0x3C) and
        then one jog value. That is not the operator turning the wheel: wait for it and drop it."""
        import queue
        end = time.time() + wait
        while time.time() < end and not stop.is_set():
            try:
                s, d1, d2 = self.events.get(timeout=0.2)
            except queue.Empty:
                continue
            if s & 0xF0 == 0xB0 and 0x34 <= d1 <= 0x3C:          # faders/knobs: the dump started
                end = min(end, time.time() + 0.3)
        while not self.events.empty():
            self.events.get_nowait()

    def run(self, stop: threading.Event, want: str):
        import queue
        midi = None
        next_try = 0.0
        while not stop.is_set():
            if midi is None or midi.handle is None:
                if time.time() >= next_try:
                    next_try = time.time() + 5
                    try:
                        midi = midi or MidiIn()
                        if midi.open(want, self.events):
                            self.skip_connect_dump(stop)
                            self.device, self.error = midi.name, None
                            log.info("DJ wheel: '%s' connected - jog tunes %s, %d Hz per step",
                                     midi.name, self.target, self.step)
                        elif self.error != "not found":
                            self.error = "not found"
                            log.warning("DJ wheel: no MIDI device matching '%s' (found: %s) - "
                                        "is the driver installed? Retrying every 5 s", want,
                                        ", ".join(midi.devices()) or "none")
                    except OSError as e:
                        if self.error != str(e):
                            log.warning("DJ wheel: %s", e)
                        self.error = str(e)
                stop.wait(0.5)
                continue
            # still plugged in?
            if time.time() >= next_try:
                next_try = time.time() + 5
                if not any(midi.name == n for n in midi.devices()):
                    log.warning("DJ wheel: '%s' disconnected", midi.name)
                    midi.close()
                    self.device, self.error = None, "disconnected"
                    continue
            try:
                ev = self.events.get(timeout=0.5)
            except queue.Empty:
                continue
            ticks = self.ticks_from(*ev)
            end = time.time() + 0.04                         # gather a short batch
            while time.time() < end:
                try:
                    ticks += self.ticks_from(*self.events.get(timeout=max(0.0, end - time.time())))
                except queue.Empty:
                    break
            try:
                self.apply(ticks)
            except (RadioError, ValueError) as e:
                log.debug("jog: %s", e)
        if midi:
            midi.close()

# ---------------------------------------------------------------------------
# Settings file (INI)
# ---------------------------------------------------------------------------
# vRadioDJ.exe = the same program with the DJ wheel on by default and its own settings file
_EXE = os.path.basename(sys.executable if getattr(sys, "frozen", False) else "").lower()
IS_DJ = _EXE.startswith("vradiodj")
CONFIG_NAME = "vradiodj.ini" if IS_DJ else "vradio.ini"
CONFIG_SECTION = "vradio"
# options that make no sense in a settings file
NOT_IN_CONFIG = {"help", "version", "port", "baud", "update", "updated", "config", "no_config",
                 "write_config"}


def _argv_value(opt: str) -> str | None:
    """Value of `opt` on the command line (`--opt X` or `--opt=X`), before argparse runs."""
    argv = sys.argv[1:]
    for i, x in enumerate(argv):
        if x == opt and i + 1 < len(argv):
            return argv[i + 1]
        if x.startswith(opt + "="):
            return x.split("=", 1)[1]
    return None


def _config_actions(ap: argparse.ArgumentParser) -> dict:
    return {act.dest: act for act in ap._actions
            if act.option_strings and act.dest not in NOT_IN_CONFIG and act.help != argparse.SUPPRESS}


def load_config(ap: argparse.ArgumentParser, path: str) -> dict:
    """Read [vradio] from an INI file -> argparse defaults (command line still wins)."""
    import configparser
    cp = configparser.ConfigParser(inline_comment_prefixes=("#",), interpolation=None)
    cp.optionxform = lambda k: k.strip().lower().replace("-", "_")
    with open(path, encoding="utf-8-sig") as f:
        cp.read_file(f)
    if not cp.has_section(CONFIG_SECTION):
        raise ValueError(f"no [{CONFIG_SECTION}] section")
    acts = _config_actions(ap)
    out = {}
    for key, raw in cp.items(CONFIG_SECTION):
        if key.startswith("winkey") and key not in acts:
            continue                                    # WinKeyer proxy was removed: old setting
        if key not in acts:
            raise KeyError(f"unknown setting '{key}' (allowed: {', '.join(sorted(acts))})")
        act, val = acts[key], raw.strip()
        if isinstance(act, argparse._StoreTrueAction):
            if val.lower() not in cp.BOOLEAN_STATES:
                raise ValueError(f"{key} = {val}: use yes or no")
            out[key] = cp.BOOLEAN_STATES[val.lower()]
            continue
        if val == "":
            continue                                    # empty = keep the default
        try:
            v = act.type(val) if act.type else val
        except ValueError:
            raise ValueError(f"{key} = {val}: not a valid value") from None
        if act.choices and v not in act.choices:
            raise ValueError(f"{key} = {val}: must be one of {', '.join(map(str, act.choices))}")
        out[key] = v
    return out


def save_config(ap: argparse.ArgumentParser, a, path: str):
    """Write the effective options as an INI file with the option help as comments."""
    import textwrap
    lines = [f"; vRadio {__version__} settings. Command-line options override these.",
             "; yes/no for on/off options; leave a value empty for the default.",
             f"[{CONFIG_SECTION}]"]
    for dest, act in _config_actions(ap).items():
        val = getattr(a, dest, None)
        if dest == "log" and val == os.path.join(APP_DIR, "vradio_log.txt"):
            val = None                                  # tray default, not a user choice
        if isinstance(act, argparse._StoreTrueAction):
            sval = "yes" if val else "no"
        else:
            sval = "" if val is None else str(val)
        lines.append("")
        lines += ["; " + h for h in textwrap.wrap(f"--{dest.replace('_', '-')}: {act.help}", 96)]
        lines.append(f"{dest} = {sval}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def apply_pcs(a) -> list[str]:
    """pcs = 2 (two PCs): radio 2 is a second PC's N1MM over the LAN. These settings belong
    together and are forced, whatever the ini says. The DJ wheel stays on this PC (midi)."""
    if a.pcs != 2:
        return []
    want = {"tcp": a.tcp or 4532, "tcp_host": "0.0.0.0", "auto_split": True, "split_off_idle": True,
            "follow_band": False, "same_band": False, "n1mm_udp": None}
    changed = []
    for k, v in want.items():
        if getattr(a, k) != v:
            setattr(a, k, v)
            changed.append(f"{k} = {'no' if v is False else 'yes' if v is True else 'off' if v is None else v}")
    return changed


def main():
    ap = Parser(
        description="Yaesu FTDX101D -> Kenwood TS-2000 CAT translator",
        usage="vRadio.exe [RADIO_PORT] [RADIO_BAUD] [options]   e.g. vRadio.exe COM5 38400 --tcp 4532")
    ap.add_argument("port", nargs="?", metavar="RADIO_PORT",
                    help="radio COM port, same as --radio (e.g. COM14)")
    ap.add_argument("baud", nargs="?", type=int, metavar="RADIO_BAUD",
                    help="radio baud, same as --radio-baud (e.g. 38400)")
    ap.add_argument("--pcs", type=int, choices=[1, 2], default=1,
                    help="1 = one PC: this PC's N1MM runs radio 1 and radio 2 (default). "
                         "2 = two PCs: a second PC's N1MM is radio 2 over the LAN (TCP 4532 on "
                         "0.0.0.0, split only during its CAT TX, follow-band off, no N1MM UDP)")
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
    ap.add_argument("--split-off-idle", action="store_true",
                    help="with --auto-split: split on only while radio 2 transmits by CAT TX (N1MM "
                         "PTT via radio command); off after every TX and while idle, whatever the focus")
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
    ap.add_argument("--midi", metavar="NAME", default="MP3" if IS_DJ else None,
                    help="DJ controller jog wheel tunes our VFO (radio 2): MIDI input whose name "
                         "contains NAME, e.g. MP3 for Hercules DJ Control MP3 e2")
    ap.add_argument("--midi-step", type=int, default=10,
                    help="Hz per jog wheel step (default 10; faster spinning = 3x / 10x)")
    ap.add_argument("--midi-cc", metavar="LIST", default="48",
                    help="MIDI controller numbers that tune (default 48 = MP3 e2 left jog wheel; "
                         "49 = right jog wheel, 48,49 = both; find others with --midi-learn)")
    ap.add_argument("--midi-no-accel", action="store_true", help="fixed step size, no acceleration")
    ap.add_argument("--midi-learn", action="store_true",
                    help="log every MIDI message (to find the wheel's controller number)")
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
    ap.add_argument("--config", metavar="FILE",
                    help=f"settings file (default: {CONFIG_NAME} next to the exe, if it exists); "
                         "command-line options override it")
    ap.add_argument("--no-config", action="store_true", help=f"ignore {CONFIG_NAME}")
    ap.add_argument("--write-config", nargs="?", const="", metavar="FILE",
                    help=f"write the current options to FILE (default {CONFIG_NAME} next to the exe) "
                         "and exit")
    ap.add_argument("--version", action="version", version=f"vRadio {__version__}")
    cfg_file, cfg_err = None, None
    if "--no-config" not in sys.argv:
        cfg_file = _argv_value("--config") or os.path.join(APP_DIR, CONFIG_NAME)
        if os.path.exists(cfg_file):
            try:
                ap.set_defaults(**load_config(ap, cfg_file))
            except (ValueError, KeyError) as e:
                ap.error(f"{cfg_file}: {e}")
        else:
            if _argv_value("--config"):
                cfg_err = f"settings file not found: {cfg_file}"
            cfg_file = None
    a = ap.parse_args()
    if cfg_err:
        ap.error(cfg_err)
    a.config_file = cfg_file
    if a.port:
        a.radio = a.port.upper()
    if a.baud:
        a.radio_baud = a.baud

    if a.write_config is not None:
        path = a.write_config or os.path.join(APP_DIR, CONFIG_NAME)
        save_config(ap, a, path)
        msg = f"Settings written to {path}"
        message_box(msg) if WINDOWED else print(msg)
        return

    a.dual_rx_cmd = a.dual_rx_cmd.strip().upper().rstrip(";") + ";"
    pcs_changes = apply_pcs(a)
    if str(a.midi or "").strip().lower() in ("no", "off", "none", "0", "false"):
        a.midi = None                                   # "no" switches the DJ wheel off
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

    log.info("vRadio %s%s", __version__, f" - settings from {a.config_file}" if a.config_file else "")
    if a.pcs == 2:
        log.info("Two PCs (pcs = 2): radio 2 is the other PC's N1MM over the LAN%s",
                 " - set " + ", ".join(pcs_changes) if pcs_changes else "")
    cleanup_old_exe()
    state = {"radio": None, "emu": None, "server": None, "error": None, "args": a,
             "update": None, "relaunch": None, "parser": ap}
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
    emu.split_off_idle = bool(a.auto_split and a.split_off_idle)
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
        if emu.split_off_idle:
            log.info("Split off when idle: split on only during radio 2's CAT TX")
        if a.n1mm_udp:
            threading.Thread(target=emu.n1mm_udp_loop,
                             args=(server.stop, a.n1mm_udp, a.n1mm_radio), daemon=True).start()
    elif a.n1mm_udp:
        log.warning("--n1mm-udp needs --auto-split; ignored")
    if a.midi:
        jog = JogTuner(emu, step=max(1, a.midi_step), ccs=parse_cc_list(a.midi_cc),
                       accel=not a.midi_no_accel, learn=a.midi_learn)
        state["jog"] = jog
        threading.Thread(target=jog.run, args=(server.stop, a.midi), daemon=True).start()
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
        lan = sorted({ip for ip in server.peers() if not ip.startswith("127.")})
        cat = f"N1MM TCP {a.tcp}: " + (f"{n} connected" if n else "waiting")
        if lan:
            cat += " (LAN " + ", ".join(lan) + ")"
        elif getattr(a, "tcp_host", "127.0.0.1") != "127.0.0.1":
            cat += f" (open on {a.tcp_host})"
    elif isinstance(server, CatServer):
        cat = f"CAT {a.cat}: " + ("open" if server.ser else "not open")
    else:
        cat = "CAT: starting"
    lines = [r, cat]
    if getattr(a, "pcs", 1) == 2:
        lines.insert(0, "Two PCs: radio 2 = other PC over the LAN")
    if a.auto_split and a.n1mm_udp:
        if emu is None:
            u = "starting"
        elif emu.udp_error:
            u = "BUSY (used by another program)"
        elif not emu.udp_listening:
            u = "starting"
        elif not emu.udp_last:
            u = "listening, no data yet"
        else:
            ago = time.time() - emu.udp_last
            if ago < 10:
                u = "receiving"
            elif ago < 120:
                u = f"listening, last data {int(ago)} s ago"
            else:
                u = f"listening, last data {int(ago // 60)} min ago"
        lines.append(f"N1MM UDP {a.n1mm_udp}: {u}")
    if emu is not None and emu.auto_split:
        own = "B" if emu.swap else "A"
        other = "A" if emu.swap else "B"
        if emu.want_own is None:
            f = "TX focus: unknown (split off)"
        elif emu.want_own:
            f = f"TX focus: radio {a.n1mm_radio} (VFO-{own})"
        else:
            f = f"TX focus: other radio (VFO-{other})"
        if emu.split_off_idle:
            f = f.replace(" (split off)", "") + " - split only during TX"
        lines.append(f)
    if emu is not None and emu.udp_error:
        color = "#c0392b"
    jog = state.get("jog")
    if getattr(a, "midi", None):
        if jog is None:
            lines.append("DJ wheel: starting")
        elif jog.device:
            lines.append(f"DJ wheel: {jog.device} ({jog.step} Hz/step)")
        else:
            lines.append(f"DJ wheel '{getattr(a, "midi", "")}': {jog.error or 'searching'}")
    if state.get("update"):
        lines.append(f"Update {state['update']['version']} available")
    if emu is not None and emu.transmitting and radio and radio.ok:
        lines.append("TRANSMITTING")
        color = "#d35400"
    return lines, color


def monitor_window(title: str = "vRadio monitor"):
    """Traffic monitor: ticks for CAT (N1MM) and radio traffic. Runs its own Tk loop
    in this thread; closing it switches all monitoring off again."""
    import tkinter as tk
    from tkinter import scrolledtext

    if getattr(monitor_window, "open", False):
        return
    monitor_window.open = True
    root = tk.Tk()
    root.title(title)
    root.geometry("980x520")
    bar = tk.Frame(root)
    bar.pack(fill="x", padx=6, pady=4)
    v_cat, v_radio, v_hide = (tk.BooleanVar(value=v) for v in (True, False, True))
    paused = tk.BooleanVar(value=False)

    def apply():
        MON.on.update(cat=v_cat.get(), radio=v_radio.get())
        MON.hide_polls = v_hide.get()

    for text, var in (("CAT (N1MM)", v_cat), ("Radio COM", v_radio),
                      ("Hide polls (IF; FA; TX; ...)", v_hide)):
        tk.Checkbutton(bar, text=text, variable=var, command=apply).pack(side="left", padx=4)
    tk.Checkbutton(bar, text="Pause", variable=paused).pack(side="left", padx=12)
    box = scrolledtext.ScrolledText(root, font=("Consolas", 9), wrap="none")
    tk.Button(bar, text="Clear", command=lambda: box.delete("1.0", "end")).pack(side="right")
    box.pack(fill="both", expand=True, padx=6, pady=(0, 6))
    apply()

    def pump():
        lines = MON.take()
        if lines and not paused.get():
            at_end = box.yview()[1] > 0.999
            box.insert("end", "\n".join(lines) + "\n")
            excess = int(box.index("end-1c").split(".")[0]) - 4000
            if excess > 0:
                box.delete("1.0", f"{excess}.0")
            if at_end:
                box.see("end")
        root.after(200, pump)

    def close():
        MON.on.update(cat=False, radio=False)
        monitor_window.open = False
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.after(200, pump)
    root.mainloop()


def run_tray(a, stop: threading.Event, state: dict):
    import pystray

    icons = {}

    def icon_for(color):
        if color not in icons:
            icons[color] = make_icon(color)
        return icons[color]

    def line(i):
        return lambda item: (status_lines(a, state)[0] + [""] * 9)[i]

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

    def open_monitor(icon, item):
        threading.Thread(target=monitor_window, args=(f"vRadio {__version__} monitor",),
                         daemon=True).start()

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

    def edit_settings(icon, item):
        path = a.config_file or os.path.join(APP_DIR, CONFIG_NAME)
        try:
            if not os.path.exists(path):
                save_config(state["parser"], a, path)
                log.info("Wrote %s from the current options", path)
                notify(f"Created {CONFIG_NAME} from the current options. "
                       "Save it, then use Restart vRadio.")
            os.startfile(path)
        except OSError as e:
            notify(f"Cannot open {path}: {e}")

    def restart(icon, item):
        emu = state["emu"]
        if emu is not None and emu.transmitting:
            notify("Not now - the radio is transmitting.")
            return
        if not getattr(sys, "frozen", False):
            notify("Restart works only for the exe.")
            return
        log.info("Restart from tray menu")
        state["relaunch"] = sys.executable
        stop.set()
        icon.stop()

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
        pystray.MenuItem(line(6), None, enabled=False, visible=visible(6)),
        pystray.MenuItem(line(7), None, enabled=False, visible=visible(7)),
        pystray.MenuItem(line(8), None, enabled=False, visible=visible(8)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"Copy VFO-{other} -> VFO-{own} (same band)", copy_ab),
        pystray.MenuItem("Monitor (CAT / radio)...", open_monitor),
        pystray.MenuItem("Open log", open_log),
        pystray.MenuItem("Open vRadio folder", open_folder),
        pystray.MenuItem(f"Edit settings ({CONFIG_NAME})", edit_settings),
        pystray.MenuItem("Restart vRadio", restart),
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
