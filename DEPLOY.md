# Publicar CostControl online (enlace fijo)

> ¿Vas a **venderlo como servicio** a varios clientes? Ve directo a
> [**Despliegue como producto (SaaS)**](#despliegue-como-producto-saas) más abajo.

Guía para tener un enlace permanente que puedas abrir desde el móvil.

Recomendación: **PythonAnywhere** (plan gratuito). ¿Por qué? Porque **guarda los
datos de forma permanente** (el archivo de base de datos y los adjuntos no se
borran), no pide tarjeta y se configura desde el navegador. Al final hay una
nota sobre Render, más fácil de desplegar pero que **borra los datos** cada vez
que se reinicia (sirve para una demo rápida, no para usarla de verdad).

> ⚠️ La app quedará accesible por internet. **Pon una contraseña** (variable
> `COSTCONTROL_PASSWORD`) y cambia `COSTCONTROL_SECRET` por una frase larga.

---

## Opción A — PythonAnywhere (recomendada, datos permanentes)

1. **Crea una cuenta gratis** en <https://www.pythonanywhere.com> (plan
   *Beginner*, gratuito).

2. Menú **Consoles → Bash**. En la consola, descarga el proyecto:
   ```bash
   git clone https://github.com/DRS605/Costcontrol.git
   cd Costcontrol
   git checkout claude/costcontrol-expense-management-5bx7hy
   ```

3. Instala las dependencias:
   ```bash
   pip install --user Flask openpyxl
   ```

4. Menú **Web → Add a new web app**:
   - *Manual configuration* (no "Flask").
   - Elige la versión de **Python 3** que te ofrezca (p.ej. 3.10).

5. En la página del *Web app*, sección **Code**, pon (sustituye `TUUSUARIO`):
   - **Source code:** `/home/TUUSUARIO/Costcontrol`
   - **Working directory:** `/home/TUUSUARIO/Costcontrol`

6. En **Code → WSGI configuration file** haz clic para editarlo, **borra todo**
   su contenido y pega esto (cambiando las 3 líneas marcadas):
   ```python
   import os, sys
   project = '/home/TUUSUARIO/Costcontrol'        # <-- tu usuario
   sys.path.insert(0, project)

   os.environ['COSTCONTROL_SECRET']   = 'una-frase-larga-y-secreta'   # <-- cámbiala
   os.environ['COSTCONTROL_PASSWORD'] = 'tu-contraseña'               # <-- ponla

   from costcontrol import db
   db.init_db()
   from costcontrol.app import app as application
   ```
   Guarda (**Save**).

7. (Opcional pero recomendado) sección **Static files**, añade:
   - URL: `/static/`
   - Directory: `/home/TUUSUARIO/Costcontrol/costcontrol/static`

8. Pulsa el botón verde **Reload**. Abre en el móvil:
   **`https://TUUSUARIO.pythonanywhere.com`**
   Te pedirá la contraseña que pusiste y ya está.

### Cargar datos de ejemplo (opcional)
En la consola Bash, antes o después:
```bash
cd ~/Costcontrol && python seed_demo.py
```
Luego **Reload** en la pestaña Web.

### Actualizar a una versión nueva
```bash
cd ~/Costcontrol && git pull
```
y pulsa **Reload**. Los datos se conservan.

---

## Opción B — Render (más fácil de desplegar, pero borra los datos)

Sirve para una demo rápida; **la base de datos se reinicia** en cada
redespliegue (Render gratuito no guarda archivos).

1. Cuenta gratis en <https://render.com>, conecta tu GitHub.
2. **New → Web Service**, elige el repo `DRS605/Costcontrol` y la rama.
3. Configuración:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn wsgi:application`
4. En **Environment** añade:
   - `COSTCONTROL_SECRET` = una frase larga
   - `COSTCONTROL_PASSWORD` = tu contraseña
5. Crea el servicio. Te dará un enlace `https://costcontrol-xxxx.onrender.com`.
   (En el plan gratis, tras un rato inactivo tarda ~30 s en "despertar".)

---

## Notas de seguridad
- Siempre define `COSTCONTROL_PASSWORD` si la publicas en modo monousuario: sin
  ella, cualquiera con el enlace entra.
- Cambia `COSTCONTROL_SECRET` por algo único y privado.

---

# Despliegue como producto (SaaS)

Para ofrecer CostControl a **varios clientes de pago** (cada uno con su cuenta,
su equipo y sus datos aislados). Recuerda: CostControl usa ficheros SQLite, así
que necesita **disco persistente** y **una sola instancia** (escala en vertical:
más CPU/RAM). Es más que suficiente para un SaaS pequeño/mediano.

## Variables de entorno de producción

| Variable | Valor | Para qué |
|----------|-------|----------|
| `COSTCONTROL_MULTIUSER` | `1` | Activa cuentas, equipos y datos aislados por empresa. |
| `COSTCONTROL_SECURE` | `1` | Cookies seguras + confianza en el proxy HTTPS (Render/nginx). |
| `COSTCONTROL_SECRET` | *(frase larga y secreta)* | Firma de sesiones. **Imprescindible.** |
| `COSTCONTROL_DATA_DIR` | ruta del disco persistente (p. ej. `/var/data`) | Dónde viven las BBDD de cada empresa. |
| `COSTCONTROL_UPLOADS` | p. ej. `/var/data/uploads` | Adjuntos (también en el disco persistente). |
| `ANTHROPIC_API_KEY` | *(tu clave)* | IA de reparto **una sola vez en el servidor**; los clientes no configuran nada. |
| `COSTCONTROL_AI_MODE` | `auto` | La IA solo se usa si el motor local no entiende la frase (mínimo coste). |

> El coste de la IA es marginal (~0,15 cént/reparto, ~1–2 % de una cuota de
> 50–75 €). Ver *Como producto (SaaS)* en el `README.md`.

## Opción 1 — Render con Blueprint (rápida)

El repo incluye [`render.yaml`](render.yaml) ya preparado (disco persistente de
5 GB, health check, HTTPS, variables). Pasos:

1. En <https://render.com>: **New → Blueprint**, elige el repo y la rama.
2. Render lee `render.yaml` y crea el servicio con su disco.
3. En el panel del servicio, pon tu **`ANTHROPIC_API_KEY`** (está marcada para
   introducirla a mano). El resto se rellena solo.
4. **Apply**. Te da un enlace `https://costcontrol-xxxx.onrender.com` con HTTPS.
   El primer usuario que entre crea su empresa en `/registro`.

> El plan con disco persistente es de pago (el gratuito borra los datos). Es el
> requisito para usarlo de verdad.

## Opción 2 — VPS propio (control total)

En un servidor Ubuntu con tu dominio:

```bash
git clone https://github.com/DRS605/Costcontrol.git && cd Costcontrol
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt anthropic

# variables (mejor en un fichero /etc/costcontrol.env y systemd EnvironmentFile)
export COSTCONTROL_MULTIUSER=1 COSTCONTROL_SECURE=1
export COSTCONTROL_SECRET="pon-aqui-una-frase-larga-y-secreta"
export COSTCONTROL_DATA_DIR=/var/lib/costcontrol
export COSTCONTROL_UPLOADS=/var/lib/costcontrol/uploads
export ANTHROPIC_API_KEY="tu-clave"

gunicorn -c gunicorn.conf.py wsgi:application   # escucha en $PORT (def. 8000)
```

Delante, un **reverse proxy con HTTPS**. Lo más fácil es **Caddy** (certificado
automático). `/etc/caddy/Caddyfile`:

```
tu-dominio.com {
    reverse_proxy 127.0.0.1:8000
}
```

Para que arranque solo, un servicio **systemd** que ejecute el `gunicorn` de
arriba con `EnvironmentFile=/etc/costcontrol.env`.

## Copias de seguridad automáticas

Todos los datos están en `COSTCONTROL_DATA_DIR`. El repo trae
[`scripts/backup_data.sh`](scripts/backup_data.sh), que empaqueta ese directorio
con fecha y conserva las últimas N copias. Prográmalo a diario con cron:

```cron
30 3 * * * COSTCONTROL_DATA_DIR=/var/lib/costcontrol /ruta/Costcontrol/scripts/backup_data.sh /var/backups 14 >> /var/log/costcontrol-backup.log 2>&1
```

En Render, ejecuta ese script como *Cron Job* apuntando al mismo disco, o
descarga periódicamente la copia JSON de cada empresa. Guarda las copias
**fuera del servidor** (otro disco o almacenamiento) para estar tranquilo.

## Salud y actualización

- **Health check:** `GET /salud` responde `{"ok": true, ...}` sin login (Render
  ya lo usa vía `render.yaml`).
- **Actualizar:** `git pull` y reinicia el servicio. Las bases de datos se
  **migran solas** al arrancar y los datos se conservan.

## Recuperación de contraseña

- **Con email (recomendado):** define `COSTCONTROL_SMTP_HOST`, `_PORT`, `_USER`,
  `_PASSWORD`, `_FROM`. Entonces `/recuperar` envía un enlace al usuario.
- **Sin email:** la restablece el **administrador** de la empresa (Ajustes →
  Equipo) o tú desde la consola: `python manage.py reset-password email@cliente`.

## Páginas legales

Rellena tus datos con `COSTCONTROL_EMPRESA`, `COSTCONTROL_CIF`,
`COSTCONTROL_DOMICILIO`, `COSTCONTROL_EMAIL_CONTACTO`, `COSTCONTROL_DOMINIO`.
Las páginas `/privacidad`, `/condiciones` y `/aviso-legal` son **plantillas
orientativas**: revísalas con un asesor legal antes de operar.

## Checklist antes de dar acceso a un cliente

- [ ] `COSTCONTROL_SECRET` puesto a una frase larga y única.
- [ ] `COSTCONTROL_SECURE=1` y el sitio abre por **https://**.
- [ ] `COSTCONTROL_DATA_DIR` en disco **persistente** (no efímero).
- [ ] `ANTHROPIC_API_KEY` puesta (si quieres la IA) — solo en el servidor.
- [ ] Datos legales (`COSTCONTROL_EMPRESA`, `_CIF`, …) y páginas legales revisadas.
- [ ] Recuperación de contraseña resuelta (SMTP configurado o proceso por consola claro).
- [ ] Copia de seguridad diaria programada y probada (restaura una para verificar).
- [ ] Entra en `/registro`, crea tu empresa y comprueba el flujo completo.
