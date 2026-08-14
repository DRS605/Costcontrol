"""Configuración de Gunicorn para CostControl en producción.

Uso:  gunicorn -c gunicorn.conf.py wsgi:application
"""

import os

# Escucha en el puerto que asigne el hosting (Render define PORT).
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Nº de procesos. Con SQLite en WAL varios workers conviven bien. Ajustable con
# WEB_CONCURRENCY; por defecto un valor moderado (SQLite serializa escrituras).
workers = int(os.environ.get("WEB_CONCURRENCY", "3"))
threads = int(os.environ.get("GUNICORN_THREADS", "2"))

timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 5

# Reinicia workers cada cierto nº de peticiones para evitar fugas de memoria.
max_requests = 1000
max_requests_jitter = 100

accesslog = "-"     # a stdout (lo recoge el hosting)
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
