#!/usr/bin/env bash
# ---- Iniciar CostControl en este portátil (Linux) ----
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "No se ha encontrado Python 3. Instálalo con el gestor de paquetes de tu distribución."
  read -r -p "Pulsa Intro para cerrar..."
  exit 1
fi

echo "Preparando el entorno (solo la primera vez tarda un poco)..."
[ -d ".venv" ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet Flask openpyxl

python run.py --host=127.0.0.1 --open

echo "CostControl se ha detenido."
read -r -p "Pulsa Intro para cerrar..."
