@echo off
setlocal

set STEAM_EXE="C:\Program Files (x86)\Steam\steam.exe"

set ARGS=-applaunch 1222670 -console -disablepacks:EP06,EP09,EP11,EP12,EP14,EP17,EP19,EP21,GP04,GP06,GP07,GP08,GP09,GP10,GP12

start "" %STEAM_EXE% %ARGS%

endlocal