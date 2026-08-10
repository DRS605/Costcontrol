@echo off
REM ---- Iniciar CostControl en este portatil (Windows) ----
cd /d "%~dp0"
title CostControl

REM Detecta Python (py o python)
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)

%PY% --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo  No se ha encontrado Python. Instalalo desde:
  echo    https://www.python.org/downloads/
  echo  Durante la instalacion, marca "Add Python to PATH".
  echo.
  pause
  exit /b
)

echo Preparando el entorno (solo la primera vez tarda un poco)...
if not exist ".venv" (
  %PY% -m venv .venv
)
call ".venv\Scripts\activate.bat"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet Flask openpyxl

REM Solo accesible desde este equipo (127.0.0.1) y abre el navegador
python run.py --host=127.0.0.1 --open

echo.
echo CostControl se ha detenido. Puedes cerrar esta ventana.
pause
