"""Build results/dashboard.html: a local review screen for runs - a "Needs you" queue of escalations
and a step-by-step audit trail per run (actions, verifier verdicts, screenshots, order vs truth).

Usage: python -m bench.dashboard   (then open results/dashboard.html in a browser)
"""
import json
import re

import config
from bench.evidence import line_evidence, product_name


def named(text):
    """Attach the catalog name to every product code, so a reviewer sees what 'TB-200' actually is."""
    if not text:
        return text
    return re.sub(r"\b([A-Z]{2}-\d{3})\b", lambda m: f"{m.group(1)} ({product_name(m.group(1))})", text)

KEEP = ["config", "condition", "po", "split", "outcome", "end", "escalated_by", "reason", "seconds", "steps",
        "llm_calls", "verifier_interventions", "po_text", "truth", "order", "skill", "correction", "skill_flagged"]


def load_runs():
    runs = []
    for p in sorted(config.TRACES_DIR.glob("*.json")):
        t = json.loads(p.read_text())
        run = {k: t.get(k) for k in KEEP}
        run["id"] = p.stem
        run["split"] = run["split"] or next(s for s, ids in config.SPLITS.items() if run["po"] in ids)
        run["reason"] = named(run["reason"])
        if run["order"]:
            for ln in run["order"]["lines"]:
                ln["name"] = product_name(ln.get("sku"))
                ln["evidence"] = line_evidence(ln, run["po_text"])
        for ln in (run["truth"] or {}).get("lines", []):
            ln["name"] = product_name(ln.get("sku"))
        run["trace"] = [{"step": s["step"], "action": s.get("action"), "result": named(s.get("result")),
                         "screenshot": f"screens/{p.stem}/{s['screenshot']}" if s.get("screenshot") else None,
                         "verdict": {"ok": s["verdict"].get("ok"), "escalate": s["verdict"].get("escalate"),
                                     "issues": [named(i) for i in s["verdict"].get("issues", [])]}
                         if s.get("verdict") else None}
                        for s in t.get("trace", [])]
        runs.append(run)
    return runs


def main():
    runs = load_runs()
    html = TEMPLATE.replace("/*DATA*/[]", json.dumps(runs).replace("</", "<\\/"))
    out = config.RESULTS_DIR / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} ({len(runs)} runs)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SkillBench Run Review</title>
<style>
:root {
  --bg: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --line: #e1e0d9; --good: #0b7a0b; --bad: #c62f2f; --warn: #a86b00; --accent: #2a78d6;
  --good-bg: #e8f5e8; --bad-bg: #fbeaea; --warn-bg: #fdf3df;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --line: #2c2c2a; --good: #4cc24c; --bad: #ef6b6b; --warn: #f0b440; --accent: #5598e7;
    --good-bg: #16301a; --bad-bg: #3a1a1a; --warn-bg: #3a2c10;
  }
}
:root[data-theme="dark"] {
  --bg: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --line: #2c2c2a; --good: #4cc24c; --bad: #ef6b6b; --warn: #f0b440; --accent: #5598e7;
  --good-bg: #16301a; --bad-bg: #3a1a1a; --warn-bg: #3a2c10;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
header { padding: 14px 16px; border-bottom: 1px solid var(--line); background: var(--surface); }
h1 { font-size: 17px; margin: 0 0 8px; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; }
select, button { font: inherit; color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px; }
main { display: grid; grid-template-columns: minmax(260px, 360px) 1fr; min-height: calc(100vh - 90px); }
@media (max-width: 800px) { main { grid-template-columns: 1fr; } }
nav { border-right: 1px solid var(--line); overflow: auto; max-height: calc(100vh - 90px); }
.tabs { display: flex; position: sticky; top: 0; background: var(--bg); border-bottom: 1px solid var(--line); }
.tabs button { flex: 1; border: 0; border-radius: 0; padding: 10px; background: transparent; cursor: pointer; color: var(--ink-2); }
.tabs button.on { color: var(--ink); box-shadow: inset 0 -2px 0 var(--accent); font-weight: 600; }
.item { padding: 10px 14px; border-bottom: 1px solid var(--line); cursor: pointer; }
.item:hover, .item.on { background: var(--surface); }
.item .sub { color: var(--muted); font-size: 12px; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip { display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 10px; margin-right: 4px; border: 1px solid var(--line); color: var(--ink-2); }
.o-correct { background: var(--good-bg); color: var(--good); border-color: transparent; }
.o-silent_failure, .o-timeout_error { background: var(--bad-bg); color: var(--bad); border-color: transparent; }
.o-correct_escalation, .o-false_escalation { background: var(--warn-bg); color: var(--warn); border-color: transparent; }
section#detail { padding: 16px; overflow: auto; max-height: calc(100vh - 90px); }
.empty { color: var(--muted); padding: 40px; text-align: center; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 1000px) { .cols { grid-template-columns: 1fr; } }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 12px; margin-bottom: 16px; }
.card h3 { margin: 0 0 8px; font-size: 13px; color: var(--ink-2); text-transform: uppercase; letter-spacing: .04em; }
pre { white-space: pre-wrap; margin: 0; font: 12.5px/1.45 ui-monospace, Consolas, monospace; }
table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
td, th { text-align: left; padding: 4px 6px; border-bottom: 1px solid var(--line); }
th { color: var(--muted); font-weight: 500; }
.miss { color: var(--bad); font-weight: 600; }
.step { display: grid; grid-template-columns: 36px 1fr auto; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--line); align-items: start; }
.step .n { color: var(--muted); font-variant-numeric: tabular-nums; }
.step code { font: 12px ui-monospace, Consolas, monospace; }
.step .res { color: var(--ink-2); font-size: 12.5px; }
.verdict { margin-top: 6px; padding: 6px 8px; border-radius: 6px; font-size: 12.5px; }
.verdict.block { background: var(--bad-bg); color: var(--bad); }
.verdict.pass { background: var(--good-bg); color: var(--good); }
.thumb { width: 120px; border: 1px solid var(--line); border-radius: 4px; cursor: zoom-in; }
#zoom { position: fixed; inset: 0; background: rgba(0,0,0,.75); display: none; align-items: center; justify-content: center; padding: 20px; }
#zoom img { max-width: 100%; max-height: 100%; }
.banner { padding: 10px 12px; border-radius: 8px; margin-bottom: 16px; }
</style>
</head>
<body>
<header>
  <h1>SkillBench run review</h1>
  <div class="filters">
    <select id="f-config"></select><select id="f-condition"></select>
    <select id="f-split"></select><select id="f-outcome"></select>
    <button id="theme" type="button">Theme</button>
    <span id="count" style="color:var(--muted);align-self:center"></span>
  </div>
</header>
<main>
  <nav>
    <div class="tabs"><button id="t-queue" class="on">Needs you</button><button id="t-all">All runs</button></div>
    <div id="list"></div>
  </nav>
  <section id="detail"><div class="empty">Select a run</div></section>
</main>
<div id="zoom"><img alt="step screenshot"></div>
<script>
const RUNS = /*DATA*/[];
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let tab = "queue", selected = null;

function fillSelect(id, key, label) {
  const vals = [...new Set(RUNS.map((r) => r[key]).filter(Boolean))].sort();
  $(id).innerHTML = `<option value="">${label}: all</option>` + vals.map((v) => `<option>${esc(v)}</option>`).join("");
  $(id).onchange = render;
}
fillSelect("#f-config", "config", "Config"); fillSelect("#f-condition", "condition", "Condition");
fillSelect("#f-split", "split", "Split"); fillSelect("#f-outcome", "outcome", "Outcome");

function filtered() {
  const f = (id, k) => (r) => !$(id).value || r[k] === $(id).value;
  let rs = RUNS.filter(f("#f-config", "config")).filter(f("#f-condition", "condition"))
               .filter(f("#f-split", "split")).filter(f("#f-outcome", "outcome"));
  if (tab === "queue") rs = rs.filter((r) => r.end !== "submitted");
  return rs;
}

function render() {
  const rs = filtered();
  $("#count").textContent = `${rs.length} runs`;
  $("#list").innerHTML = rs.map((r) => `
    <div class="item ${r.id === selected ? "on" : ""}" data-id="${r.id}">
      <span class="chip o-${r.outcome}">${esc(r.outcome.replace("_", " "))}</span>
      <b>po_${esc(r.po)}</b> <span class="chip">${esc(r.config)}</span><span class="chip">${esc(r.condition)}</span>
      <div class="sub">${tab === "queue" ? esc((r.escalated_by ? "stopped by " + r.escalated_by + ": " : "") + (r.reason || r.end))
                                          : esc(r.po_text.split("\n")[0])}</div>
    </div>`).join("") || `<div class="empty">Nothing here</div>`;
  document.querySelectorAll(".item").forEach((el) => el.onclick = () => show(el.dataset.id));
}

function orderTable(order, truth) {
  const expected = truth && truth.escalate ? `<p>Expected: <b>escalate</b> - ${esc(truth.reason)}</p>` : "";
  const key = (l) => [l.sku, l.color, l.size, Number(l.qty), Number(l.unit_price).toFixed(2)].join("|").toLowerCase();
  const want = (truth?.lines || []).map(key);
  const got = (order?.lines || []);
  const ev = (l) => !l.evidence ? "" : l.evidence.length ? `<span class="miss">${esc(l.evidence.join("; "))}</span>`
                                                           : `<span style="color:var(--good)">yes</span>`;
  const rows = got.map((l) => `<tr class="${want.includes(key(l)) ? "" : "miss"}"><td>${esc(l.sku)}</td><td>${esc(l.name)}</td>
      <td>${esc(l.color)}</td><td>${esc(l.size)}</td><td>${esc(l.qty ?? "(blank)")}</td><td>${esc(l.unit_price ?? "(blank)")}</td>
      <td>${ev(l)}</td></tr>`).join("");
  const missing = (truth?.lines || []).filter((l) => !got.map(key).includes(key(l)))
      .map((l) => `<tr><td colspan="7" class="miss">missing: ${esc([l.sku, "(" + l.name + ")", l.color, l.size, "qty " + l.qty, "@ " + l.unit_price].join(" "))}</td></tr>`).join("");
  const head = `<tr><th>Code</th><th>Product</th><th>Color</th><th>Size</th><th>Qty</th><th>Price</th><th>In the email?</th></tr>`;
  return expected + (order ? `<table>${head}${rows}${missing}</table>`
                           : `<p style="color:var(--muted)">Nothing submitted.</p>${missing ? `<table>${missing}</table>` : ""}`);
}

function show(id) {
  selected = id; render();
  const r = RUNS.find((x) => x.id === id);
  const banner = {
    correct: ["good", "Submitted and matches the PO."],
    silent_failure: ["bad", "Silent failure: a wrong order was submitted with no warning."],
    correct_escalation: ["warn", "Correctly handed to a human."],
    false_escalation: ["warn", "Handed to a human, but the order was clear (false escalation)."],
    timeout_error: ["bad", "Timed out / crashed."],
  }[r.outcome];
  const steps = r.trace.map((s) => `
    <div class="step"><div class="n">${s.step}</div>
      <div><code>${esc(JSON.stringify(s.action))}</code><div class="res">${esc(s.result)}</div>
        ${s.verdict ? `<div class="verdict ${s.verdict.ok ? "pass" : "block"}">${s.verdict.ok ? "Verifier: OK to submit"
          : "Verifier blocked:<br>" + s.verdict.issues.map(esc).join("<br>")}</div>` : ""}</div>
      <div>${s.screenshot ? `<img class="thumb" src="${esc(s.screenshot)}" alt="step ${s.step}" loading="lazy">` : ""}</div>
    </div>`).join("");
  const corr = r.correction ? `<div class="card"><h3>Human correction</h3><p>"${esc(r.correction.text)}"</p>
      <p>${r.correction.accepted ? "Applied to the skill." : "<b>Rejected by vetting:</b> " + esc(r.correction.reason)}</p></div>` : "";
  $("#detail").innerHTML = `
    <div class="banner o-${r.outcome}">${banner[1]}${r.reason ? "<br><small>" + esc(r.reason) + "</small>" : ""}</div>
    <p><span class="chip">config ${esc(r.config)}</span><span class="chip">${esc(r.condition)}</span>
       <span class="chip">${esc(r.split)}</span><span class="chip">${r.steps} steps</span>
       <span class="chip">${r.seconds}s</span><span class="chip">${r.llm_calls} LLM calls</span></p>
    <div class="cols">
      <div class="card"><h3>Purchase order</h3><pre>${esc(r.po_text)}</pre></div>
      <div class="card"><h3>Submitted vs expected</h3>${orderTable(r.order, r.truth)}</div>
    </div>
    ${corr}
    <div class="card"><h3>Audit trail</h3>${steps}</div>
    <div class="card"><h3>Skill used</h3><pre>${esc((r.skill || []).map((s, i) => `${i + 1}. ${s}`).join("\n"))}</pre></div>`;
  document.querySelectorAll(".thumb").forEach((img) => img.onclick = () => {
    $("#zoom img").src = img.src; $("#zoom").style.display = "flex"; });
}
$("#zoom").onclick = () => $("#zoom").style.display = "none";
$("#t-queue").onclick = () => { tab = "queue"; $("#t-queue").classList.add("on"); $("#t-all").classList.remove("on"); render(); };
$("#t-all").onclick = () => { tab = "all"; $("#t-all").classList.add("on"); $("#t-queue").classList.remove("on"); render(); };
$("#theme").onclick = () => {
  const dark = document.documentElement.dataset.theme === "dark" ||
    (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "light" : "dark";
};
render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
