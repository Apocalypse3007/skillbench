"""Pre-submit verifier (v2): the model reads, code compares.

1. Map the page's labels to order fields once per layout (LLM, cached, validated in code by field type).
2. Deterministic checks on the form: blanks, catalog validity, known customer, PO number present in the
   PO, prices either stated in the PO or equal to the catalog, duplicate lines.
3. The LLM independently extracts the expected order from the PO (or says it must be escalated);
   code compares that reading with the form field by field.
"""
import hashlib
import json
import re
from collections import Counter
from datetime import date

import config
from agent import prompts
from agent.llm import chat_json

HEADER_FIELDS = ["customer", "po_number", "ship_by"]
LINE_FIELDS = ["sku", "color", "size", "qty", "unit_price"]
EXPECTED_TYPE = {"customer": "select", "po_number": "text", "ship_by": "date", "sku": "text",
                 "color": "select", "size": "select", "qty": "number", "unit_price": "number"}
SIZES = {"XS", "S", "M", "L", "XL", "2XL", "N/A"}
BLANK = "(blank)"
_extract_cache = {}


def _catalog():
    return json.loads(config.CATALOG_PATH.read_text())


def form_text(form):
    """Render a label-keyed form state as plain lines (fallback when mapping fails)."""
    head = "\n".join(f"{k}: {v}" for k, v in form["fields"].items())
    lines = "\n".join(f"Line {i}: " + "; ".join(f"{k}={v}" for k, v in row.items())
                      for i, row in enumerate(form["line_items"], 1)) or "(no line items)"
    return f"{head}\n{lines}"


def _mapping_valid(mapping, form):
    header = list(form["fields"])
    row = list(form["line_items"][0])
    if not (all(mapping.get(f) in header for f in HEADER_FIELDS)
            and all(mapping.get(f) in row for f in LINE_FIELDS)
            and len({mapping[f] for f in HEADER_FIELDS + LINE_FIELDS}) == len(HEADER_FIELDS + LINE_FIELDS)):
        return False
    types = form.get("types", {})
    if types and any(types.get(mapping[f]) != t for f, t in EXPECTED_TYPE.items()):
        return False
    sizes = {r.get(mapping["size"]) for r in form["line_items"]} - {BLANK}
    return sizes <= SIZES


def map_fields(form):
    """Return {order field: page label} or None if the mapping is not trustworthy."""
    if not form["line_items"]:
        return None
    header, row = list(form["fields"]), list(form["line_items"][0])
    key = hashlib.sha1(json.dumps([config.MODEL, header, row]).encode()).hexdigest()[:12]
    cache = config.SKILL_CACHE_DIR / f"fieldmap_{key}.json"
    if cache.exists():
        mapping = json.loads(cache.read_text())
        return mapping if _mapping_valid(mapping, form) else None
    types = form.get("types", {})
    describe = lambda labels: [f"{l} ({types[l]})" if l in types else l for l in labels]  # noqa: E731
    data, _ = chat_json(prompts.FIELDMAP_SYSTEM,
                        prompts.FIELDMAP_USER.format(header=describe(header), row=describe(row)))
    if not data:
        return None
    mapping = {f: re.sub(r" \((select|text|date|number)\)$", "", str(data.get(f))) for f in EXPECTED_TYPE}
    if not _mapping_valid(mapping, form):
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(mapping, indent=1))
    return mapping


def canonical(form, mapping):
    def val(v):
        return BLANK if v in ("", None) else v
    return {
        **{f: val(form["fields"][mapping[f]]) for f in HEADER_FIELDS},
        "lines": [{f: val(row.get(mapping[f])) for f in LINE_FIELDS} for row in form["line_items"]],
    }


def blank_problems(form):
    """Blank fields can't be right: every started line item must be complete."""
    probs = [f"Line {i}: {k} is blank" for i, row in enumerate(form["line_items"], 1)
             for k, v in row.items() if v == BLANK]
    probs += [f"{k} is blank" for k, v in form["fields"].items()
              if v == BLANK and not any(w in k.lower() for w in ("note", "comment"))]
    return probs


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _squash(s):
    return re.sub(r"\s+", "", str(s).lower())


def rule_problems(order, po_text):
    """Deterministic checks on a canonical order. No PO parsing beyond finding literal values."""
    cat = _catalog()
    products = {p["sku"].lower(): p for p in cat["products"]}
    probs = []
    if order["customer"] != BLANK and order["customer"] not in cat["customers"]:
        probs.append(f"Customer '{order['customer']}' is not a known account")
    if order["po_number"] != BLANK and _squash(order["po_number"]) not in _squash(po_text):
        probs.append(f"PO number '{order['po_number']}' does not appear in the PO")
    if order["ship_by"] != BLANK:
        try:
            date.fromisoformat(order["ship_by"])
        except ValueError:
            probs.append(f"Ship date '{order['ship_by']}' is not a valid date")
    stated = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", po_text.replace(",", ""))]
    seen = set()
    for i, ln in enumerate(order["lines"], 1):
        p = products.get(ln["sku"].strip().lower())
        if ln["sku"] != BLANK and p is None:
            probs.append(f"Line {i}: product code '{ln['sku']}' is not in the catalog")
        if p:
            if ln["color"] != BLANK and ln["color"] not in p["colors"]:
                probs.append(f"Line {i}: {p['sku']} does not come in {ln['color']} (options: {', '.join(p['colors'])})")
            if ln["size"] != BLANK and ln["size"] not in p["sizes"]:
                probs.append(f"Line {i}: {p['sku']} does not come in size {ln['size']} (options: {', '.join(p['sizes'])})")
        qty, price = _num(ln["qty"]), _num(ln["unit_price"])
        if ln["qty"] != BLANK and (qty is None or qty <= 0 or qty != int(qty)):
            probs.append(f"Line {i}: quantity '{ln['qty']}' must be a positive whole number")
        if ln["unit_price"] != BLANK and (price is None or price <= 0):
            probs.append(f"Line {i}: unit price '{ln['unit_price']}' must be positive")
        elif p and price is not None and abs(price - p["price"]) > 0.005 \
                and not any(abs(price - s) < 0.005 for s in stated):
            probs.append(f"Line {i}: unit price {price:.2f} is neither stated in the PO nor the catalog "
                         f"price ({p['price']:.2f})")
        item = (ln["sku"].lower(), ln["color"].lower(), ln["size"].lower())
        if item in seen:
            probs.append(f"Line {i}: duplicate of an earlier line ({ln['sku']} {ln['color']} {ln['size']})")
        seen.add(item)
    return probs


def extract_expected(po_text):
    """The model's independent reading of the PO: the order it should produce, or an escalation."""
    if po_text not in _extract_cache:
        data, _ = chat_json(prompts.EXTRACT_SYSTEM, prompts.EXTRACT_USER.format(
            catalog=prompts.catalog_text(), po=po_text))
        _extract_cache[po_text] = data
    return _extract_cache[po_text]


def _norm(v):
    n = _num(v)
    return round(n, 2) if n is not None else str(v).strip().lower()


def _key(ln):
    return tuple(_norm(ln.get(f)) for f in LINE_FIELDS)


def _fmt(ln):
    return f"{ln.get('sku')} {ln.get('color')} {ln.get('size')} qty {ln.get('qty')} @ {ln.get('unit_price')}"


def diff_problems(order, expected):
    """Compare the form with the model's reading of the PO, in code."""
    probs = []
    for f in HEADER_FIELDS:
        want = expected.get(f)
        if want and _squash(order[f]) != _squash(want):
            probs.append(f"{f.replace('_', ' ')}: form has '{order[f]}', PO says '{want}'")
    want_lines = [ln for ln in expected.get("lines", []) if isinstance(ln, dict)]
    extra = Counter(map(_key, order["lines"])) - Counter(map(_key, want_lines))
    missing = Counter(map(_key, want_lines)) - Counter(map(_key, order["lines"]))
    by_item = {k[:3]: ln for ln in want_lines for k in [_key(ln)] if missing[k]}
    for ln in order["lines"]:
        k = _key(ln)
        if extra[k] <= 0:
            continue
        extra[k] -= 1
        twin = by_item.pop(k[:3], None)
        if twin:
            missing[_key(twin)] -= 1
            probs.append(f"Line {ln['sku']} {ln['color']} {ln['size']}: form has qty {ln['qty']} @ "
                         f"{ln['unit_price']}, PO says qty {twin.get('qty')} @ {twin.get('unit_price')}")
        else:
            probs.append(f"Form line '{_fmt(ln)}' is not in the PO")
    for ln in want_lines:
        if missing[_key(ln)] > 0:
            missing[_key(ln)] -= 1
            probs.append(f"PO asks for '{_fmt(ln)}' but the form has no such line")
    return probs


def verify(po_text, form):
    probs = blank_problems(form)
    mapping = map_fields(form)
    order = canonical(form, mapping) if mapping else None
    if order:
        probs += rule_problems(order, po_text)

    expected = extract_expected(po_text)
    if expected is None:
        return {"ok": False, "escalate": False, "issues": probs + ["Verifier could not read the PO."],
                "mapped": bool(mapping), "expected": None}
    escalate = bool(expected.get("escalate"))
    if escalate:
        probs.append(f"PO needs a human: {expected.get('escalate_reason') or 'ambiguous'}")
    elif order:
        probs += diff_problems(order, expected)
    else:
        probs.append("Could not identify the form's fields; check the form manually.")
    return {"ok": not probs, "escalate": escalate, "issues": probs, "mapped": bool(mapping),
            "expected": expected}
