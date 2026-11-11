"""Watch the agent work in a visible browser, for live demos and screen recordings.
Does not touch results/runs.jsonl.

  python -m bench.demo                     # the default scenes below
  python -m bench.demo --config A --condition bad_demo --po 003
"""
import argparse
import json

from playwright.sync_api import sync_playwright

import config
from agent import loop
from agent.skill import apply_correction, compile_skill, skill_text
from bench.score import score

SCENES = [
    ("C", "drift", "004", "UI drift: the form was redesigned. Watch the verifier catch a missed field."),
    ("A", "bad_demo", "003", "Flawed demo, baseline: the agent copies the demo's wrong price."),
    ("C", "bad_demo", "003", "Flawed demo, skeptic + verifier: the wrong step was flagged when the skill was compiled."),
    ("C", "normal", "017", "Ambiguous PO (product not in catalog): the right move is to hand it to a human."),
]

CAPTION_JS = """text => {
  let bar = document.getElementById('__demo_caption');
  if (!bar) {
    bar = document.createElement('div'); bar.id = '__demo_caption';
    bar.style.cssText = 'position:fixed;left:0;right:0;bottom:0;padding:10px 16px;background:#0b0b0b;' +
      'color:#fff;font:15px system-ui,sans-serif;z-index:99999;opacity:.92';
    document.body.appendChild(bar);
  }
  bar.textContent = text;
}"""


def run_scene(browser, cfg_name, cond, po, caption, slow):
    cfg = config.CONFIGS[cfg_name]
    form, demo, correction = config.CONDITIONS[cond]
    compiled = compile_skill(config.DEMOS[demo], skeptic=cfg["skeptic"])
    if correction:
        text = json.loads(config.CORRECTIONS_PATH.read_text())[correction]["text"]
        compiled = apply_correction(compiled, config.DEMOS[demo], text, vet=cfg["skeptic"])
    po_text = (config.POS_DIR / f"po_{po}.txt").read_text()
    truth = json.loads((config.TRUTH_DIR / f"po_{po}.json").read_text())

    print(f"\n=== Config {cfg_name} / {cond} / po_{po}: {caption}")
    for f in compiled["flagged"]:
        print(f"  skeptic flagged demo step {f.get('step')}: {f.get('problem')}")
    page = browser.new_page(viewport={"width": 1100, "height": 760})
    page.goto(config.FORMS[form].as_uri())
    label = f"Config {cfg_name} ({'verifier' if cfg['verify'] else 'no verifier'}) | {cond} | po_{po} - {caption}"
    page.evaluate(CAPTION_JS, label)

    res = loop.run_episode(page, po_text, skill_text(compiled), use_verifier=cfg["verify"])
    for s in res["trace"]:
        if s.get("verdict"):
            v = s["verdict"]
            print(f"  step {s['step']}: verifier {'OK' if v['ok'] else 'BLOCKED: ' + '; '.join(v['issues'])}")
    outcome = score(res["end"], res.get("order"), truth)["outcome"]
    print(f"  -> {res['end']} ({outcome}) in {res['steps']} steps, {res['seconds']}s"
          + (f"; reason: {res['reason']}" if res.get("reason") else ""))
    page.evaluate(CAPTION_JS, f"Result: {outcome.replace('_', ' ')}" + (f" - {res['reason']}" if res.get("reason") else ""))
    page.wait_for_timeout(3000 if slow else 500)
    page.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="C")
    ap.add_argument("--condition", default="normal")
    ap.add_argument("--po", help="run one PO instead of the default scenes")
    ap.add_argument("--slow", type=int, default=250, help="ms delay per browser action")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    if args.po:
        known = {s[:3]: s[3] for s in SCENES}
        scenes = [(args.config, args.condition, args.po,
                   known.get((args.config, args.condition, args.po), "custom run"))]
    else:
        scenes = SCENES
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=args.slow)
        for scene in scenes:
            run_scene(browser, *scene, slow=args.slow)
        browser.close()


if __name__ == "__main__":
    main()
