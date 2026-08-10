# Usar CostControl en tu portátil (local y privado)

Los datos se quedan **solo en tu portátil**: no suben a internet. La app se abre
en el navegador en `http://localhost:5000` y solo es accesible desde este equipo.

## 1. Descarga el proyecto
En GitHub (página del repositorio) pulsa el botón verde **Code → Download ZIP**
y **descomprime** el archivo. Tendrás una carpeta `Costcontrol`.

*(Si usas git: `git clone ...` y `git checkout claude/costcontrol-expense-management-5bx7hy`.)*

## 2. Necesitas Python
Si no lo tienes, instálalo desde <https://www.python.org/downloads/>.
- En **Windows**, durante la instalación marca la casilla **“Add Python to PATH”**.
- En **macOS** y **Linux** suele venir de serie; si no, instálalo desde ahí.

## 3. Arranca con doble clic
Dentro de la carpeta, abre el archivo según tu sistema:

| Sistema | Archivo |
|---------|---------|
| **Windows** | `iniciar-windows.bat` |
| **macOS** | `iniciar-mac.command` |
| **Linux** | `iniciar-linux.sh` |

La primera vez tarda un minuto (prepara todo). Después se abre solo el navegador
con CostControl. **Deja abierta** la ventana negra mientras la uses.

### Si no se abre con doble clic
- **macOS**: la primera vez, haz **clic derecho → Abrir** (macOS pregunta por ser
  de un desarrollador no identificado; acepta **Abrir**). Si aun así no va, abre
  la app **Terminal**, escribe `bash `, arrastra el archivo `iniciar-mac.command`
  a la ventana y pulsa Intro.
- **Linux**: en el terminal, dentro de la carpeta: `bash iniciar-linux.sh`.

## 4. Para pararla
Cierra la ventana negra (o pulsa `Ctrl + C` en ella). La próxima vez, doble clic
otra vez — tus datos siguen ahí.

## 5. Verla en el móvil por Wi-Fi (opcional)
Por defecto solo se ve en el portátil (lo más privado). Si además quieres abrirla
en el móvil estando en la **misma Wi-Fi**:
1. Edita el lanzador y cambia `--host=127.0.0.1` por `--host=0.0.0.0`.
2. Averigua la IP del portátil (Windows: `ipconfig`; macOS/Linux: `ifconfig` o
   `ip a`) — algo como `192.168.1.23`.
3. En el móvil abre `http://192.168.1.23:5000`.

## Notas
- Tus datos se guardan en el archivo `costcontrol.db` dentro de la carpeta. Para
  hacer copia, guarda ese archivo (o usa *Informe → Copia de seguridad*).
- Para empezar con datos de ejemplo, borra `costcontrol.db` (si existe) y arranca
  una vez con `python run.py --demo` desde el terminal; luego usa el lanzador
  normal.
