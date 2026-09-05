@echo off
REM ---------------------------------------------------------------------
REM  The local Firestore for AI Commerce Studio.
REM
REM  This is the ONLY datastore the project uses day to day. There is no
REM  switching: the app defaults to this emulator, so nothing needs setting
REM  before running the backend.
REM
REM  --import  loads firebase-export\ on start
REM  --export-on-exit  writes it back when you stop with Ctrl+C
REM
REM  So your demo data — orders, searches, merchant catalogue — survives a
REM  restart. Stop it with Ctrl+C in this window, NOT by closing the window
REM  or killing the process: a force-kill skips the export and loses
REM  anything created since the last start.
REM ---------------------------------------------------------------------
setlocal
set ROOT=%~dp0
set SNAPSHOT=%ROOT%firebase-export
set CONFIG=%ROOT%backend\firebase.json

echo.
echo   Starting the local Firestore emulator
echo   Config: %CONFIG%  (this file sets the port)
echo   Data folder: %SNAPSHOT%
echo   Stop with Ctrl+C so your data is saved.
echo.

cd /d "%ROOT%backend"

if exist "%SNAPSHOT%" (
  firebase emulators:start --config "%CONFIG%" --only firestore --project cart-pilot-9a550 --import "%SNAPSHOT%" --export-on-exit "%SNAPSHOT%"
) else (
  echo   No snapshot yet — starting empty and creating one on exit.
  firebase emulators:start --config "%CONFIG%" --only firestore --project cart-pilot-9a550 --export-on-exit "%SNAPSHOT%"
)

endlocal
