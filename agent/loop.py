"""The agent loop: observe -> LLM picks one action -> execute, with optional pre-submit verification."""
import json
import re
import time

import config
from agent import prompts
from agent.actions import execute, submitted
from agent.llm import STATS, chat_json
from agent.observe import form_state, observe, render
from agent.verify import verify

HISTORY_WINDOW = 15  # most recent steps shown to the model
SUBMIT_LABEL = re.compile(r"submit|place order", re.I)


def _screenshot(page, shots_dir, step, el_id):
    """Save the page after a step, with the element the agent acted on outlined. Returns the file name."""
    if el_id:
        page.evaluate("id => { const e = document.querySelector(`[data-agent-id='${id}']`);"
                      " if (e) e.style.outline = '3px solid #eb6834'; }", el_id)
    name = f"step{step:02d}.png"
    page.screenshot(path=str(shots_dir / name), full_page=True)
    if el_id:
        page.evaluate("id => { const e = document.querySelector(`[data-agent-id='${id}']`);"
                      " if (e) e.style.outline = ''; }", el_id)
    return name


def run_episode(page, po_text, skill, use_verifier, shots_dir=None):
    """Fill one PO. Returns a dict with end ("submitted"|"escalated"|"timeout"), order and a trace.

    shots_dir: if given, save a screenshot after every step (for the review dashboard).
    """
    if shots_dir:
        shots_dir.mkdir(parents=True, exist_ok=True)
    calls0, t0 = STATS["calls"], time.time()
    catalog = prompts.catalog_text()
    history, steps = [], []
    fix_attempts = interventions = 0
    result = {"end": "timeout", "order": None, "escalated_by": None, "reason": None}

    def shoot_previous():
        if shots_dir and steps:
            prev = steps[-1]
            prev["screenshot"] = _screenshot(page, shots_dir, prev["step"], (prev["action"] or {}).get("id"))

    for step in range(1, config.MAX_STEPS + 1):
        shoot_previous()
        obs = observe(page)
        user = prompts.AGENT_USER.format(
            skill=skill, catalog=catalog, po=po_text, obs=render(obs),
            history="\n".join(history[-HISTORY_WINDOW:]) or "(none yet)")
        action, raw = chat_json(prompts.AGENT_SYSTEM, user)
        rec = {"step": step, "action": action, "raw": None if action else raw[:500]}
        steps.append(rec)

        if action is None:
            rec["result"] = "invalid JSON"
            history.append(f"{step}. (invalid reply) -> ERROR: reply with one JSON action")
            continue
        kind = action.get("action")
        target = next((e for e in obs["elements"] if e["id"] == action.get("id")), None)
        if kind == "click" and target and SUBMIT_LABEL.search(target["label"]):
            kind = action["action"] = "submit"  # so a plain click cannot skip the verifier

        if kind == "escalate":
            result.update(end="escalated", escalated_by="agent", reason=action.get("reason", ""))
            rec["result"] = "escalated"
            break

        if kind == "submit" and use_verifier:
            verdict = verify(po_text, form_state(obs))
            rec["verdict"] = verdict
            if not verdict["ok"]:
                interventions += 1
                if fix_attempts < config.MAX_FIX_ATTEMPTS:
                    fix_attempts += 1
                    advice = " The PO may need a human: escalate." if verdict["escalate"] else ""
                    history.append(f"{step}. {json.dumps(action)} -> BLOCKED by reviewer: "
                                   + "; ".join(verdict["issues"]) + advice + " Fix the form, then submit again.")
                    rec["result"] = "blocked by verifier"
                    continue
                result.update(end="escalated", escalated_by="verifier", reason="; ".join(verdict["issues"]))
                rec["result"] = "escalated by verifier"
                break

        ok, msg = execute(page, obs, action)
        rec["result"] = msg
        history.append(f"{step}. {json.dumps(action)} -> {'OK' if ok else 'ERROR'}: {msg}")

        if kind in ("submit", "click") and ok:
            order = submitted(page)
            if order is not None:
                result.update(end="submitted", order=order)
                break
            status = observe(page)["status"]
            if status:
                history[-1] += f' Page says: "{status}"'

    shoot_previous()
    result.update(
        steps=len(steps), llm_calls=STATS["calls"] - calls0, seconds=round(time.time() - t0, 1),
        verifier_interventions=interventions, trace=steps, final_form=form_state(observe(page)))
    return result
