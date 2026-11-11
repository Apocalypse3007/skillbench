"""Evidence check for human reviewers: can each value on an order line be traced back to the email?

A line whose product, color or size is not mentioned in the email was inferred (guessed) by the agent.
This is shown to reviewers (demo, dashboard); it does not change scoring or the verifier's verdict.
"""
import json
import re

import config

SIZE_WORDS = {"XS": ["xs", "extra small"], "S": ["s", "small", "sm"], "M": ["m", "medium", "med"],
              "L": ["l", "large", "lg"], "XL": ["xl", "x-large"], "2XL": ["2xl", "xxl"]}
COLOR_WORDS = {"Heather Gray": ["heather", "gray", "grey"], "Royal Blue": ["royal"], "Forest Green": ["forest"]}


def _products():
    return {p["sku"].upper(): p for p in json.loads(config.CATALOG_PATH.read_text())["products"]}


def product_name(sku):
    p = _products().get(str(sku).strip().upper())
    return p["name"] if p else "not in catalog"


def _words(text):
    return re.findall(r"[a-z0-9/-]+", text.lower())


def line_evidence(line, email):
    """Return a list of problems ("" values mean the field is traced to the email)."""
    words, text = _words(email), email.lower()
    sku = str(line.get("sku") or "").strip().upper()
    p = _products().get(sku)
    probs = []
    if p is None:
        probs.append(f"code {sku or '(blank)'} is not in the catalog")
    elif sku.lower() not in text and not any(w[:4] in text for w in _words(p["name"]) if len(w) >= 4):
        probs.append(f"product '{p['name']}' is not mentioned in the email - agent guessed")
    color = str(line.get("color") or "")
    if color and not any(c in words for c in COLOR_WORDS.get(color, [color.lower()])):
        probs.append(f"color '{color}' is not in the email")
    size = str(line.get("size") or "")
    if size and size != "N/A" and not any(s in words or (" " in s and s in text) for s in SIZE_WORDS.get(size, [size.lower()])):
        mentioned = [t.upper() for t in words if re.fullmatch(r"\d?x+[sl]|\dxl", t)]
        probs.append(f"size {size} is not in the email" + (f" (email says {', '.join(mentioned)})" if mentioned else ""))
    return probs
