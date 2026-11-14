# vRadio → PingPong: stations that share one radio

## The problem

With vRadio in two-PC mode (`pcs = 2`), two N1MM stations work one Yaesu FTDX101D:

- **Host station:** the PC that runs vRadio. Its N1MM drives **VFO-A** directly (its own CAT
  port, e.g. COM10).
- **Client station:** another PC. Its N1MM drives **VFO-B** through vRadio (Port = TCP,
  `host:4532`, radio TS-2000).

The radio reports TX for the whole radio. So the host's N1MM sees **TX while the client
transmits**, and above all in the **tail** after the client's message (PTT tail + the radio's
break-in delay). It then sends RadioInfo `IsTransmitting = true` for its own radio, although its
operator pressed nothing. PingPong then sees a false TX from the host station.

Seen on 14 Nov 2026, PingPong log:

```
20:46:44.605  RUN3 (client, S50C-E8460P)  tx=False   <- its message has ended
20:46:44.888  RUN2 (host,   L15CAB)       tx=True    <- false: the radio is still in the tail
20:46:45.325  RUN2 (host,   L15CAB)       tx=True    <- false
```

It also happens **the other way round**: both N1MMs share one WinKeyer (VSPE splitter), so each
sees the other's CW as "keyer busy" and reports `IsTransmitting = true` for itself. Recorded on
14 Nov 2026 21:22:59-21:23:07: the client (RUN3) sent `tx=True` several times while only the host
(laptop 1, VFO-A) was on air. So for a shared radio, **neither** station's `IsTransmitting` can
be trusted; only vRadio's `Tx` / `TxFrom` is.

vRadio knows who really transmits (it keys the radio for the client, and watches the radio until
it is back on RX), so it tells PingPong directly.

## The packet

vRadio 1.0.9+ with `pcs = 2` broadcasts one UDP packet on **PingPong's own port 46070**:

- every **1 s**, and **at once** when TX starts or ends or a client connects or leaves;
- on every network interface, to `255.255.255.255` and to the `/24` broadcast address (like the
  PingPong lamps), and to `127.0.0.1`;
- UTF-8 XML, one element per packet, root **`<vRadioShare>`**
  (PingPong 1.101 already ignores it: tested, no error, nothing logged).

```xml
<vRadioShare>
  <Id>L15CAB-17400</Id>                 <!-- host name + vRadio process id: one per vRadio run -->
  <Host>L15CAB</Host>                   <!-- Windows computer name of the host station -->
  <Version>1.0.9</Version>
  <Ips>10.147.17.116,192.168.0.240</Ips><!-- the host's own IPv4 addresses (no 127.x) -->
  <Radio>FTDX101D</Radio>
  <HostVfo>A</HostVfo>                  <!-- radio VFO of the host station's N1MM -->
  <ClientVfo>B</ClientVfo>              <!-- radio VFO of the client station(s) -->
  <Clients>10.147.17.187</Clients>      <!-- IPs of the N1MM clients connected to vRadio, comma separated (no 127.x) -->
  <Tx>B</Tx>                            <!-- none | A | B : radio VFO on air right now -->
  <TxFrom>10.147.17.187</TxFrom>        <!-- who keyed it: a client IP | local | dj | empty when Tx = none -->
  <Seq>1234</Seq>                       <!-- +1 per packet -->
</vRadioShare>
```

| Field | Meaning |
|---|---|
| `Tx` | `none` = the radio receives. `A` / `B` = it transmits on that VFO. **Held until the radio is really back on RX**, so the tail of a message still counts as the same transmission. |
| `TxFrom` | A client IP = that client station keyed it (its N1MM CAT `TX;`). `local` = keyed on the host (its N1MM, WinKeyer, paddle, PTT line). `dj` = vRadio's DJ controller (MOX / ATU tune on VFO-B). |
| `Ips` / `Clients` | Match these with the `<Ips>` of the lamps' `<PingPongHello>`. |

## What PingPong should do

1. **Pairing.** A lamp whose `<Ips>` contains any address of `<Ips>` of a `vRadioShare` is the
   **host station** of that radio. A lamp whose `<Ips>` contains an address in `<Clients>` is a
   **client station** of it. Host and its clients **share one radio**. The role names (RUN2,
   RUN3, INB3, INB4…) don't matter.
2. **TX of shared stations comes from vRadio, not from N1MM's RadioInfo `IsTransmitting`:**
   - `Tx = none` → none of them transmits.
   - `Tx = HostVfo` (`A`) → the host station transmits.
   - `Tx = ClientVfo` (`B`) → the client station whose IP is `TxFrom` transmits (if `TxFrom` is
     `local` or `dj`, treat it as the host station: its operator keyed it).
   - Ignore `IsTransmitting = true` from a shared station while vRadio says it is not that
     station's transmission.
3. **Stale data.** If no `vRadioShare` with that `Id` arrives for **3 s**, forget the pairing
   and use N1MM's RadioInfo again (vRadio stopped or the network is down).
4. Stations that are not in any `vRadioShare` work exactly as today.
5. When several PingPong lamps run, each receives the broadcast itself; relaying is not needed
   (the host's lamp also gets it on `127.0.0.1`).

## Settings on the vRadio side

`pcs = 2` turns it on with port 46070. `pingpong_port = 0` in `vradiodj.ini` / `vradio.ini`
turns it off; another number sends to that port instead.
