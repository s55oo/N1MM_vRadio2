# Two PCs on one FTDX101D (vRadio server + vRadioClient)

Laptop 1 works VFO-A (MAIN) as before. Laptop 2 is a separate N1MM station that works VFO-B
(SUB) through vRadio over the LAN: frequency, mode, CW from its own N1MM, and the DJ wheel.
N1MM's multi-computer network provides the TX interlock.

```
Laptop 1                                              Laptop 2
  N1MM (radio 1 = FTDX101D, VFO-A only) - microHAM port 1
  vRadio server ---- COM14 (microHAM port 2) - VFO-B
     TCP 4532  <----------------- LAN ------------------  N1MM radio 1 = TS-2000, TCP laptop1:4532
     TCP 4533  <----------------- LAN ------------------  vRadioClient <- COM21 | COM20 -> N1MM WinKeyer
     COM2 (VSPE splitter of COM12 WinKeyer)               DJ Control MP3 e2 -> vRadioClient
  N1MM WinKeyer = COM1 (other side of the VSPE splitter)
```

## Laptop 1 (vRadio server)

1. VSPE: a **Splitter** on COM12 (the WinKeyer) with two ports, COM1 and COM2.
   N1MM's WinKeyer = COM1. COM2 is for vRadio. N1MM on laptop 1 must be running with the
   WinKeyer open, as now.
2. N1MM on laptop 1: radio 1 = FTDX101D on microHAM port 1. **No radio 2** (laptop 2 has it).
3. `vradio.ini` (use `vRadioTray.exe`; `vRadioDJ.exe` only if the wheel is plugged into laptop 1):
   ```
   tcp_host = 0.0.0.0        ; accept laptop 2
   follow_band = no          ; laptop 1's band changes must not move laptop 2
   auto_split = yes
   split_off_idle = yes      ; split only while laptop 2 transmits (its CW comes through vRadio)
   winkey = COM2             ; share the WinKeyer with laptop 2
   ```
4. Start vRadio. When Windows Firewall asks, allow it on **Private networks only**.
   The tray menu shows `N1MM TCP 4532: ... (LAN 192.168.x.y)` and `WinKeyer COM2: remote ...`.

## Laptop 2 (client)

1. Install a **virtual COM pair** (VSPE "Pair" or com0com), e.g. COM20 <-> COM21.
2. N1MM on laptop 2:
   - Radio 1 = **TS-2000**, Port = **TCP**, address `laptop1-IP`, port `4532`.
   - CW: **WinKeyer on COM20** (PTT via WinKeyer, as usual).
   - Join the N1MM multi-computer network with laptop 1 (interlock).
3. Copy `vRadioClient.exe` to a folder, create `vradioclient.ini` next to it:
   ```
   [vradio]
   server = 192.168.1.10     ; laptop 1's IP
   winkey = COM21            ; other end of the pair N1MM uses
   midi = MP3                ; DJ Control MP3 e2 (Hercules driver installed); empty = no wheel
   midi_cc = 48              ; left jog wheel
   midi_step = 10
   ```
4. Start **vRadioClient before N1MM** (N1MM opens the WinKeyer at start-up).
   The tray shows `vRadio ...:4532 (wheel): connected` and `WinKeyer COM21 -> vRadio ...: connected`.

## How a laptop 2 CW message goes out

1. Laptop 2's N1MM sends its message to "its" WinKeyer (COM20 -> vRadioClient -> LAN).
2. vRadio waits until laptop 1 is not keying, sends `ST1;` (TX on VFO-B), waits 30 ms
   (`winkey_split_delay`), then passes the text to the real WinKeyer with laptop 2's speed as a
   buffered speed change. Laptop 1's speed, weighting and PTT settings are never touched.
3. Break-in gaps don't switch the VFO. When the keyer reports idle, vRadio cancels the buffered
   speed and sends `ST0;`: TX is back on VFO-A for laptop 1.

Setup commands from laptop 2's N1MM (host open, speed, weighting, PTT times, modes) are answered by
vRadio and never reach the real keyer. The speed pot stays with laptop 1. Esc on laptop 2 clears
the keyer buffer only while laptop 2's own message is being sent.

## Checks

- Laptop 2: send a CQ. The radio must transmit on **VFO-B**; vRadio's log shows
  `WinKeyer proxy: remote CW - TX on VFO-B` and then `Remote CW done: split off, TX on VFO-A`.
- Laptop 1: send a CQ. TX stays on VFO-A and nothing appears on laptop 2.
- Turn the left jog wheel on laptop 2: VFO-B moves and both laptop 2's N1MM and the radio follow.

## Limits

- No password: anyone on the LAN can reach ports 4532/4533. Never forward them to the internet.
- One remote WinKeyer client at a time.
- If both N1MMs ever send at the same moment despite the interlock, vRadio holds laptop 2's message
  up to 10 s while laptop 1 keys, then drops it (`remote message dropped` in the log).
- The VSPE splitter merges what both hosts write. N1MM is quiet between messages, so this is
  normally fine, but it has not been tested with both keyers being heavily used.
