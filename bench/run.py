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
from agent.skill import apply_correction, compile_skill, skill_text
from bench.score import score

RUNS_PATH = config.RESULTS_DIR / "runs.jsonl"


def done_keys():
    if not RUNS_PATH.exists():
        return set()
    return {(r["config"], r["condition"], r["po"]) for r in map(json.loads, RUNS_PATH.read_text().splitlines()) if r}


def drop_runs(keys):
    """Remove these (config, condition, po) runs from runs.jsonl so they can be rerun."""
    if not RUNS_PATH.exists():
        return
    keep = []
    for line in RUNS_PATH.read_text().splitlines():
        r = json.loads(line) if line else None
        if r and (r["config"], r["condition"], r["po"]) not in keys:
            keep.append(line)
    RUNS_PATH.write_text("".join(l + "\n" for l in keep))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="+", default=list(config.CONFIGS))
    ap.add_argument("--conditions", nargs="+", default=list(config.CONDITIONS))
    ap.add_argument("--pos", nargs="+", help="PO ids like 001 007 (default: all in --splits)")
    ap.add_argument("--splits", nargs="+", default=list(config.SPLITS), help="dev and/or heldout")
    ap.add_argument("--limit", type=int, help="max number of new runs")
    ap.add_argument("--headed", action="store_true", help="show the browser")
    ap.add_argument("--slow", type=int, default=0, help="ms delay per browser action (for recordings)")
    ap.add_argument("--screenshots", action="store_true", help="save a screenshot per step for the dashboard")
    ap.add_argument("--rerun", action="store_true", help="run even if already in runs.jsonl (replaces it)")
    args = ap.parse_args()

    split_of = {po: s for s, ids in config.SPLITS.items() for po in ids}
    pos = args.pos or [po for s in args.splits for po in config.SPLITS[s]]
    done = set() if args.rerun else done_keys()
    todo = [(c, cond, po) for c in args.configs for cond in args.conditions for po in pos
            if (c, cond, po) not in done]
    if args.rerun:
        drop_runs(set(todo))
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(todo)} runs to do")
    corrections = json.loads(config.CORRECTIONS_PATH.read_text())
    config.TRACES_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed, slow_mo=args.slow)
        for i, (cfg_name, cond, po) in enumerate(todo, 1):
            cfg = config.CONFIGS[cfg_name]
            form, demo, correction = config.CONDITIONS[cond]
            po_text = (config.POS_DIR / f"po_{po}.txt").read_text()
            truth = json.loads((config.TRUTH_DIR / f"po_{po}.json").read_text())
            compiled = compile_skill(config.DEMOS[demo], skeptic=cfg["skeptic"])
            if correction:
                # Config C vets corrections the way it vets demos; A and B apply them blindly.
                compiled = apply_correction(compiled, config.DEMOS[demo], corrections[correction]["text"],
                                            vet=cfg["skeptic"])
            page = browser.new_page()
            t0 = time.time()
            try:
                page.goto(config.FORMS[form].as_uri())
                shots = config.RESULTS_DIR / "screens" / f"{cfg_name}_{cond}_{po}" if args.screenshots else None
                res = run_episode(page, po_text, skill_text(compiled), use_verifier=cfg["verify"], shots_dir=shots)
            except Exception:
                res = {"end": "error", "order": None, "error": traceback.format_exc(), "steps": 0,
                       "llm_calls": 0, "seconds": round(time.time() - t0, 1), "verifier_interventions": 0,
                       "trace": [], "final_form": None}
            finally:
                page.close()

            sc = score(res["end"], res.get("order"), truth)
            record = {
                "config": cfg_name, "condition": cond, "po": po, "split": split_of[po],
                "verifier": config.VERIFIER_VERSION if cfg["verify"] else None, "form": form, "demo": demo,
                "outcome": sc["outcome"], "field_accuracy": sc["field_accuracy"], "end": res["end"],
                "escalated_by": res.get("escalated_by"), "reason": res.get("reason"),
                "order": res.get("order"), "steps": res["steps"], "llm_calls": res["llm_calls"],
                "seconds": res["seconds"], "verifier_interventions": res["verifier_interventions"],
                "skill_flagged": compiled["flagged"], "correction": compiled.get("correction"),
                "model": config.MODEL,
            }
            trace = {**record, "skill": compiled["skill"], "po_text": po_text, "truth": truth,
                     "trace": res["trace"], "final_form": res["final_form"], "error": res.get("error")}
            (config.TRACES_DIR / f"{cfg_name}_{cond}_{po}.json").write_text(json.dumps(trace, indent=1))
            with RUNS_PATH.open("a") as f:
                f.write(json.dumps(record) + "\n")
            print(f"[{i}/{len(todo)}] {cfg_name} {cond:15} po_{po}: {sc['outcome']:18} "
                  f"steps={res['steps']} llm={res['llm_calls']} {res['seconds']}s")
        browser.close()


if __name__ == "__main__":
    main()
