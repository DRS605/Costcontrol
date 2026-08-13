"""Punto de entrada WSGI para hosting (PythonAnywhere, Render, gunicorn...).

En PythonAnywhere se suele pegar un contenido equivalente en el fichero WSGI
del panel (ver DEPLOY.md). Este archivo sirve para hosts que ejecutan el repo
directamente, p.ej.:  gunicorn wsgi:application
"""

import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

# --- CONFIGURACIÓN (cámbiala antes de publicar) ------------------------------
# Si el hosting ya define estas variables de entorno, se respetan (setdefault).
os.environ.setdefault("COSTCONTROL_SECRET", "cambia-esto-por-una-frase-larga-y-secreta")
# Deja una contraseña para proteger el acceso (la app quedará pública):
os.environ.setdefault("COSTCONTROL_PASSWORD", "")
# -----------------------------------------------------------------------------

from costcontrol.app import app as application, bootstrap  # noqa: E402
bootstrap()

if __name__ == "__main__":
    application.run()
