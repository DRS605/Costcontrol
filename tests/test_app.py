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
    for url in ["/", "/documentos", "/proyectos", "/centros", "/cuentas", "/importar",
                "/informe", "/terceros", "/reglas", "/reparto-masivo"]:
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
    assert n >= 8, f"esperados >=8 documentos, hay {n}"
    print("  ok  importar Excel de documentos"); ok += 1

    # filtros avanzados + exportación de documentos
    r = client.get("/documentos?estado=pendiente&texto=Material")
    assert r.status_code == 200
    r = client.get("/documentos/exportar?estado=pendiente")
    assert r.status_code == 200 and r.data[:2] == b"PK"
    print("  ok  filtros + exportar documentos"); ok += 1

    # terceros CRUD
    r = client.post("/terceros/guardar", data={"nombre": "Proveedor Test SL", "nif": "B12345678"},
                    follow_redirects=True)
    assert r.status_code == 200
    conn = db.connect(); ters = db.list_terceros(conn); conn.close()
    assert any(t["nombre"] == "Proveedor Test SL" for t in ters)
    print("  ok  alta de tercero"); ok += 1

    # reglas CRUD
    r = client.post("/reglas/guardar", data={"nombre": "Regla Test", "texto": "todo a PROY-A"},
                    follow_redirects=True)
    assert r.status_code == 200
    conn = db.connect(); regs = db.list_reglas(conn); conn.close()
    assert any(x["nombre"] == "Regla Test" for x in regs)
    print("  ok  alta de regla"); ok += 1

    # referenciar una regla guardada desde el reparto ("como la regla X")
    conn = db.connect()
    db.upsert_regla(conn, "Mitades", "a partes iguales entre PROY-A, PROY-B")
    dref = db.list_documentos(conn)[0]
    conn.close()
    r = client.post(f"/documentos/{dref['id']}/reparto/previsualizar",
                    json={"texto": "como la regla Mitades"})
    d = r.get_json()
    assert d["ok"] and len(d["lineas"]) == 2, d
    assert abs(d["repartido"] - dref["importe"]) < 0.01
    print("  ok  referenciar regla guardada (como la regla X)"); ok += 1

    # reparto masivo sobre documentos pendientes
    conn = db.connect()
    pend = db.list_documentos(conn, estado="pendiente")
    conn.close()
    ids = [str(d["id"]) for d in pend[:3]]
    r = client.post("/reparto-masivo/aplicar",
                    data={"texto": "a partes iguales entre PROY-A, PROY-B, PROY-C",
                          "doc_ids": ids}, follow_redirects=True)
    assert r.status_code == 200
    conn = db.connect()
    for did2 in ids:
        reps = db.get_repartos(conn, int(did2))
        assert len(reps) == 3, f"doc {did2}: {reps}"
    conn.close()
    print("  ok  reparto masivo por regla"); ok += 1

    # regla por defecto de centro aplicada al importar
    conn = db.connect()
    cid = db.upsert_centro(conn, "CC-AUTO", "Centro auto", "coste", regla_defecto="todo a PROY-A")
    conn.close()
    wb_bytes = _excel_doc_centro("CC-AUTO")
    r = client.post("/importar", data={"destino": "documentos", "tipo_defecto": "factura",
                    "archivo": (io.BytesIO(wb_bytes), "auto.xlsx")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    conn = db.connect()
    autos = db.list_documentos(conn, centro_id=cid, estado="repartido")
    assert len(autos) >= 1, "el documento del centro con regla debería quedar repartido"
    conn.close()
    print("  ok  regla por defecto de centro al importar"); ok += 1

    # copia de seguridad JSON
    r = client.get("/backup")
    assert r.status_code == 200 and b'"documentos"' in r.data
    backup_bytes = r.data
    print("  ok  copia de seguridad JSON"); ok += 1

    # detección de duplicados al reimportar el mismo Excel
    data = importer.plantilla_documentos()
    conn = db.connect(); antes = len(db.list_documentos(conn)); conn.close()
    client.post("/importar", data={"destino": "documentos", "omitir_duplicados": "on",
                "archivo": (io.BytesIO(data), "docs.xlsx")},
                content_type="multipart/form-data", follow_redirects=True)
    conn = db.connect(); despues = len(db.list_documentos(conn)); conn.close()
    assert despues == antes, f"los duplicados no se omitieron: {antes} -> {despues}"
    print("  ok  duplicados omitidos al importar"); ok += 1

    # adjuntar archivo a un documento
    conn = db.connect(); did2 = db.list_documentos(conn)[0]["id"]; conn.close()
    r = client.post(f"/documentos/{did2}/editar",
                    data={"tipo": "factura", "importe": "100",
                          "adjunto": (io.BytesIO(b"%PDF-1.4 test"), "factura.pdf")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    conn = db.connect(); doc_adj = db.get_documento(conn, did2); conn.close()
    assert doc_adj["adjunto"], "no se guardó el adjunto"
    r = client.get(f"/documentos/{did2}/adjunto")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
    print("  ok  adjuntar y descargar factura"); ok += 1

    # reparto manual (ajuste línea a línea)
    r = client.post(f"/documentos/{did2}/reparto/guardar-manual",
                    data={"proyecto_codigo": ["PROY-A", "PROY-B"], "importe": ["70", "30"]},
                    follow_redirects=True)
    assert r.status_code == 200
    conn = db.connect(); reps = db.get_repartos(conn, did2); conn.close()
    assert len(reps) == 2 and abs(sum(x["importe"] for x in reps) - 100) < 0.01
    print("  ok  reparto manual línea a línea"); ok += 1

    # restaurar copia de seguridad
    r = client.post("/restaurar", data={"archivo": (io.BytesIO(backup_bytes), "backup.json")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    conn = db.connect(); n_rest = len(db.list_documentos(conn)); conn.close()
    assert n_rest > 0, "la restauración dejó la base vacía"
    print("  ok  restaurar copia de seguridad"); ok += 1

    # páginas nuevas
    assert client.get("/presupuestos").status_code == 200
    print("  ok  GET /presupuestos"); ok += 1

    # presupuesto mensual -> anual = suma
    conn = db.connect(); pid = db.list_proyectos(conn)[0]["id"]; conn.close()
    client.post("/presupuestos/guardar",
                data={"ejercicio": "2026", f"pres_{pid}_1": "1000", f"pres_{pid}_2": "500"},
                follow_redirects=True)
    conn = db.connect(); anual = db.presupuesto_anual(conn, pid, 2026); conn.close()
    assert abs(anual - 1500) < 0.01, anual
    print("  ok  presupuesto mensual y anual"); ok += 1

    # presupuesto por centro
    conn = db.connect(); cid_b = db.list_centros(conn)[0]["id"]; conn.close()
    client.post("/presupuestos/guardar",
                data={"ejercicio": "2026", f"presc_{cid_b}_1": "2000", f"presc_{cid_b}_3": "1000"},
                follow_redirects=True)
    conn = db.connect()
    anual_c = db.presupuesto_centro_anual(conn, cid_b, 2026)
    seg_c = db.seguimiento_centros(conn, 2026)
    conn.close()
    assert abs(anual_c - 3000) < 0.01, anual_c
    assert any(s["id"] == cid_b and s["estado"] != "sin_presupuesto" for s in seg_c)
    print("  ok  presupuesto por centro y seguimiento"); ok += 1

    # cierre de periodo bloquea el reparto
    conn = db.connect()
    docs1 = [d for d in db.list_documentos(conn) if d["ejercicio"] == 2026 and d["periodo"] == 1]
    conn.close()
    assert docs1, "no hay documentos en 2026-01 para probar el cierre"
    did1 = docs1[0]["id"]
    client.post("/cierres/cambiar",
                data={"ejercicio": "2026", "periodo": "1", "accion": "cerrar"},
                follow_redirects=True)
    conn = db.connect(); cerrado = db.is_cerrado(conn, 2026, 1); conn.close()
    assert cerrado, "el periodo no quedó cerrado"
    r = client.post(f"/documentos/{did1}/reparto/guardar",
                    data={"texto": "todo a PROY-A"}, follow_redirects=True)
    assert "cerrado".encode() in r.data.lower(), "no se bloqueó el reparto en periodo cerrado"
    print("  ok  cierre de periodo bloquea el reparto"); ok += 1

    # reabrir
    client.post("/cierres/cambiar",
                data={"ejercicio": "2026", "periodo": "1", "accion": "abrir"},
                follow_redirects=True)
    conn = db.connect(); reabierto = not db.is_cerrado(conn, 2026, 1); conn.close()
    assert reabierto
    print("  ok  reabrir periodo"); ok += 1

    print(f"\nTODO OK ({ok} comprobaciones)")


def _excel_doc_centro(centro_cod):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(["Tipo", "Numero", "Fecha", "Tercero", "Concepto", "Importe", "IVA", "Cuenta", "Centro"])
    ws.append(["factura", "AUTO-1", "2026-04-01", "Proveedor X", "Coste indirecto", 1000, 21, "600000", centro_cod])
    b = io.BytesIO(); wb.save(b); return b.getvalue()


if __name__ == "__main__":
    try:
        run()
    finally:
        try:
            os.unlink(_tmp.name)
        except OSError:
            pass
