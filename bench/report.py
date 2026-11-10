"""Build results/results.md and results/chart.png from results/runs.jsonl."""
import json
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


def load():
    rows = [json.loads(l) for l in (config.RESULTS_DIR / "runs.jsonl").read_text().splitlines() if l]
    return pd.DataFrame(rows)


def pct(series, value):
    return 100 * (series == value).mean()


def main_table(df):
    conds = [c for c in config.CONDITIONS if c in set(df.condition)]
    out = ["| Config | " + " | ".join(conds) + " | all |", "|---" * (len(conds) + 2) + "|"]
    for cfg in sorted(df.config.unique()):
        cells = []
        for cond in conds + [None]:
            d = df[(df.config == cfg) & ((df.condition == cond) if cond else True)]
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


def chart(df, path):
    conds = [c for c in config.CONDITIONS if c in set(df.condition)]
    cfgs = sorted(df.config.unique())
    fig, ax = plt.subplots(figsize=(7.5, 4.2), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    width = 0.8 / len(cfgs)
    for i, cfg in enumerate(cfgs):
        vals = [pct(df[(df.config == cfg) & (df.condition == c)].outcome, "silent_failure") for c in conds]
        xs = [j + (i - (len(cfgs) - 1) / 2) * width for j in range(len(conds))]
        bars = ax.bar(xs, vals, width - 0.03, color=COLORS[cfg], label=CONFIG_NAMES[cfg], zorder=2)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}%", ha="center", va="bottom",
                    fontsize=8, color=INK)
    ax.set_xticks(range(len(conds)), conds, color=INK)
    ax.set_ylabel("Silent failure rate (%)", color=MUTED)
    ax.set_ylim(0, max(60, ax.get_ylim()[1] * 1.2))
    ax.yaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.tick_params(colors=MUTED, length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.set_title("Wrong orders submitted without warning (lower is better)", color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, ncol=len(cfgs), loc="upper left")
    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)


def catalog_prices():
    cat = json.loads(config.CATALOG_PATH.read_text())
    return {p["sku"]: p["price"] for p in cat["products"]}


def truth(po):
    return json.loads((config.TRUTH_DIR / f"po_{po}.json").read_text())


def copied_catalog_price(order, t, prices):
    """True if a line whose PO price differs from the catalog was entered at the catalog price."""
    if order is None or t.get("escalate"):
        return None
    affected = [l for l in t["lines"] if abs(l["unit_price"] - prices[l["sku"]]) > 0.001]
    if not affected:
        return None
    for l in affected:
        for s in order["lines"]:
            same_item = norm_line(s)[:3] == norm_line(l)[:3]
            if same_item and s.get("unit_price") is not None and abs(s["unit_price"] - prices[l["sku"]]) < 0.001:
                return True
    return False


def bad_demo_section(df):
    prices = catalog_prices()
    stated = [po for po in sorted(df.po.unique()) if not truth(po).get("escalate")
              and any(abs(l["unit_price"] - prices[l["sku"]]) > 0.001 for l in truth(po)["lines"])]
    lines = [f"The bad demo's injected mistake: the Unit Price step uses the catalog price and narrates "
             f"\"Always use the catalog price, even if the PO states a different price.\" "
             f"{len(stated)} POs state a non-catalog price ({', '.join('po_' + p for p in stated)}).", "",
             "| Config | Condition | Runs on affected POs | Submitted with catalog price (copied) | "
             "Correct | Escalated |", "|---|---|---|---|---|---|"]
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
        lines += ["", f"Skeptic mode flagged {len(f)} step(s) in the bad demo; "
                  f"the injected price step {'**was**' if hit else '**was not**'} among them."]
        lines += [f"- step {x.get('step')}: {x.get('problem')} -> {x.get('correction')}" for x in f]
    clean_flags = df[(df.condition != "bad_demo") & (df.config == "C")].skill_flagged
    if len(clean_flags):
        lines.append(f"\nOn the clean demo, skeptic mode flagged {len(clean_flags.iloc[0])} step(s) "
                     "(false alarms if > 0).")
    return "\n".join(lines)


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


def failure_examples(df, n=5):
    sf = df[df.outcome == "silent_failure"]
    picks, seen = [], set()
    for r in sf.itertuples():  # one per (config, condition) first, for variety
        if (r.config, r.condition) not in seen:
            seen.add((r.config, r.condition))
            picks.append(r)
    picks = picks[:n]
    if not picks:
        return "No silent failures."
    return "\n".join(f"- **{r.config} / {r.condition} / po_{r.po}** (trace `traces/{r.config}_{r.condition}_{r.po}.json`): "
                     f"{explain(r)}" for r in picks)


def main():
    df = load()
    chart(df, config.RESULTS_DIR / "chart.png")
    speed = df.groupby("config").agg(avg_seconds=("seconds", "mean"), avg_llm_calls=("llm_calls", "mean"),
                                     avg_steps=("steps", "mean"),
                                     verifier_interventions=("verifier_interventions", "sum"))
    acc = df[df.field_accuracy.notna()].groupby("config").field_accuracy.mean()
    speed_lines = ["| Config | Avg time / order | Avg LLM calls | Avg steps | Verifier interventions | "
                   "Field accuracy (submitted) |", "|---|---|---|---|---|---|"]
    for cfg, s in speed.iterrows():
        speed_lines.append(f"| {cfg} | {s.avg_seconds:.0f} s | {s.avg_llm_calls:.1f} | {s.avg_steps:.1f} | "
                           f"{int(s.verifier_interventions)} | {acc.get(cfg, float('nan')):.2f} |")

    md = f"""# SkillBench results

{len(df)} runs, model `{df.model.iloc[0]}` (local, temperature 0).

## 1. Main table

Cell = % correct / % silent failure.

{main_table(df)}

All outcomes (counts):

{outcome_table(df)}

## 2. Silent failures

![silent failure chart](chart.png)

## 3. Bad-demo analysis

{bad_demo_section(df)}

## 4. Cost and speed

{chr(10).join(speed_lines)}

Cost per order is about Rs 0 (local model, no API calls); manual entry takes roughly {MANUAL_MINUTES} minutes per order.

## 5. Failure examples

{failure_examples(df)}
"""
    (config.RESULTS_DIR / "results.md").write_text(md, encoding="utf-8")
    print(f"Wrote {config.RESULTS_DIR / 'results.md'} and chart.png ({len(df)} runs)")


if __name__ == "__main__":
    main()
