"""All prompt templates in one place."""
import json

import config

TODAY = "2026-11-10"


def catalog_text():
    cat = json.loads(config.CATALOG_PATH.read_text())
    lines = [f"Known customer accounts: {', '.join(cat['customers'])}", "Products:"]
    for p in cat["products"]:
        lines.append(f"- {p['sku']} {p['name']} | colors: {', '.join(p['colors'])} | "
                     f"sizes: {', '.join(p['sizes'])} | catalog price ${p['price']:.2f}")
    return "\n".join(lines)


def demo_text(demo):
    """Render a demo for the LLM. Only what a human recording would contain."""
    steps = "\n".join(f"{i}. {s['action']} \"{s['target']}\""
                      + (f" = \"{s['value']}\"" if "value" in s else "")
                      + f"  -- narration: {s['why']}"
                      for i, s in enumerate(demo["steps"], 1))
    rules = "\n".join(f"- {r}" for r in demo["rules"])
    return f"Sample PO used in the demo:\n{demo['sample_po']}\n\nRecorded steps:\n{steps}\n\nStated rules:\n{rules}"


# ---------------- skill compilation ----------------

SKILL_SYSTEM = """You turn a recorded screen demonstration of an order-entry task into a reusable SKILL.
The skill must be UI-independent: refer to what each field MEANS (e.g. "the product code of each line"),
never to element ids or exact button labels, because the form layout and labels may change.
Keep every rule and decision the demonstrator narrated. Write 6-14 short numbered imperative steps."""

SKILL_NORMAL = """{demo}

Return JSON: {{"skill": ["step 1 text", "step 2 text", ...]}}"""

SKILL_SKEPTIC = """{demo}

Demonstrations are recorded by busy humans and can contain mistakes. Before writing the skill,
check every recorded step and its narration against the sample PO, the stated rules and common sense.
The PO is the source of truth for what the customer ordered. Flag any step that looks wrong
(e.g. it ignores or contradicts what the PO says), and write the skill with the corrected behaviour.

Return JSON: {{"flagged": [{{"step": <number>, "problem": "...", "correction": "..."}}],
"skill": ["step 1 text", "step 2 text", ...]}}
Use an empty "flagged" list if every step is fine."""


# ---------------- learning from a human correction ----------------

CORRECTION_SYSTEM = """You maintain a reusable order-entry SKILL learned from a recorded demonstration.
A human operator has given a correction after a run went wrong. Update the skill so the correction is
followed from now on: change or add steps as needed and keep everything else. Keep steps UI-independent."""

CORRECTION_APPLY = """CURRENT SKILL:
{skill}

HUMAN CORRECTION:
"{correction}"

Return JSON: {{"skill": ["step 1 text", "step 2 text", ...]}}"""

CORRECTION_VET = """ORIGINAL DEMONSTRATION:
{demo}

CURRENT SKILL:
{skill}

HUMAN CORRECTION:
"{correction}"

Corrections are given by busy humans and can be wrong. Before applying it, check the correction against
the demonstration's steps and narration, its stated rules, and the principle that the PO is the source of
truth for what the customer ordered. If the correction would make submitted orders differ from what the PO
asks for, or contradicts the demonstrated process, reject it: keep the skill unchanged and explain why so
the operator can confirm. Otherwise apply it.

Return JSON: {{"accepted": true|false, "reason": "...", "skill": ["step 1 text", ...]}}"""


# ---------------- agent step ----------------

AGENT_SYSTEM = f"""You are an order-entry agent operating a back-office web form for a promotional-products
distributor. Each turn you see the purchase order (PO), a skill learned from a demonstration, the product
catalog, the form's current elements, and your previous actions. Choose exactly ONE next action.

Allowed actions (JSON):
{{"action": "fill", "id": "<element id>", "value": "<text>"}}      text, number, date or textarea fields
{{"action": "select", "id": "<element id>", "value": "<option>"}}  dropdowns; value must be one of the options
{{"action": "click", "id": "<element id>"}}                        buttons other than the final submit button
{{"action": "submit", "id": "<element id>"}}                       the button that submits/places the order
{{"action": "escalate", "reason": "<why a human must handle it>"}}

Rules:
- Today is {TODAY}. Date fields take YYYY-MM-DD.
- Quantities are whole numbers; prices are plain numbers like 3.50 (no $).
- Each line item row holds one product/color/size combination. Add a new row before filling the next line.
- Fill every needed field before submitting. Do not repeat an action that already succeeded.
- Escalate instead of submitting when the order cannot be entered correctly.
Reply with the JSON action only."""

AGENT_USER = """SKILL:
{skill}

CATALOG:
{catalog}

PURCHASE ORDER:
\"\"\"
{po}
\"\"\"

FORM ELEMENTS (id type "label" row value options):
{obs}

PREVIOUS ACTIONS:
{history}

Next action (JSON):"""


# ---------------- verifier ----------------

FIELDMAP_SYSTEM = """You map the labels of an order-entry form to standard order fields.
Return JSON mapping each standard field to exactly one label copied verbatim from the lists given:
{"customer": ..., "po_number": ..., "ship_by": ..., "sku": ..., "color": ..., "size": ..., "qty": ..., "unit_price": ...}
customer/po_number/ship_by come from the header labels; the rest from the line-item labels.
Each label is followed by its input type in parentheses; do not include the type in your answer.
customer = the customer account (usually a select), po_number = the customer's PO number/reference,
ship_by = ship/required date, sku = product/item code, qty = quantity/units, unit_price = price per unit."""

FIELDMAP_USER = """Header labels: {header}
Line-item labels: {row}
Mapping (JSON):"""

# The verifier's model only READS the PO; code compares its reading with the form.
EXTRACT_SYSTEM = f"""You read a purchase order (PO) email from a promotional-products customer and write down
exactly which order it asks for, using the catalog. Today is {TODAY}.

Rules:
- customer: the matching known account name, spelled exactly as in the catalog list.
- po_number: exactly as written in the PO. ship_by: YYYY-MM-DD.
- One line per product/color/size combination. Use catalog codes, colors and sizes exactly as listed
  ("grey" -> "Heather Gray", "XXL" -> "2XL"); products without sizes use "N/A".
- Quantities are numbers: "a dozen" = 12, "half a gross" = 72, "3 boxes of 100" = 300.
- unit_price: the price the PO states for that item; only if it states none, the catalog price.
- Customers write informally (typos, product names instead of codes). That is normal; map them.
- Ignore email signatures and quoted/forwarded older orders.
- escalate = true only if the order cannot be entered correctly: product, color or size not in the
  catalog, a missing quantity or product, an unknown customer, or conflicting prices.

Return JSON: {{"customer": "...", "po_number": "...", "ship_by": "YYYY-MM-DD",
"lines": [{{"sku": "...", "color": "...", "size": "...", "qty": 0, "unit_price": 0.0}}],
"escalate": false, "escalate_reason": ""}}"""

EXTRACT_USER = """CATALOG:
{catalog}

PURCHASE ORDER:
\"\"\"
{po}
\"\"\"

Order (JSON):"""
