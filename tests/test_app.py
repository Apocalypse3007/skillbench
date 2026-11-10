import json

import config

EXPECTED = {
    "customer": "Acme Corp",
    "po_number": "PO-48213",
    "ship_by": "2026-12-05",
    "lines": [
        {"sku": "TS-100", "color": "Navy", "size": "M", "qty": 20, "unit_price": 4.0},
        {"sku": "CP-100", "color": "Black", "size": "N/A", "qty": 12, "unit_price": 7.5},
    ],
    "notes": "rush",
}

V1 = {"customer": "#customer", "po": "#po_number", "ship": "#ship_by", "notes": "#notes",
      "add": "#add_line", "submit": "#submit_order", "row": "#lines tbody tr",
      "sku": ".sku", "color": ".color", "size": ".size", "qty": ".qty", "price": ".price"}
V2 = {"customer": "#acct", "po": "#ref_no", "ship": "#req_date", "notes": "#memo",
      "add": "#btn_new_row", "submit": "#btn_place", "row": "#items .item-row",
      "sku": ".f-code", "color": ".f-color", "size": ".f-size", "qty": ".f-units", "price": ".f-each"}


def fill_by_hand(page, s, order):
    page.select_option(s["customer"], order["customer"])
    page.fill(s["po"], order["po_number"])
    page.fill(s["ship"], order["ship_by"])
    for i, line in enumerate(order["lines"]):
        if i > 0:
            page.click(s["add"])
        row = page.locator(s["row"]).nth(i)
        row.locator(s["sku"]).fill(line["sku"])
        row.locator(s["color"]).select_option(line["color"])
        row.locator(s["size"]).select_option(line["size"])
        row.locator(s["qty"]).fill(str(line["qty"]))
        row.locator(s["price"]).fill(str(line["unit_price"]))
    page.fill(s["notes"], order["notes"])
    page.click(s["submit"])
    return page.evaluate("window.__submitted")


def test_v1_and_v2_submit_same_schema(open_form):
    got1 = fill_by_hand(open_form("v1"), V1, EXPECTED)
    got2 = fill_by_hand(open_form("v2"), V2, EXPECTED)
    assert got1 == EXPECTED
    assert got2 == EXPECTED


def test_missing_required_fields_blocks_submit(open_form):
    page = open_form("v1")
    page.click("#submit_order")
    assert page.evaluate("window.__submitted") is None
    assert "missing" in page.inner_text("#status")


def test_wrong_input_is_not_corrected(open_form):
    page = open_form("v2")
    page.select_option("#acct", "Acme Corp")
    page.fill("#ref_no", "PO-1")
    page.locator(".f-code").first.fill("NOT-A-SKU")
    page.locator(".f-units").first.fill("999")
    page.click("#btn_place")
    got = page.evaluate("window.__submitted")
    assert got["lines"] == [{"sku": "NOT-A-SKU", "color": "", "size": "", "qty": 999, "unit_price": None}]


def test_catalog_values_exist_in_app():
    catalog = json.loads(config.CATALOG_PATH.read_text())
    app_js = (config.APP_DIR / "app.js").read_text()
    for c in catalog["customers"]:
        assert f'"{c}"' in app_js
    for p in catalog["products"]:
        for color in p["colors"]:
            assert f'"{color}"' in app_js
