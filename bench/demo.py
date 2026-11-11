"""Watch the agent work in a visible browser, for live demos and screen recordings.
Does not touch results/runs.jsonl.

Every scene is a before/after pair of REAL runs on the same order:
  BEFORE = config A (agent alone, no checks), AFTER = config C (verifier + skeptic).
Everything shown comes from the code as it runs: the customer's email, the skill the agent learned, each
action, the verifier's verdicts, and a result card built from the submitted order vs the answer key.
The agent only reads form controls, so the panels and cards do not affect what it does.

  python -m bench.demo                  # all three scenes
  python -m bench.demo --scene 2        # one scene
  python -m bench.demo --pause 1.5      # longer pauses on explanation cards
"""
import argparse
import html
import json
from collections import Counter

from playwright.sync_api import sync_playwright

import config
from agent import loop
from agent.skill import compile_skill, skill_text
from bench.score import HEADER, norm_line, score

SCENES = [
    # Demo-only copy of po_004 with different quantities per line, so a missed line is easy to spot.
    {"title": "UI drift", "cond": "drift", "po": "demo/po_drift",
     "why": "The agent learned its skill on the original form. Business software gets redesigned all the time."},
    {"title": "Flawed demo", "cond": "bad_demo", "po": "003",
     "why": "The person who recorded the demo made one mistake in the price step."},
    {"title": "Order that needs a human", "cond": "normal", "po": "017",
     "why": "The customer asks for a product that is not in the catalog. There is no correct way to enter it."},
]
MODES = {"A": ("BEFORE - agent alone, no checks", "#c62f2f"),
         "C": ("AFTER - with checks (skeptic + verifier)", "#0b7a0b")}
RESULT_TEXT = {
    "correct": ("Correct order submitted", "#0b7a0b"),
    "silent_failure": ("WRONG order submitted - no warning (silent failure)", "#c62f2f"),
    "correct_escalation": ("Handed to a human - correct, this order cannot be entered as written", "#a86b00"),
    "false_escalation": ("Handed to a human - but this order was actually clear", "#a86b00"),
    "timeout_error": ("Ran out of steps", "#c62f2f"),
}
CHANGED_LABELS = ["Customer PO #", "Account", "Required Date", "Units", "Item Code", "Price Each",
                  "Order Comments", "+ New Row", "Place Order"]

UI_JS = """([email, mode, color, catalog]) => {
  const mk = (tag, css, parent) => { const e = document.createElement(tag); e.style.cssText = css;
    (parent || document.body).appendChild(e); return e; };
  const col = mk('div', 'position:fixed;top:12px;right:12px;width:430px;bottom:64px;display:flex;' +
    'flex-direction:column;gap:8px;z-index:99998;font:13px/1.4 system-ui,sans-serif');
  const badge = mk('div', `background:${color};color:#fff;font-weight:600;padding:8px 12px;border-radius:6px;font-size:15px`, col);
  badge.textContent = mode;
  const mail = mk('div', 'background:#fffbe6;border:1px solid #e0c96a;border-radius:6px;padding:10px;' +
    'max-height:250px;overflow:auto;white-space:pre-wrap;font:12.5px/1.4 Consolas,monospace;color:#222', col);
  mail.innerHTML = "<b style='font-family:system-ui'>Customer's email (what the agent reads)</b>\\n";
  mail.appendChild(document.createTextNode(email));
  if (catalog) {
    const cat = mk('div', 'background:#eef4fc;border:1px solid #9ec5f4;border-radius:6px;padding:8px 10px;' +
      'white-space:pre-wrap;font:12.5px/1.4 Consolas,monospace;color:#222', col);
    cat.innerHTML = "<b style='font-family:system-ui'>Catalog (what the agent also sees)</b>\\n";
    cat.appendChild(document.createTextNode(catalog));
  }
  const log = mk('div', 'flex:1;background:#fff;border:1px solid #ccc;border-radius:6px;padding:8px;overflow:auto', col);
  log.id = '__demo_log';
  log.innerHTML = "<b>Agent log (live)</b>";
  const bar = mk('div', 'position:fixed;left:0;right:0;bottom:0;padding:12px 18px;background:#0b0b0b;' +
    'color:#fff;font:16px/1.4 system-ui,sans-serif;z-index:99999');
  bar.id = '__demo_caption';
}"""

CAPTION_JS = "text => { document.getElementById('__demo_caption').textContent = text; }"

LOG_JS = """([text, color, bg]) => {
  const log = document.getElementById('__demo_log');
  const e = document.createElement('div');
  e.style.cssText = `margin-top:5px;padding:4px 6px;border-radius:4px;color:${color};background:${bg};white-space:pre-wrap`;
  e.textContent = text; log.appendChild(e); log.scrollTop = log.scrollHeight;
}"""

CARD_JS = """([inner]) => {
  let back = document.getElementById('__demo_card');
  if (back) back.remove();
  if (!inner) return;
  back = document.createElement('div'); back.id = '__demo_card';
  back.style.cssText = 'position:fixed;inset:0 0 50px 0;background:rgba(0,0,0,.45);display:flex;' +
    'align-items:center;justify-content:center;z-index:100000';
  back.innerHTML = `<div style="background:#fff;color:#111;max-width:900px;width:90%;border-radius:10px;
    padding:22px 26px;font:15px/1.5 system-ui,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.3)">${inner}</div>`;
  document.body.appendChild(back);
}"""

HIGHLIGHT_JS = """labels => {
  for (const el of document.querySelectorAll('label, button')) {
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
    if (labels.includes(own)) {
      el.style.outline = '3px solid #eb6834'; el.style.outlineOffset = '2px'; el.style.width = 'fit-content';
    }
  }
}"""

e = html.escape


def card(page, inner, seconds, pause):
    page.evaluate(CARD_JS, [inner])
    page.wait_for_timeout(int(seconds * 1000 * pause))
    page.evaluate(CARD_JS, [None])


def log(page, text, kind="action"):
    color, bg = {"action": ("#222", "#f3f3f3"), "error": ("#8a4b00", "#fdf0dc"), "block": ("#b00020", "#fde8e8"),
                 "pass": ("#0b6b0b", "#e6f4e6"), "info": ("#1c4f95", "#e8f0fb"),
                 "escalate": ("#8a5a00", "#fdf3df")}[kind]
    page.evaluate(LOG_JS, [text, color, bg])


def on_step(page):
    def handler(rec):
        n, a = rec["step"], rec.get("action") or {}
        v = rec.get("verdict")
        if v:
            if v["ok"]:
                log(page, f"{n}. Verifier: OK to submit", "pass")
            else:
                log(page, f"{n}. Verifier BLOCKED the submit:\n- " + "\n- ".join(v["issues"]), "block")
        if a.get("action") == "escalate":
            log(page, f"{n}. Agent hands it to a human: {a.get('reason', '')}", "escalate")
        elif not v or v["ok"]:
            failed = rec.get("ok") is False or rec.get("action") is None
            result = rec.get("result") or ""
            prefix = "Action failed: " if failed and not result.startswith("Action failed") else ""
            log(page, f"{n}. {prefix}{result}", "error" if failed else "action")
        if rec.get("result") == "escalated by verifier":
            log(page, f"{n}. Still wrong after 2 fixes - handed to a human", "escalate")
    return handler


def result_card(res, truth, outcome):
    """HTML built from the submitted order and the answer key."""
    title, color = RESULT_TEXT[outcome]
    out = f"<div style='font-size:20px;font-weight:700;color:{color};margin-bottom:10px'>{e(title)}</div>"
    if truth.get("escalate"):
        out += f"<p>Correct answer: <b>hand it to a human</b> ({e(truth['reason'])}).</p>"
    if res["end"] == "escalated":
        out += f"<p>Agent's reason: <i>{e((res.get('reason') or '')[:300])}</i></p>"
    order = res.get("order")
    if order and not truth.get("escalate"):
        hdr = [f"{k}: entered <b>{e(str(order.get(k)))}</b>, expected <b>{e(str(truth[k]))}</b>"
               for k in HEADER if str(order.get(k, "")).strip().lower() != str(truth[k]).strip().lower()]
        fields = ("sku", "color", "size", "qty", "unit_price")
        cells = lambda ln: "".join(  # noqa: E731
            f"<td>{e('(blank)' if ln.get(k) in (None, '') else str(ln.get(k)))}</td>" for k in fields)
        want = Counter(map(norm_line, truth["lines"]))
        rows = ""
        for ln in order["lines"]:
            ok = want[norm_line(ln)] > 0
            want[norm_line(ln)] -= ok
            rows += (f"<tr style='color:{'#0b7a0b' if ok else '#c62f2f'}'><td>{'OK' if ok else 'WRONG'}</td>"
                     f"{cells(ln)}</tr>")
        for ln in truth["lines"]:  # expected lines nothing matched, in their original spelling
            if want[norm_line(ln)] > 0:
                want[norm_line(ln)] -= 1
                rows += f"<tr style='color:#c62f2f'><td>MISSING</td>{cells(ln)}</tr>"
        out += ("<p style='margin:6px 0'>Submitted order vs the email:</p><table style='border-collapse:collapse;"
                "width:100%;font-size:14px' cellpadding='4'><tr style='color:#777'><td></td><td>Code</td>"
                "<td>Color</td><td>Size</td><td>Qty</td><td>Unit price</td></tr>" + rows + "</table>")
        out += "".join(f"<p style='color:#c62f2f'>{h}</p>" for h in hdr)
    elif order:
        out += "<p style='color:#c62f2f'>It submitted an order anyway: " + e(
            ", ".join(f"{l['sku']} {l['color']} x{l['qty']}" for l in order["lines"])) + "</p>"
    blocked = sum(1 for s in res["trace"] if s.get("verdict") and not s["verdict"]["ok"])
    if blocked:
        out += f"<p>The verifier blocked {blocked} submit attempt(s) before this.</p>"
    return out


def load_po(po):
    """Benchmark POs are ids like "003"; demo-only POs live in data/demo/ ("demo/po_drift")."""
    if po.startswith("demo/"):
        base = config.DATA_DIR / po
        return base.with_suffix(".txt").read_text(), json.loads(base.with_suffix(".json").read_text())
    return (config.POS_DIR / f"po_{po}.txt").read_text(), json.loads((config.TRUTH_DIR / f"po_{po}.json").read_text())


def catalog_lines(truth):
    """The catalog entries for the products in this order, straight from catalog.json."""
    skus = {l["sku"] for l in truth.get("lines", [])}
    cat = json.loads(config.CATALOG_PATH.read_text())
    return "\n".join(f"{p['sku']} {p['name']} - catalog price ${p['price']:.2f}"
                     for p in cat["products"] if p["sku"] in skus)


def price_step(compiled):
    return next((s for s in compiled["skill"] if "price" in s.lower()), "(no price step)")


def intro(page, scene, pause):
    """Real inputs behind the scene: the forms, the demo files, the catalog."""
    if scene["cond"] == "drift":
        card(page, "<b>Scene 1 - UI drift.</b><br>Below is the <b>original</b> form the demo was recorded on.",
             3, pause)
        page.goto(config.FORMS["v1"].as_uri())
        page.wait_for_timeout(int(4000 * pause))
        page.goto(config.FORMS["v2"].as_uri())
        page.evaluate(HIGHLIGHT_JS, CHANGED_LABELS)
        page.wait_for_timeout(int(1000 * pause))
        card(page, "This is the <b>redesigned</b> form. Every field outlined in orange was <b>renamed or moved</b> "
                   "(e.g. Quantity is now <b>Units</b> and comes first; SKU is now <b>Item Code</b>; "
                   "Submit is now <b>Place Order</b>). The agent never saw this layout.", 6, pause)
    elif scene["cond"] == "bad_demo":
        demo_bad = json.loads(config.DEMOS["bad"].read_text())
        clean = json.loads(config.DEMOS["clean"].read_text())["steps"]
        bad = demo_bad["steps"]
        i = next(k for k, (a, b) in enumerate(zip(clean, bad)) if a != b)
        card(page, f"<b>Scene 2 - flawed demo.</b> The demo was recorded on this example order:<br>"
                   f"<i>\"{e(demo_bad['sample_po'])}\"</i> (catalog price for those tees: $4.00)<br><br>"
                   f"Two recordings of it differ in one step (step {i + 1}, {e(bad[i]['target'])}):<br><br>"
                   f"Correct demo: entered <b>{e(clean[i]['value'])}</b> - <i>\"{e(clean[i]['why'])}\"</i><br>"
                   f"<span style='color:#c62f2f'>Flawed demo: entered <b>{e(bad[i]['value'])}</b> - "
                   f"<i>\"{e(bad[i]['why'])}\"</i></span><br><br>"
                   f"Both agents below learn from the <b>flawed</b> demo. This customer's email says "
                   f"<b>$3.50</b> per mug; the catalog price is $3.75.", 9, pause)
    else:
        cat = json.loads(config.CATALOG_PATH.read_text())
        names = ", ".join(p["name"] for p in cat["products"])
        card(page, "<b>Scene 3 - an order that needs a human.</b> The email asks for <b>stainless steel water "
                   f"bottles</b>.<br><br>The whole catalog: <span style='color:#555'>{e(names)}</span>.<br><br>"
                   "No water bottles - so the right answer is <b>not</b> to submit anything, but to hand it to a "
                   "human.", 9, pause)


def run(browser, scene, cfg_name, pause):
    cfg = config.CONFIGS[cfg_name]
    form, demo, _ = config.CONDITIONS[scene["cond"]]
    compiled = compile_skill(config.DEMOS[demo], skeptic=cfg["skeptic"])
    po_text, truth = load_po(scene["po"])
    mode, color = MODES[cfg_name]

    page = browser.new_page(viewport={"width": 1500, "height": 860})
    page.goto(config.FORMS[form].as_uri())
    if form == "v2":
        page.evaluate(HIGHLIGHT_JS, CHANGED_LABELS)
    page.evaluate(UI_JS, [po_text, mode, color, catalog_lines(truth)])
    page.evaluate(CAPTION_JS, f"{scene['title']}: {mode}")

    if scene["cond"] == "bad_demo":
        log(page, f"Skill learned from the demo - price rule:\n\"{price_step(compiled)}\"", "info")
        if compiled["flagged"]:
            for f in compiled["flagged"]:
                log(page, f"Skeptic check flagged demo step {f.get('step')}: {f.get('problem')}", "block")
        card(page, f"<b>{e(mode)}</b><br><br>The price rule this agent learned from the demo:<br>"
                   f"<i>\"{e(price_step(compiled))}\"</i>"
                   + ("".join(f"<p style='color:#c62f2f'>Skeptic check flagged step {f.get('step')}: "
                              f"{e(f.get('problem', ''))}</p>" for f in compiled["flagged"])
                      if compiled["flagged"] else "<p>(No skeptic check in this config.)</p>"), 7, pause)
    else:
        card(page, f"<b>{e(mode)}</b><br><br>{e(scene['why'])}<br>"
                   + ("Nothing checks the form before it is submitted." if cfg_name == "A" else
                      "Before anything is submitted, the verifier compares the form with the email."), 5, pause)

    print(f"\n=== {scene['title']} / {mode} / {scene['po']}")
    res = loop.run_episode(page, po_text, skill_text(compiled), use_verifier=cfg["verify"], on_step=on_step(page))
    outcome = score(res["end"], res.get("order"), truth)["outcome"]
    print(f"  -> {res['end']} ({outcome}) in {res['steps']} steps, {res['seconds']}s")
    page.evaluate(CAPTION_JS, f"{scene['title']}: {mode} -> {RESULT_TEXT[outcome][0]}")
    card(page, result_card(res, truth, outcome), 9, pause)
    return page, outcome


def run_scene(browser, scene, pause):
    first = browser.new_page(viewport={"width": 1500, "height": 860})
    first.goto(config.FORMS["v1"].as_uri())
    intro(first, scene, pause)
    first.close()
    outcomes = {}
    for cfg_name in ("A", "C"):
        page, outcomes[cfg_name] = run(browser, scene, cfg_name, pause)
        if cfg_name == "A":
            page.close()
    rows = "".join(f"<p><b style='color:{MODES[c][1]}'>{e(MODES[c][0])}:</b> "
                   f"<span style='color:{RESULT_TEXT[o][1]}'>{e(RESULT_TEXT[o][0])}</span></p>"
                   for c, o in outcomes.items())
    card(page, f"<div style='font-size:19px;font-weight:700;margin-bottom:8px'>{e(scene['title'])}: "
               f"before vs after</div>{rows}", 7, pause)
    page.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", type=int, choices=range(1, len(SCENES) + 1), help="run only this scene")
    ap.add_argument("--slow", type=int, default=250, help="ms delay per browser action")
    ap.add_argument("--pause", type=float, default=1.0, help="multiplier for explanation-card pauses")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    scenes = [SCENES[args.scene - 1]] if args.scene else SCENES
    pause = 0.01 if args.headless else args.pause
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=args.slow)
        for scene in scenes:
            run_scene(browser, scene, pause)
        browser.close()


if __name__ == "__main__":
    main()
