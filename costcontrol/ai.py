"""Intérprete de repartos con IA (opcional).

CostControl funciona **sin conexión** con su motor determinista de reparto. Este
módulo añade, de forma **totalmente opcional**, una capa de "traducción" con IA
(Claude) que entiende el texto libre por enrevesado que sea y lo reescribe a la
sintaxis canónica que el motor ya sabe evaluar.

Filosofía de diseño (importante para la privacidad):

* **Apagado por defecto.** Si no hay clave de API, este módulo no hace nada y la
  app sigue siendo 100 % local, como siempre.
* **La IA no calcula el dinero.** Solo *traduce* la frase a la mini-sintaxis de
  CostControl (p. ej. "40% PROY1, resto PROY2"). El importe exacto lo sigue
  calculando el motor determinista con aritmética de céntimos, y el usuario ve
  la traducción para revisarla y editarla.
* **Se activa solo cuando hace falta.** El flujo normal intenta primero el motor
  gratis/offline; solo llama a la IA si la frase no se ha entendido (modo
  ``auto``), minimizando el coste y lo que sale del equipo.

Configuración por variables de entorno:

    ANTHROPIC_API_KEY   clave de API de Anthropic (o COSTCONTROL_AI_KEY).
    COSTCONTROL_AI_MODE off | auto | siempre   (por defecto: auto si hay clave)
    COSTCONTROL_AI_MODEL modelo (por defecto claude-haiku-4-5, rápido y barato)
"""

from __future__ import annotations

import json
import os
from typing import List, Optional, Sequence

_MODEL_DEFAULT = "claude-haiku-4-5"

# Esquema de salida estructurada: la IA devuelve la frase canónica y una nota.
_SCHEMA = {
    "type": "object",
    "properties": {
        "entendido": {
            "type": "boolean",
            "description": "true si has podido traducir el reparto con seguridad.",
        },
        "reparto": {
            "type": "string",
            "description": (
                "El reparto reescrito en la sintaxis canónica de CostControl, "
                "usando SOLO códigos de proyecto existentes. Cadena vacía si no "
                "lo entiendes."
            ),
        },
        "nota": {
            "type": "string",
            "description": "Explicación breve, en español, de cómo lo has interpretado.",
        },
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
- Reutilizar una regla:  "como la regla NOMBRE"
- Regla en subconjunto:  "como la regla NOMBRE, solo PROY1 y PROY2"
- Combinar:              "50% como la regla NOMBRE, resto PROY9"

REGLAS IMPORTANTES:
- Usa SIEMPRE los CÓDIGOS de proyecto de la lista que te doy (no los nombres).
  Si el usuario nombra un proyecto por su nombre o de forma aproximada, mapéalo
  al código correcto.
- Pesos relativos: "el doble a A que a B" -> "por peso: A 2, B 1";
  "la mitad a C" respecto a otro -> ajusta los pesos (C 1, otro 2), etc.
- Si el usuario menciona un criterio (superficie, horas, m2, unidades...) que
  encaja con un driver disponible, usa "según <driver>".
- Si no puedes traducirlo con seguridad, pon entendido=false y reparto="".
- No inventes proyectos ni reglas que no estén en las listas."""


def _key() -> str:
    return (os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("COSTCONTROL_AI_KEY")
            or "").strip()


def _mode() -> str:
    m = (os.environ.get("COSTCONTROL_AI_MODE") or "").strip().lower()
    if m in ("off", "no", "0", "false"):
        return "off"
    if m in ("siempre", "always", "1", "true"):
        return "siempre"
    if m in ("auto", ""):
        return "auto" if _key() else "off"
    return "auto" if _key() else "off"


def available() -> bool:
    """True si la IA está configurada y activa (hay clave y el modo no es off)."""
    return bool(_key()) and _mode() != "off" and _sdk_present()


def mode() -> str:
    """'off' | 'auto' | 'siempre' — cómo debe usarse la IA en el flujo."""
    return _mode() if _sdk_present() else "off"


def _sdk_present() -> bool:
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


def status() -> dict:
    """Estado legible para mostrar en la interfaz de ajustes."""
    if not _sdk_present():
        return {"activa": False, "motivo": "sdk",
                "detalle": "Falta la librería 'anthropic' (pip install anthropic)."}
    if not _key():
        return {"activa": False, "motivo": "sin_clave",
                "detalle": "No hay clave de API configurada."}
    if _mode() == "off":
        return {"activa": False, "motivo": "desactivada",
                "detalle": "Desactivada por COSTCONTROL_AI_MODE=off."}
    return {"activa": True, "motivo": "ok", "modo": _mode(),
            "modelo": os.environ.get("COSTCONTROL_AI_MODEL", _MODEL_DEFAULT),
            "detalle": f"IA activa (modo {_mode()})."}


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


def interpretar(total, texto: str, projects: Sequence,
                rules: Optional[dict] = None) -> dict:
    """Traduce `texto` a la sintaxis canónica de reparto usando Claude.

    Devuelve un dict: {ok, reparto, nota, error}. `reparto` es la cadena canónica
    lista para pasar al motor determinista. Nunca lanza excepción: ante cualquier
    fallo (sin clave, sin red, error de la API) devuelve ok=False con `error`.
    """
    if not available():
        return {"ok": False, "reparto": "", "nota": "", "error": "IA no disponible."}
    texto = (texto or "").strip()
    if not texto:
        return {"ok": False, "reparto": "", "nota": "", "error": "Texto vacío."}

    try:
        import anthropic
    except Exception:
        return {"ok": False, "reparto": "", "nota": "", "error": "Falta la librería 'anthropic'."}

    model = os.environ.get("COSTCONTROL_AI_MODEL", _MODEL_DEFAULT)
    reglas_txt = ""
    if rules:
        nombres = list(rules.keys()) if isinstance(rules, dict) else [r["nombre"] for r in rules]
        if nombres:
            reglas_txt = "\n\nReglas guardadas disponibles (por nombre):\n- " + "\n- ".join(nombres)

    prompt = (
        f"Importe total del documento: {total} €\n\n"
        f"Proyectos disponibles (usa estos CÓDIGOS):\n{_proyectos_desc(projects)}"
        f"{reglas_txt}\n\n"
        f'Frase del usuario a traducir:\n"""{texto}"""'
    )

    try:
        client = anthropic.Anthropic(api_key=_key())
        msg = client.messages.create(
            model=model,
            max_tokens=400,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
        data = _extract_json(msg)
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
    except anthropic.AuthenticationError:
        return {"ok": False, "reparto": "", "nota": "",
                "error": "La clave de API no es válida."}
    except anthropic.RateLimitError:
        return {"ok": False, "reparto": "", "nota": "",
                "error": "Límite de uso de la API alcanzado; inténtalo más tarde."}
    except anthropic.APIConnectionError:
        return {"ok": False, "reparto": "", "nota": "",
                "error": "No hay conexión con la API (¿sin internet?)."}
    except Exception as e:  # noqa: BLE001 — nunca debe tumbar la app
        return {"ok": False, "reparto": "", "nota": "", "error": f"Error de IA: {e}"}


def _extract_json(msg) -> Optional[dict]:
    """Extrae el objeto JSON de la respuesta del modelo, sea cual sea la forma."""
    # Salida estructurada nativa (si el SDK la expone ya parseada).
    parsed = getattr(msg, "parsed", None)
    if isinstance(parsed, dict):
        return parsed
    # Texto: concatena bloques de tipo texto y parsea.
    fragments: List[str] = []
    for block in getattr(msg, "content", []) or []:
        txt = getattr(block, "text", None)
        if txt:
            fragments.append(txt)
    raw = "".join(fragments).strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        # Rescata el primer objeto {...} si viniera envuelto en texto.
        i, j = raw.find("{"), raw.rfind("}")
        if 0 <= i < j:
            try:
                return json.loads(raw[i:j + 1])
            except Exception:
                return None
    return None
