# CostControl

**Herramienta de control de costes por proyectos y estructuras de gasto.**

CostControl permite importar facturas, albaranes y apuntes contables desde
Excel, asociarlos a centros de coste/beneficio y **repartirlos analíticamente
entre proyectos escribiendo el reparto a mano en lenguaje natural** — la
herramienta traduce ese texto libre a líneas analíticas concretas.

---

## Qué hace

- 📥 **Importación por Excel** de facturas / albaranes / apuntes contables, con
  detección automática de columnas (acepta sinónimos, acentos y mayúsculas).
  Las cuentas y centros que no existan se crean solos.
- 🏗️ **Estructura de gasto**: proyectos, centros de coste/beneficio y cuentas
  contables.
- ✍️ **Reparto analítico en lenguaje natural**: escribes *cómo* quieres repartir
  y CostControl lo traduce. Ejemplos que entiende:

  | Escribes | CostControl reparte |
  |----------|---------------------|
  | `60% PROY-A, 40% PROY-B` | por porcentajes |
  | `a partes iguales entre PROY-A, PROY-B, PROY-C` | a partes iguales |
  | `todo a PROY-A` | 100 % a un proyecto |
  | `1.500 € a PROY-A y el resto a PROY-B` | importe fijo + resto |
  | `por m2: PROY-A 100, PROY-B 300` | ponderado por pesos |
  | `según superficie` | ponderado por un *driver* guardado en cada proyecto |
  | `PROY-A 30%, PROY-B 500 €, resto PROY-C` | mezcla de %, importe y resto |

  Cada reparto muestra una **traducción legible** de lo interpretado y avisa si
  algo no cuadra (queda importe sin repartir, se pasa del total, etc.).
- ⚡ **Reparto masivo**: aplica una misma regla a muchos documentos a la vez
  (filtrando por centro, cuenta, periodo, tipo o estado). Ideal para costes
  indirectos y de estructura.
- 🔁 **Reglas de reparto reutilizables** y **regla por defecto por centro**: los
  documentos que importas de un centro con regla se reparten **automáticamente**.
- 🧾 **Modelo contable real**: IVA (base imponible, cuota y total), ejercicios y
  periodos, y maestro de **terceros** (proveedores/clientes con NIF).
- 📊 **Panel con gráficos** (evolución mensual, coste por proyecto y por centro)
  e **informe analítico** por proyecto (presupuesto vs. imputado, desviación,
  detalle de líneas), por centro y **por cuenta contable**, exportable a Excel.
- 🔎 **Búsqueda y filtros avanzados** en documentos (texto, fechas, importe,
  ejercicio/periodo, centro, cuenta) y **exportación** de la vista filtrada.
- ✋ **Ajuste manual del reparto** línea a línea, con indicador de cuadre en
  vivo (puedes traer al editor lo que traduce el texto y afinarlo a mano).
- 📎 **Adjuntar la factura/albarán** (PDF o imagen) a cada documento.
- 🚫 **Detección de duplicados** al importar (mismo número e importe).
- 💾 **Copia de seguridad** completa en JSON, con **restauración**.
- 🔒 **Acceso por contraseña opcional** con pantalla de login de marca.

## Instalación y arranque

Requiere Python 3.9+.

```bash
pip install -r requirements.txt

python run.py --demo      # carga datos de ejemplo y arranca
# o
python run.py             # arranca en limpio
```

Abre <http://localhost:5000>. Opciones: `--port=8080`, `--debug`.

## Flujo de trabajo típico

1. **Crea o importa** tus proyectos y centros de coste/beneficio
   (`Proyectos`, `Centros`, o `Importar`).
2. **Importa los documentos** (facturas/albaranes/apuntes) desde tu Excel en
   `Importar`. Descarga primero la plantilla si quieres ver el formato.
3. En cada documento pulsa **Repartir**, escribe el reparto a mano y guárdalo.
   Puedes guardar textos frecuentes como **plantillas de reparto**.
4. Consulta el **Informe** y expórtalo a Excel.

## Reparto masivo y automatización

- **Reparto masivo** (`Reparto masivo`): filtra los documentos, selecciona los
  que quieras y aplica una sola regla a todos — cada uno se reparte según su
  propio importe.
- **Regla por defecto por centro** (`Centros`): asigna un texto de reparto a un
  centro y todos los documentos que importes de ese centro quedan repartidos
  automáticamente al importar.
- **Reglas** (`Reglas`): guarda textos de reparto frecuentes como plantillas y
  reutilízalos con un clic en cualquier documento o en el reparto masivo.

## Repartos ponderados con *drivers*

Cada proyecto puede tener *drivers* (claves de reparto) como `superficie`,
`horas`, `unidades`… Al escribir `según superficie` o `por horas`, CostControl
prorratea el importe según esos valores. También puedes dar los pesos en el
propio texto: `por m2: PROY-A 100, PROY-B 300`.

## Estructura del proyecto

```
costcontrol/
  allocation.py   # motor de reparto en lenguaje natural (el núcleo)
  db.py           # acceso a datos (SQLite, stdlib) + migraciones
  importer.py     # importación / exportación Excel (openpyxl) + backup
  charts.py       # gráficos SVG en línea (sin dependencias)
  app.py          # aplicación web (Flask) y rutas
  templates/      # interfaz en español
  static/style.css
run.py            # arranque
seed_demo.py      # datos de demostración
tests/            # pruebas del motor y de la app
```

## Datos

Se guardan en un archivo SQLite local (`costcontrol.db` por defecto; cambia la
ruta con la variable de entorno `COSTCONTROL_DB`). Sin servicios externos. La
base de datos se **migra automáticamente** al arrancar si vienes de una versión
anterior.

## Configuración (variables de entorno)

| Variable | Para qué |
|----------|----------|
| `COSTCONTROL_DB` | Ruta del archivo SQLite (por defecto `costcontrol.db`). |
| `COSTCONTROL_UPLOADS` | Carpeta donde se guardan los adjuntos (por defecto `uploads/`). |
| `COSTCONTROL_PASSWORD` | Si se define, exige contraseña para entrar (pantalla de login). Sin ella, acceso libre. |
| `COSTCONTROL_SECRET` | Clave de sesión de Flask (defínela en producción). |

## Pruebas

```bash
python tests/test_allocation.py   # motor de reparto
python tests/test_app.py          # app completa (rutas, Excel, reparto)
```

## Tecnología

Python + Flask + SQLite + openpyxl. Sin dependencias pesadas ni servicios
externos: se ejecuta en local.
