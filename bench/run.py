"""Run POs x conditions x configs; append one JSON line per run to results/runs.jsonl (resumable).

Example: python -m bench.run --configs A --conditions normal --pos 001 002 003
"""
import argparse
import json
import time
import traceback

from playwright.sync_api import sync_playwright

import config
from agent.loop import run_episode
from agent.skill import compile_skill, skill_text
from bench.score import score

RUNS_PATH = config.RESULTS_DIR / "runs.jsonl"


def done_keys():
    if not RUNS_PATH.exists():
        return set()
    return {(r["config"], r["condition"], r["po"]) for r in map(json.loads, RUNS_PATH.read_text().splitlines()) if r}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="+", default=list(config.CONFIGS))
    ap.add_argument("--conditions", nargs="+", default=list(config.CONDITIONS))
    ap.add_argument("--pos", nargs="+", help="PO ids like 001 007 (default: all)")
    ap.add_argument("--limit", type=int, help="max number of new runs")
    ap.add_argument("--headed", action="store_true", help="show the browser")
    ap.add_argument("--slow", type=int, default=0, help="ms delay per browser action (for recordings)")
    args = ap.parse_args()

    pos = args.pos or sorted(p.stem.split("_")[1] for p in config.POS_DIR.glob("po_*.txt"))
    todo = [(c, cond, po) for c in args.configs for cond in args.conditions for po in pos
            if (c, cond, po) not in done_keys()]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(todo)} runs to do")
    config.TRACES_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed, slow_mo=args.slow)
        for i, (cfg_name, cond, po) in enumerate(todo, 1):
            cfg = config.CONFIGS[cfg_name]
            form, demo = config.CONDITIONS[cond]
            po_text = (config.POS_DIR / f"po_{po}.txt").read_text()
            truth = json.loads((config.TRUTH_DIR / f"po_{po}.json").read_text())
            compiled = compile_skill(config.DEMOS[demo], skeptic=cfg["skeptic"])
            page = browser.new_page()
            t0 = time.time()
            try:
                page.goto(config.FORMS[form].as_uri())
                res = run_episode(page, po_text, skill_text(compiled), use_verifier=cfg["verify"])
            except Exception:
                res = {"end": "error", "order": None, "error": traceback.format_exc(), "steps": 0,
                       "llm_calls": 0, "seconds": round(time.time() - t0, 1), "verifier_interventions": 0,
                       "trace": [], "final_form": None}
            finally:
                page.close()

            sc = score(res["end"], res.get("order"), truth)
            record = {
                "config": cfg_name, "condition": cond, "po": po, "form": form, "demo": demo,
                "outcome": sc["outcome"], "field_accuracy": sc["field_accuracy"], "end": res["end"],
                "escalated_by": res.get("escalated_by"), "reason": res.get("reason"),
                "order": res.get("order"), "steps": res["steps"], "llm_calls": res["llm_calls"],
                "seconds": res["seconds"], "verifier_interventions": res["verifier_interventions"],
                "skill_flagged": compiled["flagged"], "model": config.MODEL,
            }
            trace = {**record, "skill": compiled["skill"], "po_text": po_text, "truth": truth,
                     "trace": res["trace"], "final_form": res["final_form"], "error": res.get("error")}
            (config.TRACES_DIR / f"{cfg_name}_{cond}_{po}.json").write_text(json.dumps(trace, indent=1))
            with RUNS_PATH.open("a") as f:
                f.write(json.dumps(record) + "\n")
            print(f"[{i}/{len(todo)}] {cfg_name} {cond:8} po_{po}: {sc['outcome']:18} "
                  f"steps={res['steps']} llm={res['llm_calls']} {res['seconds']}s")
        browser.close()


if __name__ == "__main__":
    main()
