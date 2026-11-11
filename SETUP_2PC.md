# Two PCs on one FTDX101D (vRadioServer + VSPE)

Laptop 1 works VFO-A (MAIN) as before. Laptop 2 is a separate N1MM station that works VFO-B
(SUB) over the LAN: CAT (frequency, mode, PTT) through vRadioServer, CW through the shared WinKeyer
via VSPE. The DJ wheel stays on laptop 1 and tunes VFO-B. N1MM's multi-computer network provides
the TX interlock.

```
Laptop 1                                                   Laptop 2
  N1MM (radio 1 = FTDX101D, VFO-A only) - microHAM port 1
  vRadioServer ---- COM14 (microHAM port 2) - VFO-B
     TCP 4532  <------------------- LAN -------------------  N1MM radio = TS-2000, TCP laptop1:4532
  DJ Control MP3 e2 -> vRadioServer (left wheel tunes VFO-B)
  VSPE: Splitter COM12 (WinKeyer) -> COM1, COM2
     COM1 = laptop 1's N1MM WinKeyer
     TCP Server 5555 on COM2  <------- LAN ----------------  VSPE TCP Client -> COM20 -> N1MM WinKeyer
```

## Laptop 1

1. VSPE:
   - a **Splitter** on COM12 (the WinKeyer) with two ports, COM1 and COM2. N1MM's WinKeyer = COM1.
   - a **TCP Server** on port 5555 attached to COM2.
2. N1MM on laptop 1: radio 1 = FTDX101D on microHAM port 1. **No radio 2** (laptop 2 has it).
3. `vRadioServer.exe` with `vradioserver.ini` next to it. Its defaults are already right:
   ```
   radio = COM14
   tcp = 4532
   tcp_host = 0.0.0.0        ; laptop 2 connects over the LAN
   auto_split = yes
   split_off_idle = yes      ; split only while laptop 2 transmits (CAT TX)
   follow_band = no          ; laptop 1's band changes must not move laptop 2
   midi = MP3                ; DJ Control MP3 e2 on this laptop tunes VFO-B; no = off
   ```
4. Windows Firewall: vRadioServer gets its own allow rule when it first starts. VSPE runs as a
   service and gets no prompt, so add a rule for TCP 5555 as administrator, e.g.
   `New-NetFirewallRule -DisplayName "VSPE 5555" -Direction Inbound -Protocol TCP -LocalPort 5555 -Action Allow -RemoteAddress 192.168.0.0/24`

## Laptop 2

1. VSPE: a **TCP Client** to `laptop1-IP:5555` that creates a COM port, e.g. COM20.
2. N1MM on laptop 2:
   - Radio = **TS-2000**, Port = **TCP**, address `laptop1-IP:4532` (in the port's Set dialog).
   - Set: **PTT via Radio Command CW Mode**, PTT Delay 50 ms. This is what moves TX to VFO-B.
   - WinKeyer on **COM20**.
   - Join the N1MM multi-computer network with laptop 1 (interlock).

## How a laptop 2 CW message goes out

1. Laptop 2's N1MM sends CAT `TX;` over 4532. vRadioServer sends `ST1;` (TX on VFO-B) and keys.
2. 50 ms later N1MM sends the text to the WinKeyer (COM20 -> VSPE -> LAN -> COM2 -> splitter).
3. When the message is done N1MM sends `RX;`; vRadioServer unkeys and sends `ST0;` (TX back on
   VFO-A for laptop 1).

## Checks

- Laptop 2: send a CQ. The radio transmits on **VFO-B**; vRadioServer's log shows `tcp TX;`,
  `ST1;`, then `CAT RX: split off, TX on VFO-A`.
- Laptop 1: send a CQ. TX stays on VFO-A.
- Turn the left jog wheel on laptop 1: VFO-B moves and laptop 2's N1MM follows.

## Limits

- No password: anyone on the LAN can reach ports 4532 and 5555. Never forward them to the internet.
- The VSPE splitter sends the keyer's status and echo to both N1MMs, so each one sees the other's
  CW as "keyer busy". Messages from both at once mix in the one keyer: the N1MM interlock must
  prevent that.
- If laptop 2's N1MM keys without CAT `TX;` (PTT via Radio Command CW off), its CW goes out on
  VFO-A; the log warns `keyed without CAT TX`.
