@echo off
title vRadio TEST - N1MM TCP, same band, auto-split by N1MM TX focus, full log
rem N1MM: radio 2 Port = TCP, Radio = Kenwood TS-2000, IP 127.0.0.1, port 4532
rem N1MM: Configurer > Broadcast Data > Radio = 127.0.0.1:12060 (TX focus for auto-split)
"%~dp0vRadio.exe" --tcp 4532 --follow-band --auto-split --n1mm-udp 12060 --dual-rx --dual-rx-cmd FR00; -v --log "%~dp0vradio_test_log.txt" %*
pause
