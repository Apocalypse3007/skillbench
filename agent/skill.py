"""Compile a recorded demo into a UI-independent skill (one LLM call, cached on disk)."""
import hashlib
import json

import config
from agent import prompts
from agent.llm import chat_json


def compile_skill(demo_path, skeptic=False):
    """Return {"skill": [...], "flagged": [...]}; cached per (demo content, mode, model)."""
    demo = json.loads(demo_path.read_text())
    demo.pop("injected_mistake", None)  # benchmark metadata, never shown to the model
    text = prompts.demo_text(demo)
    key = hashlib.sha1(f"{config.MODEL}|{skeptic}|{text}".encode()).hexdigest()[:12]
    cache = config.SKILL_CACHE_DIR / f"{demo_path.stem}_{'skeptic' if skeptic else 'normal'}_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    template = prompts.SKILL_SKEPTIC if skeptic else prompts.SKILL_NORMAL
    data, raw = chat_json(prompts.SKILL_SYSTEM, template.format(demo=text))
    if not data or not isinstance(data.get("skill"), list):
        raise RuntimeError(f"Skill compilation failed: {raw[:300]}")
    result = {"skill": [str(s) for s in data["skill"]], "flagged": data.get("flagged", []) or []}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result, indent=2))
    return result


def apply_correction(compiled, demo_path, correction, vet=False):
    """Update a compiled skill from one human correction ("correct it once and the skill updates").

    vet=False applies it blindly; vet=True first checks it against the demo and rules and may reject it.
    Returns {"skill", "flagged", "correction": {"text", "accepted", "reason"}}; cached on disk.
    """
    current = skill_text(compiled)
    key = hashlib.sha1(f"{config.MODEL}|{vet}|{current}|{correction}".encode()).hexdigest()[:12]
    cache = config.SKILL_CACHE_DIR / f"corrected_{'vetted' if vet else 'blind'}_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    if vet:
        demo = json.loads(demo_path.read_text())
        demo.pop("injected_mistake", None)
        user = prompts.CORRECTION_VET.format(demo=prompts.demo_text(demo), skill=current, correction=correction)
    else:
        user = prompts.CORRECTION_APPLY.format(skill=current, correction=correction)
    data, raw = chat_json(prompts.CORRECTION_SYSTEM, user)
    if not data or not isinstance(data.get("skill"), list):
        raise RuntimeError(f"Applying correction failed: {raw[:300]}")
    accepted = bool(data.get("accepted", True))
    result = {
        # A rejected correction leaves the skill as it was, whatever the model echoed back.
        "skill": [str(s) for s in data["skill"]] if accepted else compiled["skill"],
        "flagged": compiled["flagged"],
        "correction": {"text": correction, "accepted": accepted, "reason": str(data.get("reason", ""))},
    }
    cache.write_text(json.dumps(result, indent=2))
    return result


def skill_text(compiled):
    return "\n".join(f"{i}. {s}" for i, s in enumerate(compiled["skill"], 1))
