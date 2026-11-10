@echo off
title vRadio - FTDX101D as TS-2000 over TCP (N1MM)
rem N1MM Configurer: Port = TCP, Radio = Kenwood TS-2000, IP 127.0.0.1, port 4532
rem --follow-band : VFO-B (N1MM radio B) jumps to VFO-A's band whenever VFO-A changes band
"%~dp0vRadio.exe" --tcp 4532 --follow-band %*
pause
