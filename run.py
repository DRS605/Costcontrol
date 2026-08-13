#!/usr/bin/env python3
"""Punto de entrada de CostControl.

    python run.py                 # arranca en http://localhost:5000
    python run.py --demo          # carga datos de ejemplo y arranca
    python run.py --open          # abre el navegador automáticamente
    python run.py --host=127.0.0.1  # solo accesible desde este equipo (local)
    python run.py --port=8080
"""

import sys
import threading
import webbrowser

from costcontrol.app import app, bootstrap


def main():
    bootstrap()
    if "--demo" in sys.argv:
        from seed_demo import seed
        seed()
        print("Datos de demostración cargados.")

    port = 5000
    host = "0.0.0.0"
    for a in sys.argv:
        if a.startswith("--port="):
            port = int(a.split("=", 1)[1])
        elif a.startswith("--host="):
            host = a.split("=", 1)[1]

    url = f"http://localhost:{port}"
    print(f"\n  CostControl en marcha  ->  {url}")
    print("  (deja esta ventana abierta mientras la uses; ciérrala para parar)\n")

    if "--open" in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    app.run(debug="--debug" in sys.argv, host=host, port=port)


if __name__ == "__main__":
    main()
