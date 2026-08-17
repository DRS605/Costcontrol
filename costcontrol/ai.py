"""Intérprete de repartos con IA (opcional).

CostControl funciona **sin conexión** con su motor determinista de reparto. Este
módulo añade, de forma **totalmente opcional**, una capa de "traducción" con IA
que entiende el texto libre por enrevesado que sea y lo reescribe a la sintaxis
canónica que el motor ya sabe evaluar.

Hay **dos proveedores** de IA, y puedes elegir:

* ``local``  → un modelo de IA que corre **en tu propio equipo** con
  `Ollama <https://ollama.com>`_ (o cualquier servidor compatible). Es
  **gratis, sin límites y 100 % privado**: no sale nada a internet. Ideal para
  ti. Requiere instalar Ollama y descargar un modelo pequeño una vez.
* ``anthropic`` → la API de Claude (de pago, muy barata). Rápida y muy capaz,
  pero envía el texto del reparto a Anthropic.

Filosofía de diseño (privacidad primero):

* **Apagado por defecto.** Sin configurar nada, la app es 100 % local con su
  motor determinista.
* **La IA no calcula el dinero.** Solo *traduce* la frase a la mini-sintaxis de
  CostControl; el importe exacto lo calcula el motor con céntimos, y ves la
  traducción para revisarla.
* **Se activa solo cuando hace falta** (modo ``auto``): primero el motor local
  gratis; la IA solo entra si la frase no se ha entendido.

Configuración por variables de entorno:

    COSTCONTROL_AI_PROVIDER  local | anthropic | auto | off   (por defecto auto)
    COSTCONTROL_AI_MODE      off | auto | siempre              (por defecto auto)
    COSTCONTROL_AI_MODEL     modelo a usar (según proveedor)
    COSTCONTROL_AI_URL       URL del servidor local (por defecto Ollama local)
    ANTHROPIC_API_KEY        clave de Claude (activa el proveedor anthropic)
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from typing import List, Optional, Sequence

_MODEL_ANTHROPIC = "claude-haiku-4-5"
_MODEL_LOCAL = "llama3.2"
_URL_LOCAL = "http://localhost:11434"

# Esquema de salida estructurada (proveedor anthropic).
_SCHEMA = {
    "type": "object",
    "properties": {
        "entendido": {"type": "boolean",
                      "description": "true si has traducido el reparto con seguridad."},
        "reparto": {"type": "string",
                    "description": "El reparto reescrito en la sintaxis canónica de "
                                   "CostControl, usando SOLO códigos de proyecto "
                                   "existentes. Cadena vacía si no lo entiendes."},
        "nota": {"type": "string",
                 "description": "Explicación breve, en español, de cómo lo has interpretado."},
    },
    "required": ["entendido", "reparto", "nota"],
    "additionalProperties": False,
}

_SYSTEM = """Eres el traductor de repartos analíticos de CostControl.

Tu ÚNICA tarea es convertir la frase en lenguaje natural del usuario a la
sintaxis canónica de reparto de CostControl. NO calcules importes en euros: solo
reescribe la instrucción. El motor de la aplicación hará las cuentas exactas.

SINTAXIS CANÓNICA (sepáralo todo con comas):
- Porcentaje:            "40% PROY1"
- Importe fijo en euros: "1500 € PROY1"
- Resto (lo que quede):  "resto PROY2"   (o "resto PROY2 y PROY3" para partir)
- Partes iguales:        "a partes iguales entre PROY1, PROY2, PROY3"
- Todo a uno:            "todo PROY1"
- Ponderado por pesos:   "por peso: PROY1 100, PROY2 300"
- Ponderado por driver:  "según superficie"  (usa un driver guardado del proyecto)
- Ponderado por gasto:    "según el gasto de cada proyecto"  (usa el gasto ya
  imputado a cada proyecto; sirve para "en función del % de gasto de cada proyecto")
- Subconjunto por palabra: añade "de los proyectos que contengan finca" para
  limitar el reparto a los proyectos cuyo nombre/código contiene esa palabra.
- Reutilizar una regla:  "como la regla NOMBRE"
- Regla en subconjunto:  "como la regla NOMBRE, solo PROY1 y PROY2"
- Combinar:              "50% como la regla NOMBRE, resto PROY9"

REGLAS IMPORTANTES:
- Usa SIEMPRE los CÓDIGOS de proyecto de la lista que te doy (no los nombres).
  Si el usuario nombra un proyecto por su nombre o de forma aproximada, mapéalo
  al código correcto.
- Pesos relativos: "el doble a A que a B" -> "por peso: A 2, B 1".
- Si el usuario menciona un criterio (superficie, horas, m2...) que encaja con un
  driver disponible, usa "según <driver>".
- Si no puedes traducirlo con seguridad, pon entendido=false y reparto="".
- No inventes proyectos ni reglas que no estén en las listas."""

_JSON_HINT = ('Responde ÚNICAMENTE con un objeto JSON con esta forma exacta, sin '
              'texto adicional:\n'
              '{"entendido": true|false, "reparto": "<sintaxis canónica>", '
              '"nota": "<explicación breve>"}')


# --------------------------------------------------------------------------
# Configuración / detección de proveedor
# --------------------------------------------------------------------------

def _key() -> str:
    return (os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("COSTCONTROL_AI_KEY") or "").strip()


def _local_url() -> str:
    return (os.environ.get("COSTCONTROL_AI_URL") or _URL_LOCAL).rstrip("/")


def _sdk_present() -> bool:
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


def provider() -> Optional[str]:
    """Devuelve 'local' | 'anthropic' | None según la configuración."""
    p = (os.environ.get("COSTCONTROL_AI_PROVIDER") or "").strip().lower()
    if p in ("off", "no", "0", "false"):
        return None
    if p in ("local", "ollama", "lmstudio", "openai-local"):
        return "local"
    if p in ("anthropic", "claude"):
        return "anthropic" if (_key() and _sdk_present()) else None
    # auto: prioriza lo que esté configurado. Local primero si se marcó URL.
    if os.environ.get("COSTCONTROL_AI_URL"):
        return "local"
    if _key() and _sdk_present():
        return "anthropic"
    return None


def _mode() -> str:
    m = (os.environ.get("COSTCONTROL_AI_MODE") or "").strip().lower()
    if m in ("off", "no", "0", "false"):
        return "off"
    if m in ("siempre", "always", "1", "true"):
        return "siempre"
    return "auto"


def mode() -> str:
    """'off' | 'auto' | 'siempre' — cómo debe usarse la IA en el flujo."""
    return _mode() if provider() else "off"


def _model() -> str:
    env = os.environ.get("COSTCONTROL_AI_MODEL")
    if env:
        return env
    return _MODEL_LOCAL if provider() == "local" else _MODEL_ANTHROPIC


def _local_reachable(timeout=0.4) -> bool:
    """Comprueba rápido si el servidor local (Ollama) responde."""
    url = _local_url()
    try:
        host = url.split("://", 1)[-1]
        host, _, port = host.partition(":")
        port = int(port or 11434)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def available() -> bool:
    """True si la IA está configurada y activa."""
    prov = provider()
    if not prov or _mode() == "off":
        return False
    if prov == "anthropic":
        return bool(_key()) and _sdk_present()
    if prov == "local":
        return True   # configurado; la conexión se comprueba al usarla
    return False


def status() -> dict:
    """Estado legible para la pantalla de Ajustes."""
    prov = provider()
    if not prov:
        return {"activa": False, "proveedor": None,
                "detalle": "IA desactivada. La app funciona 100 % en local."}
    if prov == "anthropic":
        if not _sdk_present():
            return {"activa": False, "proveedor": "anthropic",
                    "detalle": "Falta la librería 'anthropic' (pip install anthropic)."}
        if not _key():
            return {"activa": False, "proveedor": "anthropic",
                    "detalle": "No hay clave de API configurada."}
        return {"activa": True, "proveedor": "anthropic", "modo": _mode(),
                "modelo": _model(),
                "detalle": f"IA de Claude activa (modo {_mode()}). Servicio de pago."}
    # local
    reach = _local_reachable()
    return {"activa": True, "proveedor": "local", "modo": _mode(),
            "modelo": _model(), "url": _local_url(), "conectado": reach,
            "detalle": (f"IA local activa (modo {_mode()}) — gratis y privada."
                        if reach else
                        f"IA local configurada, pero no responde en {_local_url()}. "
                        "¿Está Ollama en marcha?")}


# --------------------------------------------------------------------------
# Traducción
# --------------------------------------------------------------------------

def _proyectos_desc(projects: Sequence) -> str:
    filas = []
    for p in projects:
        drivers = ""
        if getattr(p, "drivers", None):
            ds = ", ".join(f"{k}={v}" for k, v in p.drivers.items())
            if ds:
                drivers = f"  [drivers: {ds}]"
        filas.append(f"- {p.codigo}: {p.nombre or '(sin nombre)'}{drivers}")
    return "\n".join(filas) or "(no hay proyectos)"


def _build_prompt(total, texto, projects, rules) -> str:
    reglas_txt = ""
    if rules:
        nombres = list(rules.keys()) if isinstance(rules, dict) else [r["nombre"] for r in rules]
        if nombres:
            reglas_txt = "\n\nReglas guardadas disponibles (por nombre):\n- " + "\n- ".join(nombres)
    return (
        f"Importe total del documento: {total} €\n\n"
        f"Proyectos disponibles (usa estos CÓDIGOS):\n{_proyectos_desc(projects)}"
        f"{reglas_txt}\n\n"
        f'Frase del usuario a traducir:\n\"\"\"{texto}\"\"\"'
    )


def interpretar(total, texto: str, projects: Sequence,
                rules: Optional[dict] = None) -> dict:
    """Traduce `texto` a la sintaxis canónica de reparto usando IA.

    Devuelve {ok, reparto, nota, error}. Nunca lanza excepción: ante cualquier
    fallo devuelve ok=False con `error`.
    """
    prov = provider()
    if not prov or _mode() == "off":
        return {"ok": False, "reparto": "", "nota": "", "error": "IA no disponible."}
    texto = (texto or "").strip()
    if not texto:
        return {"ok": False, "reparto": "", "nota": "", "error": "Texto vacío."}

    prompt = _build_prompt(total, texto, projects, rules)
    if prov == "local":
        return _interpretar_local(prompt)
    return _interpretar_anthropic(prompt)


def _finalize(data: Optional[dict]) -> dict:
    if data is None:
        return {"ok": False, "reparto": "", "nota": "",
                "error": "La IA no devolvió un resultado interpretable."}
    entendido = bool(data.get("entendido"))
    reparto = (data.get("reparto") or "").strip()
    nota = (data.get("nota") or "").strip()
    if not entendido or not reparto:
        return {"ok": False, "reparto": "", "nota": nota,
                "error": nota or "La IA no ha entendido el reparto."}
    return {"ok": True, "reparto": reparto, "nota": nota, "error": ""}


def _interpretar_anthropic(prompt: str) -> dict:
    try:
        import anthropic
    except Exception:
        return {"ok": False, "reparto": "", "nota": "", "error": "Falta la librería 'anthropic'."}
    try:
        client = anthropic.Anthropic(api_key=_key())
        msg = client.messages.create(
            model=_model(),
            max_tokens=400,
            # El prompt de sistema es fijo -> caché de prompt: en llamadas
            # seguidas su coste de entrada baja ~10x (clave para el margen al
            # facturar el producto).
            system=[{"type": "text", "text": _SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
        return _finalize(_extract_json_anthropic(msg))
    except anthropic.AuthenticationError:
        return {"ok": False, "reparto": "", "nota": "", "error": "La clave de API no es válida."}
    except anthropic.RateLimitError:
        return {"ok": False, "reparto": "", "nota": "",
                "error": "Límite de uso de la API alcanzado; inténtalo más tarde."}
    except anthropic.APIConnectionError:
        return {"ok": False, "reparto": "", "nota": "", "error": "No hay conexión con la API."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reparto": "", "nota": "", "error": f"Error de IA: {e}"}


def _interpretar_local(prompt: str) -> dict:
    """Llama a un servidor local compatible con Ollama (/api/chat)."""
    url = _local_url() + "/api/chat"
    body = json.dumps({
        "model": _model(),
        "messages": [
            {"role": "system", "content": _SYSTEM + "\n\n" + _JSON_HINT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    # los servidores locales no pasan por el proxy: abrir sin proxy
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=90) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"ok": False, "reparto": "", "nota": "",
                "error": f"No se pudo conectar con la IA local en {_local_url()} "
                         f"(¿Ollama en marcha?). {e}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reparto": "", "nota": "", "error": f"Error de IA local: {e}"}
    content = (((payload or {}).get("message") or {}).get("content") or "").strip()
    return _finalize(_parse_json_text(content))


def _extract_json_anthropic(msg) -> Optional[dict]:
    parsed = getattr(msg, "parsed", None)
    if isinstance(parsed, dict):
        return parsed
    fragments: List[str] = []
    for block in getattr(msg, "content", []) or []:
        txt = getattr(block, "text", None)
        if txt:
            fragments.append(txt)
    return _parse_json_text("".join(fragments))


def _parse_json_text(raw: str) -> Optional[dict]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        i, j = raw.find("{"), raw.rfind("}")
        if 0 <= i < j:
            try:
                return json.loads(raw[i:j + 1])
            except Exception:
                return None
    return None
