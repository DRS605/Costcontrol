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
  | `la mitad a PROY-A, un tercio a PROY-B` | fracciones escritas en palabras |
  | `60% a PROY-A, el resto a los demás` | el resto entre los proyectos no asignados |
  | `20% a cada uno` · `300 € a cada proyecto` | misma cifra a cada proyecto |
  | `mitad y mitad entre PROY-A y PROY-B` | a partes iguales (coloquial) |
  | `por m2: PROY-A 100, PROY-B 300` | ponderado por pesos |
  | `el doble a PROY-A que a PROY-B` | pesos relativos (2 : 1) |
  | `según superficie` · `proporcional a horas` | ponderado por un *driver* guardado |
  | `PROY-A 30%, PROY-B 500 €, resto PROY-C` | mezcla de %, importe y resto |
  | `como la regla Obra estándar` | reutiliza una **regla guardada** por su nombre |
  | `según la regla Obra, pero solo PROY-A y PROY-B` | **reescala** la regla a un subconjunto |
  | `50% como la regla Obra, resto a PROY-Z` | **combina** una regla con reparto directo |

  Las reglas se guardan una vez (sección *Reglas*) y se invocan por nombre con
  `como la regla NOMBRE` / `según la regla NOMBRE` en cualquier documento; se
  pueden **reescalar a un subconjunto** (`… solo A y B`, o `… excepto C`),
  **combinar** con reparto directo (`50% como la regla X, resto a Z`;
  `1000 € a Z, resto como la regla X`), **anidar** (una regla que referencia a
  otra) y el motor detecta ciclos.

  Cada reparto muestra una **traducción legible** de lo interpretado y avisa si
  algo no cuadra (queda importe sin repartir, se pasa del total, etc.).
- 🤖 **Intérprete con IA (opcional).** El motor anterior funciona **100 % en
  local**. Si además activas la IA, CostControl entiende frases mucho más libres
  —*«la mitad para la nave y el resto repártelo entre los demás según las horas»*—
  traduciéndolas a su sintaxis exacta antes de calcular. Puedes usar una **IA
  local gratuita y privada** (Ollama, no sale nada de tu equipo) o la **API de
  Claude** (de pago). **La IA solo traduce la frase; el importe lo calcula siempre
  el motor local** con aritmética de céntimos, y ves la traducción para revisarla
  (ver *IA de repartos*).
- ⚡ **Reparto masivo**: aplica una misma regla a muchos documentos a la vez
  (filtrando por centro, cuenta, periodo, tipo o estado). Ideal para costes
  indirectos y de estructura.
- 🔁 **Reglas de reparto reutilizables** y **regla por defecto por centro**: los
  documentos que importas de un centro con regla se reparten **automáticamente**.
- 🧾 **Modelo contable real**: IVA (base imponible, cuota y total), ejercicios y
  periodos, y maestro de **terceros** (proveedores/clientes con NIF).
- 📊 **Panel con gráficos** (evolución mensual, coste por proyecto y por centro,
  y **comparativa año vs. año anterior** con variación) e **informe analítico**
  por proyecto (presupuesto vs. imputado, desviación, detalle de líneas), por
  centro y **por cuenta contable**, exportable a Excel.
- 🔎 **Búsqueda y filtros avanzados** en documentos (texto, fechas, importe,
  ejercicio/periodo, centro, cuenta) y **exportación** de la vista filtrada.
- 🎯 **Presupuestos por proyecto y por centro**, por periodo (mensual; el anual
  es la suma), con **seguimiento y alertas de desviación** (semáforo
  verde/ámbar/rojo) en la página de presupuestos y en el panel. El de proyecto
  se compara con lo imputado por reparto; el de centro, con el importe real de
  sus documentos.
- 🔒 **Cierre de periodo**: cierra un mes y sus documentos quedan bloqueados (no
  se pueden crear, editar, borrar, repartir ni importar); reversible.
- ✋ **Ajuste manual del reparto** línea a línea, con indicador de cuadre en
  vivo (puedes traer al editor lo que traduce el texto y afinarlo a mano).
- 📎 **Adjuntar la factura/albarán** (PDF o imagen) a cada documento.
- 🚫 **Detección de duplicados** al importar (mismo número e importe).
- 💾 **Copia de seguridad** completa en JSON, con **restauración**.
- 🔒 **Acceso por contraseña opcional** con pantalla de login de marca.

## Instalación y arranque

**Forma fácil (doble clic, en tu portátil):** descarga el proyecto y abre el
lanzador de tu sistema — `iniciar-windows.bat`, `iniciar-mac.command` o
`iniciar-linux.sh`. Prepara todo y abre el navegador solo. Guía detallada en
[`RUN_LOCAL.md`](RUN_LOCAL.md).

**Forma manual** (requiere Python 3.9+):

```bash
pip install -r requirements.txt

python run.py --demo      # carga datos de ejemplo y arranca
# o
python run.py             # arranca en limpio
```

Abre <http://localhost:5000>. Opciones: `--host=127.0.0.1` (solo este equipo),
`--open` (abre el navegador), `--port=8080`, `--debug`.

Para publicarla online con enlace fijo, ver [`DEPLOY.md`](DEPLOY.md).

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
  ai.py           # intérprete de repartos con IA (opcional, Claude)
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
| `COSTCONTROL_AI_PROVIDER` | `local` (IA gratis y privada con Ollama), `anthropic` (Claude, de pago), `auto` (por defecto) u `off`. |
| `COSTCONTROL_AI_MODE` | `auto` (usa la IA solo si el motor local no entiende la frase), `siempre` u `off`. |
| `COSTCONTROL_AI_MODEL` | Modelo a usar (por defecto `llama3.2` en local, `claude-haiku-4-5` en Anthropic). |
| `COSTCONTROL_AI_URL` | URL del servidor local (por defecto `http://localhost:11434`, el de Ollama). |
| `ANTHROPIC_API_KEY` (o `COSTCONTROL_AI_KEY`) | Clave de Claude; activa el proveedor `anthropic`. |

### IA de repartos: gratis y privada, o en la nube

El motor determinista ya entiende la mayoría de repartos **sin conexión ni IA**. Si
quieres además comprensión de frases muy libres, hay dos formas:

**🆓 Opción gratis y privada (recomendada) — IA local con Ollama.** Corre un modelo
de IA en tu propio equipo; es gratis, sin límites y **no envía nada a internet**.

1. Instala [Ollama](https://ollama.com) (Windows/Mac/Linux).
2. Descarga un modelo pequeño: `ollama pull llama3.2`.
3. Arranca CostControl con `COSTCONTROL_AI_PROVIDER=local`.

**☁️ Opción en la nube — Claude (Anthropic).** Más potente, de pago (céntimos por
reparto). `pip install anthropic`, consigue tu clave y arranca con
`ANTHROPIC_API_KEY=tu-clave`.

**Privacidad:** sin IA, o con la IA **local**, nada sale de tu equipo. Con la IA de
Claude solo se envía **el texto del reparto** y los **códigos/nombres de proyecto**;
nunca importes, terceros ni la base de datos. En modo `auto`, la IA solo se usa
cuando el motor local no entiende la frase. Revisa el estado en **Ajustes**.

### Como producto (SaaS) — coste de la IA

Si vendes CostControl como servicio, configura **una sola** `ANTHROPIC_API_KEY` en el
servidor: tus clientes no ven ni configuran nada. El coste de la IA es **marginal**:

- La tarea (traducir una frase corta) es diminuta: ≈ 1.000 tokens de entrada y 80 de
  salida. Con `claude-haiku-4-5` sale a **≈ 0,15 céntimos por reparto**.
- El **modo `auto`** (por defecto) solo llama a la IA cuando el motor local no entiende
  la frase, así que la mayoría de repartos **no cuestan nada**.
- El prompt de sistema va con **caché de prompt**, bajando aún más el coste en ráfagas.

Estimación por cliente y mes: un uso intenso (varios cientos de traducciones por IA)
ronda **0,50–1 € de coste**, frente a una cuota de 50–75 €. Es **~1–2 % de COGS**. Para
más calidad puedes subir a `COSTCONTROL_AI_MODEL=claude-sonnet-4-6` (≈ 3× coste, sigue
siendo trivial). A gran escala (cientos de clientes) puedes autohospedar el proveedor
`local` en tu servidor y dejar el coste por reparto en cero.

## Pruebas

```bash
python tests/test_allocation.py   # motor de reparto
python tests/test_app.py          # app completa (rutas, Excel, reparto)
```

## Tecnología

Python + Flask + SQLite + openpyxl. Sin dependencias pesadas ni servicios
externos: se ejecuta en local.
