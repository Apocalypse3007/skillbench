"""Thin wrapper around Ollama: JSON-only replies, temperature 0, thinking off, one retry."""
import json
import time

import ollama

import config

STATS = {"calls": 0, "seconds": 0.0}


def chat_json(system, user):
    """Return (parsed_json or None, raw_text). Retries once on invalid JSON."""
    raw = ""
    for _ in range(2):
        t0 = time.time()
        resp = ollama.chat(
            model=config.MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            format="json",
            think=False,
            options={"temperature": config.TEMPERATURE, "seed": config.SEED, "num_ctx": config.NUM_CTX},
        )
        STATS["calls"] += 1
        STATS["seconds"] += time.time() - t0
        raw = resp.message.content
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data, raw
        except json.JSONDecodeError:
            pass
    return None, raw
