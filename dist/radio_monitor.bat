@echo off
title vRadio radio monitor (read-only) - stop vRadio first
"%~dp0radio_monitor.exe" COM14 38400 %*
pause
