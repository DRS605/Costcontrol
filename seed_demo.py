"""Carga datos de demostración en CostControl."""

from costcontrol import db


def seed():
    db.init_db()
    conn = db.connect()

    # Proyectos con drivers para reparto ponderado
    p1 = db.upsert_proyecto(conn, "PROY-A", "Reforma Nave Norte", presupuesto=150000,
                            drivers={"superficie": 400, "horas": 1200})
    p2 = db.upsert_proyecto(conn, "PROY-B", "Ampliación Oficinas", presupuesto=80000,
                            drivers={"superficie": 200, "horas": 600})
    p3 = db.upsert_proyecto(conn, "PROY-C", "Mantenimiento General", presupuesto=40000,
                            drivers={"superficie": 100, "horas": 300})

    # Centros de coste / beneficio (CC-ESTRUCTURA con regla de reparto por defecto)
    obras = db.upsert_centro(conn, "CC-OBRAS", "Obras y ejecución", "coste")
    estr = db.upsert_centro(conn, "CC-ESTRUCTURA", "Estructura / indirectos", "coste",
                            regla_defecto="según superficie")
    cc_log = db.upsert_centro(conn, "CC-LOG", "Logística y transporte", "coste")
    db.upsert_centro(conn, "CB-VENTAS", "Ventas", "beneficio")

    # Cuentas contables
    c600 = db.upsert_cuenta(conn, "600000", "Compras de mercaderías", "6")
    c624 = db.upsert_cuenta(conn, "624000", "Transportes", "6")
    c640 = db.upsert_cuenta(conn, "640000", "Sueldos y salarios", "6")

    # Terceros
    t1 = db.upsert_tercero(conn, "Suministros Levante SL", nif="B96000001")
    t2 = db.upsert_tercero(conn, "Transportes Mediterráneo", nif="B96000002")
    t3 = db.upsert_tercero(conn, "Cementos del Turia", nif="B96000003")

    # Regla de reparto guardada (plantilla)
    db.upsert_regla(conn, "Obra 60/40", "60% PROY-A, 40% PROY-B")

    docs = [
        dict(tipo="factura", numero="F-2026/001", fecha="2026-01-15",
             tercero="Suministros Levante SL", tercero_id=t1, concepto="Material de obra ferralla",
             importe=3630.50, iva_pct=21, cuenta_id=c600, centro_id=obras),
        dict(tipo="albaran", numero="ALB-1042", fecha="2026-01-20",
             tercero="Transportes Mediterráneo", tercero_id=t2, concepto="Portes de enero",
             importe=480.00, iva_pct=21, cuenta_id=c624, centro_id=cc_log),
        dict(tipo="apunte", numero="AS-5501", fecha="2026-01-31",
             tercero="Nómina personal técnico", concepto="Personal indirecto de estructura",
             importe=12500.00, iva_pct=0, cuenta_id=c640, centro_id=estr),
        dict(tipo="factura", numero="F-2026/014", fecha="2026-02-10",
             tercero="Cementos del Turia", tercero_id=t3, concepto="Hormigón y áridos",
             importe=8250.75, iva_pct=21, cuenta_id=c600, centro_id=obras),
        dict(tipo="factura", numero="F-2026/021", fecha="2026-03-05",
             tercero="Suministros Levante SL", tercero_id=t1, concepto="Material eléctrico",
             importe=1980.00, iva_pct=21, cuenta_id=c600, centro_id=obras),
    ]
    for d in docs:
        db.insert_documento(conn, estado="pendiente", **d)

    conn.close()
    return {"proyectos": 3, "documentos": len(docs)}


if __name__ == "__main__":
    r = seed()
    print("Demo cargada:", r)
