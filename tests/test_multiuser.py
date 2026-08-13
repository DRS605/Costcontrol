"""Pruebas del modo multiusuario / multi-empresa (aislamiento por cliente)."""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configura el modo multiusuario ANTES de importar la app.
_TMP = tempfile.mkdtemp(prefix="cc_mu_")
os.environ["COSTCONTROL_MULTIUSER"] = "1"
os.environ["COSTCONTROL_DATA_DIR"] = _TMP
os.environ["COSTCONTROL_UPLOADS"] = os.path.join(_TMP, "uploads")
os.environ["COSTCONTROL_SECRET"] = "test-secret"

from costcontrol import auth  # noqa: E402
from costcontrol.app import app, bootstrap  # noqa: E402


def _registrar(client, empresa, email, pw="secreto123"):
    return client.post("/registro", data={
        "empresa": empresa, "email": email, "password": pw, "nombre": "Admin"
    }, follow_redirects=True)


def _crear_proyecto(client, codigo, nombre):
    return client.post("/proyectos/guardar", data={
        "codigo": codigo, "nombre": nombre, "presupuesto": "0", "activo": "1"
    }, follow_redirects=True)


def run():
    bootstrap()
    ok = 0

    # sin login, el panel redirige a la pantalla de acceso
    anon = app.test_client()
    r = anon.get("/", follow_redirects=False)
    assert r.status_code in (301, 302) and "/entrar" in r.headers.get("Location", "")
    ok += 1
    print("  ok  acceso protegido: redirige a login")

    # empresa A
    ca = app.test_client()
    r = _registrar(ca, "Empresa A", "a@a.com")
    assert r.status_code == 200
    assert b"Empresa A" in r.data
    ok += 1
    print("  ok  alta de empresa A + login automático")

    _crear_proyecto(ca, "AAA", "Proyecto de A")
    r = ca.get("/proyectos")
    assert b"AAA" in r.data
    ok += 1
    print("  ok  empresa A crea su proyecto")

    # empresa B (cliente distinto)
    cb = app.test_client()
    _registrar(cb, "Empresa B", "b@b.com")
    _crear_proyecto(cb, "BBB", "Proyecto de B")

    # AISLAMIENTO: A no ve datos de B y viceversa
    ra = ca.get("/proyectos")
    assert b"AAA" in ra.data and b"BBB" not in ra.data, "¡A ve datos de B!"
    rb = cb.get("/proyectos")
    assert b"BBB" in rb.data and b"AAA" not in rb.data, "¡B ve datos de A!"
    ok += 1
    print("  ok  aislamiento total entre empresas A y B")

    # cada empresa tiene su propio fichero de base de datos
    from costcontrol.auth import connect_auth
    conn = connect_auth()
    orgs = [r["id"] for r in conn.execute("SELECT id FROM organizaciones ORDER BY id").fetchall()]
    conn.close()
    assert len(orgs) == 2
    for oid in orgs:
        assert os.path.isfile(auth.tenant_db_path(oid)), "falta el fichero de datos del tenant"
    assert auth.tenant_db_path(orgs[0]) != auth.tenant_db_path(orgs[1])
    ok += 1
    print("  ok  una base de datos por empresa (ficheros separados)")

    # no se puede duplicar email
    try:
        auth.crear_organizacion("Otra", "a@a.com", "secreto123")
        assert False, "debería impedir email duplicado"
    except ValueError:
        ok += 1
        print("  ok  email duplicado rechazado")

    # login/logout con credenciales
    cc = app.test_client()
    r = cc.post("/entrar", data={"email": "a@a.com", "password": "malo"}, follow_redirects=True)
    assert "incorrect" in r.data.decode("utf-8", "ignore").lower()
    r = cc.post("/entrar", data={"email": "a@a.com", "password": "secreto123"}, follow_redirects=True)
    assert b"AAA" in cc.get("/proyectos").data
    cc.get("/salir")
    r = cc.get("/", follow_redirects=False)
    assert r.status_code in (301, 302)
    ok += 1
    print("  ok  login/logout con email y contraseña")

    print(f"\nTODO OK ({ok} comprobaciones)")


if __name__ == "__main__":
    try:
        run()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
