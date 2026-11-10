# Changelog

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
