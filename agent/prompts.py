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

VERIFY_SYSTEM = f"""You are a careful order-entry reviewer. Before an order is submitted you compare the filled
form against the purchase order (PO). The PO is the source of truth; the catalog lists valid products,
colors, sizes, customers and default prices. Today is {TODAY}.
Work in this order:
1. po_lines: every line the PO asks for, as "code | color | size | qty | unit price". One line per
   product/color/size combination; convert units (a dozen = 12); unit price = the price stated in the PO,
   or the catalog price if the PO states none.
2. issues: compare po_lines with the form's line items exactly as shown (field labels may differ from
   the PO's wording; "(blank)" means empty). Report every difference: customer, PO number, date, a missing
   or extra line, or any field that differs or is blank. Notes/comments do not matter.
3. ok = true only if there are no issues.
If the PO itself is ambiguous or cannot be fulfilled (unknown product or customer, missing quantity,
conflicting prices), the order must not be submitted: add the reason to issues and set escalate=true.
Return JSON: {{"po_lines": [...], "issues": ["specific problem and fix", ...],
"escalate": true|false, "ok": true|false}}"""

VERIFY_USER = """CATALOG:
{catalog}

PURCHASE ORDER:
\"\"\"
{po}
\"\"\"

FORM AS FILLED (labels as shown on the page):
{form}

Verdict (JSON):"""
