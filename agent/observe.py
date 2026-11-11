"""Turn the current page into a compact text list of interactive elements."""

# Runs in the page. Ids (e1, e2, ...) are stored on the elements so they stay
# stable across steps, e.g. when a new line-item row is added.
_JS = r"""
() => {
  window.__agentNext = window.__agentNext || 1;
  const ownText = (el) => Array.from(el.childNodes)
    .filter((n) => n.nodeType === Node.TEXT_NODE).map((n) => n.textContent).join(" ").trim();
  const labelOf = (el) => {
    if (el.tagName === "BUTTON") return el.innerText.trim();
    if (el.id) {
      const l = document.querySelector(`label[for="${el.id}"]`);
      if (l) return l.innerText.trim();
    }
    if (el.getAttribute("aria-label")) return el.getAttribute("aria-label");
    const wrap = el.closest("label");
    if (wrap && ownText(wrap)) return ownText(wrap);
    const td = el.closest("td");
    if (td) {
      const th = td.closest("table").querySelectorAll("thead th")[td.cellIndex];
      if (th) return th.innerText.trim();
    }
    return el.placeholder || el.name || "";
  };
  const rowOf = (el) => {
    const r = el.closest('tbody > tr, [class*="row"]');
    if (!r) return null;
    const same = Array.from(r.parentElement.children)
      .filter((c) => c.tagName === r.tagName && c.className === r.className);
    return same.indexOf(r) + 1;
  };
  const out = [];
  for (const el of document.querySelectorAll("input, select, textarea, button")) {
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden" || el.type === "hidden") continue;
    if (!el.dataset.agentId) el.dataset.agentId = "e" + window.__agentNext++;
    out.push({
      id: el.dataset.agentId,
      tag: el.tagName.toLowerCase(),
      type: el.tagName === "INPUT" ? el.type : el.tagName.toLowerCase(),
      label: labelOf(el),
      name: el.name || "",
      value: el.tagName === "BUTTON" ? null : el.value,
      options: el.tagName === "SELECT" ? Array.from(el.options).map((o) => o.value).filter((v) => v) : null,
      row: rowOf(el),
      disabled: el.disabled,
    });
  }
  const status = document.querySelector('[role="status"]');
  return { elements: out, status: status ? status.innerText.trim() : "" };
}
"""


def observe(page):
    """Return {"elements": [...], "status": str} for the current page."""
    return page.evaluate(_JS)


def render(obs):
    """Format an observation as the text the LLM sees."""
    lines = []
    for e in obs["elements"]:
        kind = e["type"] if e["tag"] == "input" else e["tag"]
        parts = [e["id"], kind, f'"{e["label"]}"']
        if e["row"]:
            parts.append(f"row={e['row']}")
        if e["value"] is not None:
            parts.append(f'value="{e["value"]}"')
        if e["options"] is not None:
            parts.append("options=[" + ", ".join(e["options"]) + "]")
        if e["disabled"]:
            parts.append("(disabled)")
        lines.append(" ".join(parts))
    if obs["status"]:
        lines.append(f'page message: "{obs["status"]}"')
    return "\n".join(lines)


def form_state(obs):
    """Current form contents keyed by the page's own labels (UI-agnostic, for the verifier)."""
    fields, rows, types = {}, {}, {}
    for e in obs["elements"]:
        if e["value"] is None:
            continue
        value = e["value"] if e["value"] != "" else "(blank)"
        types[e["label"]] = e["type"]
        if e["row"]:
            rows.setdefault(e["row"], {})[e["label"]] = value
        else:
            fields[e["label"]] = value
    # Fully blank rows are never submitted, so leave them out.
    lines = [r for _, r in sorted(rows.items()) if any(v != "(blank)" for v in r.values())]
    return {"fields": fields, "line_items": lines, "types": types}
