"""Capa de acceso a datos de CostControl sobre SQLite (stdlib)."""

from __future__ import annotations

import json
import os
import sqlite3
from decimal import Decimal
from typing import Any, Dict, List, Optional

DEFAULT_DB = os.environ.get(
    "COSTCONTROL_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "costcontrol.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS proyectos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL DEFAULT '',
    descripcion TEXT DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1,
    presupuesto REAL NOT NULL DEFAULT 0,
    drivers TEXT NOT NULL DEFAULT '{}',
    creado TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS centros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL DEFAULT '',
    tipo TEXT NOT NULL DEFAULT 'coste',   -- 'coste' | 'beneficio'
    descripcion TEXT DEFAULT '',
    regla_defecto TEXT NOT NULL DEFAULT ''  -- reparto sugerido por defecto
);

CREATE TABLE IF NOT EXISTS terceros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nif TEXT DEFAULT '',
    nombre TEXT NOT NULL DEFAULT '',
    tipo TEXT NOT NULL DEFAULT 'proveedor', -- proveedor | cliente
    UNIQUE(nombre)
);

CREATE TABLE IF NOT EXISTS cuentas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL DEFAULT '',
    grupo TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS documentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL DEFAULT 'factura',  -- factura | albaran | apunte
    numero TEXT DEFAULT '',
    fecha TEXT DEFAULT '',
    tercero TEXT DEFAULT '',
    tercero_id INTEGER REFERENCES terceros(id) ON DELETE SET NULL,
    concepto TEXT DEFAULT '',
    importe REAL NOT NULL DEFAULT 0,      -- base imponible (importe a repartir)
    iva_pct REAL NOT NULL DEFAULT 0,
    iva_importe REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,        -- base + iva (informativo)
    ejercicio INTEGER,
    periodo INTEGER,                      -- mes 1-12
    cuenta_id INTEGER REFERENCES cuentas(id) ON DELETE SET NULL,
    centro_id INTEGER REFERENCES centros(id) ON DELETE SET NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente', -- pendiente | repartido
    notas TEXT DEFAULT '',
    creado TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS repartos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id INTEGER NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE SET NULL,
    proyecto_codigo TEXT DEFAULT '',
    importe REAL NOT NULL DEFAULT 0,
    porcentaje REAL NOT NULL DEFAULT 0,
    base TEXT DEFAULT '',
    creado TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reglas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    texto TEXT NOT NULL,
    creado TEXT DEFAULT (datetime('now'))
);
"""


def connect(path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DEFAULT_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Columnas añadidas después de la primera versión: {tabla: [(col, definición)]}
_MIGRATIONS = {
    "centros": [("regla_defecto", "TEXT NOT NULL DEFAULT ''")],
    "documentos": [
        ("tercero_id", "INTEGER"),
        ("iva_pct", "REAL NOT NULL DEFAULT 0"),
        ("iva_importe", "REAL NOT NULL DEFAULT 0"),
        ("total", "REAL NOT NULL DEFAULT 0"),
        ("ejercicio", "INTEGER"),
        ("periodo", "INTEGER"),
    ],
}


def _migrate(conn) -> None:
    for tabla, cols in _MIGRATIONS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
        for col, definicion in cols:
            if col not in existing:
                conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {definicion}")
    # rellena ejercicio/periodo/total a partir de datos existentes
    conn.execute(
        "UPDATE documentos SET ejercicio = CAST(substr(fecha,1,4) AS INTEGER) "
        "WHERE (ejercicio IS NULL OR ejercicio=0) AND length(fecha)>=4 AND substr(fecha,1,4) GLOB '[0-9][0-9][0-9][0-9]'")
    conn.execute(
        "UPDATE documentos SET periodo = CAST(substr(fecha,6,2) AS INTEGER) "
        "WHERE (periodo IS NULL OR periodo=0) AND length(fecha)>=7")
    conn.execute("UPDATE documentos SET total = importe + iva_importe WHERE total=0")


def periodo_desde_fecha(fecha: str):
    """Devuelve (ejercicio, periodo) a partir de 'YYYY-MM-DD'."""
    ejercicio = periodo = None
    s = str(fecha or "")
    if len(s) >= 4 and s[:4].isdigit():
        ejercicio = int(s[:4])
    if len(s) >= 7 and s[5:7].isdigit():
        periodo = int(s[5:7])
    return ejercicio, periodo


def init_db(path: Optional[str] = None) -> None:
    conn = connect(path)
    with conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
    conn.close()


def rows_to_dicts(rows) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows]


# --- Proyectos ------------------------------------------------------------
def list_proyectos(conn, solo_activos: bool = False) -> List[Dict[str, Any]]:
    q = "SELECT * FROM proyectos"
    if solo_activos:
        q += " WHERE activo = 1"
    q += " ORDER BY codigo"
    out = []
    for r in conn.execute(q).fetchall():
        d = dict(r)
        try:
            d["drivers"] = json.loads(d.get("drivers") or "{}")
        except (ValueError, TypeError):
            d["drivers"] = {}
        out.append(d)
    return out


def get_proyecto(conn, pid: int) -> Optional[Dict[str, Any]]:
    r = conn.execute("SELECT * FROM proyectos WHERE id=?", (pid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["drivers"] = json.loads(d.get("drivers") or "{}")
    except (ValueError, TypeError):
        d["drivers"] = {}
    return d


def upsert_proyecto(conn, codigo, nombre, descripcion="", activo=1,
                    presupuesto=0, drivers=None, pid=None) -> int:
    drivers_json = json.dumps(drivers or {})
    with conn:
        if pid:
            conn.execute(
                """UPDATE proyectos SET codigo=?, nombre=?, descripcion=?, activo=?,
                   presupuesto=?, drivers=? WHERE id=?""",
                (codigo, nombre, descripcion, int(activo), float(presupuesto), drivers_json, pid),
            )
            return pid
        cur = conn.execute(
            """INSERT INTO proyectos (codigo, nombre, descripcion, activo, presupuesto, drivers)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(codigo) DO UPDATE SET nombre=excluded.nombre,
                 descripcion=excluded.descripcion, activo=excluded.activo,
                 presupuesto=excluded.presupuesto, drivers=excluded.drivers""",
            (codigo, nombre, descripcion, int(activo), float(presupuesto), drivers_json),
        )
        if cur.lastrowid:
            return cur.lastrowid
        r = conn.execute("SELECT id FROM proyectos WHERE codigo=?", (codigo,)).fetchone()
        return r["id"]


def delete_proyecto(conn, pid: int) -> None:
    with conn:
        conn.execute("DELETE FROM proyectos WHERE id=?", (pid,))


# --- Centros --------------------------------------------------------------
def list_centros(conn) -> List[Dict[str, Any]]:
    return rows_to_dicts(conn.execute("SELECT * FROM centros ORDER BY codigo").fetchall())


def get_centro(conn, cid: int) -> Optional[Dict[str, Any]]:
    r = conn.execute("SELECT * FROM centros WHERE id=?", (cid,)).fetchone()
    return dict(r) if r else None


def upsert_centro(conn, codigo, nombre, tipo="coste", descripcion="",
                  regla_defecto=None, cid=None) -> int:
    with conn:
        if cid:
            if regla_defecto is None:
                conn.execute(
                    "UPDATE centros SET codigo=?, nombre=?, tipo=?, descripcion=? WHERE id=?",
                    (codigo, nombre, tipo, descripcion, cid))
            else:
                conn.execute(
                    "UPDATE centros SET codigo=?, nombre=?, tipo=?, descripcion=?, regla_defecto=? WHERE id=?",
                    (codigo, nombre, tipo, descripcion, regla_defecto, cid))
            return cid
        cur = conn.execute(
            """INSERT INTO centros (codigo, nombre, tipo, descripcion, regla_defecto)
               VALUES (?,?,?,?,?)
               ON CONFLICT(codigo) DO UPDATE SET nombre=excluded.nombre,
                 tipo=excluded.tipo, descripcion=excluded.descripcion""",
            (codigo, nombre, tipo, descripcion, regla_defecto or ""),
        )
        if cur.lastrowid:
            return cur.lastrowid
        return conn.execute("SELECT id FROM centros WHERE codigo=?", (codigo,)).fetchone()["id"]


def delete_centro(conn, cid: int) -> None:
    with conn:
        conn.execute("DELETE FROM centros WHERE id=?", (cid,))


# --- Cuentas --------------------------------------------------------------
def list_cuentas(conn) -> List[Dict[str, Any]]:
    return rows_to_dicts(conn.execute("SELECT * FROM cuentas ORDER BY codigo").fetchall())


def upsert_cuenta(conn, codigo, nombre, grupo="", cid=None) -> int:
    with conn:
        if cid:
            conn.execute("UPDATE cuentas SET codigo=?, nombre=?, grupo=? WHERE id=?",
                         (codigo, nombre, grupo, cid))
            return cid
        cur = conn.execute(
            """INSERT INTO cuentas (codigo, nombre, grupo) VALUES (?,?,?)
               ON CONFLICT(codigo) DO UPDATE SET nombre=excluded.nombre, grupo=excluded.grupo""",
            (codigo, nombre, grupo),
        )
        if cur.lastrowid:
            return cur.lastrowid
        return conn.execute("SELECT id FROM cuentas WHERE codigo=?", (codigo,)).fetchone()["id"]


def delete_cuenta(conn, cid: int) -> None:
    with conn:
        conn.execute("DELETE FROM cuentas WHERE id=?", (cid,))


# --- Documentos -----------------------------------------------------------
def list_documentos(conn, estado=None, centro_id=None, tipo=None, cuenta_id=None,
                    ejercicio=None, periodo=None, texto=None, fecha_desde=None,
                    fecha_hasta=None, importe_min=None, importe_max=None,
                    ids=None) -> List[Dict[str, Any]]:
    q = ("SELECT d.*, c.codigo AS cuenta_codigo, c.nombre AS cuenta_nombre, "
         "ce.codigo AS centro_codigo, ce.nombre AS centro_nombre "
         "FROM documentos d "
         "LEFT JOIN cuentas c ON c.id = d.cuenta_id "
         "LEFT JOIN centros ce ON ce.id = d.centro_id WHERE 1=1")
    params: List[Any] = []
    if estado:
        q += " AND d.estado=?"; params.append(estado)
    if centro_id:
        q += " AND d.centro_id=?"; params.append(centro_id)
    if tipo:
        q += " AND d.tipo=?"; params.append(tipo)
    if cuenta_id:
        q += " AND d.cuenta_id=?"; params.append(cuenta_id)
    if ejercicio:
        q += " AND d.ejercicio=?"; params.append(int(ejercicio))
    if periodo:
        q += " AND d.periodo=?"; params.append(int(periodo))
    if texto:
        like = f"%{texto}%"
        q += " AND (d.numero LIKE ? OR d.tercero LIKE ? OR d.concepto LIKE ?)"
        params += [like, like, like]
    if fecha_desde:
        q += " AND d.fecha >= ?"; params.append(fecha_desde)
    if fecha_hasta:
        q += " AND d.fecha <= ?"; params.append(fecha_hasta)
    if importe_min not in (None, ""):
        q += " AND d.importe >= ?"; params.append(float(importe_min))
    if importe_max not in (None, ""):
        q += " AND d.importe <= ?"; params.append(float(importe_max))
    if ids:
        q += f" AND d.id IN ({','.join('?' for _ in ids)})"; params += list(ids)
    q += " ORDER BY d.fecha DESC, d.id DESC"
    return rows_to_dicts(conn.execute(q, params).fetchall())


def get_documento(conn, did: int) -> Optional[Dict[str, Any]]:
    r = conn.execute(
        "SELECT d.*, c.codigo AS cuenta_codigo, c.nombre AS cuenta_nombre, "
        "ce.codigo AS centro_codigo, ce.nombre AS centro_nombre "
        "FROM documentos d LEFT JOIN cuentas c ON c.id=d.cuenta_id "
        "LEFT JOIN centros ce ON ce.id=d.centro_id WHERE d.id=?", (did,)).fetchone()
    return dict(r) if r else None


def insert_documento(conn, **kw) -> int:
    importe = float(kw.get("importe", 0) or 0)
    iva_pct = float(kw.get("iva_pct", 0) or 0)
    iva_importe = kw.get("iva_importe")
    if iva_importe in (None, "") and iva_pct:
        iva_importe = round(importe * iva_pct / 100, 2)
    iva_importe = float(iva_importe or 0)
    ejercicio, periodo = periodo_desde_fecha(kw.get("fecha", ""))
    with conn:
        cur = conn.execute(
            """INSERT INTO documentos (tipo, numero, fecha, tercero, tercero_id, concepto,
               importe, iva_pct, iva_importe, total, ejercicio, periodo,
               cuenta_id, centro_id, estado, notas)
               VALUES (:tipo,:numero,:fecha,:tercero,:tercero_id,:concepto,
                       :importe,:iva_pct,:iva_importe,:total,:ejercicio,:periodo,
                       :cuenta_id,:centro_id,:estado,:notas)""",
            {
                "tipo": kw.get("tipo", "factura"),
                "numero": kw.get("numero", ""),
                "fecha": kw.get("fecha", ""),
                "tercero": kw.get("tercero", ""),
                "tercero_id": kw.get("tercero_id"),
                "concepto": kw.get("concepto", ""),
                "importe": importe,
                "iva_pct": iva_pct,
                "iva_importe": iva_importe,
                "total": round(importe + iva_importe, 2),
                "ejercicio": ejercicio,
                "periodo": periodo,
                "cuenta_id": kw.get("cuenta_id"),
                "centro_id": kw.get("centro_id"),
                "estado": kw.get("estado", "pendiente"),
                "notas": kw.get("notas", ""),
            },
        )
        return cur.lastrowid


def update_documento(conn, did, **kw) -> None:
    campos = ["tipo", "numero", "fecha", "tercero", "tercero_id", "concepto", "importe",
              "iva_pct", "iva_importe", "cuenta_id", "centro_id", "estado", "notas"]
    sets, params = [], []
    for c in campos:
        if c in kw:
            sets.append(f"{c}=?")
            params.append(kw[c])
    # recalcula derivados si cambia importe/iva/fecha
    if "importe" in kw or "iva_pct" in kw or "iva_importe" in kw:
        cur = get_documento(conn, did) or {}
        importe = float(kw.get("importe", cur.get("importe", 0)) or 0)
        iva_pct = float(kw.get("iva_pct", cur.get("iva_pct", 0)) or 0)
        if "iva_importe" in kw and kw["iva_importe"] not in (None, ""):
            iva_importe = float(kw["iva_importe"] or 0)
        elif iva_pct:
            iva_importe = round(importe * iva_pct / 100, 2)
        else:
            iva_importe = float(cur.get("iva_importe", 0) or 0)
        sets += ["iva_importe=?", "total=?"]
        params += [iva_importe, round(importe + iva_importe, 2)]
    if "fecha" in kw:
        ej, per = periodo_desde_fecha(kw["fecha"])
        sets += ["ejercicio=?", "periodo=?"]
        params += [ej, per]
    if not sets:
        return
    params.append(did)
    with conn:
        conn.execute(f"UPDATE documentos SET {', '.join(sets)} WHERE id=?", params)


def delete_documento(conn, did: int) -> None:
    with conn:
        conn.execute("DELETE FROM documentos WHERE id=?", (did,))


# --- Repartos -------------------------------------------------------------
def get_repartos(conn, documento_id: int) -> List[Dict[str, Any]]:
    return rows_to_dicts(conn.execute(
        "SELECT * FROM repartos WHERE documento_id=? ORDER BY id", (documento_id,)).fetchall())


def replace_repartos(conn, documento_id: int, lines: List[Dict[str, Any]]) -> None:
    """Sustituye el reparto de un documento y actualiza su estado."""
    with conn:
        conn.execute("DELETE FROM repartos WHERE documento_id=?", (documento_id,))
        for l in lines:
            conn.execute(
                """INSERT INTO repartos (documento_id, proyecto_id, proyecto_codigo,
                   importe, porcentaje, base) VALUES (?,?,?,?,?,?)""",
                (documento_id, l.get("proyecto_id"), l.get("proyecto_codigo", ""),
                 float(l.get("importe", 0)), float(l.get("porcentaje", 0)), l.get("base", "")),
            )
        estado = "repartido" if lines else "pendiente"
        conn.execute("UPDATE documentos SET estado=? WHERE id=?", (estado, documento_id))


# --- Informes -------------------------------------------------------------
def resumen_por_proyecto(conn) -> List[Dict[str, Any]]:
    return rows_to_dicts(conn.execute(
        """SELECT p.id, p.codigo, p.nombre, p.presupuesto,
                  COALESCE(SUM(r.importe),0) AS imputado,
                  COUNT(r.id) AS n_lineas
           FROM proyectos p
           LEFT JOIN repartos r ON r.proyecto_id = p.id
           GROUP BY p.id ORDER BY imputado DESC""").fetchall())


def resumen_por_centro(conn) -> List[Dict[str, Any]]:
    return rows_to_dicts(conn.execute(
        """SELECT ce.id, ce.codigo, ce.nombre, ce.tipo,
                  COALESCE(SUM(d.importe),0) AS importe, COUNT(d.id) AS n_docs
           FROM centros ce LEFT JOIN documentos d ON d.centro_id = ce.id
           GROUP BY ce.id ORDER BY importe DESC""").fetchall())


def detalle_proyecto(conn, proyecto_id: int) -> List[Dict[str, Any]]:
    return rows_to_dicts(conn.execute(
        """SELECT r.importe, r.porcentaje, r.base,
                  d.numero, d.fecha, d.tercero, d.concepto, d.tipo, d.importe AS doc_importe,
                  ce.codigo AS centro_codigo
           FROM repartos r JOIN documentos d ON d.id = r.documento_id
           LEFT JOIN centros ce ON ce.id = d.centro_id
           WHERE r.proyecto_id=? ORDER BY d.fecha DESC, r.id DESC""",
        (proyecto_id,)).fetchall())


def totales(conn, ejercicio=None) -> Dict[str, Any]:
    q = ("""SELECT COUNT(*) AS n_docs, COALESCE(SUM(importe),0) AS total,
                  COALESCE(SUM(CASE WHEN estado='pendiente' THEN importe ELSE 0 END),0) AS pendiente,
                  SUM(CASE WHEN estado='pendiente' THEN 1 ELSE 0 END) AS n_pendientes
           FROM documentos WHERE 1=1""")
    params: List[Any] = []
    if ejercicio:
        q += " AND ejercicio=?"; params.append(int(ejercicio))
    return dict(conn.execute(q, params).fetchone())


# --- Terceros -------------------------------------------------------------
def list_terceros(conn) -> List[Dict[str, Any]]:
    return rows_to_dicts(conn.execute("SELECT * FROM terceros ORDER BY nombre").fetchall())


def upsert_tercero(conn, nombre, nif="", tipo="proveedor", tid=None) -> int:
    with conn:
        if tid:
            conn.execute("UPDATE terceros SET nombre=?, nif=?, tipo=? WHERE id=?",
                         (nombre, nif, tipo, tid))
            return tid
        cur = conn.execute(
            """INSERT INTO terceros (nombre, nif, tipo) VALUES (?,?,?)
               ON CONFLICT(nombre) DO UPDATE SET nif=excluded.nif, tipo=excluded.tipo""",
            (nombre, nif, tipo))
        if cur.lastrowid:
            return cur.lastrowid
        return conn.execute("SELECT id FROM terceros WHERE nombre=?", (nombre,)).fetchone()["id"]


def delete_tercero(conn, tid: int) -> None:
    with conn:
        conn.execute("DELETE FROM terceros WHERE id=?", (tid,))


# --- Reglas ---------------------------------------------------------------
def list_reglas(conn) -> List[Dict[str, Any]]:
    return rows_to_dicts(conn.execute("SELECT * FROM reglas ORDER BY nombre").fetchall())


def upsert_regla(conn, nombre, texto, rid=None) -> int:
    with conn:
        if rid:
            conn.execute("UPDATE reglas SET nombre=?, texto=? WHERE id=?", (nombre, texto, rid))
            return rid
        cur = conn.execute("INSERT INTO reglas (nombre, texto) VALUES (?,?)", (nombre, texto))
        return cur.lastrowid


def delete_regla(conn, rid: int) -> None:
    with conn:
        conn.execute("DELETE FROM reglas WHERE id=?", (rid,))


# --- Informes adicionales -------------------------------------------------
def resumen_por_cuenta(conn) -> List[Dict[str, Any]]:
    return rows_to_dicts(conn.execute(
        """SELECT c.id, c.codigo, c.nombre, c.grupo,
                  COALESCE(SUM(d.importe),0) AS importe, COUNT(d.id) AS n_docs
           FROM cuentas c LEFT JOIN documentos d ON d.cuenta_id = c.id
           GROUP BY c.id ORDER BY importe DESC""").fetchall())


def serie_mensual(conn, ejercicio=None) -> List[Dict[str, Any]]:
    q = ("SELECT periodo, COALESCE(SUM(importe),0) AS importe FROM documentos "
         "WHERE periodo IS NOT NULL")
    params: List[Any] = []
    if ejercicio:
        q += " AND ejercicio=?"; params.append(int(ejercicio))
    q += " GROUP BY periodo ORDER BY periodo"
    return rows_to_dicts(conn.execute(q, params).fetchall())


def ejercicios(conn) -> List[int]:
    rows = conn.execute(
        "SELECT DISTINCT ejercicio FROM documentos WHERE ejercicio IS NOT NULL ORDER BY ejercicio DESC"
    ).fetchall()
    return [r["ejercicio"] for r in rows]
