from agent.actions import execute, submitted
from agent.observe import form_state, observe, render

V1_LABELS = ["Customer", "PO Number", "Ship By", "SKU", "Color", "Size", "Quantity",
             "Unit Price", "Add Line Item", "Notes", "Submit Order"]
V2_LABELS = ["Customer PO #", "Account", "Required Date", "Units", "Item Code", "Size", "Color",
             "Price Each", "Order Comments", "+ New Row", "Place Order"]


def by_label(obs, label, row=None):
    return next(e for e in obs["elements"] if e["label"] == label and e["row"] == row)


def test_labels_in_page_order(open_form):
    assert [e["label"] for e in observe(open_form("v1"))["elements"]] == V1_LABELS
    assert [e["label"] for e in observe(open_form("v2"))["elements"]] == V2_LABELS


def test_rows_options_and_stable_ids(open_form):
    for version, add, sku in [("v1", "Add Line Item", "SKU"), ("v2", "+ New Row", "Item Code")]:
        page = open_form(version)
        obs = observe(page)
        assert by_label(obs, sku, row=1)
        color = by_label(obs, "Color", row=1)
        assert "Navy" in color["options"] and "" not in color["options"]
        assert by_label(obs, "Size", row=1)["options"] == ["XS", "S", "M", "L", "XL", "2XL", "N/A"]
        assert "Acme Corp" in next(e for e in obs["elements"] if e["tag"] == "select" and not e["row"])["options"]

        ok, _ = execute(page, obs, {"action": "click", "id": by_label(obs, add)["id"]})
        assert ok
        obs2 = observe(page)
        assert by_label(obs2, sku, row=2)
        # ids of existing elements do not change when a row is added
        assert by_label(obs2, sku, row=1)["id"] == by_label(obs, sku, row=1)["id"]


def test_actions_by_id_fill_and_submit(open_form):
    page = open_form("v2")
    obs = observe(page)
    ids = {(e["label"], e["row"]): e["id"] for e in obs["elements"]}
    steps = [
        {"action": "select", "id": ids[("Account", None)], "value": "acme corp"},
        {"action": "fill", "id": ids[("Customer PO #", None)], "value": "PO-9"},
        {"action": "fill", "id": ids[("Required Date", None)], "value": "2026-12-01"},
        {"action": "fill", "id": ids[("Item Code", 1)], "value": "MG-100"},
        {"action": "select", "id": ids[("Color", 1)], "value": "White"},
        {"action": "select", "id": ids[("Size", 1)], "value": "N/A"},
        {"action": "fill", "id": ids[("Units", 1)], "value": "24"},
        {"action": "fill", "id": ids[("Price Each", 1)], "value": "3.75"},
    ]
    for s in steps:
        ok, msg = execute(page, obs, s)
        assert ok, msg
    state = form_state(observe(page))
    assert state["fields"]["Account"] == "Acme Corp"
    assert state["line_items"][0]["Units"] == "24"
    ok, msg = execute(page, obs, {"action": "submit", "id": ids[("Place Order", None)]})
    assert ok, msg
    assert submitted(page)["lines"] == [
        {"sku": "MG-100", "color": "White", "size": "N/A", "qty": 24, "unit_price": 3.75}]
    assert 'page message: "Order submitted"' in render(observe(page))


def test_action_errors_are_feedback(open_form):
    page = open_form("v1")
    obs = observe(page)
    ids = {(e["label"], e["row"]): e["id"] for e in obs["elements"]}
    assert not execute(page, obs, {"action": "fill", "id": "e999", "value": "x"})[0]
    assert not execute(page, obs, {"action": "select", "id": ids[("Customer", None)], "value": "Nobody"})[0]
    assert not execute(page, obs, {"action": "fill", "id": ids[("Ship By", None)], "value": "Dec 5"})[0]
    assert not execute(page, obs, {"action": "fly"})[0]
