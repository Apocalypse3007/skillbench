"""Compare a run's end state with the truth file and assign exactly one outcome."""
from collections import Counter

OUTCOMES = ["correct", "silent_failure", "correct_escalation", "false_escalation", "timeout_error"]
HEADER = ["customer", "po_number", "ship_by"]
LINE = ["sku", "color", "size", "qty", "unit_price"]


def _norm(v):
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return round(float(v), 2)
    s = str(v).strip().lower()
    try:
        return round(float(s), 2)
    except ValueError:
        return s


def norm_line(line):
    return tuple(_norm(line.get(k)) for k in LINE)


def orders_match(order, truth):
    return (all(_norm(order.get(k)) == _norm(truth.get(k)) for k in HEADER)
            and Counter(map(norm_line, order.get("lines", []))) == Counter(map(norm_line, truth["lines"])))


def field_accuracy(order, truth):
    """Fraction of fields correct: 3 header fields + 5 per line, lines paired greedily by best overlap."""
    correct = sum(_norm(order.get(k)) == _norm(truth.get(k)) for k in HEADER)
    remaining = [norm_line(l) for l in order.get("lines", [])]
    for t in map(norm_line, truth["lines"]):
        if not remaining:
            break
        best = max(remaining, key=lambda s: sum(a == b for a, b in zip(s, t)))
        correct += sum(a == b for a, b in zip(best, t))
        remaining.remove(best)
    total = len(HEADER) + len(LINE) * max(len(truth["lines"]), len(order.get("lines", [])))
    return round(correct / total, 3)


def score(end, order, truth):
    """end: "submitted" | "escalated" | anything else (timeout/crash)."""
    should_escalate = bool(truth.get("escalate"))
    if end == "submitted" and order is not None:
        if should_escalate:
            return {"outcome": "silent_failure", "field_accuracy": None}
        ok = orders_match(order, truth)
        return {"outcome": "correct" if ok else "silent_failure", "field_accuracy": field_accuracy(order, truth)}
    if end == "escalated":
        return {"outcome": "correct_escalation" if should_escalate else "false_escalation", "field_accuracy": None}
    return {"outcome": "timeout_error", "field_accuracy": None}
