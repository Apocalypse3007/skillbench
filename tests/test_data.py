import json

import config

CATALOG = json.loads(config.CATALOG_PATH.read_text())
PRODUCTS = {p["sku"]: p for p in CATALOG["products"]}


def load_truths():
    return {p.stem: json.loads(p.read_text()) for p in sorted(config.TRUTH_DIR.glob("po_*.json"))}


def test_every_po_has_truth():
    pos = {p.stem for p in config.POS_DIR.glob("po_*.txt")}
    assert len(pos) == 20
    assert pos == set(load_truths())


def test_truth_schema_and_catalog():
    for name, t in load_truths().items():
        if t.get("escalate"):
            assert t["reason"], name
            continue
        assert set(t) == {"customer", "po_number", "ship_by", "lines", "notes"}, name
        assert t["customer"] in CATALOG["customers"], name
        assert t["po_number"] and len(t["ship_by"]) == 10, name
        assert t["lines"], name
        for line in t["lines"]:
            p = PRODUCTS[line["sku"]]
            assert line["color"] in p["colors"], (name, line)
            assert line["size"] in p["sizes"], (name, line)
            assert isinstance(line["qty"], int) and line["qty"] > 0, (name, line)
            assert line["unit_price"] > 0, (name, line)


def test_four_escalations():
    assert sum(1 for t in load_truths().values() if t.get("escalate")) == 4


def test_bad_demo_differs_in_exactly_one_step():
    clean = json.loads(config.DEMOS["clean"].read_text())
    bad = json.loads(config.DEMOS["bad"].read_text())
    diffs = [i for i, (a, b) in enumerate(zip(clean["steps"], bad["steps"])) if a != b]
    assert len(diffs) == 1
    assert clean["rules"] == bad["rules"]
