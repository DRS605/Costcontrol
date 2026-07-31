#!/usr/bin/env python3
"""Punto de entrada de CostControl.

    python run.py            # arranca el servidor en http://localhost:5000
    python run.py --demo     # carga datos de ejemplo y arranca
"""

import sys

from costcontrol import db
from costcontrol.app import app


def main():
    db.init_db()
    if "--demo" in sys.argv:
        from seed_demo import seed
        seed()
        print("Datos de demostración cargados.")
    port = 5000
    for a in sys.argv:
        if a.startswith("--port="):
            port = int(a.split("=", 1)[1])
    print(f"CostControl en http://localhost:{port}")
    app.run(debug="--debug" in sys.argv, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
