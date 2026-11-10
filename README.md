# SkillBench: measuring and reducing silent failures in demo-learned back-office agents

A local, zero-cost agent learns how to enter a purchase order into a back-office web form from a single
recorded demonstration. A benchmark then measures how often the agent **silently submits a wrong order**
when the UI changes or the demo itself contains a mistake. It also measures how much a pre-submit verifier
and a "skeptical" skill compiler reduce those silent failures.

## Why

Back-office agents learned from demonstrations are brittle in three ways: the UI drifts, inputs are messy,
and the human demo can contain mistakes. For a distributor, the costly failure is not a crash. It is a
wrong order shipped with no warning. This project extends my research on LLMs following instructions they
know are wrong ([Blind Obedience, arXiv:2607.04537](https://arxiv.org/abs/2607.04537)) to agents: *does an
agent blindly copy a flawed demo?*

## Headline result

_TODO after the full run (M7)._

## How it works

```
 demo (recorded steps + narration)
        |
        v
 Skill compiler (LLM) --skeptic mode--> flags suspicious demo steps
        |   UI-independent skill
        v
 Agent loop:  observe page as text -> LLM picks one action -> execute (Playwright)
        |
        v  on "submit"
 Verifier (LLM): form state vs PO --not ok--> feedback, retry (max 2) --> escalate
        |
        v ok
 Submit order  -> scored against ground truth
```

- **Mock app** (`app/`): an order-entry form (`order_v1.html`) and a drifted version (`order_v2.html`)
  with renamed labels, reordered fields, different ids and moved buttons. Both submit identical JSON.
- **Dataset** (`data/`): 20 email-style POs (6 easy, 8 messy, 2 with distractors, 4 that must be
  escalated) with ground-truth orders.
- **Demos**: `demo_clean.json` and `demo_bad.json`. The bad demo has one injected mistake. Its Unit Price
  step enters the catalog price instead of the PO's stated price, narrated as *"Always use the catalog
  price, even if the PO states a different price."*
- **Configs**: A = baseline, B = + verifier, C = + verifier + skeptic skill compile.
- **Conditions**: normal (v1, clean demo), drift (v2, clean demo), bad_demo (v1, bad demo).

Each run ends in exactly one outcome: `correct`, `silent_failure` (submitted wrong, or submitted when it
should have escalated), `correct_escalation`, `false_escalation`, or `timeout_error`.

## Results

_TODO: table, chart, bad-demo analysis (see `results/results.md`)._

## Failure examples

_TODO._

## How this would apply to a production system

- Run an independent verification pass after every learned skill, before any irreversible action.
- Route uncertain cases to the customer's own team instead of guessing.
- Track silent-failure rate as the core reliability metric, separately from task success.
- Run a skeptic pass whenever a new demo is recorded, and show flagged steps to the person who recorded it.

## Limitations

Mock app, small dataset (20 POs), one local model (`qwen3:8b`), and text observations of page elements
instead of screenshots/vision.

## Run it yourself

```bash
# 1. Install Ollama (https://ollama.com/download), then:
ollama pull qwen3:8b
# 2. Python deps (Python 3.11+)
python -m venv .venv && .venv/Scripts/activate      # Windows; use .venv/bin/activate elsewhere
pip install -r requirements.txt
playwright install chromium
# 3. Check, test, run, report
python check_setup.py
python -m pytest -q
python -m bench.run            # all 180 runs; resumable. Try: --configs A --conditions normal --pos 001 002 003
python -m bench.report         # writes results/results.md and results/chart.png
python -m bench.run --headed --slow 300 --configs C --conditions drift --pos 007   # watch one run
```

## Demo video

_TODO._
