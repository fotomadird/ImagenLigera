@echo off
setlocal
cd /d "%~dp0"
title ImagenLigera - compilar para Windows
echo === ImagenLigera: compilando para Windows ===

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo No encuentro Python. Instala Python 3.10 o superior desde python.org
  echo y marca "Add python.exe to PATH".
  goto error
)
%PY% --version

if not exist .venv\Scripts\python.exe (
  %PY% -m venv .venv || goto error
)
call .venv\Scripts\activate.bat || goto error
python -m pip install --upgrade pip >nul
pip install -r requirements.txt || goto error

pyinstaller --noconfirm --clean ImagenLigera.spec || goto error

echo.
echo Listo: %CD%\dist\ImagenLigera.exe
if /i not "%~1"=="nopause" pause
exit /b 0

:error
echo.
echo *** ERROR durante la compilacion ***
if /i not "%~1"=="nopause" pause
exit /b 1
