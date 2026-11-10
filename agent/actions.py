"""Execute one LLM-chosen action on the page. Returns (ok, message)."""

VALID = {"fill", "select", "click", "submit", "escalate"}


def _find(obs, el_id):
    return next((e for e in obs["elements"] if e["id"] == el_id), None)


def execute(page, obs, action):
    kind = action.get("action")
    if kind not in VALID:
        return False, f"Unknown action '{kind}'. Use one of: {', '.join(sorted(VALID))}."
    if kind == "escalate":
        return True, "escalated"
    el = _find(obs, action.get("id"))
    if el is None:
        return False, f"No element with id '{action.get('id')}'."
    if el["disabled"]:
        return False, f"Element {el['id']} is disabled."
    loc = page.locator(f'[data-agent-id="{el["id"]}"]')
    value = "" if action.get("value") is None else str(action["value"]).strip()
    try:
        if kind == "fill":
            if el["tag"] not in ("input", "textarea"):
                return False, f"{el['id']} is a {el['tag']}, not a text field."
            loc.fill(value, timeout=2000)
            actual = loc.input_value()
            if actual != value:
                hint = " Dates must be YYYY-MM-DD." if el["type"] == "date" else ""
                return False, f'{el["id"]} rejected "{value}" (field now "{actual}").{hint}'
            return True, f'Filled {el["id"]} ("{el["label"]}") with "{value}".'
        if kind == "select":
            if el["tag"] != "select":
                return False, f"{el['id']} is not a select."
            match = next((o for o in el["options"] if o.lower() == value.lower()), None)
            if match is None:
                return False, f'"{value}" is not an option of {el["id"]}. Options: {el["options"]}.'
            loc.select_option(match, timeout=2000)
            return True, f'Selected "{match}" in {el["id"]} ("{el["label"]}").'
        # click / submit
        if el["tag"] != "button":
            return False, f"{el['id']} is not a button."
        loc.click(timeout=2000)
        return True, f'Clicked {el["id"]} ("{el["label"]}").'
    except Exception as exc:  # Playwright errors, e.g. malformed date or number
        return False, f"Action failed: {str(exc).splitlines()[0]}"


def submitted(page):
    return page.evaluate("window.__submitted || null")
