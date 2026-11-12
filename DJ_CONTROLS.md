# DJ Control MP3 e2: map the controls to VFO-B (vRadioDJ)

vRadioDJ has a mapper page, like the one in
[MP3e2_to_AetherSDR](https://github.com/s55oo/MP3e2_to_AetherSDR): a picture of the controller
where you click a control, or touch it on the real controller, and pick what it does.
Everything acts on **VFO-B (the SUB receiver) of the FTDX101D**.

## Open it

Tray icon > **DJ controller mapping...**, or open `http://127.0.0.1:8065/` in a browser on the PC
that runs vRadioDJ. The page only answers this PC.

1. **Pick a control:** click it in the picture, or touch it on the controller. With
   *Select by touching the controller (radio paused)* ticked (the default), touching a control
   only selects it: the radio does not change while the page is open with that box ticked.
   Untick it to try your mapping on the radio.
2. **Pick its function:** the list shows only functions that suit that control: buttons get
   on/off and step functions, faders and knobs get levels, endless wheels get tuning, filter
   width, IF shift and notch frequency.
3. It applies at once and is saved in `vradiodj_midi.json` next to `vRadioDJ.exe`. There is
   no Save or Load button: your layout is always the one in use, also after a restart.

**Unassign** frees a control. **Load VFO-B starter layout** replaces your layout with the one
below; **Clear all** frees every control. Both first copy your layout to
`vradiodj_midi.bak.json`, and **Undo** brings it back (pressing Undo again swaps back).
**Save picture (JPG)** downloads `vRadioDJ_mapping.jpg`: the controller with your functions
written on it and the full list under it, to print or keep next to the station. The number keys 5–8 (Loops/Fx lit) have their own view:
*Keys 5–8*. *Controller activity* lists the last MIDI messages.

## Functions (all on VFO-B)

| Group | Functions | CAT |
|---|---|---|
| Tuning | tune (wheel), step down / up (1–500 Hz), lock wheel, ±1 MHz, ±1 kHz, band up / down, copy VFO-A → VFO-B | `FB`, `BU1`/`BD1`, `AB` |
| Mode | mode down / up, LSB, USB, CW-U, CW-L, AM, FM, RTTY-L, RTTY-U, DATA-L, DATA-U | `MD1` |
| Audio | AF gain (fader), mute on/off | `AG1` |
| Receive | RF gain, squelch level, squelch on/off, AGC cycle, IPO / AMP1 / AMP2 cycle, attenuator cycle | `RG1`, `SQ1`, `GT1`, `PA1`, `RA1` |
| Filter | narrower / wider (buttons), width (wheel), IF shift (wheel), IF shift to 0 | `SH1`, `IS1` |
| Noise | NB, NR, NR level (fader or cycle), auto notch (DNF), manual notch on/off and frequency | `NB1`, `NR1`, `RL1`, `BC1`, `BP1` |
| Transmit on VFO-B | **MOX** (press on, press off, off by itself after 60 s), **ATU tune** | `ST1`, `TX1` / `TX0`; `AC002` |

MOX and ATU tune are refused while the radio already transmits. Mode, band and frequency
functions do nothing while transmitting. Functions that would change the whole radio (RF
power, mic gain, VOX, processor, monitor) are not offered.

## VFO-B starter layout

The AetherSDR starter layout, translated: jog A = tune; Deck A: M.Tempo NB, Sync NR, pitch
bend −/+ filter, pitch knob IF shift, keys 1–4 mode −/+, squelch on/off, notch on/off,
◀◀/▶▶ tune step, Cue LSB, Play USB, volume AF gain, treble squelch, medium RF gain, PFL mute,
Load A copy A→B. Centre: Scratch lock, arrows band, Folder NR level, Files AGC.
Deck B: keys 1–5 CW, AM, FM, DATA-U, DNF; pitch knob notch frequency; ◀◀/▶▶ ±1 MHz;
Cue ATU tune; Play MOX.

## Settings (`vradiodj.ini`)

| Setting | Effect |
|---|---|
| `dj_web_port = 8065` | port of the mapper page |
| `midi_no_buttons = yes` | only the jog wheel tunes (`midi_cc`); no mapping, no page |
