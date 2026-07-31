"""Prueba de humo de la app Flask completa (rutas + reparto + Excel)."""

import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# BD temporal aislada
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["COSTCONTROL_DB"] = _tmp.name

from costcontrol import db, importer  # noqa: E402
from costcontrol.app import app  # noqa: E402


def run():
    db.init_db()
    import seed_demo
    seed_demo.seed()
    client = app.test_client()
    ok = 0

    # páginas principales
    for url in ["/", "/documentos", "/proyectos", "/centros", "/cuentas", "/importar", "/informe"]:
        r = client.get(url)
        assert r.status_code == 200, f"{url} -> {r.status_code}"
        ok += 1
        print(f"  ok  GET {url}")

    conn = db.connect()
    doc = db.list_documentos(conn)[0]
    did = doc["id"]
    conn.close()

    # previsualización de reparto (traducción en vivo)
    r = client.post(f"/documentos/{did}/reparto/previsualizar",
                    json={"texto": "60% PROY-A, 40% PROY-B"})
    d = r.get_json()
    assert d["ok"] and len(d["lineas"]) == 2, d
    assert abs(d["repartido"] - doc["importe"]) < 0.01
    print("  ok  previsualizar reparto porcentajes"); ok += 1

    # guardar reparto
    r = client.post(f"/documentos/{did}/reparto/guardar",
                    data={"texto": "a partes iguales entre PROY-A, PROY-B, PROY-C"},
                    follow_redirects=True)
    assert r.status_code == 200
    conn = db.connect()
    reps = db.get_repartos(conn, did)
    assert len(reps) == 3, reps
    doc2 = db.get_documento(conn, did)
    assert doc2["estado"] == "repartido"
    conn.close()
    print("  ok  guardar reparto a partes iguales"); ok += 1

    # reparto ponderado por driver
    conn = db.connect()
    doc_b = [x for x in db.list_documentos(conn) if x["id"] != did][0]
    conn.close()
    r = client.post(f"/documentos/{doc_b['id']}/reparto/previsualizar",
                    json={"texto": "según superficie"})
    d = r.get_json()
    assert d["ok"] and len(d["lineas"]) == 3, d
    print("  ok  reparto ponderado por driver"); ok += 1

    # plantillas Excel descargables
    for clase in ["documentos", "proyectos", "centros", "cuentas"]:
        r = client.get(f"/plantilla/{clase}")
        assert r.status_code == 200 and len(r.data) > 500
    print("  ok  plantillas Excel"); ok += 1

    # exportar informe
    r = client.get("/informe/exportar")
    assert r.status_code == 200 and r.data[:2] == b"PK"
    print("  ok  exportar informe Excel"); ok += 1

    # importar documentos desde Excel generado
    data = importer.plantilla_documentos()
    r = client.post("/importar",
                    data={"destino": "documentos", "tipo_defecto": "factura",
                          "archivo": (io.BytesIO(data), "docs.xlsx")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    conn = db.connect()
    n = len(db.list_documentos(conn))
    conn.close()
    assert n >= 7, f"esperados >=7 documentos, hay {n}"
    print("  ok  importar Excel de documentos"); ok += 1

    print(f"\nTODO OK ({ok} comprobaciones)")


if __name__ == "__main__":
    try:
        run()
    finally:
        try:
            os.unlink(_tmp.name)
        except OSError:
            pass
