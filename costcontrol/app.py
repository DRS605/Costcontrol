"""Aplicación web de CostControl (Flask)."""

from __future__ import annotations

import json
import os
from decimal import Decimal

from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, send_file, session, url_for)
import io

from . import ai, auth, charts, db, importer
from .allocation import Allocator, Project, money

MESES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

app = Flask(__name__)
app.secret_key = os.environ.get("COSTCONTROL_SECRET", "costcontrol-dev-secret")

# Acceso opcional: si se define COSTCONTROL_PASSWORD, se exige contraseña.
PASSWORD = os.environ.get("COSTCONTROL_PASSWORD", "").strip()

# Multiusuario / multi-empresa: cada cliente en su propia base de datos aislada.
MULTIUSER = auth.multiuser_activo()


def _truthy(name):
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "si", "sí", "yes", "on")


# Endurecimiento para producción (detrás de HTTPS/proxy): COSTCONTROL_SECURE=1
SECURE = _truthy("COSTCONTROL_SECURE")
if SECURE:
    from werkzeug.middleware.proxy_fix import ProxyFix
    # Confía en las cabeceras del proxy (Render/nginx) para HTTPS y la IP real.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PREFERRED_URL_SCHEME="https",
    )
    if app.secret_key == "costcontrol-dev-secret":
        import warnings
        warnings.warn("COSTCONTROL_SECRET no está definido: define una clave larga y secreta en producción.")

# Carpeta para adjuntos (facturas/albaranes en PDF o imagen).
UPLOADS = os.environ.get(
    "COSTCONTROL_UPLOADS",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads"))
os.makedirs(UPLOADS, exist_ok=True)
ADJUNTO_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".xlsx", ".xls", ".doc", ".docx"}
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB por subida


def _uploads_dir():
    """Carpeta de adjuntos, aislada por organización en modo multiusuario."""
    d = UPLOADS
    if MULTIUSER and getattr(g, "org_id", None):
        d = os.path.join(UPLOADS, f"org_{g.org_id}")
    os.makedirs(d, exist_ok=True)
    return d


def _guardar_adjunto(did, file):
    """Guarda el archivo subido y devuelve el nombre almacenado (o None)."""
    from werkzeug.utils import secure_filename
    import uuid
    if not file or not file.filename:
        return None
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ADJUNTO_EXT:
        return None
    base = secure_filename(os.path.splitext(file.filename)[0])[:60] or "adjunto"
    stored = f"doc{did}_{uuid.uuid4().hex[:8]}_{base}{ext}"
    file.save(os.path.join(_uploads_dir(), stored))
    return stored


_PUBLIC_ENDPOINTS = ("login", "logout", "registro", "static", "salud",
                     "recuperar", "restablecer",
                     "privacidad", "condiciones", "aviso_legal")
_tenants_inicializados = set()


@app.route("/salud")
def salud():
    """Comprobación de salud para el hosting (sin autenticación)."""
    return {"ok": True, "version": __import__("costcontrol").__version__,
            "multiusuario": MULTIUSER}


def _legal_ctx():
    """Datos de la empresa que presta el servicio (para las páginas legales)."""
    return {
        "empresa": os.environ.get("COSTCONTROL_EMPRESA", "[NOMBRE DE TU EMPRESA]"),
        "cif": os.environ.get("COSTCONTROL_CIF", "[CIF/NIF]"),
        "domicilio": os.environ.get("COSTCONTROL_DOMICILIO", "[DOMICILIO]"),
        "email": os.environ.get("COSTCONTROL_EMAIL_CONTACTO", "[EMAIL DE CONTACTO]"),
        "dominio": os.environ.get("COSTCONTROL_DOMINIO", "[tu-dominio.com]"),
    }


@app.route("/privacidad")
def privacidad():
    return render_template("legal_privacidad.html", **_legal_ctx())


@app.route("/condiciones")
def condiciones():
    return render_template("legal_condiciones.html", **_legal_ctx())


@app.route("/aviso-legal")
def aviso_legal():
    return render_template("legal_aviso.html", **_legal_ctx())


@app.before_request
def _gate():
    if MULTIUSER:
        if request.endpoint in _PUBLIC_ENDPOINTS:
            return
        uid = session.get("user_id")
        if not uid:
            return redirect(url_for("login", next=request.path))
        # revalida el usuario y fija la base de datos de su organización
        user = auth.get_usuario(uid)
        if not user:
            session.clear()
            return redirect(url_for("login"))
        g.user = user
        g.org_id = user["org_id"]
        g.db_path = auth.tenant_db_path(user["org_id"])
        if g.org_id not in _tenants_inicializados:
            db.init_db(g.db_path)
            _tenants_inicializados.add(g.org_id)
        return
    # modo monousuario con contraseña opcional (comportamiento clásico)
    if not PASSWORD:
        return
    if request.endpoint in ("login", "static", "salud",
                            "privacidad", "condiciones", "aviso_legal"):
        return
    if session.get("cc_auth"):
        return
    return redirect(url_for("login", next=request.path))


@app.route("/entrar", methods=["GET", "POST"])
def login():
    if MULTIUSER:
        if session.get("user_id"):
            return redirect(url_for("index"))
        error = None
        if request.method == "POST":
            user = auth.autenticar(request.form.get("email", ""),
                                   request.form.get("password", ""))
            if user:
                session.clear()
                session["user_id"] = user["id"]
                session["email"] = user["email"]
                session["org_nombre"] = user["org_nombre"]
                return redirect(request.args.get("next") or url_for("index"))
            error = "Email o contraseña incorrectos."
        return render_template("login.html", error=error, multiuser=True)

    if not PASSWORD:
        return redirect(url_for("index"))
    error = False
    if request.method == "POST":
        if request.form.get("password", "") == PASSWORD:
            session["cc_auth"] = True
            destino = request.args.get("next") or url_for("index")
            return redirect(destino)
        error = True
    return render_template("login.html", error=error, multiuser=False)


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if not MULTIUSER:
        abort(404)
    if session.get("user_id"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        try:
            r = auth.crear_organizacion(
                request.form.get("empresa", ""),
                request.form.get("email", ""),
                request.form.get("password", ""),
                request.form.get("nombre", ""))
            u = auth.autenticar(request.form.get("email", ""),
                                request.form.get("password", ""))
            session.clear()
            session["user_id"] = u["id"]
            session["email"] = u["email"]
            session["org_nombre"] = u["org_nombre"]
            flash(f"¡Bienvenido a CostControl, {r['org_nombre']}!", "ok")
            return redirect(url_for("index"))
        except ValueError as e:
            error = str(e)
    return render_template("registro.html", error=error)


@app.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    """Solicitar restablecimiento de contraseña (sin revelar si el email existe)."""
    if not MULTIUSER:
        abort(404)
    enviado = False
    link_directo = None
    if request.method == "POST":
        email = request.form.get("email", "")
        token = auth.crear_token_reset(email)
        if token:
            url = url_for("restablecer", token=token, _external=True)
            cuerpo = (f"Has solicitado restablecer tu contraseña de CostControl.\n\n"
                      f"Abre este enlace (caduca en 2 horas):\n{url}\n\n"
                      f"Si no has sido tú, ignora este mensaje.")
            if not auth.enviar_email(email, "Restablecer tu contraseña · CostControl", cuerpo):
                # Sin SMTP: no podemos enviar el correo. El operador puede dar el
                # enlace desde la consola; aquí no se muestra por seguridad.
                app.logger.info("Reset solicitado para %s (sin SMTP). Enlace: %s", email, url)
        enviado = True
    return render_template("recuperar.html", enviado=enviado,
                           hay_email=auth.smtp_configurado(), link_directo=link_directo)


@app.route("/restablecer/<token>", methods=["GET", "POST"])
def restablecer(token):
    if not MULTIUSER:
        abort(404)
    datos = auth.usuario_por_token(token)
    if not datos:
        return render_template("restablecer.html", valido=False)
    error = None
    if request.method == "POST":
        nueva = request.form.get("password", "")
        if nueva != request.form.get("password2", ""):
            error = "Las contraseñas no coinciden."
        elif auth.consumir_token_reset(token, nueva):
            flash("Contraseña actualizada. Ya puedes entrar.", "ok")
            return redirect(url_for("login"))
        else:
            error = "El enlace ha caducado o no es válido."
    return render_template("restablecer.html", valido=True, email=datos["email"], error=error)


@app.route("/cuenta/password", methods=["POST"])
def cuenta_password():
    if not MULTIUSER:
        abort(404)
    try:
        auth.cambiar_password(g.user["id"], request.form.get("actual", ""),
                              request.form.get("nueva", ""))
        flash("Contraseña cambiada correctamente.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("ajustes"))


@app.route("/equipo/<int:uid>/reset", methods=["POST"])
def equipo_reset(uid):
    if not MULTIUSER:
        abort(404)
    if g.user.get("rol") != "admin":
        flash("Solo un administrador puede hacer esto.", "error")
        return redirect(url_for("ajustes"))
    try:
        auth.admin_reset_password(g.org_id, uid, request.form.get("password", ""))
        flash("Contraseña del usuario actualizada.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("ajustes"))


@app.route("/equipo/<int:uid>/estado", methods=["POST"])
def equipo_estado(uid):
    if not MULTIUSER:
        abort(404)
    if g.user.get("rol") != "admin":
        flash("Solo un administrador puede hacer esto.", "error")
        return redirect(url_for("ajustes"))
    if uid == g.user["id"]:
        flash("No puedes desactivar tu propia cuenta.", "error")
        return redirect(url_for("ajustes"))
    try:
        auth.set_activo(g.org_id, uid, request.form.get("activo") == "1")
        flash("Estado del usuario actualizado.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("ajustes"))


@app.route("/salir")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --- utilidades -----------------------------------------------------------
def get_conn():
    if MULTIUSER:
        return db.connect(getattr(g, "db_path", None))
    return db.connect()


def _doc_bloqueado(conn, doc):
    """True si el documento cae en un periodo cerrado."""
    return bool(doc) and db.is_cerrado(conn, doc.get("ejercicio"), doc.get("periodo"))


def _projects_for_allocator(conn):
    out = []
    for p in db.list_proyectos(conn, solo_activos=True):
        drivers = {k: Decimal(str(v)) for k, v in (p.get("drivers") or {}).items()}
        out.append(Project(codigo=p["codigo"], nombre=p["nombre"], drivers=drivers))
    return out


def _allocator(conn):
    """Crea un Allocator con los proyectos activos y las reglas guardadas."""
    rules = {r["nombre"]: r["texto"] for r in db.list_reglas(conn)}
    return Allocator(_projects_for_allocator(conn), rules=rules)


def _interpretar(alloc, importe, texto):
    """Interpreta el reparto: motor determinista + IA opcional como refuerzo.

    - Modo 'siempre': la IA traduce primero la frase a la sintaxis canónica y el
      motor la evalúa; si la IA falla, se usa el motor directamente.
    - Modo 'auto' (por defecto con clave): se intenta el motor determinista y,
      solo si no entiende la frase, se recurre a la IA para traducirla.
    - Sin clave / modo 'off': solo el motor determinista (100 % local).

    En todos los casos el importe exacto lo calcula el motor, no la IA.
    """
    modo = ai.mode()

    def _con_ia(res_previo=None):
        r = ai.interpretar(importe, texto, alloc.projects, alloc.rules_map())
        if not r["ok"]:
            return None
        res2 = alloc.allocate(importe, r["reparto"])
        res2.ia = {"usada": True, "reparto": r["reparto"], "nota": r["nota"],
                   "original": texto}
        if res2.ok:
            res2.explanation.insert(
                0, f'Interpretado con IA como: «{r["reparto"]}».')
        return res2

    if modo == "siempre" and ai.available():
        out = _con_ia()
        if out is not None and out.ok:
            return out

    res = alloc.allocate(importe, texto)
    if not res.ok and modo in ("auto", "siempre") and ai.available():
        out = _con_ia(res)
        if out is not None and out.ok:
            return out
    return res


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
    return {"version": __import__("costcontrol").__version__,
            "auth_activo": bool(PASSWORD) or MULTIUSER,
            "multiuser": MULTIUSER,
            "usuario": getattr(g, "user", None) if MULTIUSER else None,
            "org_nombre": session.get("org_nombre") if MULTIUSER else None,
            "ia_activa": ai.available()}


@app.route("/ajustes")
def ajustes():
    equipo = None
    if MULTIUSER and getattr(g, "org_id", None):
        equipo = {"usuarios": auth.listar_usuarios(g.org_id),
                  "es_admin": g.user.get("rol") == "admin",
                  "yo": g.user["email"]}
    return render_template("ajustes.html", ia=ai.status(), equipo=equipo)


@app.route("/equipo/anadir", methods=["POST"])
def equipo_anadir():
    if not MULTIUSER:
        abort(404)
    if g.user.get("rol") != "admin":
        flash("Solo un administrador puede añadir usuarios.", "error")
        return redirect(url_for("ajustes"))
    try:
        auth.crear_usuario(g.org_id, request.form.get("email", ""),
                           request.form.get("password", ""),
                           request.form.get("nombre", ""),
                           request.form.get("rol", "usuario"))
        flash("Usuario añadido al equipo.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("ajustes"))


# --- panel ----------------------------------------------------------------
@app.route("/")
def index():
    conn = get_conn()
    ejercicio = request.args.get("ejercicio") or None
    tot = db.totales(conn, ejercicio=ejercicio)
    por_proyecto = db.resumen_por_proyecto(conn)
    por_centro = db.resumen_por_centro(conn)
    ejercicios_l = db.ejercicios(conn)
    serie = db.serie_mensual(conn, ejercicio=ejercicio)
    # alertas de presupuesto para el ejercicio seleccionado (o el más reciente)
    ej_pres = int(ejercicio) if ejercicio else (ejercicios_l[0] if ejercicios_l else None)
    seg = db.seguimiento_presupuestario(conn, ej_pres) if ej_pres else []
    seg_c = db.seguimiento_centros(conn, ej_pres) if ej_pres else []
    alertas = {
        "excedido": [s for s in seg if s["estado"] == "excedido"],
        "aviso": [s for s in seg if s["estado"] == "aviso"],
        "excedido_c": [s for s in seg_c if s["estado"] == "excedido"],
        "aviso_c": [s for s in seg_c if s["estado"] == "aviso"],
        "ejercicio": ej_pres,
    }
    alertas["hay"] = any([alertas["excedido"], alertas["aviso"],
                          alertas["excedido_c"], alertas["aviso_c"]])
    # comparativa año actual vs. anterior
    comp = None
    if ej_pres:
        s_act = {s["periodo"]: s["importe"] for s in db.serie_mensual(conn, ej_pres)}
        s_ant = {s["periodo"]: s["importe"] for s in db.serie_mensual(conn, ej_pres - 1)}
        tot_act = sum(s_act.values())
        tot_ant = sum(s_ant.values())
        if tot_act or tot_ant:
            datos_comp = [(MESES[m], s_ant.get(m, 0), s_act.get(m, 0)) for m in range(1, 13)]
            comp = {
                "ej_act": ej_pres, "ej_ant": ej_pres - 1,
                "tot_act": tot_act, "tot_ant": tot_ant,
                "var": ((tot_act - tot_ant) / tot_ant * 100) if tot_ant else None,
                "grafico": charts.barras_comparativa(datos_comp),
            }
    conn.close()

    # gráficos SVG
    graf_centro = charts.barras_horizontales(
        [(c["codigo"], c["importe"]) for c in por_centro if c["importe"]][:8])
    graf_proyecto = charts.barras_horizontales(
        [(p["codigo"], p["imputado"]) for p in por_proyecto if p["imputado"]][:8])
    serie_datos = [(MESES[s["periodo"]] if 1 <= (s["periodo"] or 0) <= 12 else str(s["periodo"]),
                    s["importe"]) for s in serie]
    graf_mensual = charts.barras_verticales(serie_datos)

    return render_template("index.html", tot=tot, por_proyecto=por_proyecto,
                           por_centro=por_centro, ejercicios=ejercicios_l,
                           ejercicio_sel=ejercicio, graf_centro=graf_centro,
                           graf_proyecto=graf_proyecto, graf_mensual=graf_mensual,
                           hay_serie=bool(serie_datos), alertas=alertas, comp=comp)


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
                     regla_defecto=f.get("regla_defecto", "").strip(),
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
def _doc_filtros():
    a = request.args
    return dict(
        estado=a.get("estado") or None,
        centro_id=int(a["centro"]) if a.get("centro") else None,
        tipo=a.get("tipo") or None,
        cuenta_id=int(a["cuenta"]) if a.get("cuenta") else None,
        ejercicio=a.get("ejercicio") or None,
        periodo=a.get("periodo") or None,
        texto=a.get("texto") or None,
        fecha_desde=a.get("desde") or None,
        fecha_hasta=a.get("hasta") or None,
        importe_min=a.get("min") or None,
        importe_max=a.get("max") or None,
    )


@app.route("/documentos")
def documentos():
    conn = get_conn()
    filtros = _doc_filtros()
    data = db.list_documentos(conn, **filtros)
    centros_l = db.list_centros(conn)
    cuentas_l = db.list_cuentas(conn)
    ejercicios_l = db.ejercicios(conn)
    conn.close()
    total_filtrado = sum(d["importe"] or 0 for d in data)
    return render_template("documentos.html", documentos=data, centros=centros_l,
                           cuentas=cuentas_l, ejercicios=ejercicios_l, meses=MESES,
                           filtro={k: (request.args.get(k) or "") for k in
                                   ["estado", "centro", "tipo", "cuenta", "ejercicio",
                                    "periodo", "texto", "desde", "hasta", "min", "max"]},
                           total_filtrado=total_filtrado)


@app.route("/documentos/exportar")
def documentos_exportar():
    conn = get_conn()
    data = db.list_documentos(conn, **_doc_filtros())
    xlsx = importer.export_documentos(conn, data)
    conn.close()
    return send_file(io.BytesIO(xlsx), as_attachment=True,
                     download_name="documentos_costcontrol.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/documentos/nuevo", methods=["GET", "POST"])
@app.route("/documentos/<int:did>/editar", methods=["GET", "POST"])
def documento_editar(did=None):
    conn = get_conn()
    if request.method == "POST":
        f = request.form
        def parse_imp(v):
            from .allocation import parse_number
            return float(parse_number(v) or 0)
        tercero_txt = f.get("tercero", "").strip()
        tercero_id = None
        if tercero_txt:
            tercero_id = db.upsert_tercero(conn, tercero_txt)
        payload = dict(
            tipo=f.get("tipo", "factura"),
            numero=f.get("numero", "").strip(),
            fecha=f.get("fecha", "").strip(),
            tercero=tercero_txt,
            tercero_id=tercero_id,
            concepto=f.get("concepto", "").strip(),
            importe=parse_imp(f.get("importe", "0")),
            iva_pct=parse_imp(f.get("iva_pct", "0")),
            cuenta_id=int(f["cuenta_id"]) if f.get("cuenta_id") else None,
            centro_id=int(f["centro_id"]) if f.get("centro_id") else None,
            notas=f.get("notas", "").strip(),
        )
        # control de periodo cerrado (destino y, si se edita, origen)
        ej_new, per_new = db.periodo_desde_fecha(payload["fecha"])
        bloqueado = db.is_cerrado(conn, ej_new, per_new)
        if did and not bloqueado:
            bloqueado = _doc_bloqueado(conn, db.get_documento(conn, did))
        if bloqueado:
            conn.close()
            flash("El periodo está cerrado: no se puede crear o modificar documentos en él.", "error")
            return redirect(url_for("documento_editar", did=did) if did else url_for("documentos"))

        if did:
            db.update_documento(conn, did, **payload)
        else:
            did = db.insert_documento(conn, estado="pendiente", **payload)
        # adjunto (opcional)
        stored = _guardar_adjunto(did, request.files.get("adjunto"))
        if stored:
            prev = db.get_documento(conn, did)
            if prev and prev.get("adjunto"):
                _borrar_archivo(prev["adjunto"])
            db.update_documento(conn, did, adjunto=stored)
        conn.close()
        flash("Documento guardado.", "ok")
        return redirect(url_for("documento_reparto", did=did))

    doc = db.get_documento(conn, did) if did else None
    if did and not doc:
        conn.close()
        abort(404)
    cuentas_l = db.list_cuentas(conn)
    centros_l = db.list_centros(conn)
    terceros_l = db.list_terceros(conn)
    conn.close()
    return render_template("documento_editar.html", doc=doc, cuentas=cuentas_l,
                           centros=centros_l, terceros=terceros_l)


@app.route("/documentos/<int:did>/borrar", methods=["POST"])
def documento_borrar(did):
    conn = get_conn()
    doc = db.get_documento(conn, did)
    if _doc_bloqueado(conn, doc):
        conn.close()
        flash("El periodo está cerrado: no se puede eliminar este documento.", "error")
        return redirect(url_for("documento_reparto", did=did))
    if doc and doc.get("adjunto"):
        _borrar_archivo(doc["adjunto"])
    db.delete_documento(conn, did)
    conn.close()
    flash("Documento eliminado.", "ok")
    return redirect(url_for("documentos"))


def _borrar_archivo(nombre):
    try:
        p = os.path.join(_uploads_dir(), os.path.basename(nombre))
        if os.path.isfile(p):
            os.remove(p)
    except OSError:
        pass


@app.route("/documentos/<int:did>/adjunto")
def documento_adjunto(did):
    conn = get_conn()
    doc = db.get_documento(conn, did)
    conn.close()
    if not doc or not doc.get("adjunto"):
        abort(404)
    return send_file(os.path.join(_uploads_dir(), os.path.basename(doc["adjunto"])),
                     download_name=doc["adjunto"], as_attachment=False)


@app.route("/documentos/<int:did>/adjunto/borrar", methods=["POST"])
def documento_adjunto_borrar(did):
    conn = get_conn()
    doc = db.get_documento(conn, did)
    if doc and doc.get("adjunto"):
        _borrar_archivo(doc["adjunto"])
        db.update_documento(conn, did, adjunto="")
    conn.close()
    flash("Adjunto eliminado.", "ok")
    return redirect(url_for("documento_editar", did=did))


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
    cerrado = _doc_bloqueado(conn, doc)
    conn.close()
    return render_template("reparto.html", doc=doc, proyectos=proyectos_l,
                           repartos=repartos, reglas=reglas, texto_previo="",
                           cerrado=cerrado)


@app.route("/documentos/<int:did>/reparto/previsualizar", methods=["POST"])
def reparto_previsualizar(did):
    """Traduce el texto libre a un reparto concreto y lo devuelve como JSON."""
    conn = get_conn()
    doc = db.get_documento(conn, did)
    if not doc:
        conn.close()
        abort(404)
    alloc = _allocator(conn)
    conn.close()
    texto = request.json.get("texto", "") if request.is_json else request.form.get("texto", "")
    res = _interpretar(alloc, doc["importe"], texto)
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
        "ia": res.ia,
    }


@app.route("/documentos/<int:did>/reparto/guardar", methods=["POST"])
def reparto_guardar(did):
    conn = get_conn()
    doc = db.get_documento(conn, did)
    if not doc:
        conn.close()
        abort(404)
    if _doc_bloqueado(conn, doc):
        conn.close()
        flash("El periodo está cerrado: no se puede modificar el reparto.", "error")
        return redirect(url_for("documento_reparto", did=did))
    alloc = _allocator(conn)
    texto = request.form.get("texto", "")
    res = _interpretar(alloc, doc["importe"], texto)
    if not res.ok:
        conn.close()
        flash("No se pudo interpretar el reparto: " + " ".join(res.warnings), "error")
        return redirect(url_for("documento_reparto", did=did))

    # mapa código -> id
    cod2id = {p["codigo"]: p["id"] for p in db.list_proyectos(conn)}
    origen = texto.strip()
    if res.ia and res.ia.get("usada"):
        origen = f'{texto.strip()} → IA: {res.ia.get("reparto")}'
    lines = [{
        "proyecto_id": cod2id.get(l.proyecto),
        "proyecto_codigo": l.proyecto,
        "importe": float(l.importe),
        "porcentaje": float(l.porcentaje),
        "base": f"{origen} · {l.base}",
    } for l in res.lines]
    db.replace_repartos(conn, did, lines)
    conn.close()
    extra = " (interpretado con IA)" if res.ia and res.ia.get("usada") else ""
    flash(f"Reparto guardado: {len(lines)} línea(s) analítica(s).{extra}", "ok")
    return redirect(url_for("documento_reparto", did=did))


@app.route("/documentos/<int:did>/reparto/guardar-manual", methods=["POST"])
def reparto_guardar_manual(did):
    """Guarda un reparto ajustado a mano (importe por proyecto), sin re-interpretar texto."""
    conn = get_conn()
    doc = db.get_documento(conn, did)
    if not doc:
        conn.close()
        abort(404)
    if _doc_bloqueado(conn, doc):
        conn.close()
        flash("El periodo está cerrado: no se puede modificar el reparto.", "error")
        return redirect(url_for("documento_reparto", did=did))
    from .allocation import parse_number
    cod2id = {p["codigo"]: p["id"] for p in db.list_proyectos(conn)}
    total = float(doc["importe"] or 0)
    codigos = request.form.getlist("proyecto_codigo")
    importes = request.form.getlist("importe")
    lines = []
    for cod, imp in zip(codigos, importes):
        cod = (cod or "").strip()
        val = parse_number(imp)
        if not cod or val is None or float(val) == 0:
            continue
        valf = float(val)
        pct = round(valf / total * 100, 2) if total else 0
        lines.append({"proyecto_id": cod2id.get(cod), "proyecto_codigo": cod,
                      "importe": valf, "porcentaje": pct,
                      "base": "ajuste manual"})
    if not lines:
        conn.close()
        flash("No se ha indicado ningún importe para el reparto manual.", "error")
        return redirect(url_for("documento_reparto", did=did))
    db.replace_repartos(conn, did, lines)
    conn.close()
    suma = sum(l["importe"] for l in lines)
    dif = round(total - suma, 2)
    msg = f"Reparto manual guardado: {len(lines)} línea(s)."
    if abs(dif) >= 0.01:
        msg += f" Aviso: la suma ({suma:.2f} €) difiere del total en {dif:.2f} €."
    flash(msg, "ok")
    return redirect(url_for("documento_reparto", did=did))


@app.route("/documentos/<int:did>/reparto/limpiar", methods=["POST"])
def reparto_limpiar(did):
    conn = get_conn()
    if _doc_bloqueado(conn, db.get_documento(conn, did)):
        conn.close()
        flash("El periodo está cerrado: no se puede modificar el reparto.", "error")
        return redirect(url_for("documento_reparto", did=did))
    db.replace_repartos(conn, did, [])
    conn.close()
    flash("Reparto eliminado; el documento vuelve a estado pendiente.", "ok")
    return redirect(url_for("documento_reparto", did=did))


# --- reglas de reparto (plantillas gestionables) --------------------------
@app.route("/reglas")
def reglas():
    conn = get_conn()
    data = db.list_reglas(conn)
    proyectos_l = db.list_proyectos(conn, solo_activos=True)
    conn.close()
    return render_template("reglas.html", reglas=data, proyectos=proyectos_l)


@app.route("/reglas/guardar", methods=["POST"])
def reglas_guardar():
    f = request.form
    conn = get_conn()
    db.upsert_regla(conn, f.get("nombre", "").strip() or "Regla",
                    f.get("texto", "").strip(),
                    rid=int(f["id"]) if f.get("id") else None)
    conn.close()
    flash("Regla de reparto guardada.", "ok")
    return redirect(request.referrer or url_for("reglas"))


@app.route("/reglas/<int:rid>/borrar", methods=["POST"])
def reglas_borrar(rid):
    conn = get_conn()
    db.delete_regla(conn, rid)
    conn.close()
    flash("Regla eliminada.", "ok")
    return redirect(url_for("reglas"))


# --- terceros -------------------------------------------------------------
@app.route("/terceros")
def terceros():
    conn = get_conn()
    data = db.list_terceros(conn)
    conn.close()
    return render_template("terceros.html", terceros=data)


@app.route("/terceros/guardar", methods=["POST"])
def terceros_guardar():
    f = request.form
    conn = get_conn()
    db.upsert_tercero(conn, f["nombre"].strip(), nif=f.get("nif", "").strip(),
                      tipo=f.get("tipo", "proveedor"),
                      tid=int(f["id"]) if f.get("id") else None)
    conn.close()
    flash("Tercero guardado.", "ok")
    return redirect(url_for("terceros"))


@app.route("/terceros/<int:tid>/borrar", methods=["POST"])
def terceros_borrar(tid):
    conn = get_conn()
    db.delete_tercero(conn, tid)
    conn.close()
    flash("Tercero eliminado.", "ok")
    return redirect(url_for("terceros"))


# --- REPARTO MASIVO -------------------------------------------------------
@app.route("/reparto-masivo", methods=["GET"])
def reparto_masivo():
    conn = get_conn()
    filtros = _doc_filtros()
    filtro_display = {k: (request.args.get(k) or "") for k in
                      ["estado", "centro", "tipo", "cuenta", "ejercicio", "periodo"]}
    if not any(filtros.values()):
        filtros["estado"] = "pendiente"
        filtro_display["estado"] = "pendiente"
    docs = db.list_documentos(conn, **filtros)
    centros_l = db.list_centros(conn)
    cuentas_l = db.list_cuentas(conn)
    ejercicios_l = db.ejercicios(conn)
    proyectos_l = db.list_proyectos(conn, solo_activos=True)
    reglas_l = db.list_reglas(conn)
    conn.close()
    total = sum(d["importe"] or 0 for d in docs)
    return render_template("reparto_masivo.html", documentos=docs, centros=centros_l,
                           cuentas=cuentas_l, ejercicios=ejercicios_l, meses=MESES,
                           proyectos=proyectos_l, reglas=reglas_l, total=total,
                           filtro=filtro_display)


@app.route("/reparto-masivo/aplicar", methods=["POST"])
def reparto_masivo_aplicar():
    conn = get_conn()
    texto = request.form.get("texto", "")
    ids = [int(x) for x in request.form.getlist("doc_ids") if x]
    if not ids or not texto.strip():
        conn.close()
        flash("Selecciona documentos y escribe una regla de reparto.", "error")
        return redirect(request.referrer or url_for("reparto_masivo"))
    allocator = _allocator(conn)
    cod2id = {p["codigo"]: p["id"] for p in db.list_proyectos(conn)}
    docs = db.list_documentos(conn, ids=ids)
    cerrados = db.cierres_set(conn)

    # La misma frase se aplica a muchos documentos: si hace falta la IA, se
    # traduce UNA sola vez a la sintaxis canónica y luego se aplica a cada
    # documento con el motor determinista (importe recalculado por documento).
    efectivo, ia_usada = texto, False
    modo = ai.mode()
    if modo != "off" and ai.available():
        probe = allocator.allocate(Decimal("1000"), texto)
        if modo == "siempre" or not probe.ok:
            r = ai.interpretar(1000, texto, allocator.projects, allocator.rules_map())
            if r["ok"]:
                efectivo, ia_usada = r["reparto"], True

    aplicados, fallidos, bloqueados = 0, 0, 0
    for d in docs:
        if (d.get("ejercicio"), d.get("periodo")) in cerrados:
            bloqueados += 1
            continue
        res = allocator.allocate(d["importe"], efectivo)
        if res.ok and res.lines:
            origen = texto.strip() if not ia_usada else f"{texto.strip()} → IA: {efectivo}"
            lines = [{
                "proyecto_id": cod2id.get(l.proyecto),
                "proyecto_codigo": l.proyecto,
                "importe": float(l.importe),
                "porcentaje": float(l.porcentaje),
                "base": f"[masivo] {origen} · {l.base}",
            } for l in res.lines]
            db.replace_repartos(conn, d["id"], lines)
            aplicados += 1
        else:
            fallidos += 1
    conn.close()
    msg = f"Reparto masivo aplicado a {aplicados} documento(s)."
    if ia_usada:
        msg += " (interpretado con IA)"
    if fallidos:
        msg += f" {fallidos} no se pudieron interpretar."
    if bloqueados:
        msg += f" {bloqueados} en periodo cerrado (omitidos)."
    flash(msg, "ok" if aplicados else "error")
    return redirect(url_for("documentos", estado="repartido"))


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
                    conn, data, tipo_defecto=request.form.get("tipo_defecto", "factura"),
                    omitir_duplicados=bool(request.form.get("omitir_duplicados")),
                    cerrados=db.cierres_set(conn))
                msg = f"{r['importados']} documento(s) importado(s)."
                extras = []
                if r["cuentas_creadas"]:
                    extras.append(f"{r['cuentas_creadas']} cuenta(s)")
                if r["centros_creados"]:
                    extras.append(f"{r['centros_creados']} centro(s)")
                if r.get("terceros_creados"):
                    extras.append(f"{r['terceros_creados']} tercero(s)")
                if extras:
                    msg += " Creados: " + ", ".join(extras) + "."
                if r.get("repartidos_auto"):
                    msg += f" {r['repartidos_auto']} repartido(s) automáticamente por regla de centro."
                if r.get("duplicados"):
                    msg += f" {r['duplicados']} duplicado(s) omitido(s)."
                if r.get("cerrados_omitidos"):
                    msg += f" {r['cerrados_omitidos']} en periodo cerrado (omitidos)."
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
    por_cuenta = db.resumen_por_cuenta(conn)
    detalle = {}
    for p in por_proyecto:
        detalle[p["id"]] = db.detalle_proyecto(conn, p["id"])
    conn.close()
    graf_proyecto = charts.barras_horizontales(
        [(p["codigo"], p["imputado"]) for p in por_proyecto if p["imputado"]][:10])
    graf_cuenta = charts.barras_horizontales(
        [(c["codigo"], c["importe"]) for c in por_cuenta if c["importe"]][:10])
    return render_template("informe.html", por_proyecto=por_proyecto,
                           por_centro=por_centro, por_cuenta=por_cuenta, detalle=detalle,
                           graf_proyecto=graf_proyecto, graf_cuenta=graf_cuenta)


@app.route("/backup")
def backup():
    conn = get_conn()
    data = importer.export_backup(conn)
    conn.close()
    return send_file(io.BytesIO(data), as_attachment=True,
                     download_name="costcontrol_backup.json", mimetype="application/json")


@app.route("/restaurar", methods=["POST"])
def restaurar():
    file = request.files.get("archivo")
    if not file or not file.filename:
        flash("Selecciona un archivo de copia (.json).", "error")
        return redirect(url_for("informe"))
    conn = get_conn()
    r = importer.restore_backup(conn, file.read())
    conn.close()
    if r.get("ok"):
        flash(f"Copia restaurada: {r.get('documentos',0)} documentos, "
              f"{r.get('proyectos',0)} proyectos, {r.get('repartos',0)} líneas de reparto.", "ok")
    else:
        flash("No se pudo restaurar: " + r.get("error", "error desconocido"), "error")
    return redirect(url_for("index"))


@app.route("/informe/exportar")
def informe_exportar():
    conn = get_conn()
    data = importer.export_informe(conn)
    conn.close()
    return send_file(io.BytesIO(data), as_attachment=True,
                     download_name="informe_costcontrol.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# --- PRESUPUESTOS Y CIERRE DE PERIODO ------------------------------------
@app.route("/presupuestos")
def presupuestos():
    conn = get_conn()
    ejs = db.ejercicios(conn)
    ejercicio = request.args.get("ejercicio")
    if not ejercicio:
        ejercicio = ejs[0] if ejs else 2026
    ejercicio = int(ejercicio)
    proyectos_l = db.list_proyectos(conn)
    pres = db.get_presupuestos(conn, ejercicio)
    seguimiento = db.seguimiento_presupuestario(conn, ejercicio)
    centros_l = db.list_centros(conn)
    pres_centro = db.get_presupuestos_centro(conn, ejercicio)
    seguimiento_centro = db.seguimiento_centros(conn, ejercicio)
    cierres = db.list_cierres(conn)
    cerrados = db.cierres_set(conn)
    conn.close()
    return render_template("presupuestos.html", proyectos=proyectos_l, pres=pres,
                           ejercicio=ejercicio, ejercicios=ejs or [ejercicio],
                           seguimiento=seguimiento, meses=MESES, cierres=cierres,
                           cerrados=cerrados, centros=centros_l, pres_centro=pres_centro,
                           seguimiento_centro=seguimiento_centro,
                           anios=sorted({ejercicio, 2025, 2026, 2027}))


@app.route("/presupuestos/guardar", methods=["POST"])
def presupuestos_guardar():
    from .allocation import parse_number
    conn = get_conn()
    ejercicio = int(request.form.get("ejercicio") or 2026)
    for p in db.list_proyectos(conn):
        for mes in range(1, 13):
            campo = f"pres_{p['id']}_{mes}"
            if campo in request.form:
                val = parse_number(request.form.get(campo)) or 0
                db.set_presupuesto(conn, p["id"], ejercicio, mes, float(val))
    for c in db.list_centros(conn):
        for mes in range(1, 13):
            campo = f"presc_{c['id']}_{mes}"
            if campo in request.form:
                val = parse_number(request.form.get(campo)) or 0
                db.set_presupuesto_centro(conn, c["id"], ejercicio, mes, float(val))
    conn.close()
    flash("Presupuestos guardados.", "ok")
    return redirect(url_for("presupuestos", ejercicio=ejercicio))


@app.route("/cierres/cambiar", methods=["POST"])
def cierres_cambiar():
    conn = get_conn()
    ejercicio = int(request.form.get("ejercicio") or 2026)
    periodo = int(request.form.get("periodo") or 0)
    accion = request.form.get("accion")
    if periodo:
        if accion == "cerrar":
            db.cerrar_periodo(conn, ejercicio, periodo)
            flash(f"Periodo {MESES[periodo]} {ejercicio} cerrado.", "ok")
        else:
            db.abrir_periodo(conn, ejercicio, periodo)
            flash(f"Periodo {MESES[periodo]} {ejercicio} reabierto.", "ok")
    conn.close()
    return redirect(url_for("presupuestos", ejercicio=ejercicio))


def bootstrap():
    """Prepara las bases de datos según el modo (mono o multiusuario)."""
    if MULTIUSER:
        auth.init_auth_db()
    else:
        db.init_db()


def create_app():
    bootstrap()
    return app


if __name__ == "__main__":
    bootstrap()
    app.run(debug=True, port=5000)
