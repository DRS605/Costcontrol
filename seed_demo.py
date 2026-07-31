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

    # Centros de coste / beneficio
    db.upsert_centro(conn, "CC-OBRAS", "Obras y ejecución", "coste")
    db.upsert_centro(conn, "CC-ESTRUCTURA", "Estructura / indirectos", "coste")
    cc_log = db.upsert_centro(conn, "CC-LOG", "Logística y transporte", "coste")
    db.upsert_centro(conn, "CB-VENTAS", "Ventas", "beneficio")

    # Cuentas contables
    c600 = db.upsert_cuenta(conn, "600000", "Compras de mercaderías", "6")
    c624 = db.upsert_cuenta(conn, "624000", "Transportes", "6")
    c640 = db.upsert_cuenta(conn, "640000", "Sueldos y salarios", "6")

    obras = db.upsert_centro(conn, "CC-OBRAS", "Obras y ejecución", "coste")
    estr = db.upsert_centro(conn, "CC-ESTRUCTURA", "Estructura / indirectos", "coste")

    docs = [
        dict(tipo="factura", numero="F-2026/001", fecha="2026-01-15",
             tercero="Suministros Levante SL", concepto="Material de obra ferralla",
             importe=3630.50, cuenta_id=c600, centro_id=obras),
        dict(tipo="albaran", numero="ALB-1042", fecha="2026-01-20",
             tercero="Transportes Mediterráneo", concepto="Portes de enero",
             importe=480.00, cuenta_id=c624, centro_id=cc_log),
        dict(tipo="apunte", numero="AS-5501", fecha="2026-01-31",
             tercero="Nómina personal técnico", concepto="Personal indirecto de estructura",
             importe=12500.00, cuenta_id=c640, centro_id=estr),
        dict(tipo="factura", numero="F-2026/014", fecha="2026-02-10",
             tercero="Cementos del Turia", concepto="Hormigón y áridos",
             importe=8250.75, cuenta_id=c600, centro_id=obras),
    ]
    for d in docs:
        db.insert_documento(conn, estado="pendiente", **d)

    conn.close()
    return {"proyectos": 3, "documentos": len(docs)}


if __name__ == "__main__":
    r = seed()
    print("Demo cargada:", r)
