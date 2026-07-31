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
