#!/usr/bin/env bash
# Copia de seguridad de todos los datos de CostControl (multi-empresa).
#
# Empaqueta el directorio de datos (todas las BBDD de empresas + adjuntos) en un
# .tar.gz con fecha y mantiene solo las últimas N copias.
#
# Uso:
#   COSTCONTROL_DATA_DIR=/var/data ./scripts/backup_data.sh [/ruta/backups] [N]
#
# Programar a diario con cron (ej.: 3:30 de la madrugada):
#   30 3 * * * COSTCONTROL_DATA_DIR=/var/data /ruta/Costcontrol/scripts/backup_data.sh /var/backups 14 >> /var/log/costcontrol-backup.log 2>&1

set -euo pipefail

DATA_DIR="${COSTCONTROL_DATA_DIR:-data}"
DEST="${1:-${COSTCONTROL_BACKUP_DIR:-backups}}"
KEEP="${2:-14}"

if [ ! -d "$DATA_DIR" ]; then
  echo "No existe el directorio de datos: $DATA_DIR" >&2
  exit 1
fi

mkdir -p "$DEST"
STAMP="$(date +%Y%m%d_%H%M%S)"
FILE="$DEST/costcontrol_${STAMP}.tar.gz"

# -C para guardar rutas relativas; incluye las BBDD (.db, .db-wal, .db-shm) y adjuntos.
tar -czf "$FILE" -C "$(dirname "$DATA_DIR")" "$(basename "$DATA_DIR")"
echo "Copia creada: $FILE ($(du -h "$FILE" | cut -f1))"

# Conserva solo las últimas $KEEP copias.
ls -1t "$DEST"/costcontrol_*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
  rm -f "$old"
  echo "Copia antigua eliminada: $old"
done
