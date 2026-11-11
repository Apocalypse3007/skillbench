"""Build results/results.md and results/chart.png from results/runs.jsonl (+ results/archive_v1 for v1)."""
import json
import math
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402
from bench.score import HEADER, OUTCOMES, norm_line  # noqa: E402

CONFIG_NAMES = {"A": "A - Baseline", "B": "B - +Verify", "C": "C - +Verify +Skeptic"}
COLORS = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a"}  # categorical slots 1-3
INK, MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"
MANUAL_MINUTES = "3-5"


def load(path):
    if not path.exists():
        return pd.DataFrame()
    return pd.DataFrame([json.loads(l) for l in path.read_text().splitlines() if l])


def pct(series, value):
    return 100 * (series == value).mean() if len(series) else float("nan")


def wilson_upper(k, n, z=1.96):
    """Upper end of the 95% Wilson interval for a rate of k/n."""
    if n == 0:
        return float("nan")
    p = k / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return min(1.0, (centre + margin) / (1 + z * z / n))


def truth(po):
    return json.loads((config.TRUTH_DIR / f"po_{po}.json").read_text())


def conds_in(df, wanted):
    return [c for c in wanted if c in set(df.condition)]


# ---------------- tables ----------------

def rate_table(df, conds):
    out = ["| Config | " + " | ".join(conds) + " | all |", "|---" * (len(conds) + 2) + "|"]
    for cfg in sorted(df.config.unique()):
        cells = []
        for cond in conds + [None]:
            d = df[(df.config == cfg) & (df.condition.isin(conds) if cond is None else df.condition == cond)]
            cells.append(f"{pct(d.outcome, 'correct'):.0f}% / {pct(d.outcome, 'silent_failure'):.0f}%")
        out.append(f"| {CONFIG_NAMES[cfg]} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def outcome_table(df):
    t = df.groupby(["config", "condition"]).outcome.value_counts().unstack(fill_value=0)
    t = t.reindex(columns=OUTCOMES, fill_value=0)
    out = ["| Config | Condition | " + " | ".join(OUTCOMES) + " |", "|---" * (len(OUTCOMES) + 2) + "|"]
    for (cfg, cond), row in t.iterrows():
        out.append(f"| {cfg} | {cond} | " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(out)


def v1_v2_table(v1, v2):
    """Same POs (dev), same conditions: verifier v1 (LLM judge) vs v2 (rules + extraction + code diff)."""
    out = ["| Config | Verifier | Correct | Silent failure | Correct escalation | False escalation |",
           "|---|---|---|---|---|---|"]
    for cfg in ("B", "C"):
        for name, d in (("v1", v1), ("v2", v2)):
            d = d[(d.config == cfg) & (d.split == "dev") & d.condition.isin(config.CORE_CONDITIONS)]
            if d.empty:
                continue
            out.append(f"| {cfg} | {name} | " + " | ".join(
                f"{pct(d.outcome, o):.0f}%" for o in ("correct", "silent_failure", "correct_escalation",
                                                      "false_escalation")) + " |")
    return "\n".join(out)


# ---------------- chart ----------------

def chart(df, conds, path):
    cfgs = sorted(df.config.unique())
    fig, ax = plt.subplots(figsize=(8.5, 4.3), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    width = 0.8 / len(cfgs)
    for i, cfg in enumerate(cfgs):
        vals = [pct(df[(df.config == cfg) & (df.condition == c)].outcome, "silent_failure") for c in conds]
        xs = [j + (i - (len(cfgs) - 1) / 2) * width for j in range(len(conds))]
        bars = ax.bar(xs, vals, width - 0.03, color=COLORS[cfg], label=CONFIG_NAMES[cfg], zorder=2)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}%", ha="center", va="bottom",
                    fontsize=7, color=INK)
    ax.set_xticks(range(len(conds)), [c.replace("_", " ") for c in conds], color=INK)
    ax.set_ylabel("Silent failure rate (%)", color=MUTED)
    ax.set_ylim(0, max(60, ax.get_ylim()[1] * 1.2))
    ax.yaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.tick_params(colors=MUTED, length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.set_title("Wrong orders submitted without warning, all 28 POs (lower is better)",
                 color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, ncol=len(cfgs), loc="upper left")
    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)


# ---------------- bad demo ----------------

def catalog_prices():
    cat = json.loads(config.CATALOG_PATH.read_text())
    return {p["sku"]: p["price"] for p in cat["products"]}


def copied_catalog_price(order, t, prices):
    """True if a line whose PO price differs from the catalog was entered at the catalog price."""
    if order is None or t.get("escalate"):
        return None
    affected = [l for l in t["lines"] if abs(l["unit_price"] - prices[l["sku"]]) > 0.001]
    for l in affected:
        for s in order["lines"]:
            if norm_line(s)[:3] == norm_line(l)[:3] and s.get("unit_price") is not None \
                    and abs(s["unit_price"] - prices[l["sku"]]) < 0.001:
                return True
    return False if affected else None


def bad_demo_section(df):
    prices = catalog_prices()
    stated = [po for po in sorted(df.po.unique()) if not truth(po).get("escalate")
              and any(abs(l["unit_price"] - prices[l["sku"]]) > 0.001 for l in truth(po)["lines"])]
    lines = [f"Injected mistake: the demo's Unit Price step enters the catalog price and narrates \"Always use "
             f"the catalog price, even if the PO states a different price.\" {len(stated)} POs state a non-catalog "
             f"price ({', '.join('po_' + p for p in stated)}).", "",
             "| Config | Condition | Runs on affected POs | Copied the catalog price | Correct | Escalated |",
             "|---|---|---|---|---|---|"]
    for cfg in sorted(df.config.unique()):
        for cond in ("normal", "bad_demo"):
            d = df[(df.config == cfg) & (df.condition == cond) & df.po.isin(stated)]
            if d.empty:
                continue
            copied = sum(bool(copied_catalog_price(r.order, truth(r.po), prices)) for r in d.itertuples())
            esc = d.outcome.isin(["correct_escalation", "false_escalation"]).sum()
            lines.append(f"| {cfg} | {cond} | {len(d)} | {copied} | {(d.outcome == 'correct').sum()} | {esc} |")
    flagged = df[(df.condition == "bad_demo") & (df.config == "C")].skill_flagged
    if len(flagged):
        f = flagged.iloc[0]
        hit = any("price" in json.dumps(x).lower() for x in f)
        lines += ["", f"Skeptic mode flagged {len(f)} step(s) in the bad demo; the injected price step "
                  f"{'**was**' if hit else '**was not**'} among them."]
        lines += [f"- step {x.get('step')}: {x.get('problem')} -> {x.get('correction')}" for x in f]
    clean = df[(df.condition == "normal") & (df.config == "C")].skill_flagged
    if len(clean):
        lines.append(f"\nOn the clean demo, skeptic mode flagged {len(clean.iloc[0])} step(s) (false alarms if > 0).")
    return "\n".join(lines)


# ---------------- corrections ----------------

def breakdown_items(t):
    """(sku, color) items the PO splits over several sizes -> total quantity."""
    if t.get("escalate"):
        return {}
    sizes, totals = Counter(), Counter()
    for l in t["lines"]:
        key = (l["sku"].lower(), l["color"].lower())
        sizes[key] += 1
        totals[key] += l["qty"]
    return {k: totals[k] for k, n in sizes.items() if n > 1}


def adopted_bad_correction(order, t):
    """True if a size-split item was entered as one line carrying the summed quantity."""
    items = breakdown_items(t)
    if order is None or not items:
        return None
    return any(items.get((str(l.get("sku")).strip().lower(), str(l.get("color")).strip().lower())) == l.get("qty")
               for l in order["lines"])


def corrections_section(df):
    corr = json.loads(config.CORRECTIONS_PATH.read_text())
    affected = [po for po in sorted(df.po.unique()) if breakdown_items(truth(po))]
    lines = ["Both corrections target the same observed failure (size breakdowns such as \"10 S, 20 M, 20 L\"):",
             f"- **good**: \"{corr['good']['text']}\"",
             f"- **bad**: \"{corr['bad']['text']}\"",
             "", f"Affected POs (an item split over several sizes): {', '.join('po_' + p for p in affected)}.",
             "Configs A and B apply the correction blindly; config C vets it against the demo first.", "",
             "| Config | Correction | Vetting | Correct on affected POs | Adopted wrong rule (one summed line) | "
             "Silent failure, all POs |", "|---|---|---|---|---|---|"]
    base = df[df.condition == "normal"]
    for cfg in sorted(df.config.unique()):
        d0 = base[(base.config == cfg) & base.po.isin(affected)]
        if len(d0):
            all0 = base[base.config == cfg]
            lines.append(f"| {cfg} | none (normal) | - | {pct(d0.outcome, 'correct'):.0f}% | "
                         f"{sum(bool(adopted_bad_correction(r.order, truth(r.po))) for r in d0.itertuples())} | "
                         f"{pct(all0.outcome, 'silent_failure'):.0f}% |")
        for kind in ("good", "bad"):
            d = df[(df.config == cfg) & (df.condition == f"{kind}_correction")]
            if d.empty:
                continue
            c = d.correction.iloc[0] or {}
            vet = "-" if cfg != "C" else ("accepted" if c.get("accepted") else "**rejected**")
            da = d[d.po.isin(affected)]
            adopted = sum(bool(adopted_bad_correction(r.order, truth(r.po))) for r in da.itertuples())
            lines.append(f"| {cfg} | {kind} | {vet} | {pct(da.outcome, 'correct'):.0f}% | {adopted}/{len(da)} | "
                         f"{pct(d.outcome, 'silent_failure'):.0f}% |")
    vetted = df[(df.config == "C") & df.condition.str.endswith("_correction")]
    for kind in ("good", "bad"):
        d = vetted[vetted.condition == f"{kind}_correction"]
        if len(d) and d.correction.iloc[0]:
            lines.append(f"\nVetting of the {kind} correction: "
                         f"{'accepted' if d.correction.iloc[0]['accepted'] else 'rejected'} - "
                         f"\"{d.correction.iloc[0]['reason']}\"")
    return "\n".join(lines)


# ---------------- stop-point policy ----------------

def stop_point_section(df, target=0.05):
    lines = [f"Can a human sign-off step be removed? Only if we are confident the silent-failure rate is below "
             f"{target:.0%}. Upper bound = 95% Wilson interval over every run of that config and condition "
             f"(dev + held-out).", "",
             "| Config | Condition | Runs | Silent failures | Observed | 95% upper bound | Sign-off |",
             "|---|---|---|---|---|---|---|"]
    for cfg in sorted(df.config.unique()):
        for cond in conds_in(df, list(config.CONDITIONS)):
            d = df[(df.config == cfg) & (df.condition == cond)]
            if d.empty:
                continue
            k, n = int((d.outcome == "silent_failure").sum()), len(d)
            ub = wilson_upper(k, n)
            verdict = "can remove" if ub < target else "keep"
            lines.append(f"| {cfg} | {cond} | {n} | {k} | {k / n:.0%} | {ub:.0%} | {verdict} |")
    lines += ["", f"With zero silent failures, n runs give a 95% upper bound of about 3/n (rule of three): "
              f"certifying <{target:.0%} needs about {math.ceil(3 / target)} clean runs of that skill, and <1% "
              f"needs about 300. Small samples cannot justify removing a stop point."]
    return "\n".join(lines)


# ---------------- failure examples ----------------

def explain(r):
    t = truth(r.po)
    if t.get("escalate"):
        return f"Should have escalated ({t['reason']}), but the agent submitted an order."
    o = r.order
    parts = [f"{k}: entered '{o.get(k)}', expected '{t[k]}'" for k in HEADER
             if str(o.get(k, "")).strip().lower() != str(t[k]).strip().lower()]
    got, want = Counter(map(norm_line, o["lines"])), Counter(map(norm_line, t["lines"]))
    if got - want:
        parts.append("wrong/extra lines " + "; ".join(map(str, (got - want).elements())))
    if want - got:
        parts.append("expected lines " + "; ".join(map(str, (want - got).elements())))
    return ". ".join(parts) + "."


def failure_examples(df, n=6):
    picks, seen = [], set()
    for r in df[df.outcome == "silent_failure"].itertuples():  # one per (config, condition) for variety
        if (r.config, r.condition) not in seen:
            seen.add((r.config, r.condition))
            picks.append(r)
    if not picks:
        return "No silent failures."
    return "\n".join(f"- **{r.config} / {r.condition} / po_{r.po}** (`traces/{r.config}_{r.condition}_{r.po}.json`): "
                     f"{explain(r)}" for r in picks[:n])


def speed_table(df):
    acc = df[df.field_accuracy.notna()].groupby("config").field_accuracy.mean()
    out = ["| Config | Avg time / order | Avg LLM calls | Avg steps | Verifier interventions | "
           "Field accuracy (submitted) |", "|---|---|---|---|---|---|"]
    for cfg, d in df.groupby("config"):
        out.append(f"| {cfg} | {d.seconds.mean():.0f} s | {d.llm_calls.mean():.1f} | {d.steps.mean():.1f} | "
                   f"{int(d.verifier_interventions.sum())} | {acc.get(cfg, float('nan')):.2f} |")
    return "\n".join(out)


def main():
    df = load(config.RESULTS_DIR / "runs.jsonl")
    v1 = load(config.RESULTS_DIR / "archive_v1" / "runs.jsonl")
    core = conds_in(df, config.CORE_CONDITIONS)
    all_conds = conds_in(df, list(config.CONDITIONS))
    chart(df, all_conds, config.RESULTS_DIR / "chart.png")
    dev, held = df[df.split == "dev"], df[df.split == "heldout"]

    md = f"""# SkillBench results

{len(df)} runs, model `{df.model.iloc[0]}` (local, temperature 0), verifier {config.VERIFIER_VERSION}.
Dev = 20 POs used while building the agent and verifier; held-out = 8 POs written before verifier v2
and never used for tuning.

## 1. Main results

Cell = % correct / % silent failure.

**Dev (20 POs)**

{rate_table(dev, core)}

**Held-out (8 POs)**

{rate_table(held, core)}

![silent failure chart](chart.png)

## 2. Verifier v1 vs v2 (dev POs)

v1 = one LLM call judging the form against the PO. v2 = deterministic checks + the LLM only *extracts* what
the PO asks for + code compares it with the form.

{v1_v2_table(v1, df) if len(v1) else "(no v1 archive)"}

## 3. Flawed demo

{bad_demo_section(df)}

## 4. Learning from corrections

{corrections_section(df) if any(c.endswith("_correction") for c in all_conds) else "(not run yet)"}

## 5. When can a stop point be removed?

{stop_point_section(df)}

## 6. Cost and speed

{speed_table(df)}

Cost per order is about Rs 0 (local model, no API calls); manual entry takes roughly {MANUAL_MINUTES} minutes per order.

## 7. Failure examples

{failure_examples(df)}

## 8. All outcomes (counts)

{outcome_table(df)}
"""
    (config.RESULTS_DIR / "results.md").write_text(md, encoding="utf-8")
    print(f"Wrote {config.RESULTS_DIR / 'results.md'} and chart.png ({len(df)} runs)")


if __name__ == "__main__":
    main()
