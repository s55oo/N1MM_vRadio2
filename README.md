# vRadio — Yaesu FTDX101D as a Kenwood TS-2000 for N1MM

vRadio connects to the FTDX101D on **COM14 (38400 8N1)** and presents the radio's **VFO-B (SUB)**
to N1MM Logger+ as **radio 2**, a Kenwood TS-2000, over **TCP port 4532**.
N1MM radio 1 stays on its own connection to the radio's VFO-A (MAIN).

```
FTDX101D ── COM14 38400 8N1 ──> vRadio.exe ── TCP 127.0.0.1:4532 ──> N1MM radio 2 (TS-2000)
                                    ^
                                    └── UDP 12064 <── N1MM RadioInfo broadcast (TX focus)
```

Status 10 Nov 2026: everything confirmed on air except the dual RX value (see "Open items").

## Download

Get the latest exes from **[Releases](https://github.com/s55oo/N1MM_vRadio2/releases/latest)**
(also in the `dist` folder of this repo):

- `vRadio.exe`: console version
- `vRadioTray.exe`: system tray version
- `radio_monitor.exe`: read-only CAT monitor for testing

No installation and no Python needed. Put the exes in one folder (for example `C:\Ham\vRadio\dist`)
and start them with the commands below. Windows SmartScreen may warn about an unsigned exe:
click *More info → Run anyway*.

Requirements:
- Windows 10/11
- Yaesu FTDX101D reachable on a COM port (here COM14 via an ELTIMA virtual port, 38400 8N1)
- N1MM Logger+

The `vRadio Tray.lnk` shortcut and the `.bat` files use the path `C:\Ham\vRadio\dist`. Edit them
if you use another folder.

---

## 1. Start (the full working command)

Double-click `dist\vRadio_TEST.bat`, or run:

```
C:\Ham\vRadio\dist\vRadio.exe --tcp 4532 --follow-band --auto-split --n1mm-udp 12064 --dual-rx --dual-rx-cmd FR00; -v --log C:\Ham\vRadio\dist\vradio_test_log.txt
```

Without the debug log (normal use):

```
C:\Ham\vRadio\dist\vRadio.exe --tcp 4532 --follow-band --auto-split --n1mm-udp 12064 --dual-rx --dual-rx-cmd FR00;
```

Without dual RX (if FR00; turns out to be wrong):

```
C:\Ham\vRadio\dist\vRadio.exe --tcp 4532 --follow-band --auto-split --n1mm-udp 12064
```

### System tray version

Double-click `dist\vRadio Tray.lnk` (runs `dist\vRadioTray.exe` with the normal-use options above).
vRadioTray has no console window; it sits in the system tray (next to the clock):

| Icon | Meaning |
|---|---|
| green | radio answers |
| red | radio not answering, or an error (hover/right-click for details) |
| orange | transmitting |
| grey | starting / connecting |

Right-click menu: radio status, N1MM connection, N1MM UDP listener (`receiving` / `listening, last data
… ago` / `BUSY`), TX focus, *Copy VFO-A -> VFO-B (same band)*,
*Open log*, *Open vRadio folder*, *Edit settings (vradio.ini)*, *Restart vRadio*,
*Install update* (only when there is one), *Check for updates*,
*Exit vRadio*. The log goes to `dist\vradio_log.txt`
(rotating, max 4 x 2 MB). Only one vRadioTray can run at a time.
Same options as vRadio.exe; e.g. `vRadioTray.exe COM5 38400 --tcp 4532 ...`.
Start with Windows: copy `vRadio Tray.lnk` into the Startup folder (Win+R, `shell:startup`).

Radio on another port: put the port and speed first, e.g.

```
C:\Ham\vRadio\dist\vRadio.exe COM5 38400 --tcp 4532 --follow-band --auto-split --n1mm-udp 12064
```

Stop: close the vRadio window or press Ctrl+C. Only one program can use COM14 at a time.

### Settings file (vradio.ini)

Instead of a long command line, put the options in **`vradio.ini` next to the exe**
(`dist\vradio.ini`). vRadio reads it at every start. Options given on the command line override
the file.

```ini
[vradio]
radio = COM14
radio_baud = 38400
tcp = 4532
follow_band = yes
auto_split = yes
n1mm_udp = 12064
dual_rx = yes
dual_rx_cmd = FR00;
auto_update = yes
```

With that file in place, `vRadio.exe` or `vRadioTray.exe` with no options does the same as the full
command above.

- Keys are the long option names: `--n1mm-udp` → `n1mm_udp` (or `n1mm-udp`). On/off options take
  `yes` / `no`. An empty value means the default. Comments start with `;` or `#`.
- `dist\vradio.example.ini` lists every setting with its explanation. Copy it to `vradio.ini` and edit.
- `vRadio.exe ... --write-config` saves the options you give it to `vradio.ini`, then exits.
  `--write-config FILE` saves them to another file.
- `--config FILE` uses another file (e.g. one per contest setup). `--no-config` ignores `vradio.ini`.
- A wrong key or value stops vRadio with a message naming the file and the setting.
- Tray menu: *Edit settings (vradio.ini)* opens the file in Notepad (it is created from the current
  options if missing). Then use *Restart vRadio* to apply it.
- An on/off option set to `yes` in the file can't be turned off on the command line; use `--no-config`
  or edit the file.

### Updates

vRadio checks GitHub Releases at start and every 6 hours. It never updates in the middle of
operating by itself:

- **Tray:** a notification appears, and the menu gets *Install update vX (restarts vRadio)*. A click
  downloads the new exe, closes COM14, and restarts vRadio with the same options. It is refused while
  transmitting. You can also use *Check for updates*.
- **Console:** the log says `vRadio vX is available`. Run `vRadio.exe --update`, then start it again.
- **`--auto-update`:** installs a newer version at start, before connecting to the radio, and restarts
  with it. The tray shortcut and `vRadio_TEST.bat` use this.
- `--no-update-check` turns the check off. `--version` shows the version.

The old exe is kept as `vRadio.exe.old` / `vRadioTray.exe.old` until the next start. To go back,
close vRadio and rename it. After an update, N1MM radio 2 may need a reconnect
(Configurer → Hardware → OK).

## 2. N1MM setup

Configurer → Hardware, radio 2:
- Port: **TCP**
- Radio: **Kenwood TS-2000**
- IP: **127.0.0.1**, port: **4532**

Configurer → Broadcast Data:
- **Radio** ticked, add **127.0.0.1:12064** to the addresses (space-separated), e.g.
  `127.0.0.1:12060 127.0.0.1:12061 127.0.0.1:12062 127.0.0.1:12064`. vRadio reads the TX focus from it.

Why 12064 and not 12060: on Windows only one program gets N1MM's packets on a UDP port. The other
S55OO tools already use these ports:

| UDP port | Used by |
|---|---|
| 12060 | Callbooker, QSOrouter, POUNCer (default), PingPong's n1mm_watch |
| 12061 | POUNCer (own port) |
| 12062 / 12063 | PingPong lamp / its alternative |
| **12064** | **vRadio** |
| 12070, 12080 | N1MM itself: do not use |
| 12079 | POUNCer team |

vRadio takes its port exclusively. If another program already has it, the log says
`UDP 12064 is used by another program` and the tray icon turns red (`UDP 12064 busy`).

---

## 3. What each option does

| Option | Effect |
|---|---|
| `COM5 38400` (first, no dashes) | Radio port and speed, e.g. `vRadio.exe COM5 38400 --tcp 4532 ...`. Same as `--radio COM5 --radio-baud 38400`. Default COM14 38400. |
| `--pcs 1` / `--pcs 2` | `1` (default) = **one PC**: this PC's N1MM runs radio 1 and radio 2. `2` = **two PCs**: a second PC's N1MM is radio 2 over the LAN; sets `tcp 4532`, `tcp_host 0.0.0.0`, `auto_split`, `split_off_idle`, no `follow_band`, no `n1mm_udp`. The DJ console stays on this PC. WinKeyer sharing and N1MM settings: see `SETUP_2PC.md`. |
| `--tcp 4532` | Serve the TS-2000 emulation on TCP 4532 instead of a COM port. |
| `--tcp-host 0.0.0.0` | Accept TCP from other PCs (default 127.0.0.1 = this PC only). Allow vRadio.exe in the firewall. |
| `--vfo B` | Default. N1MM's VFO-A = radio VFO-B (SUB), N1MM's VFO-B = radio VFO-A. `--vfo A` = normal mapping. |
| `--follow-band` | When radio VFO-A (N1MM radio 1) changes band, VFO-B jumps to that band (`AB;`). You can still move B afterwards. N1MM itself refuses to put both radios on one band; this gets around it. |
| `--same-band` | Copy VFO-A to VFO-B once, at startup. |
| `--auto-split` | vRadio decides the TX VFO itself: `ST1;` = TX on VFO-B, `ST0;` = TX on VFO-A (split off). CAT `TX;` from radio 2 → TX on VFO-B. After every TX→RX the TX VFO is set again. N1MM sees radio 2 as non-split. |
| `--midi MP3` | DJ controller jog wheel tunes radio 2 (VFO-B). `vRadioDJ.exe` has it on, settings in `vradiodj.ini`. `--midi-cc 48` = left jog wheel of the Hercules DJ Control MP3 e2 (49 = right), `--midi-step 10` Hz per step, `--midi-learn` logs every MIDI message. Never tunes during TX. |
| `--dj-web-port 8065` | DJ mapper page `http://127.0.0.1:8065/` (tray: *DJ controller mapping...*): click or touch a control on the MP3 e2 and pick its VFO-B function (AF/RF gain, squelch, filter, IF shift, NB/NR/notch, mode, band, MOX, ATU tune...). Saved in `vradiodj_midi.json`. See `DJ_CONTROLS.md`. `--midi-no-buttons`: jog wheel only. |
| `--n1mm-udp 12064` | With `--auto-split`: follow N1MM's TX focus (`ActiveRadioNr`). Radio 2 focus → `ST1;`, radio 1 focus → `ST0;`. Works with WinKeyer CW too. Never switches during a transmission. While receiving, the TX VFO is checked every 0.15 s and corrected, so split can't stay on while focus is on radio 1 (v1.0.3). |
| `--split-off-idle` | With `--auto-split` (v1.0.4): split is on **only** during radio 2's own transmission (CAT `TX;` → `ST1;`, `RX;` → `ST0;`) and off after every TX, whatever the focus, so a radio A message can never go out split. Needs N1MM to key radio 2 by CAT (PTT via radio command); otherwise the log warns. **Leave it off (`split_off_idle = no`) when a WinKeyer keys the radio**: then radio 2's CW would go out on VFO-A. |
| `--n1mm-radio 2` | Which N1MM radio number vRadio is (default 2). |
| `--dual-rx --dual-rx-cmd FR00;` | Keep dual receive on: 4 times a second read `FR;`, re-send `FR00;` if it changed (N1MM radio 1 switches it off when it jumps to a spot with Ctrl+Up/Down). Overrides manual toggles. |
| `--tx-follow` | At startup set TX to the controlled VFO. Ignored with `--auto-split`. |
| `--usb-data` / `--lsb-data` | USB/LSB from the software selects DATA-U/DATA-L (FT8 etc.). |
| `--radio COM14 --radio-baud 38400` | Radio port (defaults shown). |
| `--cat COM1 --cat-baud 38400` | COM-port mode instead of TCP (software then uses COM2 of the VSPE pair). |
| `-v` / `--log FILE` | Log every command / also write the log to a file (rotating, 4 x 2 MB). |
| `--tray` | Run as a tray icon (vRadioTray.exe always does). |
| `--auto-update` | At start, install a newer GitHub release and restart with it. |
| `--update` | Install the latest release now, then exit. |
| `--no-update-check` | Do not check GitHub for new versions. |
| `--version` | Show the version. |
| `--config FILE` | Settings file (default `vradio.ini` next to the exe, if it exists). |
| `--no-config` | Ignore `vradio.ini`. |
| `--write-config [FILE]` | Save the given options to `vradio.ini` (or FILE) and exit. |

N1MM macro: `{CAT2ASC VRAB;}` copies VFO-A → VFO-B on a key press.

---

## 4. Files

| File | Purpose |
|---|---|
| `dist\vRadio.exe` | The translator, console version (no Python needed). |
| `dist\vRadioTray.exe` | The same, as a system tray app (no console). |
| `dist\vRadio Tray.lnk` | Shortcut: vRadioTray with the full working options. |
| `dist\vradio.example.ini` | Every setting with its explanation; copy to `vradio.ini`. |
| `dist\vRadio_TEST.bat` | Full working setup with debug log. |
| `dist\vRadio_N1MM_TCP.bat` | Older launcher: TCP + follow-band only (no auto-split). |
| `dist\radio_monitor.exe` / `.bat` | Read-only monitor of FR/FT/ST/VS/TX/FA/FB/MD; prints every change. Stop vRadio first. |
| `dist\update_vRadio.bat` | Copies `dist\new\vRadio.exe` over `dist\vRadio.exe` (after a rebuild while vRadio was running). |
| `vradio.py` | Source. |
| `probe_yaesu.py`, `test_client.py`, `test_tcp.py` | Small test tools (Python). |
| `NOTES_auto_split.md` | Background on auto-split and dual RX. |
| `CHANGELOG.md` | Release history. |

## 5. Rebuild the exe

```
cd C:\Ham\vRadio
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m PyInstaller --onefile --console --icon vradio.ico --name vRadio vradio.py
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m PyInstaller --onefile --windowed --icon vradio.ico --name vRadioTray vradio.py
```
(Python 3.12, pyserial and PyInstaller are installed for this user.)

---

## 6. TS-2000 commands supported

ID, TY, AI (emulated by polling), PS, FA, FB, IF, MD, TX, RX, FT, FR, VV, SM (0–255 → 0–30), AG, RG, SQ,
PC, KS, VX, NB, NR, PA, RA, RT, XT, RC, RU, RD, BY, UP, DN, plus vRadio's own `VRAB`.
Anything else is answered `?;`. Not mapped: KY (CW text), SH/SL (filters), EX (menu).

## 7. Troubleshooting

- **COM14 busy:** a vRadio or radio_monitor is still running. Close it, or end `vRadio.exe` in Task Manager.
  (The one-file exe runs as two processes; end both.)
- **Radio does not answer (no `ID0681;`):** COM14 is an ELTIMA virtual port, not the radio's USB.
  Start the program that links COM14 to the radio, and check the radio is on.
- **N1MM shows "Can not set both radios to the same band!":** use `--follow-band` or the `VRAB` macro.
- **TX on the wrong VFO:** check N1MM Broadcast Data → Radio → 127.0.0.1:12064, and look in the log for
  `N1MM TX focus -> ...` lines.

## 8. Open items

- Confirm on site that `FR00;` really means dual RX (both sides receiving). The radio accepts and keeps it.
  Check: stop vRadio, run `dist\radio_monitor.bat`, toggle dual RX (Ctrl+Alt+D or radio button), read the
  `FR;` value with dual on, and use it in `--dual-rx-cmd`.
- Tray version: N1MM radio 2 connected and disconnected repeatedly in one test. Not diagnosed yet;
  use the console version (`vRadio_TEST.bat`) until then.
