"""M0 check: Ollama has the model, it returns JSON, and Playwright opens the form headless."""
import ollama
from playwright.sync_api import sync_playwright

import config
from agent.llm import chat_json

names = [m.model for m in ollama.list().models]
print("ollama models:", names)
assert any(n.startswith(config.MODEL) for n in names), f"run: ollama pull {config.MODEL}"

data, raw = chat_json("Reply in JSON.", 'Return {"ok": true, "sum": 2+3 as a number}.')
print("model reply:", raw)
assert data is not None

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto(config.FORMS["v1"].as_uri())
    print("page title:", page.title())
    b.close()
print("setup OK")
