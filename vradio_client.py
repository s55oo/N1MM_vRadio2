"""vRadioClient - the second PC's side of a vRadio server: DJ wheel and WinKeyer over the LAN.

Laptop 1 runs vRadio (radio on COM14, tcp_host = 0.0.0.0, winkey = COM2). Laptop 2 runs N1MM with
a TS-2000 on TCP laptop1:4532 and its WinKeyer on one end of a virtual COM pair; this program
takes the other end and passes the WinKeyer bytes to vRadio (TCP 4533), which sends them to the
real keyer with TX on VFO-B. The DJ wheel (Hercules DJ Control MP3 e2) tunes VFO-B through the
same vRadio server, so laptop 2's N1MM follows.

    vRadioClient.exe --server 192.168.1.10 --winkey COM21     (settings in vradioclient.ini)
"""
import argparse
import logging
import os
import queue
import socket
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

import vradio
from vradio import JogTuner, parse_cc_list, load_config, save_config, message_box, Parser

log = logging.getLogger("vradio")
__version__ = vradio.__version__
WINDOWED = sys.stderr is None
APP_DIR = vradio.APP_DIR
CONFIG_NAME = "vradioclient.ini"


class VRadioLink:
    """TCP connection to a vRadio server, speaking TS-2000 CAT (for the wheel)."""

    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self.sock = None
        self.lock = threading.Lock()
        self.replies = queue.Queue()
        self.error = None

    @property
    def ok(self) -> bool:
        return self.sock is not None

    def connect(self) -> bool:
        try:
            s = socket.create_connection((self.host, self.port), timeout=3)
        except OSError as e:
            if self.error != str(e):
                log.warning("vRadio server %s:%d: %s - retrying every 3 s", self.host, self.port, e)
            self.error = str(e)
            return False
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.settimeout(None)
        self.sock, self.error = s, None
        log.info("Connected to vRadio server %s:%d", self.host, self.port)
        threading.Thread(target=self._reader, args=(s,), daemon=True).start()
        return True

    def _reader(self, s):
        buf = ""
        try:
            while True:
                data = s.recv(1024)
                if not data:
                    break
                buf += data.decode("ascii", "ignore")
                while ";" in buf:
                    msg, buf = buf.split(";", 1)
                    self.replies.put(msg.strip() + ";")
        except OSError:
            pass
        if self.sock is s:
            log.warning("vRadio server %s:%d disconnected", self.host, self.port)
            self.close("disconnected")

    def close(self, why=None):
        s, self.sock = self.sock, None
        if s:
            try:
                s.close()
            except OSError:
                pass
        if why:
            self.error = why

    def query_if(self, timeout: float = 1.0):
        """Ask vRadio for IF; -> (frequency of radio 2, transmitting?)."""
        with self.lock:
            while not self.replies.empty():          # drop AI pushes and old answers
                self.replies.get_nowait()
            if not self._send("IF;"):
                return None
            end = time.time() + timeout
            while time.time() < end:
                try:
                    r = self.replies.get(timeout=max(0.01, end - time.time()))
                except queue.Empty:
                    break
                if r.startswith("IF") and len(r) >= 38:
                    return int(r[2:13]), r[28] == "1"
            return None

    def set_freq(self, hz: int) -> bool:
        with self.lock:
            return self._send(f"FA{hz:011d};")

    def _send(self, s: str) -> bool:
        if not self.sock:
            return False
        try:
            self.sock.sendall(s.encode("ascii"))
            return True
        except OSError as e:
            log.warning("vRadio server: %s", e)
            self.close(str(e))
            return False


class RemoteJog(JogTuner):
    """JogTuner that tunes through a vRadio server instead of a local radio."""

    def __init__(self, link: VRadioLink, **kw):
        super().__init__(None, **kw)
        self.link = link
        self.target = f"radio 2 via vRadio {link.host}:{link.port}"

    def apply(self, ticks: int):
        if not ticks or not self.link.ok:
            return
        cur = self.link.query_if()             # always fresh: N1MM spots, band changes, the radio knob
        if cur is None:
            return
        freq, tx = cur
        if tx:
            return                             # never tune while transmitting
        f = freq + ticks * self.step * self.multiplier(ticks)
        f = max(30_000, min(f, 75_000_000))
        f -= f % self.step
        self.link.set_freq(f)
        log.debug("Jog %+d -> %d Hz", ticks, f)


class WinkeyBridge:
    """Virtual COM port (laptop 2's N1MM WinKeyer) <-> TCP to the vRadio server's WinKeyer proxy.
    Bytes pass through unchanged; the server answers N1MM's setup commands itself."""

    def __init__(self, port: str, baud: int, host: str, tcp: int):
        self.port, self.baud, self.host, self.tcp = port, baud, host, tcp
        self.ser = None
        self.sock = None
        self.error = None

    def open_serial(self):
        import serial
        return serial.Serial(self.port, self.baud, bytesize=8, parity="N", stopbits=2,
                             timeout=0.05, write_timeout=1)

    def run(self, stop: threading.Event):
        while not stop.is_set():
            if self.ser is None:
                try:
                    self.ser = self.open_serial()
                    log.info("WinKeyer bridge: %s open (N1MM's WinKeyer port is the other end)", self.port)
                    self.error = None
                except Exception as e:
                    if self.error != str(e):
                        log.error("WinKeyer bridge: cannot open %s: %s - retrying every 5 s", self.port, e)
                    self.error = str(e)
                    stop.wait(5)
                    continue
            if self.sock is None:
                try:
                    s = socket.create_connection((self.host, self.tcp), timeout=3)
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    s.settimeout(None)
                    self.sock, self.error = s, None
                    log.info("WinKeyer bridge: connected to vRadio %s:%d", self.host, self.tcp)
                    threading.Thread(target=self._from_server, args=(s,), daemon=True).start()
                except OSError as e:
                    if self.error != str(e):
                        log.warning("WinKeyer bridge: vRadio %s:%d: %s - retrying every 3 s",
                                    self.host, self.tcp, e)
                    self.error = str(e)
                    self._drain(stop, 3)
                    continue
            try:
                data = self.ser.read(256)
            except Exception as e:
                log.warning("WinKeyer bridge: %s: %s", self.port, e)
                self._close_serial(str(e))
                continue
            if data:
                try:
                    self.sock.sendall(data)
                except OSError as e:
                    log.warning("WinKeyer bridge: vRadio connection lost: %s", e)
                    self._close_sock(str(e))
        self._close_sock("stopped")
        self._close_serial("stopped")

    def _drain(self, stop: threading.Event, secs: float):
        """While the server is unreachable, throw away what N1MM sends (no keyer to send it to)."""
        end = time.time() + secs
        while time.time() < end and not stop.is_set():
            try:
                self.ser.read(256)
            except Exception:
                self._close_serial("port error")
                return

    def _from_server(self, s):
        try:
            while True:
                data = s.recv(512)
                if not data:
                    break
                ser = self.ser
                if ser is not None:
                    ser.write(data)
        except Exception:
            pass
        if self.sock is s:
            log.warning("WinKeyer bridge: vRadio %s:%d disconnected", self.host, self.tcp)
            self._close_sock("disconnected")

    def _close_sock(self, why: str):
        s, self.sock = self.sock, None
        if s:
            try:
                s.close()
            except OSError:
                pass
        self.error = why

    def _close_serial(self, why: str):
        s, self.ser = self.ser, None
        if s:
            try:
                s.close()
            except Exception:
                pass
        self.error = why

    def status(self) -> str:
        if self.ser is None:
            return f"WinKeyer {self.port}: {self.error or 'opening...'}"[:100]
        if self.sock is None:
            return f"WinKeyer {self.port} -> vRadio {self.host}:{self.tcp}: {self.error or 'connecting...'}"[:100]
        return f"WinKeyer {self.port} -> vRadio {self.host}:{self.tcp}: connected"


def link_loop(link: VRadioLink, stop: threading.Event):
    while not stop.is_set():
        if not link.ok:
            link.connect()
        stop.wait(3)


def status_lines(a, link, jog, wk):
    lines, color = [], "#1e8449"
    if link is not None:
        if link.ok:
            lines.append(f"vRadio {a.server}:{a.port} (wheel): connected")
        else:
            lines.append(f"vRadio {a.server}:{a.port} (wheel): {link.error or 'connecting...'}"[:100])
            color = "#c0392b"
    if jog is not None:
        if jog.device:
            lines.append(f"DJ wheel: {jog.device} ({jog.step} Hz/step)")
        else:
            lines.append(f"DJ wheel '{a.midi}': {jog.error or 'searching'}")
            if color != "#c0392b":
                color = "#d35400"
    if wk is not None:
        lines.append(wk.status())
        if wk.ser is None or wk.sock is None:
            color = "#c0392b"
    if not lines:
        lines, color = ["Nothing to do: set midi and/or winkey"], "#7f8c8d"
    return lines, color


def run_tray(a, stop: threading.Event, link, jog, wk):
    import pystray

    icons = {}

    def icon_for(color):
        if color not in icons:
            icons[color] = vradio.make_icon(color)
        return icons[color]

    def line(i):
        return lambda item: (status_lines(a, link, jog, wk)[0] + ["", "", ""])[i]

    def visible(i):
        return lambda item: len(status_lines(a, link, jog, wk)[0]) > i

    def open_log(icon, item):
        if a.log and os.path.exists(a.log):
            os.startfile(a.log)

    def edit_settings(icon, item):
        path = a.config_file or os.path.join(APP_DIR, CONFIG_NAME)
        if not os.path.exists(path):
            save_config(a.parser, a, path)
        os.startfile(path)

    def quit_app(icon, item):
        stop.set()

    menu = pystray.Menu(
        pystray.MenuItem(line(0), None, enabled=False),
        pystray.MenuItem(line(1), None, enabled=False, visible=visible(1)),
        pystray.MenuItem(line(2), None, enabled=False, visible=visible(2)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open log", open_log),
        pystray.MenuItem(f"Edit settings ({CONFIG_NAME}) - restart after", edit_settings),
        pystray.MenuItem("Exit vRadioClient", quit_app),
    )
    icon = pystray.Icon("vRadioClient", icon_for("#7f8c8d"), "vRadioClient - starting", menu)

    def updater(icon):
        icon.visible = True
        last = None
        while not stop.is_set():
            lines, color = status_lines(a, link, jog, wk)
            title = ("vRadioClient - " + " | ".join(lines))[:127]
            if (title, color) != last:
                icon.icon, icon.title = icon_for(color), title
                icon.update_menu()
                last = (title, color)
            stop.wait(1.0)
        icon.stop()

    icon.run(setup=updater)


def single_instance() -> bool:
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.CreateMutexW(None, False, "Local\\vRadioClient")
    if k32.GetLastError() == 183:
        k32.CloseHandle(h)
        return False
    single_instance.handle = h
    return True


def main():
    ap = Parser(description="Second PC's side of a vRadio server: DJ wheel and WinKeyer over the LAN",
                usage="vRadioClient.exe --server LAPTOP1_IP [--winkey COM21] [options]")
    ap.add_argument("--server", default="127.0.0.1",
                    help="IP address or name of the PC running vRadio (vRadio needs tcp_host = 0.0.0.0)")
    ap.add_argument("--port", type=int, default=4532, help="vRadio CAT TCP port (default 4532)")
    ap.add_argument("--midi", metavar="NAME", default="MP3",
                    help="MIDI input whose name contains NAME (default MP3 = Hercules DJ Control MP3 e2); "
                         "empty = no wheel")
    ap.add_argument("--midi-cc", metavar="LIST", default="48",
                    help="MIDI controller numbers that tune (default 48 = left jog wheel; 49 = right)")
    ap.add_argument("--midi-step", type=int, default=10, help="Hz per wheel step (default 10)")
    ap.add_argument("--midi-no-accel", action="store_true", help="fixed step size, no acceleration")
    ap.add_argument("--midi-learn", action="store_true", help="log every MIDI message")
    ap.add_argument("--winkey", metavar="COM",
                    help="our end of a virtual COM pair whose other end is N1MM's WinKeyer port (e.g. COM21)")
    ap.add_argument("--winkey-baud", type=int, default=1200, help="WinKeyer baud (default 1200)")
    ap.add_argument("--winkey-tcp", type=int, default=4533, help="vRadio's WinKeyer TCP port (default 4533)")
    ap.add_argument("-v", "--verbose", action="store_true", help="log every wheel step")
    ap.add_argument("--log", metavar="FILE", help="also write the log to this file")
    ap.add_argument("--config", metavar="FILE", help=f"settings file (default {CONFIG_NAME} next to the exe)")
    ap.add_argument("--no-config", action="store_true", help=f"ignore {CONFIG_NAME}")
    ap.add_argument("--write-config", nargs="?", const="", metavar="FILE",
                    help=f"write the current options to FILE (default {CONFIG_NAME}) and exit")
    ap.add_argument("--version", action="version", version=f"vRadioClient {__version__}")

    cfg_file = None
    if "--no-config" not in sys.argv:
        cfg_file = vradio._argv_value("--config") or os.path.join(APP_DIR, CONFIG_NAME)
        if os.path.exists(cfg_file):
            try:
                ap.set_defaults(**load_config(ap, cfg_file))
            except (ValueError, KeyError) as e:
                ap.error(f"{cfg_file}: {e}")
        else:
            cfg_file = None
    a = ap.parse_args()
    a.config_file, a.parser = cfg_file, ap
    if a.write_config is not None:
        path = a.write_config or os.path.join(APP_DIR, CONFIG_NAME)
        save_config(ap, a, path)
        msg = f"Settings written to {path}"
        message_box(msg, "vRadioClient") if WINDOWED else print(msg)
        return

    if WINDOWED and not a.log:
        a.log = os.path.join(APP_DIR, "vradioclient_log.txt")
    handlers = []
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    if a.log:
        handlers.append(RotatingFileHandler(a.log, maxBytes=1_000_000, backupCount=2, encoding="utf-8"))
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    log.info("vRadioClient %s - server %s%s", __version__, a.server,
             f" - settings from {a.config_file}" if a.config_file else "")

    if WINDOWED and not single_instance():
        message_box("vRadioClient is already running (see the tray icon).", "vRadioClient")
        return

    stop = threading.Event()
    link = jog = wk = None
    if a.midi:
        link = VRadioLink(a.server, a.port)
        jog = RemoteJog(link, step=max(1, a.midi_step), ccs=parse_cc_list(a.midi_cc),
                        accel=not a.midi_no_accel, learn=a.midi_learn)
        threading.Thread(target=link_loop, args=(link, stop), daemon=True).start()
        threading.Thread(target=jog.run, args=(stop, a.midi), daemon=True).start()
    if a.winkey:
        wk = WinkeyBridge(a.winkey, a.winkey_baud, a.server, a.winkey_tcp)
        threading.Thread(target=wk.run, args=(stop,), daemon=True).start()
    try:
        if WINDOWED:
            run_tray(a, stop, link, jog, wk)
        else:
            while not stop.is_set():
                stop.wait(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if link:
            link.close()
        time.sleep(0.6)


if __name__ == "__main__":
    main()
