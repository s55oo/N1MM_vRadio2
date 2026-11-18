@echo off
rem vRadioTM with the TMate 1.0 knob: starts loopMIDI, Tmate-as-MIDI and vRadioTM in that order.
rem Anything already running is left alone. Edit the paths if your folders differ.
setlocal
set "LOOPMIDI=C:\Program Files (x86)\Tobias Erichsen\loopMIDI\loopMIDI.exe"
set "TMATE=C:\Ham\Tmate-as-MIDI\bin\tmate1-midi-hidden.vbs"
set "VRADIOTM=%~dp0vRadioTM.exe"

echo 1/3 loopMIDI (port "TMate 1.0")
tasklist /FI "IMAGENAME eq loopMIDI.exe" | find /I "loopMIDI.exe" >nul
if not errorlevel 1 goto loopmidi_ok
if not exist "%LOOPMIDI%" goto no_loopmidi
start "" "%LOOPMIDI%"
timeout /t 3 /nobreak >nul
echo    started
goto tmate
:loopmidi_ok
echo    already running

:tmate
echo 2/3 Tmate-as-MIDI (http://127.0.0.1:8067/)
powershell -NoProfile -Command "try { Invoke-WebRequest http://127.0.0.1:8067/api/state -UseBasicParsing -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }"
if not errorlevel 1 goto tmate_ok
if not exist "%TMATE%" goto no_tmate
wscript "%TMATE%"
timeout /t 4 /nobreak >nul
echo    started
goto vradio
:tmate_ok
echo    already running

:vradio
echo 3/3 vRadioTM
for %%P in (vRadioTM.exe vRadioDJ.exe vRadioTray.exe vRadio.exe) do call :running %%P
if defined BUSY goto busy
start "" "%VRADIOTM%"
echo    started - watch the tray icon (TMate wheel: TMate 1.0 ...)
goto done
:busy
echo    %BUSY% is already running - COM14 is taken, vRadioTM not started

:done
timeout /t 5 >nul
exit /b 0

:running
tasklist /FI "IMAGENAME eq %1" | find /I "%1" >nul
if not errorlevel 1 if not defined BUSY set "BUSY=%1"
exit /b 0

:no_loopmidi
echo    loopMIDI not found: %LOOPMIDI%
pause
exit /b 1

:no_tmate
echo    Tmate-as-MIDI not found: %TMATE%
pause
exit /b 1
