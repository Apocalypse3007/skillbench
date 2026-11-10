"""Pre-submit verifier: a rule-based completeness check plus an independent LLM check of the form vs the PO."""
from agent import prompts
from agent.llm import chat_json


def form_text(form):
    """Render the form state as plain lines so the model compares instead of transcribing."""
    head = "\n".join(f"{k}: {v}" for k, v in form["fields"].items())
    lines = "\n".join(f"Line {i}: " + "; ".join(f"{k}={v}" for k, v in row.items())
                      for i, row in enumerate(form["line_items"], 1)) or "(no line items)"
    return f"{head}\n{lines}"


def blank_issues(form):
    """Blank fields can't be right: every started line item must be complete."""
    issues = [f"Line {i}: {k} is blank" for i, row in enumerate(form["line_items"], 1)
              for k, v in row.items() if v == "(blank)"]
    # Header blanks (notes/comments may legitimately be empty).
    issues += [f"{k} is blank" for k, v in form["fields"].items()
               if v == "(blank)" and not any(w in k.lower() for w in ("note", "comment"))]
    return issues


def verify(po_text, form):
    rule_issues = blank_issues(form)
    data, raw = chat_json(prompts.VERIFY_SYSTEM, prompts.VERIFY_USER.format(
        catalog=prompts.catalog_text(), po=po_text, form=form_text(form)))
    if data is None:
        # An unreadable verdict must not wave the order through.
        return {"ok": False, "escalate": False, "issues": rule_issues + ["Verifier returned invalid JSON."],
                "po_lines": None}
    escalate = bool(data.get("escalate"))
    issues = rule_issues + [str(i) for i in data.get("issues", []) or []]
    ok = bool(data.get("ok")) and not escalate and not issues
    return {"ok": ok, "escalate": escalate, "issues": issues, "po_lines": data.get("po_lines")}
