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

    @property
    def repartido(self) -> Decimal:
        return money(sum((l.importe for l in self.lines), Decimal("0")))


# --- palabras clave -------------------------------------------------------

_EQUAL_KW = ["partes iguales", "a partes iguales", "por igual", "equitativ", "equiparte"]
_REST_KW = ["resto", "el resto", "restante", "lo que quede", "lo demas"]
_ALL_KW = ["todo", "integro", "integramente", "100%", "el total", "la totalidad"]
_WEIGHT_PREPS = ["por ", "segun ", "en funcion de ", "en proporcion a ", "prorrateo por ", "prorratear por "]

_SPLIT_RE = re.compile(r"[,;\n/]| y | e | mas | \+ ", re.IGNORECASE)
# referencia a una regla guardada: "como la regla X", "según la regla X"...
_RULEREF_RE = re.compile(
    r"\b(?:como|segun|aplica|aplicar|usa|usar|con)\s+(?:la\s+|el\s+)?regla\s+(.+)")
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

    def _match_rule(self, tail: str):
        """Encuentra la regla cuyo nombre encabeza el texto tras 'regla'."""
        tail = norm(tail)
        for name_norm, data in sorted(self._rules.items(), key=lambda kv: -len(kv[0])):
            if re.match(re.escape(name_norm) + r"(\b|$)", tail):
                return data
        return None

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

    def _detect_driver(self, text: str) -> Optional[str]:
        n = norm(text)
        for prep in _WEIGHT_PREPS:
            idx = n.find(prep)
            if idx >= 0:
                tail = n[idx + len(prep):]
                # el driver es la primera palabra "sustantiva" tras la preposición
                m = re.match(r"([a-z0-9º²]+)", tail)
                if m:
                    word = m.group(1)
                    if word not in ("igual", "iguales", "partes", "cierto", "ahora"):
                        return word
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

        equal_mode = any(k in n for k in _EQUAL_KW)
        driver = self._detect_driver(raw)

        # ---- MODO: a partes iguales -------------------------------------
        if equal_mode and not _numbers(raw):
            projs = self._find_projects_in(raw) or self.projects
            projs = [p for p in projs] or self.projects
            if not projs:
                res.warnings.append("No se han identificado proyectos para el reparto.")
                return res
            return self._equal(total, projs, res)

        # ---- MODO: ponderado por driver guardado (sin números) ----------
        if driver and not _numbers(raw):
            projs = self._find_projects_in(raw) or self.projects
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
        """Evalúa la regla guardada `matched` sobre el importe actual."""
        nombre, texto = matched
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
        sub.criterio = f'regla «{nombre}»'
        sub.explanation.insert(0, f'Aplicada la regla guardada «{nombre}» ("{texto}").')
        return sub

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
        all_project = None
        unknown_segments: List[str] = []

        text_has_pct = "%" in raw or "por ciento" in norm(raw)

        for seg in segments:
            sn = norm(seg)
            projs = self._find_projects_in(seg)
            is_rest = any(k in sn for k in _REST_KW)
            is_all = any(k in sn for k in _ALL_KW) and "100%" not in sn.replace(" ", "")
            nums = _numbers(seg)
            value = parse_number(nums[0]) if nums else None
            has_pct = "%" in seg or "por ciento" in sn
            has_eur = bool(re.search(r"€|eur", seg, re.IGNORECASE))

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
        if pct_items and not text_has_pct and not amt_items and not weight_items:
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

        if not pct_items and not amt_items and not rest_projs:
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
