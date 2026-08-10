# Publicar CostControl online (enlace fijo)

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
- Siempre define `COSTCONTROL_PASSWORD` si la publicas: sin ella, cualquiera con
  el enlace entra.
- Cambia `COSTCONTROL_SECRET` por algo único y privado.
- Es un buen entorno de prueba; para uso serio con varias personas harían falta
  usuarios con permisos y un despliegue endurecido (fuera del alcance actual).
