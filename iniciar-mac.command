#!/usr/bin/env bash
# ---- Iniciar CostControl en este portátil (macOS) ----
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo
  echo "  No se ha encontrado Python 3. Instálalo desde:"
  echo "    https://www.python.org/downloads/"
  echo
  read -r -p "Pulsa Intro para cerrar..."
  exit 1
fi

echo "Preparando el entorno (solo la primera vez tarda un poco)..."
[ -d ".venv" ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet Flask openpyxl

# Solo accesible desde este equipo (127.0.0.1) y abre el navegador
python run.py --host=127.0.0.1 --open

echo
echo "CostControl se ha detenido. Puedes cerrar esta ventana."
read -r -p "Pulsa Intro para cerrar..."
