@echo off
title vRadio - FTDX101D as TS-2000
rem Radio: COM14 38400 8N1  ->  TS-2000 emulation on COM1 (software connects to COM2)
rem Add --usb-data to make "USB" from software select DATA-U on the radio (FT8 etc.)
rem Add -v to log every command.
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%~dp0vradio.py" --radio COM14 --radio-baud 38400 --cat COM1 --cat-baud 38400 %*
pause
