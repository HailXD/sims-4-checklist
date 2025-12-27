@echo off
setlocal

set "TS4_EXE=C:\Program Files (x86)\Steam\steamapps\common\The Sims 4\Game\Bin\TS4_x64.exe"

set ARGS=-disablepacks:EP06,EP08,EP12,EP14,GP03,GP04,GP06,GP07,GP08,GP09,GP10,GP12

start "" "%TS4_EXE%" %ARGS%

endlocal
