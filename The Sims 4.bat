@echo off
setlocal

set STEAM_EXE="C:\Program Files (x86)\Steam\steam.exe"

set ARGS=-applaunch 1222670 -console -disablepacks:

start "" %STEAM_EXE% %ARGS%

endlocal