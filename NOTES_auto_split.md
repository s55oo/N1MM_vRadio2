# Auto split and dual RX - status 10 Nov 2026

## Working on air
    vRadio.exe --tcp 4532 --follow-band --auto-split --n1mm-udp 12060 --dual-rx --dual-rx-cmd FR00;
(= dist\vRadio_TEST.bat, which also logs with -v to vradio_test_log.txt)

- N1MM radio 2 = radio VFO-B (SUB) on TCP 4532, as Kenwood TS-2000.
- TX VFO follows N1MM TX focus (`ActiveRadioNr` in the RadioInfo UDP broadcast on 12060):
  radio 2 -> `ST1;` (TX VFO-B), radio 1 -> `ST0;` (TX VFO-A). Works with WinKeyer CW too.
- A focus change during TX waits until the radio is back on RX.
- N1MM sees radio 2 as a plain, non-split radio.

## Why UDP and not CAT
N1MM sent CAT TX/RX to radio 2 only a few times. Most keying (WinKeyer CW) bypasses CAT,
so only N1MM's TX focus tells which radio is about to transmit.

## Still open
- Confirm `FR00;` is really dual RX (both sides receiving) on the FTDX101D.
  The radio reported `FR01;` before vRadio sent `FR00;`.
