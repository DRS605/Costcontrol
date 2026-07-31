"""Aplicación web de CostControl (Flask)."""

from __future__ import annotations

import json
import os
from decimal import Decimal

from flask import (Flask, Response, abort, flash, redirect, render_template,
                   request, send_file, url_for)
import io

from . import db, importer
from .allocation import Allocator, Project, money

app = Flask(__name__)
app.secret_key = os.environ.get("COSTCONTROL_SECRET", "costcontrol-dev-secret")


# --- utilidades -----------------------------------------------------------
def get_conn():
    return db.connect()


def _projects_for_allocator(conn):
    out = []
    for p in db.list_proyectos(conn, solo_activos=True):
        drivers = {k: Decimal(str(v)) for k, v in (p.get("drivers") or {}).items()}
        out.append(Project(codigo=p["codigo"], nombre=p["nombre"], drivers=drivers))
    return out


@app.template_filter("eur")
def eur(value):
    try:
        d = Decimal(str(value or 0))
    except Exception:
        return value
    s = f"{d:,.2f}"
    # formato español: 1.234,56
    s = s.replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{s} €"


@app.context_processor
def inject_globals():
    return {"version": __import__("costcontrol").__version__}


# --- panel ----------------------------------------------------------------
@app.route("/")
def index():
    conn = get_conn()
    tot = db.totales(conn)
    por_proyecto = db.resumen_por_proyecto(conn)
    por_centro = db.resumen_por_centro(conn)
    conn.close()
    return render_template("index.html", tot=tot, por_proyecto=por_proyecto,
                           por_centro=por_centro)


# --- proyectos ------------------------------------------------------------
@app.route("/proyectos")
def proyectos():
    conn = get_conn()
    data = db.list_proyectos(conn)
    # imputado por proyecto para mostrar consumo
    resumen = {r["id"]: r for r in db.resumen_por_proyecto(conn)}
    conn.close()
    return render_template("proyectos.html", proyectos=data, resumen=resumen)


@app.route("/proyectos/guardar", methods=["POST"])
def proyectos_guardar():
    f = request.form
    drivers = {}
    for clave, valor in zip(f.getlist("driver_clave"), f.getlist("driver_valor")):
        clave = clave.strip()
        if clave:
            try:
                drivers[clave] = float(str(valor).replace(",", "."))
            except ValueError:
                drivers[clave] = 0
    conn = get_conn()
    db.upsert_proyecto(
        conn,
        codigo=f["codigo"].strip(),
        nombre=f.get("nombre", "").strip(),
        descripcion=f.get("descripcion", "").strip(),
        activo=1 if f.get("activo") else 0,
        presupuesto=float(str(f.get("presupuesto", "0") or "0").replace(".", "").replace(",", ".") or 0)
        if f.get("presupuesto") else 0,
        drivers=drivers,
        pid=int(f["id"]) if f.get("id") else None,
    )
    conn.close()
    flash("Proyecto guardado.", "ok")
    return redirect(url_for("proyectos"))


@app.route("/proyectos/<int:pid>/borrar", methods=["POST"])
def proyectos_borrar(pid):
    conn = get_conn()
    db.delete_proyecto(conn, pid)
    conn.close()
    flash("Proyecto eliminado.", "ok")
    return redirect(url_for("proyectos"))


# --- centros --------------------------------------------------------------
@app.route("/centros")
def centros():
    conn = get_conn()
    data = db.list_centros(conn)
    conn.close()
    return render_template("centros.html", centros=data)


@app.route("/centros/guardar", methods=["POST"])
def centros_guardar():
    f = request.form
    conn = get_conn()
    db.upsert_centro(conn, f["codigo"].strip(), f.get("nombre", "").strip(),
                     tipo=f.get("tipo", "coste"), descripcion=f.get("descripcion", "").strip(),
                     cid=int(f["id"]) if f.get("id") else None)
    conn.close()
    flash("Centro guardado.", "ok")
    return redirect(url_for("centros"))


@app.route("/centros/<int:cid>/borrar", methods=["POST"])
def centros_borrar(cid):
    conn = get_conn()
    db.delete_centro(conn, cid)
    conn.close()
    flash("Centro eliminado.", "ok")
    return redirect(url_for("centros"))


# --- cuentas --------------------------------------------------------------
@app.route("/cuentas")
def cuentas():
    conn = get_conn()
    data = db.list_cuentas(conn)
    conn.close()
    return render_template("cuentas.html", cuentas=data)


@app.route("/cuentas/guardar", methods=["POST"])
def cuentas_guardar():
    f = request.form
    conn = get_conn()
    db.upsert_cuenta(conn, f["codigo"].strip(), f.get("nombre", "").strip(),
                     grupo=f.get("grupo", "").strip(),
                     cid=int(f["id"]) if f.get("id") else None)
    conn.close()
    flash("Cuenta guardada.", "ok")
    return redirect(url_for("cuentas"))


@app.route("/cuentas/<int:cid>/borrar", methods=["POST"])
def cuentas_borrar(cid):
    conn = get_conn()
    db.delete_cuenta(conn, cid)
    conn.close()
    flash("Cuenta eliminada.", "ok")
    return redirect(url_for("cuentas"))


# --- documentos -----------------------------------------------------------
@app.route("/documentos")
def documentos():
    estado = request.args.get("estado") or None
    centro_id = request.args.get("centro") or None
    tipo = request.args.get("tipo") or None
    conn = get_conn()
    data = db.list_documentos(conn, estado=estado,
                              centro_id=int(centro_id) if centro_id else None, tipo=tipo)
    centros_l = db.list_centros(conn)
    conn.close()
    return render_template("documentos.html", documentos=data, centros=centros_l,
                           filtro={"estado": estado, "centro": centro_id, "tipo": tipo})


@app.route("/documentos/nuevo", methods=["GET", "POST"])
@app.route("/documentos/<int:did>/editar", methods=["GET", "POST"])
def documento_editar(did=None):
    conn = get_conn()
    if request.method == "POST":
        f = request.form
        def parse_imp(v):
            from .allocation import parse_number
            return float(parse_number(v) or 0)
        payload = dict(
            tipo=f.get("tipo", "factura"),
            numero=f.get("numero", "").strip(),
            fecha=f.get("fecha", "").strip(),
            tercero=f.get("tercero", "").strip(),
            concepto=f.get("concepto", "").strip(),
            importe=parse_imp(f.get("importe", "0")),
            cuenta_id=int(f["cuenta_id"]) if f.get("cuenta_id") else None,
            centro_id=int(f["centro_id"]) if f.get("centro_id") else None,
            notas=f.get("notas", "").strip(),
        )
        if did:
            db.update_documento(conn, did, **payload)
        else:
            did = db.insert_documento(conn, estado="pendiente", **payload)
        conn.close()
        flash("Documento guardado.", "ok")
        return redirect(url_for("documento_reparto", did=did))

    doc = db.get_documento(conn, did) if did else None
    if did and not doc:
        conn.close()
        abort(404)
    cuentas_l = db.list_cuentas(conn)
    centros_l = db.list_centros(conn)
    conn.close()
    return render_template("documento_editar.html", doc=doc, cuentas=cuentas_l, centros=centros_l)


@app.route("/documentos/<int:did>/borrar", methods=["POST"])
def documento_borrar(did):
    conn = get_conn()
    db.delete_documento(conn, did)
    conn.close()
    flash("Documento eliminado.", "ok")
    return redirect(url_for("documentos"))


# --- REPARTO ANALÍTICO (núcleo) ------------------------------------------
@app.route("/documentos/<int:did>/reparto")
def documento_reparto(did):
    conn = get_conn()
    doc = db.get_documento(conn, did)
    if not doc:
        conn.close()
        abort(404)
    proyectos_l = db.list_proyectos(conn, solo_activos=True)
    repartos = db.get_repartos(conn, did)
    reglas = db.rows_to_dicts(conn.execute("SELECT * FROM reglas ORDER BY nombre").fetchall())
    conn.close()
    # texto previo (si ya se repartió, reconstruye una pista)
    texto_previo = repartos[0]["base"] if False else ""
    return render_template("reparto.html", doc=doc, proyectos=proyectos_l,
                           repartos=repartos, reglas=reglas, texto_previo=texto_previo)


@app.route("/documentos/<int:did>/reparto/previsualizar", methods=["POST"])
def reparto_previsualizar(did):
    """Traduce el texto libre a un reparto concreto y lo devuelve como JSON."""
    conn = get_conn()
    doc = db.get_documento(conn, did)
    if not doc:
        conn.close()
        abort(404)
    projects = _projects_for_allocator(conn)
    conn.close()
    texto = request.json.get("texto", "") if request.is_json else request.form.get("texto", "")
    res = Allocator(projects).allocate(doc["importe"], texto)
    return {
        "ok": res.ok,
        "criterio": res.criterio,
        "total": float(res.total),
        "repartido": float(res.repartido),
        "lineas": [
            {"proyecto": l.proyecto, "nombre": l.nombre, "importe": float(l.importe),
             "porcentaje": float(l.porcentaje), "base": l.base}
            for l in res.lines
        ],
        "explicacion": res.explanation,
        "avisos": res.warnings,
    }


@app.route("/documentos/<int:did>/reparto/guardar", methods=["POST"])
def reparto_guardar(did):
    conn = get_conn()
    doc = db.get_documento(conn, did)
    if not doc:
        conn.close()
        abort(404)
    projects = _projects_for_allocator(conn)
    texto = request.form.get("texto", "")
    res = Allocator(projects).allocate(doc["importe"], texto)
    if not res.ok:
        conn.close()
        flash("No se pudo interpretar el reparto: " + " ".join(res.warnings), "error")
        return redirect(url_for("documento_reparto", did=did))

    # mapa código -> id
    cod2id = {p["codigo"]: p["id"] for p in db.list_proyectos(conn)}
    lines = [{
        "proyecto_id": cod2id.get(l.proyecto),
        "proyecto_codigo": l.proyecto,
        "importe": float(l.importe),
        "porcentaje": float(l.porcentaje),
        "base": f"{texto.strip()} · {l.base}",
    } for l in res.lines]
    db.replace_repartos(conn, did, lines)
    conn.close()
    flash(f"Reparto guardado: {len(lines)} línea(s) analítica(s).", "ok")
    return redirect(url_for("documento_reparto", did=did))


@app.route("/documentos/<int:did>/reparto/limpiar", methods=["POST"])
def reparto_limpiar(did):
    conn = get_conn()
    db.replace_repartos(conn, did, [])
    conn.close()
    flash("Reparto eliminado; el documento vuelve a estado pendiente.", "ok")
    return redirect(url_for("documento_reparto", did=did))


# --- reglas guardadas -----------------------------------------------------
@app.route("/reglas/guardar", methods=["POST"])
def reglas_guardar():
    f = request.form
    conn = get_conn()
    with conn:
        conn.execute("INSERT INTO reglas (nombre, texto) VALUES (?,?)",
                     (f.get("nombre", "").strip() or "Regla", f.get("texto", "").strip()))
    conn.close()
    flash("Regla de reparto guardada como plantilla.", "ok")
    return redirect(request.referrer or url_for("index"))


# --- importación ----------------------------------------------------------
@app.route("/importar", methods=["GET", "POST"])
def importar():
    if request.method == "POST":
        file = request.files.get("archivo")
        destino = request.form.get("destino", "documentos")
        if not file or not file.filename:
            flash("Selecciona un archivo Excel.", "error")
            return redirect(url_for("importar"))
        data = file.read()
        conn = get_conn()
        try:
            if destino == "documentos":
                r = importer.import_documentos(
                    conn, data, tipo_defecto=request.form.get("tipo_defecto", "factura"))
                msg = f"{r['importados']} documento(s) importado(s)."
                if r["cuentas_creadas"] or r["centros_creados"]:
                    msg += f" Creadas {r['cuentas_creadas']} cuenta(s) y {r['centros_creados']} centro(s)."
                if r["errores"]:
                    msg += " Incidencias: " + " | ".join(r["errores"][:5])
            else:
                r = importer.import_maestro(conn, data, destino)
                msg = f"{r['importados']} registro(s) importado(s) en {destino}."
                if r["errores"]:
                    msg += " Incidencias: " + " | ".join(r["errores"][:5])
        except Exception as e:  # noqa
            conn.close()
            flash(f"Error al leer el Excel: {e}", "error")
            return redirect(url_for("importar"))
        conn.close()
        flash(msg, "ok" if r["importados"] else "error")
        return redirect(url_for("documentos") if destino == "documentos" else url_for(destino))
    return render_template("importar.html")


@app.route("/importar/previsualizar", methods=["POST"])
def importar_previsualizar():
    file = request.files.get("archivo")
    if not file or not file.filename:
        return {"error": "Sin archivo"}, 400
    prev = importer.preview_workbook(file.read())
    return prev


# --- plantillas y exportación --------------------------------------------
@app.route("/plantilla/<clase>")
def plantilla(clase):
    if clase == "documentos":
        data = importer.plantilla_documentos()
        name = "plantilla_documentos.xlsx"
    elif clase in ("proyectos", "centros", "cuentas"):
        data = importer.plantilla_maestro(clase)
        name = f"plantilla_{clase}.xlsx"
    else:
        abort(404)
    return send_file(io.BytesIO(data), as_attachment=True, download_name=name,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/informe")
def informe():
    conn = get_conn()
    por_proyecto = db.resumen_por_proyecto(conn)
    por_centro = db.resumen_por_centro(conn)
    # detalle por proyecto
    detalle = {}
    for p in por_proyecto:
        detalle[p["id"]] = db.detalle_proyecto(conn, p["id"])
    conn.close()
    return render_template("informe.html", por_proyecto=por_proyecto,
                           por_centro=por_centro, detalle=detalle)


@app.route("/informe/exportar")
def informe_exportar():
    conn = get_conn()
    data = importer.export_informe(conn)
    conn.close()
    return send_file(io.BytesIO(data), as_attachment=True,
                     download_name="informe_costcontrol.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def create_app():
    db.init_db()
    return app


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=5000)
