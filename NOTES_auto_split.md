# Auto split and dual RX - status 18 Nov 2026

## Working on air
    vRadio.exe --tcp 4532 --follow-band --auto-split --n1mm-udp 12064 --dual-rx --dual-rx-cmd FR00;
(= dist\vRadio_TEST.bat, which also logs with -v to vradio_test_log.txt)

- N1MM radio 2 = radio VFO-B (SUB) on TCP 4532, as Kenwood TS-2000.
- TX VFO follows N1MM TX focus (`ActiveRadioNr` in the RadioInfo UDP broadcast on 12064):
  radio 2 -> `ST1;` (TX VFO-B), radio 1 -> `ST0;` (TX VFO-A). Works with WinKeyer CW too.
- A focus change during TX waits until the radio is back on RX.
- N1MM sees radio 2 as a plain, non-split radio.

## Why UDP and not CAT
N1MM sent CAT TX/RX to radio 2 only a few times. Most keying (WinKeyer CW) bypasses CAT,
so only N1MM's TX focus tells which radio is about to transmit.

## Dual RX
- `FR00;` = dual receive (MAIN + SUB), `FR01;` = single receive: confirmed on air 18 Nov 2026.
- N1MM radio 1 (FTDX101D, also in SO1V) sends `FR01;` at every spot jump (bandmap click,
  Ctrl+Up/Down) on its own port COM10, so VFO-B goes silent. vRadio can't block it from COM14;
  the keeper re-sends `FR00;` within `dual_rx_interval` (0.1 s since v1.0.10, was 0.25 s).
