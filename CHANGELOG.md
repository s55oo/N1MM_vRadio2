# Changelog

## Unreleased (v1.0.6)

- **Two PCs on one radio** (see `SETUP_2PC.md`). Laptop 2 runs its own N1MM on VFO-B through the vRadio
  server over the LAN (`tcp_host = 0.0.0.0`).
- **WinKeyer proxy** (`winkey = COM2`, our side of a VSPE splitter of the WinKeyer): laptop 2's N1MM
  gets a virtual WinKeyer on TCP 4533. Its setup commands are answered by vRadio. Only its CW
  goes to the real keyer, with its own speed as a buffered speed change. vRadio sends `ST1;` before
  each laptop 2 message and `ST0;` when the keyer is idle again, and keeps ST1 through break-in
  gaps. Laptop 1's settings and speed pot are untouched. A laptop 2 message waits while laptop 1 keys.
- **vRadioClient.exe** for laptop 2: bridges a virtual COM port (N1MM's WinKeyer) to the server,
  and the DJ jog wheel tunes VFO-B through the server. Settings are in `vradioclient.ini`.
- The DJ wheel no longer jumps back when N1MM or follow-band sets the frequency while you turn it.
- Tray: LAN clients (`N1MM TCP 4532: 2 connected (LAN 192.168.1.20)`) and the WinKeyer proxy state.

- `split_off_idle` is back to `no` in `vradio.example.ini`, and the README warns against it with a
  WinKeyer. In a contest on 10 Nov the WinKeyer keyed radio 2 without CAT `TX;`, so with
  `split_off_idle = yes` radio 2's CW stayed on VFO-A (log: `keyed without CAT TX`). Use the
  default: split follows N1MM's TX focus and the split keeper corrects it while receiving.

## v1.0.5 - 10 Nov 2026

- **DJ controller jog wheel tunes radio 2** (VFO-B). `vRadioDJ.exe` is vRadio with the wheel on and
  its own settings file `vradiodj.ini`; `vRadioTray.exe` works as before.
- Made for the Hercules DJ Control MP3 e2 (Hercules driver needed). Left jog wheel = CC 48
  (`midi_cc = 48`; 49 = right wheel, `48,49` = both). 10 Hz per step, faster spinning 2x / 5x.
- No tuning while transmitting. The controller's position dump about 4 s after connecting is
  ignored. If it's unplugged, vRadio reconnects by itself.
- Options: `--midi NAME`, `--midi-cc`, `--midi-step`, `--midi-no-accel`, `--midi-learn` (logs every
  MIDI message). Windows winmm is used directly, no extra packages.
- Tray: `DJ wheel: DJ Control MP3 e2 MIDI (10 Hz/step)`.

## v1.0.4 - 10 Nov 2026

- **`--split-off-idle`** (ini `split_off_idle = yes`): split is on only while radio 2 transmits.
  N1MM's CAT `TX;` -> `ST1;` + `TX1;`, `RX;` -> `TX0;` + `ST0;`. After every TX on radio B, split
  goes off at once and stays off, whatever the N1MM focus. Before this, split stayed on all the time
  radio 2 had focus, so a radio A message sent just after a focus change could still go out split
  (seen on air 10 Nov 16:39).
- The split keeper keeps split off while idle in this mode and never undoes a radio 2 CAT TX.
- Log warning if radio 2 has focus and the radio is keyed without CAT TX (N1MM PTT via radio
  command off): that transmission goes out on VFO-A.
- Tray: `TX focus: ... - split only during TX`.

## v1.0.3 - 10 Nov 2026

- **Split keeper** (with `--auto-split`): while the radio receives, vRadio checks the TX VFO every
  0.15 s and puts it back where N1MM's TX focus says. Example: focus on radio A but split still on
  -> `ST0;` before your next message goes out. Before this, a lost `ST` command or a split switched
  on by hand stayed on until the next TX -> RX.
- It never switches during a transmission. If something keys the radio on the wrong VFO anyway, the
  log says `TX started on the wrong VFO`.
- If the radio refuses the change 3 times, vRadio waits 5 s before trying again, so the radio is
  not flooded with commands.

## v1.0.2 - 10 Nov 2026

- **Settings file:** `vradio.ini` next to the exe is read at every start. Its keys are the long
  option names (`n1mm_udp = 12064`, `follow_band = yes`). Command-line options override it.
- `--config FILE`, `--no-config`, `--write-config [FILE]` (save the given options and exit).
- `dist\vradio.example.ini`: every setting with its explanation, filled in with the working setup.
- Tray menu: *Edit settings (vradio.ini)* (creates it from the current options if missing) and
  *Restart vRadio* (refused while transmitting).
- Wrong keys or values stop vRadio with a clear message naming the file and the setting.
- Tray menu shows the N1MM UDP listener: `N1MM UDP 12064: receiving` / `listening, no data yet` /
  `listening, last data 45 s ago` / `BUSY (used by another program)`.

## v1.0.1 - 10 Nov 2026

- **N1MM UDP port moved from 12060 to 12064.** 12060-12063 are used by Callbooker, QSOrouter,
  POUNCer and PingPong, and on Windows only one of them gets each packet. In N1MM add
  `127.0.0.1:12064` to Broadcast Data → Radio.
- The UDP port is taken exclusively (no more `SO_REUSEADDR`). A busy port is reported in the log and
  in the tray (red, `UDP 12064 busy`) instead of failing silently. vRadio retries every 5 s.
- **Auto-updater** from GitHub Releases:
  - tray: notification plus *Install update* / *Check for updates* menu items; restarts with the same options
  - `--update`, `--auto-update` (at start only), `--no-update-check`, `--version`
  - the previous exe is kept as `.old` until the next start
- The tray shortcut and `vRadio_TEST.bat` use `--n1mm-udp 12064 --auto-update`.

## v1.0.0 - 10 Nov 2026

First release. Tested on air with an FTDX101D and N1MM Logger+.

- Emulates a Kenwood TS-2000 on top of the Yaesu FTDX101D's new CAT protocol (COM14 38400 8N1 by default).
- `--vfo B` (default): N1MM radio 2 controls the radio's VFO-B (SUB). N1MM radio 1 keeps its own connection to VFO-A (MAIN).
- `--tcp 4532`: N1MM network radio (TCP) instead of a virtual COM pair. `--cat COM1` still works.
- `--follow-band` / `--same-band` / `VRAB` macro: both N1MM radios on the same band (via `AB;`).
- `--auto-split` + `--n1mm-udp 12060`: TX VFO follows N1MM's TX focus (RadioInfo broadcast). Radio 2 -> `ST1;`, radio 1 -> `ST0;`. Works with WinKeyer CW. After every TX -> RX, TX goes back to the VFO that has focus.
- `--dual-rx --dual-rx-cmd FR00;`: keeps dual receive on (the `FR00;` value still needs checking on site).
- Radio port and speed can be given first (positional): `vRadio.exe COM5 38400 ...`.
- `vRadioTray.exe`: tray app with a status icon (green/red/orange/grey), a menu, and a rotating log (`vradio_log.txt`). Only one copy can run at a time.
- `radio_monitor.exe`: read-only monitor of FR/FT/ST/VS/TX/FA/FB/MD.
- Manual: `vRadio_Manual.pdf`.

Known issues:
- Tray version: in one test N1MM radio 2 connected and disconnected repeatedly. Not reproduced or diagnosed yet. The console version works.
- The console version has no single-instance guard. Only one program can use COM14 at a time.
