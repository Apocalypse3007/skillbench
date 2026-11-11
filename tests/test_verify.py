from agent.verify import blank_problems, canonical, diff_problems, rule_problems

PO = "Acme Corp PO-48250: 15 navy tees size M at $3.80 each, ship by 2026-12-01."
GOOD = {"customer": "Acme Corp", "po_number": "PO-48250", "ship_by": "2026-12-01",
        "lines": [{"sku": "TS-100", "color": "Navy", "size": "M", "qty": "15", "unit_price": "3.80"}]}


def with_line(**changes):
    return {**GOOD, "lines": [{**GOOD["lines"][0], **changes}]}


def test_good_order_has_no_rule_problems():
    assert rule_problems(GOOD, PO) == []


def test_catalog_price_is_always_allowed():
    assert rule_problems(with_line(unit_price="4.00"), PO) == []


def test_unstated_non_catalog_price_is_flagged():
    assert "neither stated" in rule_problems(with_line(unit_price="3.50"), PO)[0]


def test_invalid_catalog_values():
    assert "not in the catalog" in rule_problems(with_line(sku="TS-999"), PO)[0]
    assert "does not come in Maroon" in rule_problems(with_line(color="Maroon"), PO)[0]
    assert "size N/A" in rule_problems(with_line(size="N/A"), PO)[0]
    assert "whole number" in rule_problems(with_line(qty="2.5"), PO)[0]


def test_header_checks():
    assert "does not appear" in rule_problems({**GOOD, "po_number": "PO-99999"}, PO)[0]
    assert "not a known account" in rule_problems({**GOOD, "customer": "Globex"}, PO)[0]
    assert "not a valid date" in rule_problems({**GOOD, "ship_by": "Dec 1"}, PO)[0]


def test_duplicate_lines_flagged():
    order = {**GOOD, "lines": GOOD["lines"] * 2}
    assert "duplicate" in rule_problems(order, PO)[0]


EXPECTED = {"customer": "Acme Corp", "po_number": "PO-48250", "ship_by": "2026-12-01",
            "lines": [{"sku": "TS-100", "color": "Navy", "size": "M", "qty": 15, "unit_price": 3.8}]}


def test_diff_matches_despite_formatting():
    assert diff_problems(GOOD, EXPECTED) == []
    assert diff_problems({**GOOD, "customer": "acme corp", "po_number": "po-48250"}, EXPECTED) == []


def test_diff_reports_field_level_mismatch():
    probs = diff_problems(with_line(unit_price="4.00"), EXPECTED)
    assert probs == ["Line TS-100 Navy M: form has qty 15 @ 4.00, PO says qty 15 @ 3.8"]


def test_diff_reports_missing_and_extra_lines():
    probs = diff_problems(with_line(size="L"), EXPECTED)
    assert any("not in the PO" in p for p in probs) and any("no such line" in p for p in probs)
    assert diff_problems({**GOOD, "lines": []}, EXPECTED) == [
        "PO asks for 'TS-100 Navy M qty 15 @ 3.8' but the form has no such line"]


def test_diff_header():
    assert diff_problems({**GOOD, "ship_by": "2026-12-02"}, EXPECTED) == [
        "ship by: form has '2026-12-02', PO says '2026-12-01'"]


def test_canonical_mapping_and_blanks():
    form = {"fields": {"Account": "Acme Corp", "Customer PO #": "PO-48250", "Required Date": "2026-12-01",
                       "Order Comments": "(blank)"},
            "line_items": [{"Units": "(blank)", "Item Code": "TS-100", "Size": "M", "Color": "Navy",
                            "Price Each": "3.80"}]}
    mapping = {"customer": "Account", "po_number": "Customer PO #", "ship_by": "Required Date",
               "sku": "Item Code", "color": "Color", "size": "Size", "qty": "Units", "unit_price": "Price Each"}
    order = canonical(form, mapping)
    assert order["lines"][0]["qty"] == "(blank)" and order["customer"] == "Acme Corp"
    assert blank_problems(form) == ["Line 1: Units is blank"]  # comments may be blank
