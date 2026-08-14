"""Multiusuario / multi-empresa (control de acceso y aislamiento por cliente).

Modelo de aislamiento: **una base de datos por empresa** (tenant). Es el enfoque
más seguro con SQLite —los datos de un cliente viven en un fichero distinto, así
que es imposible que una consulta "se cuele" y muestre datos de otro cliente— y
además permite copiar o borrar un cliente moviendo un único archivo.

Este módulo gestiona el "plano de control" (un SQLite aparte) con las tablas de
**organizaciones** y **usuarios**. Los datos de negocio de cada organización
(proyectos, documentos, repartos…) siguen usando el esquema normal de `db.py`,
pero en el fichero de esa organización.

Se activa con la variable de entorno ``COSTCONTROL_MULTIUSER=1``. Si no, la app
funciona como siempre (monousuario, con contraseña opcional).
"""

from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash

from . import db


def multiuser_activo() -> bool:
    return (os.environ.get("COSTCONTROL_MULTIUSER") or "").strip().lower() in (
        "1", "true", "si", "sí", "yes", "on")


def _data_dir() -> str:
    d = os.environ.get("COSTCONTROL_DATA_DIR") or "data"
    os.makedirs(d, exist_ok=True)
    return d


def _auth_db_path() -> str:
    return os.environ.get("COSTCONTROL_AUTH_DB") or os.path.join(_data_dir(), "costcontrol_auth.db")


def tenant_db_path(org_id: int) -> str:
    """Ruta del fichero SQLite de datos de una organización."""
    return os.path.join(_data_dir(), f"tenant_{int(org_id)}.db")


_AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS organizaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    slug TEXT UNIQUE,
    plan TEXT NOT NULL DEFAULT 'basico',
    activo INTEGER NOT NULL DEFAULT 1,
    creado TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizaciones(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nombre TEXT NOT NULL DEFAULT '',
    rol TEXT NOT NULL DEFAULT 'admin',      -- admin | usuario
    activo INTEGER NOT NULL DEFAULT 1,
    creado TEXT DEFAULT (datetime('now')),
    ultimo_acceso TEXT
);
CREATE INDEX IF NOT EXISTS idx_usuarios_org ON usuarios(org_id);
"""


def connect_auth() -> sqlite3.Connection:
    conn = sqlite3.connect(_auth_db_path(), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def init_auth_db() -> None:
    conn = connect_auth()
    with conn:
        conn.executescript(_AUTH_SCHEMA)
    conn.close()


def _slug(nombre: str) -> str:
    s = unicodedata.normalize("NFD", str(nombre or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "empresa"


def _email_norm(email: str) -> str:
    return (email or "").strip().lower()


def email_valido(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", _email_norm(email)))


def email_existe(conn, email: str) -> bool:
    row = conn.execute("SELECT 1 FROM usuarios WHERE email=?", (_email_norm(email),)).fetchone()
    return row is not None


def crear_organizacion(nombre_empresa: str, email: str, password: str,
                       nombre_usuario: str = "") -> dict:
    """Crea una organización nueva con su primer usuario administrador.

    Crea también el fichero de datos aislado de la organización. Lanza
    ValueError si el email ya existe o los datos no son válidos.
    """
    nombre_empresa = (nombre_empresa or "").strip()
    email = _email_norm(email)
    if not nombre_empresa:
        raise ValueError("Indica el nombre de la empresa.")
    if not email_valido(email):
        raise ValueError("El email no es válido.")
    if len(password or "") < 6:
        raise ValueError("La contraseña debe tener al menos 6 caracteres.")

    conn = connect_auth()
    try:
        if email_existe(conn, email):
            raise ValueError("Ya existe una cuenta con ese email.")
        # slug único
        base = _slug(nombre_empresa)
        slug, i = base, 2
        while conn.execute("SELECT 1 FROM organizaciones WHERE slug=?", (slug,)).fetchone():
            slug, i = f"{base}-{i}", i + 1
        with conn:
            cur = conn.execute(
                "INSERT INTO organizaciones (nombre, slug) VALUES (?, ?)",
                (nombre_empresa, slug))
            org_id = cur.lastrowid
            conn.execute(
                "INSERT INTO usuarios (org_id, email, password_hash, nombre, rol) "
                "VALUES (?, ?, ?, ?, 'admin')",
                (org_id, email, generate_password_hash(password), (nombre_usuario or "").strip()))
    finally:
        conn.close()

    # crea el fichero de datos aislado de la organización
    db.init_db(tenant_db_path(org_id))
    return {"org_id": org_id, "email": email, "org_nombre": nombre_empresa}


def crear_usuario(org_id: int, email: str, password: str, nombre: str = "",
                  rol: str = "usuario") -> dict:
    """Añade un usuario a una organización existente (para equipos)."""
    email = _email_norm(email)
    if not email_valido(email):
        raise ValueError("El email no es válido.")
    if len(password or "") < 6:
        raise ValueError("La contraseña debe tener al menos 6 caracteres.")
    rol = "admin" if rol == "admin" else "usuario"
    conn = connect_auth()
    try:
        if email_existe(conn, email):
            raise ValueError("Ya existe una cuenta con ese email.")
        with conn:
            cur = conn.execute(
                "INSERT INTO usuarios (org_id, email, password_hash, nombre, rol) "
                "VALUES (?, ?, ?, ?, ?)",
                (int(org_id), email, generate_password_hash(password), (nombre or "").strip(), rol))
            return {"id": cur.lastrowid, "email": email, "rol": rol}
    finally:
        conn.close()


def autenticar(email: str, password: str) -> Optional[dict]:
    """Devuelve los datos del usuario si el email/contraseña son correctos."""
    email = _email_norm(email)
    conn = connect_auth()
    try:
        u = conn.execute(
            "SELECT u.*, o.nombre AS org_nombre, o.activo AS org_activo "
            "FROM usuarios u JOIN organizaciones o ON o.id=u.org_id WHERE u.email=?",
            (email,)).fetchone()
        if not u or not u["activo"] or not u["org_activo"]:
            return None
        if not check_password_hash(u["password_hash"], password or ""):
            return None
        with conn:
            conn.execute("UPDATE usuarios SET ultimo_acceso=datetime('now') WHERE id=?", (u["id"],))
        return {"id": u["id"], "org_id": u["org_id"], "email": u["email"],
                "nombre": u["nombre"], "rol": u["rol"], "org_nombre": u["org_nombre"]}
    finally:
        conn.close()


def get_usuario(user_id: int) -> Optional[dict]:
    conn = connect_auth()
    try:
        u = conn.execute(
            "SELECT u.*, o.nombre AS org_nombre, o.activo AS org_activo "
            "FROM usuarios u JOIN organizaciones o ON o.id=u.org_id WHERE u.id=?",
            (int(user_id),)).fetchone()
        if not u or not u["activo"] or not u["org_activo"]:
            return None
        return {"id": u["id"], "org_id": u["org_id"], "email": u["email"],
                "nombre": u["nombre"], "rol": u["rol"], "org_nombre": u["org_nombre"]}
    finally:
        conn.close()


def listar_usuarios(org_id: int) -> list:
    conn = connect_auth()
    try:
        rows = conn.execute(
            "SELECT id, email, nombre, rol, activo, creado, ultimo_acceso "
            "FROM usuarios WHERE org_id=? ORDER BY creado", (int(org_id),)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
