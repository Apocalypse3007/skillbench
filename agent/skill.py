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


def skill_text(compiled):
    return "\n".join(f"{i}. {s}" for i, s in enumerate(compiled["skill"], 1))
