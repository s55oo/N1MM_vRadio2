# One PC or two PCs on one FTDX101D

vRadio (`vRadioTray.exe`, or `vRadioDJ.exe` with the DJ wheel) makes the radio's VFO-B look like a
TS-2000 for N1MM radio 2. One setting chooses the setup:

| `pcs` | Setup | Radio 2 is |
|---|---|---|
| `pcs = 1` (default) | **One PC**: this laptop's N1MM runs radio 1 (VFO-A) and radio 2 (VFO-B), SO2R | this PC's N1MM, TCP 127.0.0.1:4532 |
| `pcs = 2` | **Two PCs**: laptop 1 works VFO-A, laptop 2 works VFO-B, each SO1R | laptop 2's N1MM over the LAN, TCP laptop1:4532 |

The **DJ console (Hercules DJ Control MP3 e2) is always connected to the PC that runs vRadio**
(laptop 1) and its left jog wheel tunes VFO-B there, also with `pcs = 2`. Use `vRadioDJ.exe`
(settings in `vradiodj.ini`) when it is plugged in, `vRadioTray.exe` (`vradio.ini`) when not.
Run only one vRadio at a time: they share COM14.

## Two PCs (`pcs = 2`)

```
Laptop 1 (vRadio)                                          Laptop 2
  N1MM radio 1 = FTDX101D (VFO-A) - microHAM port 1
  vRadio (pcs = 2) ---- COM14 (microHAM port 2) - VFO-B
     TCP 4532  <------------------- LAN -------------------  N1MM radio = TS-2000, TCP laptop1:4532
  DJ Control MP3 e2 -> vRadio (left jog wheel tunes VFO-B)
  VSPE: Splitter COM12 (WinKeyer) => COM1, COM2
     COM1 = laptop 1's N1MM WinKeyer
     TcpServer COM2 : 5555  <--------- LAN ----------------  VSPE TcpClient COM2 <=> Pair <=> COM1 -> N1MM WinKeyer
```

`pcs = 2` sets these together, whatever else the ini says (the log lists what it changed):
`tcp = 4532`, `tcp_host = 0.0.0.0`, `auto_split = yes`, `split_off_idle = yes` (split only while
laptop 2 transmits by CAT), `follow_band = no` (laptop 1's band changes never move laptop 2),
`n1mm_udp` off. The tray shows `Two PCs: radio 2 = other PC over the LAN`.

### Laptop 1

1. `vradiodj.ini` (or `vradio.ini`): `pcs = 2`. Keep `radio = COM14`, `vfo = B`, `dual_rx = yes`,
   `midi = MP3`.
2. N1MM: radio 1 = FTDX101D on COM10 (microHAM port 1), WinKeyer on COM1. **No radio 2**
   (laptop 2 has it). Details in the N1MM table below.
3. Firewall: vRadio gets its own allow rule when Windows asks at the first start. VSPE runs as a
   service and gets no prompt: add a rule for TCP 5555 as administrator, e.g.
   `New-NetFirewallRule -DisplayName "VSPE 5555" -Direction Inbound -Protocol TCP -LocalPort 5555 -Action Allow -RemoteAddress 192.168.0.0/24`

### Laptop 2

1. VSPE (see the WinKeyer section below): Pair COM1 <=> COM2 and a TcpClient on COM2 to
   `laptop1-IP:5555`. Start VSPE before N1MM.
2. N1MM: SO1V, radio **TS-2000** on **TCP 192.168.0.240:4532**, WinKeyer on **COM1**. Details in
   the N1MM table below.

   PTT via Radio Command is what moves TX to VFO-B: N1MM sends CAT `TX;`, vRadio sends `ST1;` and
   keys, and after `RX;` sends `ST0;`.
3. Join the N1MM multi-computer network with laptop 1 (TX interlock).
4. Over ZeroTier instead of the LAN, use laptop 1's ZeroTier address (e.g. 10.147.17.116) in both
   places: the N1MM radio port and the VSPE TcpClient.

## microHAM Router on laptop 1 (micro KEYER III), as tested

microHAM USB Device Router 9.3.5, micro KEYER III firmware v2.12 (WinKey rev. 31), radio
**Yaesu FTdx101D**. Ports tab:

| Router port | COM | Shown as | Used by |
|---|---|---|---|
| CAT | **COM10** | open 38400 8N2 | laptop 1's N1MM radio 1 (VFO-A) |
| 2nd CAT | **COM14** | open 38400 8N1 | vRadio (VFO-B) |
| PTT | **COM11** | RTS | (not used by N1MM: PTT goes by CAT command) |
| Foot Switch | **COM13** | CTS | |
| WinKey | **COM12** | open 115200 8N1 | VSPE Splitter source |
| FSK, 2nd FSK, CW, 2nd PTT, Auxiliary, Control | none | | |

Both CAT ports reach the same radio. The router also hands each program answers meant for the
other one; vRadio skips answers that don't match its own query.

## WinKeyer settings (shared through VSPE)

There is one WinKeyer (microKEYER, COM12) and both N1MMs use it. vRadio does not touch the keyer.

**VSPE on laptop 1** (start VSPE before N1MM; save the configuration so it loads at start):

| Device | Settings | Used by |
|---|---|---|
| Splitter | source **COM12** (the WinKeyer) => **COM1, COM2** | COM1 = laptop 1's N1MM, COM2 = the TCP server |
| TcpServer | port **COM2**, TCP port **5555** | laptop 2 |

VSPE's device list then shows `Splitter: COM12 => COM1,2` (Connections 2/2) and
`TcpServer: TCP COM2 : 5555,0` (Connections 1 when laptop 2 is connected).

**VSPE on laptop 2** (start VSPE before N1MM; save the configuration):

| Device | Settings | Used by |
|---|---|---|
| Pair | **COM1 <=> COM2** | COM1 = laptop 2's N1MM WinKeyer |
| TcpClient | port **COM2** => **192.168.0.240:5555** (laptop 1) | the link to laptop 1's keyer |

VSPE's device list shows `Pair: COM1 <=> COM2` (Connections 2/2) and
`TcpClient: TCP COM2 => 192.168.0.240:5555,0` (Connections 1/1 when connected to laptop 1).

## N1MM configuration (Configurer > Hardware), as tested

| Row | Laptop 1 (local) | Laptop 2 (remote) |
|---|---|---|
| Operating mode | as before (radio 1 only) | **SO1V** |
| Radio port | **COM10**, Radio **FTDX101D** (VFO-A, microHAM port 1) | **TCP**, Radio **TS-2000**, IP Addr:Port **192.168.0.240:4532** |
| Radio `Set` | **PTT via Radio Command CW Mode**, PTT Delay 50 | **PTT via Radio Command CW Mode**, PTT Delay 50 (N1MM shows `38400,N,8,2,Handshake,Tx=1`) |
| WinKeyer port | **COM1** (VSPE splitter end), CW/Other ticked | **COM1** (VSPE pair end), CW/Other ticked |
| WinKeyer `Set` | DTR **Always On**, RTS **Always Off**, PTT Delay **50**, **WinKey** ticked, VFO Nr **1**, Two Radio Protocol None, FootSwitch None | the same |
| Winkey tab (mode, weighting, sidetone, PTT lead/tail) | **identical on both laptops** | **identical on both laptops** |

Laptop 1 has no radio 2 row: VFO-B belongs to laptop 2.

Things to know:

- **Speed is per laptop.** N1MM sends its own speed with every message (buffered speed change),
  so each operator keeps their own WPM.
- **Setup is shared.** When an N1MM opens the WinKeyer (at start-up) it sends its mode, weighting,
  sidetone and PTT lead/tail to the one keyer, for both laptops. Keep those settings identical, or
  the laptop that started last wins.
- **Both N1MMs see each other's CW** as "keyer busy" and as echoed characters: the splitter sends
  the keyer's output to both. That's harmless; a message started meanwhile queues behind.
- **Never send from both at once**: the two messages would mix in one keyer. The N1MM interlock
  must prevent it.
- **Esc** (or the next F-key) sends CLEAR to the shared keyer and cuts the message currently being
  sent, from either laptop.

## Checks

- Laptop 2: send a CQ. The radio transmits on **VFO-B**; vRadio's log (verbose) shows `tcp TX;`,
  `ST1;`, then `CAT RX: split off, TX on VFO-A`.
- Laptop 1: send a CQ. TX stays on VFO-A.
- Turn the left jog wheel on laptop 1: VFO-B moves and laptop 2's N1MM follows.
- Ctrl+Up/Down (jump to spot) on laptop 1: N1MM switches dual receive off; vRadio switches it back
  on within about 0.25 s (`Dual RX: radio reported FR01, sent FR00;`).

## Limits

- No password: anyone on the LAN can reach ports 4532 and 5555. Never forward them to the internet.
- If laptop 2's N1MM keys without CAT `TX;` (PTT via Radio Command off), its CW goes out on
  VFO-A; the log warns `keyed without CAT TX`.
