"""
NEGOTIATOR AGENT

Drafts a message to the seller of a real listing, grounded in that
listing's actual data — price, condition, seller feedback, and whatever
the trust agent flagged on it.

WHAT THIS AGENT CANNOT DO, STATED PLAINLY:
AI Commerce Studio cannot send this message. eBay's Browse API is read-only;
messaging a seller requires the Sell API plus per-user OAuth against the
buyer's own eBay account, which this project has neither the keyset nor
the consent flow for. So the agent writes the message and hands back the
real listing URL for the person to send it themselves.

Drafting it is still genuinely useful work, and it is genuinely real —
a local model reading real listing data. What would not be real is a
"message sent ✓" toast over an API call that never happened.
"""
import ollama

from app.config import OLLAMA_MODEL
from app.agent import settings

_client = ollama.Client()

# What the person wants out of the conversation. Kept to a short, closed
# set so the prompt stays grounded rather than open-ended.
GOALS = {
    "price": "ask whether they would accept a lower price, and name a specific, polite figure",
    "condition": "ask precise questions about the item's actual condition and any wear or faults",
    "authenticity": "ask for evidence the item is genuine — serial numbers, receipts, or extra photos",
    "shipping": "ask about shipping cost, method, and realistic delivery time to India",
}


def draft_message(product: dict, goal: str = None) -> dict:
    """
    Returns {goal, draft, grounding, listing_url, can_send}.

    `grounding` is the exact set of facts handed to the model, so the UI can
    show what the draft was based on rather than asking anyone to trust it.

    Both the default ask and the sentence cap are tunable from the
    Negotiator node on the hive canvas.
    """
    if goal not in GOALS:
        goal = settings.get("negotiator", "goal")
    max_sentences = settings.get("negotiator", "max_sentences")

    # Read defensively — live marketplace data doesn't always carry
    # every field, and a KeyError here would kill the request.
    price_paise = product.get("price_paise") or 0
    trust = product.get("trust") or {}
    flags = trust.get("reasons") or []

    grounding = {
        "title": product.get("name"),
        "price_inr": round(price_paise / 100),
        "condition": product.get("condition") or "not stated by the seller",
        "seller_feedback": product.get("seller_feedback"),
        "trust_flags": flags,
    }

    feedback = grounding["seller_feedback"]
    prompt = f"""You are helping a buyer write a short message to a seller on eBay.

These are the ONLY facts you know about the listing. Do not invent any
others — no invented model numbers, no invented history, no claims about
what the seller said:
- Title: {grounding['title']}
- Asking price: about Rs {grounding['price_inr']}
- Condition as listed: {grounding['condition']}
- Seller feedback score: {f'{feedback}%' if feedback is not None else 'not reported'}
- Concerns an automated check raised: {'; '.join(flags) if flags else 'none'}

The buyer wants to {GOALS[goal]}.

Write the message itself and nothing else — no subject line, no greeting
placeholder like [Name], no sign-off placeholder. Be polite, specific and
brief: {max_sentences} sentence{'s' if max_sentences != 1 else ''} at most.
Plain text."""

    response = _client.chat(model=OLLAMA_MODEL, messages=[
        {"role": "user", "content": prompt}
    ], options={"temperature": settings.get("ollama", "temperature") * 0.01})
    draft = response["message"]["content"].strip()

    return {
        "goal": goal,
        "draft": draft,
        "grounding": grounding,
        "listing_url": product.get("url"),
        # The frontend uses this to render the disclosure rather than a
        # send button. It is always False, and it is meant to be.
        "can_send": False,
    }
