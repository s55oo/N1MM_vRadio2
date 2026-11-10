# Changelog

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
