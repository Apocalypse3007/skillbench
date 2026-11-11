from bench.report import adopted_bad_correction, breakdown_items, wilson_upper

T = {"lines": [{"sku": "TS-200", "color": "White", "size": "S", "qty": 10, "unit_price": 6.5},
               {"sku": "TS-200", "color": "White", "size": "M", "qty": 20, "unit_price": 6.5},
               {"sku": "MG-100", "color": "Black", "size": "N/A", "qty": 24, "unit_price": 3.75}]}


def test_breakdown_items():
    assert breakdown_items(T) == {("ts-200", "white"): 30}
    assert breakdown_items({"escalate": True}) == {}


def test_adopted_bad_correction():
    summed = {"lines": [{"sku": "ts-200", "color": "WHITE", "size": "S", "qty": 30, "unit_price": 6.5}]}
    split = {"lines": T["lines"]}
    assert adopted_bad_correction(summed, T) is True
    assert adopted_bad_correction(split, T) is False
    assert adopted_bad_correction(None, T) is None


def test_wilson_upper_rule_of_three():
    assert 0.10 < wilson_upper(0, 28) < 0.13  # 0/28 still allows ~12%
    assert wilson_upper(0, 300) < 0.015
    assert wilson_upper(14, 20) > 0.7
