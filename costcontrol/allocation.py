"""Motor de reparto analítico en lenguaje natural.

El usuario escribe *a mano* cómo quiere repartir el importe de un documento
entre proyectos y esta herramienta "traduce" ese texto libre a un reparto
concreto (proyecto -> importe), con una explicación legible de lo que ha
entendido.

Ejemplos de frases que entiende:

    "60% al PROY1 y 40% al PROY2"
    "PROY1 60, PROY2 40"                 (porcentajes si suman ~100)
    "a partes iguales entre PROY1, PROY2 y PROY3"
    "todo a PROY1"
    "1.500 € a PROY1 y el resto a PROY2"
    "por m2: PROY1 100, PROY2 300"       (reparto ponderado por pesos)
    "según superficie"                    (ponderado por un driver guardado)
    "PROY1 30%, PROY2 500 €, resto PROY3"
    "como la regla Obra estándar"        (reutiliza una regla guardada por nombre)

El motor es tolerante: acepta acentos, mayúsculas, formato de número
español (1.234,56) o inglés (1234.56) y separadores variados (comas, "y",
saltos de línea, ";", "/").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, List, Optional, Sequence

CENT = Decimal("0.01")


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def norm(s: str) -> str:
    """Normaliza para comparar: sin acentos, minúsculas, espacios colapsados."""
    return re.sub(r"\s+", " ", _strip_accents(str(s or "")).lower()).strip()


def money(value) -> Decimal:
    """Redondea a céntimos."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_number(raw: str) -> Optional[Decimal]:
    """Convierte un número escrito en formato ES (1.234,56) o EN (1234.56)."""
    if raw is None:
        return None
    s = str(raw).strip()
    s = re.sub(r"[€$%\s]|eur(os)?", "", s, flags=re.IGNORECASE).strip()
    if not s:
        return None
    neg = s.startswith("-")
    s = s.lstrip("+-")
    if "," in s and "." in s:
        # El separador que aparece más a la derecha es el decimal.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # Una sola coma -> decimal si tiene 1-2 cifras detrás, si no miles.
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        # Sólo puntos. Grupos de 3 cifras -> separador de millar (1.500 = 1500).
        parts = s.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            s = s.replace(".", "")
        # en otro caso se interpreta como decimal (12.34, 1.5)
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    return -d if neg else d


@dataclass
class Project:
    codigo: str
    nombre: str = ""
    drivers: Dict[str, Decimal] = field(default_factory=dict)

    def driver(self, clave: str) -> Optional[Decimal]:
        for k, v in self.drivers.items():
            if norm(k) == norm(clave):
                return Decimal(str(v))
        return None


@dataclass
class AllocationLine:
    proyecto: str          # código
    nombre: str
    importe: Decimal
    porcentaje: Decimal
    base: str              # explicación de cómo salió esta línea


@dataclass
class AllocationResult:
    ok: bool
    total: Decimal
    lines: List[AllocationLine] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    criterio: str = ""     # etiqueta del modo detectado
    ia: Optional[dict] = None  # info de la interpretación con IA, si se usó

    @property
    def repartido(self) -> Decimal:
        return money(sum((l.importe for l in self.lines), Decimal("0")))


# --- palabras clave -------------------------------------------------------

_EQUAL_KW = ["partes iguales", "a partes iguales", "por igual", "equitativ",
             "equiparte", "mitad y mitad", "a medias", "mismo importe",
             "misma cantidad", "mismas cantidades", "a escote", "lo mismo cada",
             "misma parte", "misma proporcion"]
_REST_KW = ["resto", "el resto", "restante", "lo que quede", "lo demas",
            "lo que sobra", "lo que sobre", "sobrante", "lo que falta",
            "remanente", "lo restante"]
# proyectos "restantes" a los que va el resto ("… y el resto a los demás")
_OTHERS_KW = ["los demas", "las demas", "resto de proyectos", "resto de los proyectos",
              "los otros", "los restantes", "otros proyectos", "demas proyectos",
              "a los demas", "entre los demas"]

# ponderar por el gasto/coste ya imputado a cada proyecto (driver calculado)
_COST_WORDS = ("gasto", "gastos", "coste", "costes", "gasto acumulado", "imputad")
_PERPROJ_KW = ("cada proyecto", "cada uno de los proyectos", "por proyecto",
               "de los proyectos", "de cada", "que ha tenido", "que han tenido",
               "acumulad", "imputad", "historic")

# subconjunto de proyectos por palabra en su nombre/código
# "que contienen finca", "que contengan la palabra finca", "que incluyan finca"...
_SCOPE_RE = re.compile(
    r"\bque\s+(?:contien\w+|conteng\w+|inclu\w+|lleven|lleva|tienen|tengan)\s+"
    r"(?:la\s+palabra\s+|el\s+texto\s+|el\s+termino\s+|el\s+nombre\s+)?"
    r"['\"]?([a-z0-9ñáéíóú]{2,})['\"]?")
_SCOPE_RE_CON = re.compile(r"\bcon\s+['\"]?([a-z0-9ñáéíóú]{2,})['\"]?\s+en\s+(?:el\s+)?nombre")
_SCOPE_RE_EMP = re.compile(r"\bempie\w+\s+(?:por|con)\s+['\"]?([a-z0-9ñáéíóú]{2,})['\"]?")
_SCOPE_STOP = {"la", "el", "los", "las", "un", "una", "palabra", "texto", "termino",
               "nombre", "proyecto", "proyectos", "que", "de"}
_ALL_KW = ["todo", "integro", "integramente", "100%", "el total", "la totalidad"]
_WEIGHT_PREPS = ["por ", "segun ", "en funcion de ", "en proporcion a ",
                 "prorrateo por ", "prorratear por ", "proporcional a ",
                 "proporcionalmente a ", "a prorrata de ", "en base a ",
                 "en base al ", "conforme a ", "de acuerdo con ", "de acuerdo a ",
                 "ponderado por ", "en relacion a ", "atendiendo a "]

# fracciones escritas en palabras -> porcentaje (buscar frases largas primero)
_FRAC_MAP = [
    ("tres cuartas partes", Decimal("75")), ("tres cuartos", Decimal("75")),
    ("dos terceras partes", Decimal("200") / Decimal("3")),
    ("dos tercios", Decimal("200") / Decimal("3")),
    ("cuatro quintos", Decimal("80")), ("tres quintos", Decimal("60")),
    ("dos quintos", Decimal("40")),
    ("una cuarta parte", Decimal("25")), ("un cuarto", Decimal("25")),
    ("una tercera parte", Decimal("100") / Decimal("3")),
    ("un tercio", Decimal("100") / Decimal("3")),
    ("un quinto", Decimal("20")),
    ("tres cuartas", Decimal("75")),
    ("la mitad", Decimal("50")), ("mitad de", Decimal("50")),
]


def _fraction_pct(segment_norm: str) -> Optional[Decimal]:
    """Devuelve el porcentaje de una fracción escrita ('un tercio' -> 33.33…)."""
    for phrase, pct in _FRAC_MAP:
        if phrase in segment_norm:
            return pct
    return None

_SPLIT_RE = re.compile(r"[,;\n/]| y | e | mas | \+ ", re.IGNORECASE)
# referencia a una regla guardada: "como la regla X", "según la regla X"...
_RULEREF_RE = re.compile(
    r"\b(?:como|segun|aplica|aplicar|usa|usar|con)\s+(?:la\s+|el\s+)?regla\s+(.+)")
# bloque de regla con peso, dentro de una combinación:
#   "50% como la regla X", "1000€ como la regla X", "resto como la regla X"
_COMBO_SPLIT = re.compile(r"[,;\n]")
_RULEBLOCK_RE = re.compile(
    r"(?:\d[\d.,]*\s*%|\d[\d.,]*\s*(?:€|eur\w*)|\bresto\b)\s*"
    r"(?:como|segun|aplica\w*|usa\w*|con)\s+(?:la\s+|el\s+)?regla\b")
# Números "de verdad": no cuentan los dígitos pegados a letras (p.ej. el 1 de
# PROY1 o el 2 de m2). El número debe empezar tras un espacio, inicio, € o (.
_NUM_RE = re.compile(r"(?<![A-Za-z0-9])\d[\d\.\,]*")


def _numbers(text: str) -> List[str]:
    out = []
    for m in _NUM_RE.findall(text):
        out.append(m.rstrip(".,"))
    return [x for x in out if x]


class Allocator:
    def __init__(self, projects: Sequence[Project], rules=None):
        self.projects = list(projects)
        # índices normalizados: código y nombre -> proyecto
        self._by_cod = {norm(p.codigo): p for p in self.projects}
        self._by_name = {norm(p.nombre): p for p in self.projects if p.nombre}
        # reglas guardadas: {nombre_normalizado: (nombre, texto)}
        self._rules: Dict[str, tuple] = {}
        if rules:
            items = rules.items() if isinstance(rules, dict) else [(r["nombre"], r["texto"]) for r in rules]
            for nombre, texto in items:
                if nombre and texto:
                    self._rules[norm(nombre)] = (nombre, texto)

    def rules_map(self) -> Dict[str, str]:
        """Devuelve las reglas guardadas como {nombre: texto} (para la IA)."""
        return {nombre: texto for (nombre, texto) in self._rules.values()}

    def _match_rule(self, tail: str):
        """Encuentra la regla cuyo nombre encabeza el texto tras 'regla'.

        Devuelve (nombre, texto, resto), donde `resto` es lo que sigue al nombre
        (p.ej. "pero solo PROY-A y PROY-B"), o None si no hay coincidencia.
        """
        tail = norm(tail)
        for name_norm, (nombre, texto) in sorted(self._rules.items(), key=lambda kv: -len(kv[0])):
            mm = re.match(re.escape(name_norm) + r"(\b|$)", tail)
            if mm:
                return (nombre, texto, tail[mm.end():].strip())
        return None

    _SUBSET_EXCL = re.compile(r"\b(excepto|salvo|menos|quitando)\b")
    _SUBSET_KEEP = re.compile(r"\b(solo|solamente|unicamente)\b")

    def _subset_filter(self, resto: str):
        """Detecta un subconjunto en `resto`: ('solo'|'excepto', [proyectos]) o None."""
        if not resto:
            return None
        r = norm(resto)
        keep = bool(self._SUBSET_KEEP.search(r))
        excl = bool(self._SUBSET_EXCL.search(r))
        if not (keep or excl):
            return None
        projs = self._find_projects_in(resto)
        if not projs:
            return None
        return ("excepto" if excl and not keep else "solo", projs)

    # -- búsqueda de proyectos en el texto --------------------------------
    def _find_projects_in(self, segment: str) -> List[Project]:
        n = norm(segment)
        found: List[Project] = []
        seen = set()
        # código como palabra completa (prioritario)
        for cod, p in sorted(self._by_cod.items(), key=lambda kv: -len(kv[0])):
            if not cod:
                continue
            if re.search(r"(?<![\w])" + re.escape(cod) + r"(?![\w])", n) and p.codigo not in seen:
                found.append(p)
                seen.add(p.codigo)
        # nombre como subcadena (por orden de aparición)
        for name, p in sorted(self._by_name.items(), key=lambda kv: -len(kv[0])):
            if len(name) >= 3 and name in n and p.codigo not in seen:
                found.append(p)
                seen.add(p.codigo)
        return found

    # multiplicadores relativos ("el doble", "la mitad", "el triple"...)
    _MULT = {
        "doble": Decimal("2"), "duplo": Decimal("2"), "triple": Decimal("3"),
        "cuadruple": Decimal("4"), "quintuple": Decimal("5"),
        "mitad": Decimal("0.5"), "tercio": Decimal("1") / Decimal("3"),
        "cuarto": Decimal("0.25"), "doble mas": Decimal("2"),
    }
    _REL_RE = re.compile(
        r"\b(?:el|la)\s+(doble|duplo|triple|cuadruple|quintuple|mitad|tercio|cuarto)\b"
        r"(.*?)\bque\s+a?\b(.*)", re.DOTALL)

    def _relative_weights(self, raw: str):
        """Detecta 'el doble a A que a B' -> ([A,B], [2,1]). None si no aplica."""
        n = norm(raw)
        m = self._REL_RE.search(n)
        if not m:
            return None
        mult = self._MULT.get(m.group(1))
        if mult is None:
            return None
        left = self._find_projects_in(m.group(2))
        right = self._find_projects_in(m.group(3))
        if len(left) != 1 or len(right) != 1 or left[0].codigo == right[0].codigo:
            return None
        return ([left[0], right[0]], [mult, Decimal("1")])

    def _cada_uno(self, raw: str):
        """'20% a cada uno' / '300 € a cada proyecto' -> (texto_canónico, nota).

        Reparte la misma cifra a cada proyecto indicado (o a todos si no se
        nombra ninguno). Devuelve None si no aplica con claridad.
        """
        n = norm(raw)
        nums = _numbers(raw)
        if len({x for x in nums}) != 1:   # necesitamos una única cifra
            return None
        has_pct = "%" in raw or "por ciento" in n
        has_eur = bool(re.search(r"€|eur", raw, re.IGNORECASE))
        if not (has_pct or has_eur):
            return None
        projs = self._find_projects_in(raw) or self.projects
        if not projs:
            return None
        unit = "%" if has_pct else "€"
        v = nums[0]
        canon = ", ".join(f"{v} {unit} {p.codigo}" for p in projs)
        nota = (f'"cada uno": {v}{unit} a cada uno de {len(projs)} proyecto(s).')
        return (canon, nota)

    # artículos que se saltan tras la preposición ("proporcional a las horas")
    _DRIVER_SKIP = {"la", "el", "los", "las", "un", "una", "unos", "unas",
                    "de", "del", "numero", "nº", "cantidad", "valor", "su", "sus"}
    # palabras que indican que NO es un driver (es otro modo de reparto)
    _DRIVER_ABORT = {"igual", "iguales", "partes", "cierto", "ahora", "cada",
                     "todo", "todos", "cada"}

    def _keyword_scope(self, raw: str):
        """Subconjunto de proyectos cuyo nombre/código contiene una palabra.

        Devuelve (True, [proyectos]) si el texto pide 'los proyectos que
        contienen X'; (True, []) si lo pide pero ninguno casa; None si no aplica.
        """
        n = norm(raw)
        kw = None
        for rx in (_SCOPE_RE, _SCOPE_RE_CON, _SCOPE_RE_EMP):
            m = rx.search(n)
            if m and m.group(1) not in _SCOPE_STOP:
                kw = m.group(1)
                break
        if not kw:
            return None
        sel = [p for p in self.projects
               if kw in norm(p.codigo) or kw in norm(p.nombre or "")]
        return (True, sel, kw)

    def _scoped_projects(self, raw: str, res):
        """Proyectos sobre los que operar. Si se pide un subconjunto por palabra
        y ninguno casa, avisa y devuelve None (el llamador debe abortar)."""
        ks = self._keyword_scope(raw)
        if ks is not None:
            if not ks[1]:
                res.warnings.append(
                    f'Ningún proyecto contiene «{ks[2]}» en su nombre o código.')
                return None
            return ks[1]
        return self._find_projects_in(raw) or self.projects

    def _is_cost_weight(self, n: str) -> bool:
        """True si se pide ponderar por el gasto/coste imputado de cada proyecto."""
        has_cost = any(w in n for w in _COST_WORDS)
        per_proj = any(w in n for w in _PERPROJ_KW)
        return has_cost and per_proj

    def _cost_weighted(self, total, raw, res):
        """Reparte proporcionalmente al gasto/coste ya imputado a cada proyecto.

        Usa el driver calculado 'gasto' (o 'coste') que la app inyecta con el
        importe acumulado por proyecto. Respeta el subconjunto por palabra.
        """
        ks = self._keyword_scope(raw)
        if ks is not None and not ks[1]:
            res.warnings.append(f'Ningún proyecto contiene «{ks[2]}» en su nombre o código.')
            return res
        scope = ks[1] if ks is not None else (self._find_projects_in(raw) or self.projects)
        usable, weights = [], []
        for p in scope:
            w = p.driver("gasto")
            if w is None:
                w = p.driver("coste")
            if w is not None and Decimal(str(w)) > 0:
                usable.append(p)
                weights.append(Decimal(str(w)))
        if not usable or sum(weights, Decimal("0")) <= 0:
            res.warnings.append(
                "No hay gasto imputado en esos proyectos todavía, así que no se "
                "puede repartir en función del gasto. Reparte algo primero o usa "
                "otro criterio (p. ej. por superficie o a partes iguales).")
            return res
        res.criterio = "ponderado por gasto imputado"
        out = self._weighted(total, usable, weights, res, "gasto imputado")
        etiqueta = f" (proyectos con «{ks[2]}»)" if ks is not None else ""
        out.explanation.insert(
            0, f"Reparto proporcional al gasto ya imputado de cada proyecto{etiqueta}.")
        return out

    def _detect_driver(self, text: str) -> Optional[str]:
        n = norm(text)
        for prep in _WEIGHT_PREPS:
            idx = n.find(prep)
            if idx < 0:
                continue
            words = re.findall(r"[a-z0-9º²]+", n[idx + len(prep):])
            i = 0
            while i < len(words) and words[i] in self._DRIVER_SKIP:
                i += 1
            if i < len(words) and words[i] not in self._DRIVER_ABORT:
                return words[i]
        return None

    # -- API principal -----------------------------------------------------
    def allocate(self, total, text: str, _seen=None) -> AllocationResult:
        total = money(total)
        res = AllocationResult(ok=False, total=total)
        raw = (text or "").strip()
        if not raw:
            res.warnings.append("No se ha escrito ninguna regla de reparto.")
            return res
        n = norm(raw)

        # ---- MODO: combinar regla(s) con reparto directo -----------------
        if self._rules and _RULEBLOCK_RE.search(n):
            return self._combine(total, raw, res, _seen)

        # ---- MODO: reutilizar una regla guardada ("como la regla X") -----
        if self._rules:
            m = _RULEREF_RE.search(n)
            if m:
                matched = self._match_rule(m.group(1).strip())
                if matched:
                    return self._apply_rule(total, matched, res, _seen)
                res.warnings.append(
                    "No se ha encontrado esa regla. Reglas guardadas: "
                    + ", ".join(sorted(v[0] for v in self._rules.values())))
                return res

        # ---- MODO: pesos relativos ("el doble a A que a B") -------------
        if "%" not in raw and not re.search(r"€|eur", raw, re.IGNORECASE):
            rel = self._relative_weights(raw)
            if rel:
                projs, weights = rel
                res.criterio = "pesos relativos"
                out = self._weighted(total, projs, weights, res, "proporción indicada")
                out.explanation.insert(
                    0, f"Reparto proporcional: {projs[0].codigo} recibe "
                       f"{weights[0]}× respecto a {projs[1].codigo}.")
                return out

        # ---- MODO: "cada uno" con cifra ("20% a cada uno", "300€ cada uno")
        if re.search(r"\bcada\b", n) and _numbers(raw):
            canon = self._cada_uno(raw)
            if canon:
                out = self._by_segments(total, canon[0], res, None)
                out.explanation.insert(0, canon[1])
                return out

        # ---- MODO: ponderado por el gasto/coste imputado de cada proyecto
        if not _numbers(raw) and self._is_cost_weight(n):
            return self._cost_weighted(total, raw, res)

        cada_igual = bool(re.search(r"cada (uno|proyecto|centro)", n))
        equal_mode = any(k in n for k in _EQUAL_KW) or cada_igual
        driver = self._detect_driver(raw)

        # ---- MODO: a partes iguales -------------------------------------
        if equal_mode and not _numbers(raw):
            projs = self._scoped_projects(raw, res)
            if projs is None:
                return res
            if not projs:
                res.warnings.append("No se han identificado proyectos para el reparto.")
                return res
            return self._equal(total, projs, res)

        # ---- MODO: ponderado por driver guardado (sin números) ----------
        if driver and not _numbers(raw):
            projs = self._scoped_projects(raw, res)
            if projs is None:
                return res
            weights = []
            usable = []
            for p in projs:
                w = p.driver(driver)
                if w is not None:
                    usable.append(p)
                    weights.append(Decimal(str(w)))
            if not usable:
                res.warnings.append(
                    f'No hay valores del criterio "{driver}" guardados en los proyectos.'
                )
                return res
            res.criterio = f"ponderado por {driver}"
            return self._weighted(total, usable, weights, res, driver)

        # ---- MODO general: por segmentos --------------------------------
        return self._by_segments(total, raw, res, driver)

    def _apply_rule(self, total, matched, res, _seen) -> AllocationResult:
        """Evalúa la regla guardada `matched` sobre el importe actual.

        Si tras el nombre hay un subconjunto ("pero solo A y B" / "excepto C"),
        filtra las líneas de la regla a ese subconjunto y **reescala** sus
        proporciones para que vuelvan a sumar el total.
        """
        nombre, texto, resto = matched
        _seen = set(_seen or ())
        key = norm(nombre)
        if key in _seen:
            res.warnings.append(f'Referencia circular a la regla «{nombre}».')
            return res
        sub = self.allocate(total, texto, _seen | {key})
        if not sub.ok:
            res.warnings.append(
                f'La regla «{nombre}» no se pudo aplicar: ' + " ".join(sub.warnings))
            return res

        subset = self._subset_filter(resto)
        if subset:
            modo, projs = subset
            codes = {p.codigo for p in projs}
            if modo == "excepto":
                kept = [l for l in sub.lines if l.proyecto not in codes]
                desc = "excepto " + ", ".join(sorted(codes))
            else:
                kept = [l for l in sub.lines if l.proyecto in codes]
                desc = "solo " + ", ".join(sorted(codes))
            base = sum((l.importe for l in kept), Decimal("0"))
            if not kept or base <= 0:
                res.warnings.append(
                    f'El subconjunto ({desc}) no deja importe de la regla «{nombre}» para reescalar.')
                return res
            lines = []
            for l in kept:
                imp = money(total * l.importe / base)
                pct = money(imp / total * 100) if total else Decimal("0")
                lines.append(AllocationLine(l.proyecto, l.nombre, imp, pct,
                                            f'reescalado de regla «{nombre}»'))
            dif = money(total - sum((x.importe for x in lines), Decimal("0")))
            if lines and dif != 0:
                biggest = max(lines, key=lambda x: x.importe)
                biggest.importe = money(biggest.importe + dif)
                biggest.porcentaje = money(biggest.importe / total * 100) if total else Decimal("0")
            res.lines = lines
            res.ok = True
            res.criterio = f'regla «{nombre}» ({desc})'
            res.explanation.insert(0, f'Regla «{nombre}» reescalada a {desc}.')
            return res

        sub.criterio = f'regla «{nombre}»'
        sub.explanation.insert(0, f'Aplicada la regla guardada «{nombre}» ("{texto}").')
        return sub

    @staticmethod
    def _merge_lines(lines, total):
        """Suma las líneas del mismo proyecto y recalcula porcentajes."""
        order, agg = [], {}
        for l in lines:
            if l.proyecto not in agg:
                agg[l.proyecto] = AllocationLine(l.proyecto, l.nombre, Decimal("0"),
                                                 Decimal("0"), l.base)
                order.append(l.proyecto)
            agg[l.proyecto].importe = money(agg[l.proyecto].importe + l.importe)
        out = []
        for code in order:
            a = agg[code]
            a.porcentaje = money(a.importe / total * 100) if total else Decimal("0")
            out.append(a)
        return out

    def _combine(self, total, raw, res, _seen) -> AllocationResult:
        """Combina bloques de regla (con peso) con segmentos de reparto directo.

        Cada bloque "N% / N€ como la regla X" se expande a importes concretos;
        "resto como la regla X" reparte el remanente según esa regla. El resto
        de segmentos (porcentajes, importes, resto a un proyecto) se resuelven
        con el motor normal.
        """
        euro_segments: List[str] = []   # segmentos sintéticos "importe € CODIGO"
        direct_segments: List[str] = []  # segmentos directos, tal cual
        rest_rule = None                 # líneas de la regla que absorbe el remanente
        nombres: List[str] = []

        for seg in (s.strip() for s in _COMBO_SPLIT.split(raw) if s.strip()):
            sn = norm(seg)
            mref = _RULEREF_RE.search(sn)
            matched = self._match_rule(mref.group(1).strip()) if mref else None
            if not matched:
                direct_segments.append(seg)
                continue
            sub = self._apply_rule(total, matched, AllocationResult(ok=False, total=total), _seen)
            if not sub.ok:
                res.warnings.append(f'La regla «{matched[0]}» no se pudo aplicar en la combinación.')
                return res
            nombres.append(matched[0])
            has_pct = "%" in seg or "por ciento" in sn
            has_eur = bool(re.search(r"€|eur", seg, re.IGNORECASE))
            nums = _numbers(seg)
            val = parse_number(nums[0]) if nums else None
            if val is not None and has_pct:
                for l in sub.lines:
                    imp = money(l.importe * val / 100)
                    if imp:
                        euro_segments.append(f"{imp} € {l.proyecto}")
            elif val is not None and has_eur:
                for l in sub.lines:
                    imp = money(val * l.importe / total) if total else Decimal("0")
                    if imp:
                        euro_segments.append(f"{imp} € {l.proyecto}")
            else:
                rest_rule = sub.lines  # "resto como la regla X"

        # resuelve la parte directa (importes fijos de las reglas + segmentos directos)
        parts = euro_segments + direct_segments
        text2 = ", ".join(parts)
        if text2.strip():
            base = self._by_segments(total, text2, AllocationResult(ok=False, total=total), None)
        else:
            base = AllocationResult(ok=True, total=total)
        lines = list(base.lines)

        # el remanente lo reparte la regla marcada como "resto"
        if rest_rule is not None:
            asignado = sum((l.importe for l in lines), Decimal("0"))
            remaining = money(total - asignado)
            if remaining > 0:
                fr_total = sum((l.importe for l in rest_rule), Decimal("0")) or total
                add = []
                for l in rest_rule:
                    imp = money(remaining * l.importe / fr_total)
                    if imp:
                        add.append(AllocationLine(l.proyecto, l.nombre, imp,
                                                  money(imp / total * 100) if total else Decimal("0"),
                                                  "resto por regla"))
                dif = money(remaining - sum((x.importe for x in add), Decimal("0")))
                if add and dif != 0:
                    biggest = max(add, key=lambda x: x.importe)
                    biggest.importe = money(biggest.importe + dif)
                lines += add
            elif remaining < 0:
                res.warnings.append("Lo asignado supera el total; no queda remanente para la regla.")

        merged = self._merge_lines(lines, total)
        res.lines = merged
        res.ok = bool(merged)
        res.criterio = "combinación"
        etiqueta = f" (reglas: {', '.join(nombres)})" if nombres else ""
        res.explanation.insert(0, f"Reparto combinado{etiqueta}.")
        dif = money(total - sum((l.importe for l in merged), Decimal("0")))
        if dif > 0:
            res.warnings.append(f"Quedan {dif} € sin repartir (¿falta un 'resto'?).")
        elif dif < 0:
            res.warnings.append(f"Se ha repartido {abs(dif)} € de más respecto al total.")
        return res

    # -- estrategias -------------------------------------------------------
    def _equal(self, total, projs, res) -> AllocationResult:
        res.criterio = "a partes iguales"
        n = len(projs)
        share = money(total / n)
        importes = [share] * n
        importes[-1] = money(total - share * (n - 1))
        for p, imp in zip(projs, importes):
            pct = money(imp / total * 100) if total else Decimal("0")
            res.lines.append(AllocationLine(p.codigo, p.nombre, imp, pct, "parte igual"))
        res.explanation.append(f"Reparto a partes iguales entre {n} proyectos.")
        res.ok = True
        return res

    def _weighted(self, total, projs, weights, res, label) -> AllocationResult:
        tw = sum(weights, Decimal("0"))
        if tw <= 0:
            res.warnings.append("La suma de pesos es cero; no se puede prorratear.")
            return res
        importes = [money(total * w / tw) for w in weights]
        importes[-1] = money(total - sum(importes[:-1], Decimal("0")))
        for p, w, imp in zip(projs, weights, importes):
            pct = money(imp / total * 100) if total else Decimal("0")
            res.lines.append(
                AllocationLine(p.codigo, p.nombre, imp, pct, f"peso {w} de {label}")
            )
        res.explanation.append(
            f"Reparto ponderado por {label}: pesos totales {tw}."
        )
        res.ok = True
        return res

    def _by_segments(self, total, raw, res, driver) -> AllocationResult:
        segments = [s for s in _SPLIT_RE.split(raw) if s.strip()]
        # Cada asignación: (proyecto, tipo, valor, texto)
        pct_items: List[tuple] = []      # (proyecto, Decimal pct)
        amt_items: List[tuple] = []      # (proyecto, Decimal importe)
        weight_items: List[tuple] = []   # (proyecto, Decimal peso)
        rest_projs: List[Project] = []
        rest_others = False              # "… y el resto a los demás"
        all_project = None
        unknown_segments: List[str] = []
        has_fraction = False             # se usó una fracción escrita

        text_has_pct = "%" in raw or "por ciento" in norm(raw)

        for seg in segments:
            sn = norm(seg)
            # "los demás / el resto de proyectos": el resto va a los no asignados
            if any(k in sn for k in _OTHERS_KW):
                rest_others = True
                continue
            projs = self._find_projects_in(seg)
            is_rest = any(k in sn for k in _REST_KW)
            is_all = any(k in sn for k in _ALL_KW) and "100%" not in sn.replace(" ", "")
            nums = _numbers(seg)
            value = parse_number(nums[0]) if nums else None
            has_pct = "%" in seg or "por ciento" in sn
            has_eur = bool(re.search(r"€|eur", seg, re.IGNORECASE))
            # fracción escrita ("un tercio", "la mitad") -> porcentaje
            if value is None and not is_rest and not is_all:
                frac = _fraction_pct(sn)
                if frac is not None:
                    value = frac
                    has_pct = True
                    has_fraction = True

            if not projs:
                # segmento sin proyecto: puede ser ruido ("y el", "reparte")
                if value is not None or is_rest:
                    unknown_segments.append(seg.strip())
                continue

            p = projs[0]
            extra = projs[1:]  # varios proyectos en un mismo segmento

            if is_rest:
                rest_projs.extend(projs)
                continue
            if is_all and value is None:
                all_project = p
                continue

            if value is None:
                # proyecto mencionado sin cifra -> lo tratamos como resto candidato
                rest_projs.extend(projs)
                continue

            # varios proyectos comparten un valor en el segmento (raro): repetir
            targets = [p] + extra
            for tp in targets:
                if has_pct or (text_has_pct and not has_eur):
                    pct_items.append((tp, value))
                elif has_eur:
                    amt_items.append((tp, value))
                elif driver:
                    weight_items.append((tp, value))
                else:
                    # sin unidad y sin % en el texto: si suman ~100 -> %, si no -> importe
                    pct_items.append((tp, value))  # se re-decide abajo

        # Si asumimos porcentajes pero no hay "%" en el texto, comprobamos suma
        if pct_items and not text_has_pct and not has_fraction and not amt_items and not weight_items:
            suma = sum((v for _, v in pct_items), Decimal("0"))
            if not (Decimal("95") <= suma <= Decimal("105")):
                # No parecen porcentajes -> los tratamos como importes fijos
                amt_items = [(p, v) for p, v in pct_items]
                pct_items = []

        if all_project is not None:
            res.criterio = "todo a un proyecto"
            res.lines.append(
                AllocationLine(all_project.codigo, all_project.nombre, total,
                               Decimal("100.00"), "todo el importe")
            )
            res.explanation.append(f"Todo el importe imputado a {all_project.codigo}.")
            res.ok = True
            return res

        if weight_items:
            res.criterio = f"ponderado por {driver}" if driver else "ponderado por pesos"
            projs = [p for p, _ in weight_items]
            weights = [w for _, w in weight_items]
            return self._weighted(total, projs, weights, res, driver or "pesos")

        if not pct_items and not amt_items and not rest_projs and not rest_others:
            res.warnings.append(
                "No se ha entendido el reparto. Indica proyectos con % , importes € "
                "o usa 'a partes iguales'."
            )
            if unknown_segments:
                res.warnings.append("Sin proyecto reconocido en: " + "; ".join(unknown_segments))
            return res

        # --- resolver importes fijos + porcentajes + resto ---------------
        asignado = Decimal("0")
        pct_total = Decimal("0")
        tmp_lines: List[AllocationLine] = []

        for p, amt in amt_items:
            imp = money(amt)
            asignado += imp
            pct = money(imp / total * 100) if total else Decimal("0")
            tmp_lines.append(AllocationLine(p.codigo, p.nombre, imp, pct, "importe fijo"))

        for p, pct in pct_items:
            imp = money(total * pct / 100)
            asignado += imp
            pct_total += pct
            tmp_lines.append(AllocationLine(p.codigo, p.nombre, imp, money(pct), f"{money(pct)} %"))

        restante = money(total - asignado)

        # "los demás": el resto se reparte entre los proyectos aún no asignados
        if rest_others:
            asignados_cod = {l.proyecto for l in tmp_lines} | {p.codigo for p in rest_projs}
            for p in self.projects:
                if p.codigo not in asignados_cod:
                    rest_projs.append(p)

        if rest_projs:
            # dedup preservando orden
            seen = set()
            uniq = [p for p in rest_projs if not (p.codigo in seen or seen.add(p.codigo))]
            if restante < 0:
                res.warnings.append(
                    f"Lo asignado ({money(asignado)}) supera el total; no queda resto para repartir."
                )
            share = money(restante / len(uniq)) if uniq else Decimal("0")
            reparto_rest = [share] * len(uniq)
            if uniq:
                reparto_rest[-1] = money(restante - share * (len(uniq) - 1))
            for p, imp in zip(uniq, reparto_rest):
                pct = money(imp / total * 100) if total else Decimal("0")
                tmp_lines.append(AllocationLine(p.codigo, p.nombre, imp, pct, "resto"))
            restante = Decimal("0")

        res.lines = tmp_lines
        res.criterio = res.criterio or ("porcentajes" if pct_items else "importes fijos")

        # avisos de cuadre
        dif = money(total - res.repartido)
        if dif != 0:
            if dif > 0:
                res.warnings.append(
                    f"Quedan {dif} € sin repartir (falta un 'resto' o llegar al 100%)."
                )
            else:
                res.warnings.append(
                    f"Se ha repartido {abs(dif)} € de más respecto al total del documento."
                )
        if pct_items and not (Decimal("99.5") <= pct_total <= Decimal("100.5")) and not rest_projs:
            res.explanation.append(f"Los porcentajes indicados suman {money(pct_total)} %.")

        # ajuste de céntimos por redondeo si cuadra casi exacto
        if res.lines and abs(dif) <= Decimal("0.05") * max(len(res.lines), 1) and dif != 0:
            biggest = max(res.lines, key=lambda l: l.importe)
            biggest.importe = money(biggest.importe + dif)
            biggest.porcentaje = money(biggest.importe / total * 100) if total else Decimal("0")
            res.warnings = [w for w in res.warnings if "sin repartir" not in w and "de más" not in w]
            res.explanation.append(f"Ajuste de redondeo de {dif} € aplicado a {biggest.proyecto}.")

        res.ok = len(res.lines) > 0
        parts = ", ".join(f"{l.proyecto} {l.importe} €" for l in res.lines)
        res.explanation.insert(0, f"Reparto ({res.criterio}): {parts}.")
        return res


def allocate(total, text: str, projects: Sequence[Project], rules=None) -> AllocationResult:
    """Atajo funcional."""
    return Allocator(projects, rules=rules).allocate(total, text)
