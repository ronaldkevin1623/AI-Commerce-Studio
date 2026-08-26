"""
Real local LLM inference via Ollama. Two jobs:
1. Parse free-text user intent into structured constraints
2. Rank real catalog candidates and explain the pick in plain language

Requires Ollama running locally with a tool/JSON-capable model pulled, e.g.:
    ollama pull qwen2.5:7b
"""
import json
import ollama
from app.config import OLLAMA_MODEL

_client = ollama.Client()


def parse_intent(user_text: str) -> dict:
    """
    Turns "wireless earbuds under 2000, fast delivery" into:
    {"category": "earbuds", "max_price_paise": 200000, "priority": "delivery_days"}
    """
    prompt = f"""You are an intent parser for a shopping agent. Convert the user's
request into strict JSON with exactly these keys: category (string, one of:
earbuds), max_price_paise (integer, price in INR paise, i.e. rupees * 100),
priority (string, one of: rating, delivery_days, price, discount — use
"discount" when the user asks for deals, offers, discounts, or best price cuts).

User request: "{user_text}"

Respond with ONLY the JSON object, no other text."""

    response = _client.chat(model=OLLAMA_MODEL, messages=[
        {"role": "user", "content": prompt}
    ])
    content = response["message"]["content"].strip()
    # Models sometimes wrap JSON in markdown fences — strip if present
    content = content.replace("```json", "").replace("```", "").strip()
    return json.loads(content)


def rank_candidates(candidates: list[dict], priority: str) -> dict:
    """
    Given real catalog candidates, asks the LLM to pick the best one
    and explain why in one sentence. Returns the chosen product plus
    the explanation.
    """
    prompt = f"""You are a shopping agent choosing the best product for a
customer who cares most about: {priority}.

Candidates (JSON) — note some items include discount_percent and
original_price_paise when a real discount is available; treat items
without these fields as having no current discount:
{json.dumps(candidates, indent=2)}

Pick exactly one product ID and explain the choice in ONE short sentence.
If priority is "discount", prefer the item with the highest discount_percent.
Respond with ONLY this JSON shape:
{{"chosen_id": "<id>", "reason": "<one sentence>"}}"""

    response = _client.chat(model=OLLAMA_MODEL, messages=[
        {"role": "user", "content": prompt}
    ])
    content = response["message"]["content"].strip()
    content = content.replace("```json", "").replace("```", "").strip()
    result = json.loads(content)

    chosen = next(c for c in candidates if c["id"] == result["chosen_id"])
    return {"product": chosen, "reason": result["reason"]}