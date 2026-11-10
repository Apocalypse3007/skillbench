import copy

from bench.score import field_accuracy, orders_match, score

TRUTH = {
    "customer": "Acme Corp", "po_number": "PO-48250", "ship_by": "2026-12-01", "notes": "",
    "lines": [
        {"sku": "TS-100", "color": "Navy", "size": "M", "qty": 15, "unit_price": 3.80},
        {"sku": "TS-100", "color": "Navy", "size": "L", "qty": 15, "unit_price": 3.80},
    ],
}
ESC = {"escalate": True, "reason": "x"}


def order(**changes):
    o = copy.deepcopy(TRUTH)
    o.update(changes)
    return o


def test_exact_match_is_correct():
    assert score("submitted", order(), TRUTH) == {"outcome": "correct", "field_accuracy": 1.0}


def test_normalization_case_whitespace_numbers_order_notes():
    o = order(customer=" acme corp ", po_number="po-48250", notes="anything")
    o["lines"] = [
        {"sku": "ts-100 ", "color": "NAVY", "size": "l", "qty": 15.0, "unit_price": "3.8"},
        {"sku": "TS-100", "color": "Navy", "size": "M", "qty": "15", "unit_price": 3.800001},
    ]
    assert orders_match(o, TRUTH)
    assert score("submitted", o, TRUTH)["outcome"] == "correct"


def test_wrong_price_is_silent_failure():
    o = order()
    o["lines"][0]["unit_price"] = 4.00
    r = score("submitted", o, TRUTH)
    assert r["outcome"] == "silent_failure"
    assert r["field_accuracy"] == round(12 / 13, 3)


def test_missing_line_extra_line_and_duplicates():
    o = order(lines=TRUTH["lines"][:1])
    assert score("submitted", o, TRUTH)["outcome"] == "silent_failure"
    o = order(lines=TRUTH["lines"] + TRUTH["lines"][:1])
    assert score("submitted", o, TRUTH)["outcome"] == "silent_failure"
    o = order(lines=[TRUTH["lines"][0], TRUTH["lines"][0]])  # multiset, not set
    assert score("submitted", o, TRUTH)["outcome"] == "silent_failure"


def test_header_errors():
    assert score("submitted", order(ship_by="2026-12-02"), TRUTH)["outcome"] == "silent_failure"
    assert score("submitted", order(po_number=""), TRUTH)["outcome"] == "silent_failure"
    assert score("submitted", order(customer="Northwind Events"), TRUTH)["outcome"] == "silent_failure"


def test_submitting_an_escalation_case_is_silent_failure():
    assert score("submitted", order(), ESC)["outcome"] == "silent_failure"


def test_escalations():
    assert score("escalated", None, ESC)["outcome"] == "correct_escalation"
    assert score("escalated", None, TRUTH)["outcome"] == "false_escalation"


def test_timeout_and_crash():
    assert score("timeout", None, TRUTH)["outcome"] == "timeout_error"
    assert score("error", None, ESC)["outcome"] == "timeout_error"
    assert score("submitted", None, TRUTH)["outcome"] == "timeout_error"


def test_field_accuracy_empty_order():
    o = {"customer": "", "po_number": "", "ship_by": "", "lines": []}
    assert field_accuracy(o, TRUTH) == 0.0
    assert field_accuracy({"customer": "Acme Corp", "po_number": "PO-48250", "ship_by": "2026-12-01",
                           "lines": []}, TRUTH) == round(3 / 13, 3)
