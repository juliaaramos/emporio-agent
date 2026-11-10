from decimal import Decimal

import yaml

from emporio.eval import GOLDEN, check_turn, money_values


def test_money_extraction():
    assert money_values("Sai por R$ 5.519,08 ou 12x de R$ 459,92 (antes R$ 5.999)") == {
        Decimal("5519.08"), Decimal("459.92"), Decimal("5999")
    }


def test_check_turn_rules():
    exp = {"tools_all": ["calcular_pagamento"], "numbers": ["2.089,05"], "forbid_numbers": ["1.935,12"]}
    assert check_turn(exp, "No PIX fica R$ 2.089,05", ["calcular_pagamento"], ["calcular_pagamento"]).ok
    bad = check_turn(exp, "Fica R$ 1.935,12", [], [])
    assert not bad.ok and len(bad.failures) == 3
    assert not check_turn({"policy": True}, "Aceitamos PIX", [], []).ok


def test_golden_set_is_well_formed():
    cases = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    assert sum(1 for c in cases if c.get("holdout")) == 5
    assert len(cases) - 5 >= 25
    allowed = {"tools_all", "tools_any", "tools_none", "policy", "numbers", "forbid_numbers", "contains_any", "not_contains"}
    for c in cases:
        for t in c["turns"]:
            assert set(t.get("expect", {})) <= allowed, c["id"]
