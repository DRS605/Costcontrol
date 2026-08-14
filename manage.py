#!/usr/bin/env python3
"""Herramienta de administración de CostControl (modo multi-empresa).

Para el operador del servicio (tú). Permite dar soporte sin depender del email:
crear empresas, restablecer contraseñas, listar y activar/desactivar usuarios.

Necesita las mismas variables de entorno que la app (COSTCONTROL_DATA_DIR, etc.).

Ejemplos:
    python manage.py listar-empresas
    python manage.py listar-usuarios --org 3
    python manage.py crear-empresa "Mi Cliente SL" cliente@correo.com
    python manage.py reset-password cliente@correo.com
    python manage.py reset-password cliente@correo.com --password nueva123
    python manage.py desactivar cliente@correo.com
    python manage.py activar cliente@correo.com
"""

import argparse
import secrets
import sys

from costcontrol import auth


def _pwd(arg):
    return arg or (secrets.token_urlsafe(9))


def cmd_listar_empresas(_):
    auth.init_auth_db()
    conn = auth.connect_auth()
    rows = conn.execute(
        "SELECT o.id, o.nombre, o.activo, o.creado, "
        "(SELECT COUNT(*) FROM usuarios u WHERE u.org_id=o.id) AS n "
        "FROM organizaciones o ORDER BY o.id").fetchall()
    conn.close()
    if not rows:
        print("(no hay empresas)")
        return
    print(f"{'ID':>3}  {'Empresa':32}  {'Usuarios':>8}  Estado   Creada")
    for r in rows:
        estado = "activa" if r["activo"] else "INACTIVA"
        print(f"{r['id']:>3}  {r['nombre'][:32]:32}  {r['n']:>8}  {estado:8} {r['creado']}")


def cmd_listar_usuarios(args):
    auth.init_auth_db()
    usuarios = auth.listar_usuarios(args.org)
    if not usuarios:
        print("(sin usuarios)")
        return
    for u in usuarios:
        estado = "activo" if u["activo"] else "INACTIVO"
        print(f"[{u['id']}] {u['email']:32} {u['rol']:8} {estado:9} último: {u['ultimo_acceso'] or '—'}")


def cmd_crear_empresa(args):
    auth.init_auth_db()
    pwd = _pwd(args.password)
    r = auth.crear_organizacion(args.empresa, args.email, pwd, args.nombre or "")
    print(f"Empresa creada: {r['org_nombre']} (id {r['org_id']})")
    print(f"Usuario admin:  {r['email']}")
    print(f"Contraseña:     {pwd}")
    print("Compártela con el cliente por un canal seguro; que la cambie al entrar.")


def cmd_reset_password(args):
    auth.init_auth_db()
    conn = auth.connect_auth()
    u = conn.execute("SELECT id, org_id FROM usuarios WHERE email=?",
                     (args.email.strip().lower(),)).fetchone()
    conn.close()
    if not u:
        print(f"No existe el usuario {args.email}", file=sys.stderr)
        sys.exit(1)
    pwd = _pwd(args.password)
    auth.admin_reset_password(u["org_id"], u["id"], pwd)
    print(f"Contraseña de {args.email} restablecida a: {pwd}")


def _set_estado(email, activo):
    auth.init_auth_db()
    conn = auth.connect_auth()
    u = conn.execute("SELECT id, org_id FROM usuarios WHERE email=?",
                     (email.strip().lower(),)).fetchone()
    conn.close()
    if not u:
        print(f"No existe el usuario {email}", file=sys.stderr)
        sys.exit(1)
    auth.set_activo(u["org_id"], u["id"], activo)
    print(f"{email} -> {'activo' if activo else 'inactivo'}")


def cmd_activar(args):
    _set_estado(args.email, True)


def cmd_desactivar(args):
    _set_estado(args.email, False)


def main():
    p = argparse.ArgumentParser(description="Administración de CostControl (multi-empresa).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("listar-empresas").set_defaults(func=cmd_listar_empresas)

    s = sub.add_parser("listar-usuarios")
    s.add_argument("--org", type=int, required=True)
    s.set_defaults(func=cmd_listar_usuarios)

    s = sub.add_parser("crear-empresa")
    s.add_argument("empresa")
    s.add_argument("email")
    s.add_argument("--nombre", default="")
    s.add_argument("--password", default="")
    s.set_defaults(func=cmd_crear_empresa)

    s = sub.add_parser("reset-password")
    s.add_argument("email")
    s.add_argument("--password", default="")
    s.set_defaults(func=cmd_reset_password)

    s = sub.add_parser("activar")
    s.add_argument("email")
    s.set_defaults(func=cmd_activar)

    s = sub.add_parser("desactivar")
    s.add_argument("email")
    s.set_defaults(func=cmd_desactivar)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
