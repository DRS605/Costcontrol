"""Pruebas del motor de reparto en lenguaje natural."""

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from costcontrol.allocation import Project, allocate, parse_number


def _projs():
    return [
        Project("PROY1", "Nave Norte", {"m2": 100, "superficie": 100}),
        Project("PROY2", "Nave Sur", {"m2": 300, "superficie": 300}),
        Project("PROY3", "Oficinas", {"m2": 100, "superficie": 100}),
    ]


def imp(res, cod):
    for l in res.lines:
        if l.proyecto == cod:
            return l.importe
    return Decimal("0")


def test_parse_number():
    assert parse_number("1.234,56") == Decimal("1234.56")
    assert parse_number("1234.56") == Decimal("1234.56")
    assert parse_number("1.500 €") == Decimal("1500")
    assert parse_number("40%") == Decimal("40")
    assert parse_number("60") == Decimal("60")


def test_percentages():
    r = allocate("1000", "60% al PROY1 y 40% al PROY2", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("600.00")
    assert imp(r, "PROY2") == Decimal("400.00")
    assert r.repartido == Decimal("1000.00")


def test_percentages_no_symbol():
    r = allocate("1000", "PROY1 70, PROY2 30", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("700.00")
    assert imp(r, "PROY2") == Decimal("300.00")


def test_equal_split():
    r = allocate("1000", "a partes iguales entre PROY1, PROY2 y PROY3", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("333.33")
    assert r.repartido == Decimal("1000.00")


def test_all_to_one():
    r = allocate("1000", "todo a PROY1", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("1000.00")
    assert len(r.lines) == 1


def test_fixed_amount_plus_rest():
    r = allocate("2000", "1.500 € a PROY1 y el resto a PROY2", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("1500.00")
    assert imp(r, "PROY2") == Decimal("500.00")


def test_weighted_by_driver():
    r = allocate("1000", "según superficie", _projs())
    assert r.ok
    # pesos 100/300/100 = total 500 -> 200/600/200
    assert imp(r, "PROY1") == Decimal("200.00")
    assert imp(r, "PROY2") == Decimal("600.00")
    assert imp(r, "PROY3") == Decimal("200.00")


def test_weighted_explicit():
    r = allocate("1000", "por m2: PROY1 100, PROY2 300", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("250.00")
    assert imp(r, "PROY2") == Decimal("750.00")


def test_mixed_pct_and_rest():
    r = allocate("1000", "PROY1 30%, resto PROY2", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("300.00")
    assert imp(r, "PROY2") == Decimal("700.00")


def test_by_name():
    r = allocate("1000", "todo a Nave Norte", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("1000.00")


def test_under_allocation_warns():
    r = allocate("1000", "PROY1 30%", _projs())
    assert any("sin repartir" in w for w in r.warnings)


def test_regla_referencia():
    rules = {"Obra estándar": "60% PROY1, 40% PROY2"}
    r = allocate("1000", "como la regla Obra estándar", _projs(), rules=rules)
    assert r.ok
    assert imp(r, "PROY1") == Decimal("600.00")
    assert imp(r, "PROY2") == Decimal("400.00")
    # también con "según la regla"
    r2 = allocate("1000", "según la regla Obra estándar", _projs(), rules=rules)
    assert r2.ok and imp(r2, "PROY1") == Decimal("600.00")


def test_regla_inexistente_avisa():
    r = allocate("1000", "como la regla NoExiste", _projs(), rules={"Otra": "todo a PROY1"})
    assert not r.ok
    assert any("no se ha encontrado" in w.lower() for w in r.warnings)


def test_regla_anidada():
    rules = {"Base": "a partes iguales entre PROY1, PROY2",
             "Compuesta": "como la regla Base"}
    r = allocate("1000", "como la regla Compuesta", _projs(), rules=rules)
    assert r.ok
    assert imp(r, "PROY1") == Decimal("500.00")


def test_regla_subconjunto_solo():
    rules = {"Tres": "50% PROY1, 30% PROY2, 20% PROY3"}
    r = allocate("1000", "según la regla Tres, pero solo PROY1 y PROY2", _projs(), rules=rules)
    assert r.ok
    # 50:30 reescalado a 100 -> 62.5 / 37.5
    assert imp(r, "PROY1") == Decimal("625.00")
    assert imp(r, "PROY2") == Decimal("375.00")
    assert imp(r, "PROY3") == Decimal("0")
    assert r.repartido == Decimal("1000.00")


def test_regla_subconjunto_excepto():
    rules = {"Tres": "50% PROY1, 30% PROY2, 20% PROY3"}
    r = allocate("1000", "como la regla Tres excepto PROY3", _projs(), rules=rules)
    assert r.ok
    assert imp(r, "PROY1") == Decimal("625.00")
    assert imp(r, "PROY2") == Decimal("375.00")


def test_combina_regla_pct_y_resto():
    rules = {"Obra": "60% PROY1, 40% PROY2"}
    r = allocate("1000", "50% como la regla Obra, resto a PROY3", _projs(), rules=rules)
    assert r.ok
    assert imp(r, "PROY1") == Decimal("300.00")   # 50%*60%
    assert imp(r, "PROY2") == Decimal("200.00")   # 50%*40%
    assert imp(r, "PROY3") == Decimal("500.00")   # resto
    assert r.repartido == Decimal("1000.00")


def test_combina_regla_pct_y_pct():
    rules = {"Obra": "60% PROY1, 40% PROY2"}
    r = allocate("1000", "50% como la regla Obra, 50% a PROY3", _projs(), rules=rules)
    assert r.ok
    assert imp(r, "PROY1") == Decimal("300.00")
    assert imp(r, "PROY3") == Decimal("500.00")


def test_combina_importe_y_resto_regla():
    rules = {"Obra": "60% PROY1, 40% PROY2"}
    r = allocate("1000", "400 € a PROY3, resto como la regla Obra", _projs(), rules=rules)
    assert r.ok
    assert imp(r, "PROY3") == Decimal("400.00")
    assert imp(r, "PROY1") == Decimal("360.00")   # 60% de 600
    assert imp(r, "PROY2") == Decimal("240.00")   # 40% de 600
    assert r.repartido == Decimal("1000.00")


def test_regla_circular_no_cuelga():
    rules = {"A": "como la regla B", "B": "como la regla A"}
    r = allocate("1000", "como la regla A", _projs(), rules=rules)
    assert not r.ok  # detecta el ciclo y no se cuelga


def test_pesos_relativos_doble():
    r = allocate("900", "el doble a PROY1 que a PROY2", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("600.00")   # peso 2 de 3
    assert imp(r, "PROY2") == Decimal("300.00")   # peso 1 de 3
    assert r.repartido == Decimal("900.00")


def test_pesos_relativos_mitad():
    r = allocate("900", "la mitad a PROY1 que a PROY2", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("300.00")   # peso 0.5
    assert imp(r, "PROY2") == Decimal("600.00")   # peso 1
    assert r.repartido == Decimal("900.00")


def test_fraccion_mitad_resto():
    r = allocate("1000", "la mitad a PROY1 y el resto a PROY2", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("500.00")
    assert imp(r, "PROY2") == Decimal("500.00")


def test_fraccion_tercios():
    r = allocate("900", "un tercio a PROY1, un tercio a PROY2, un tercio a PROY3", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("300.00")
    assert imp(r, "PROY2") == Decimal("300.00")
    assert imp(r, "PROY3") == Decimal("300.00")
    assert r.repartido == Decimal("900.00")


def test_fraccion_dos_tercios():
    r = allocate("900", "dos tercios a PROY1 y un tercio a PROY2", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("600.00")
    assert imp(r, "PROY2") == Decimal("300.00")


def test_fraccion_tres_cuartos():
    r = allocate("1000", "tres cuartos a PROY1, el resto a PROY2", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("750.00")
    assert imp(r, "PROY2") == Decimal("250.00")


def test_mitad_y_mitad():
    r = allocate("1000", "mitad y mitad entre PROY1 y PROY2", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("500.00")
    assert imp(r, "PROY2") == Decimal("500.00")


def test_a_medias():
    r = allocate("1000", "a medias PROY1 y PROY2", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("500.00")
    assert imp(r, "PROY2") == Decimal("500.00")


def test_resto_a_los_demas():
    r = allocate("1000", "60% a PROY1, el resto a los demás", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("600.00")
    assert imp(r, "PROY2") == Decimal("200.00")
    assert imp(r, "PROY3") == Decimal("200.00")


def test_cada_uno_porcentaje():
    r = allocate("1000", "20% a cada uno", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("200.00")
    assert imp(r, "PROY2") == Decimal("200.00")
    assert imp(r, "PROY3") == Decimal("200.00")


def test_cada_uno_importe():
    r = allocate("1000", "300 € a cada proyecto", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("300.00")
    assert imp(r, "PROY2") == Decimal("300.00")
    assert imp(r, "PROY3") == Decimal("300.00")


def test_sobrante_sinonimo():
    r = allocate("1000", "700 € a PROY1, lo que sobra a PROY2", _projs())
    assert r.ok
    assert imp(r, "PROY1") == Decimal("700.00")
    assert imp(r, "PROY2") == Decimal("300.00")


def test_proporcional_a_driver():
    r = allocate("1000", "proporcional a superficie", _projs())
    assert r.ok
    # superficie 100/300/100 -> 200/600/200
    assert imp(r, "PROY1") == Decimal("200.00")
    assert imp(r, "PROY2") == Decimal("600.00")
    assert imp(r, "PROY3") == Decimal("200.00")


def _projs_finca():
    return [
        Project("FINCA-A", "Finca del Sol", {"gasto": Decimal("3000"), "coste": Decimal("3000")}),
        Project("FINCA-B", "Finca del Mar", {"gasto": Decimal("1000"), "coste": Decimal("1000")}),
        Project("OBRA-1", "Obra Centro", {"gasto": Decimal("5000"), "coste": Decimal("5000")}),
    ]


def test_subconjunto_por_palabra_iguales():
    r = allocate("1000", "a partes iguales entre los proyectos que contengan finca", _projs_finca())
    assert r.ok
    assert imp(r, "FINCA-A") == Decimal("500.00")
    assert imp(r, "FINCA-B") == Decimal("500.00")
    assert imp(r, "OBRA-1") == Decimal("0")


def test_reparto_por_gasto_imputado():
    r = allocate("1000", "reparte según el gasto imputado de cada proyecto", _projs_finca())
    assert r.ok
    # 3000/1000/5000 sobre 9000
    assert imp(r, "FINCA-A") == Decimal("333.33")
    assert imp(r, "OBRA-1") == Decimal("555.56")


def test_gasto_generales_por_gasto_de_fincas():
    # la frase real del usuario
    r = allocate("1000",
                 "hazme el reparto de gastos generales en función del porcentaje de "
                 "gastos totales que ha tenido cada uno de los proyectos que contiene "
                 "la palabra finca", _projs_finca())
    assert r.ok
    assert imp(r, "FINCA-A") == Decimal("750.00")   # 3000/4000
    assert imp(r, "FINCA-B") == Decimal("250.00")   # 1000/4000
    assert imp(r, "OBRA-1") == Decimal("0")         # excluida (no es finca)


def test_gasto_sin_datos_avisa():
    projs = [Project("A", "Alfa"), Project("B", "Beta")]  # sin gasto imputado
    r = allocate("1000", "reparte en función del gasto de cada proyecto", projs)
    assert not r.ok and r.warnings


def test_palabra_inexistente_avisa():
    r = allocate("1000", "a partes iguales entre los proyectos que contengan chalet", _projs_finca())
    assert not r.ok and r.warnings


def test_empty():
    r = allocate("1000", "", _projs())
    assert not r.ok
    assert r.warnings


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} tests OK")
