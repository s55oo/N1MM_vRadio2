@echo off
rem Close the running vRadio window first, then run this to replace dist\vRadio.exe
copy /Y "%~dp0new\vRadio.exe" "%~dp0vRadio.exe" && echo vRadio.exe updated.
pause
