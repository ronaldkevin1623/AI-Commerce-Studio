"""
WHAT THE MERCHANT AGENT IS ALLOWED TO DO, RATHER THAN ONLY REPORT.

The advisor answers questions from computed records and changes nothing.
This is the other half: a merchant describes something in the chat and the
agent performs it against the real store.

THREE RULES, AND THEY ARE THE WHOLE DESIGN.

1. AN ACTION DECLARES WHAT IT NEEDS, AND THE AGENT ASKS FOR THE REST.
   Every action lists its required fields. What the merchant said is parsed
   into those fields; anything missing is asked for by name rather than
   guessed at. A price the agent invented would be a price the shop then
   sells at.

2. THE AGENT PREPARES; A PERSON PUBLISHES.
   A new product is written as a DRAFT. `store.create_product` already
   treats that as the boundary — a draft stays out of `search`, so no
   buying agent can discover or check out something the merchant has not
   looked at. The agent does all the work up to the point where goods
   become sellable, and stops there. That is the same shape as the growth
   gate: propose freely, and let a person cross the line that costs money.

3. EVERY ACTION IS WRITTEN DOWN.
   Same decision log as everything else, with the same fields, so an action
   taken by the agent is auditable beside one taken by hand. An action that
   only the person who ran it can find is not an audited action.

ADDING A CAPABILITY IS ADDING AN ENTRY HERE.
   The registry below is the extension point: give an action its required
   fields, a parser, and an executor, and the conversation, the prompting
   for missing values, the confirmation and the audit entry all come for
   free. The alternative — a new endpoint and a new conversational path per
   capability — is how this kind of feature turns into six half-built ones.
"""
import re

# ── Reading values out of what the merchant typed ────────────────────────

# Currency-marked, which is unambiguous: "₹2,450", "Rs 2450", "INR 2450".
_PRICE_CURRENCY_RE = re.compile(
    r"(?:₹|\brs\.?|\binr\b)\s*([\d][\d,]*(?:\.\d{1,2})?)", re.I
)
# Trailing unit: "2450 rupees".
_PRICE_TRAILING_RE = re.compile(
    r"\b([\d][\d,]*(?:\.\d{1,2})?)\s*(?:rupees|rs\b)", re.I
)
# Keyword-anchored, with room for the words people put in between:
# "price it at 899", "sell it for 2450", "costs 1290", "for 2450".
# Up to three filler words, non-greedy, so the number that gets picked is
# the one nearest the keyword rather than the last number in the sentence.
_PRICE_KEYWORD_RE = re.compile(
    r"\b(?:price[a-z]*|cost[a-z]*|sell(?:ing)?|for|at)\b"
    r"(?:\s+\w+){0,3}?\s*"
    r"(?:₹|rs\.?|inr)?\s*"
    r"([\d][\d,]*(?:\.\d{1,2})?)",
    re.I,
)
_STOCK_RE = re.compile(
    r"\b(?:stock|qty|quantity|units?|pieces?|have)\s*(?:of|is|:)?\s*(\d+)\b", re.I
)
_STOCK_SUFFIX_RE = re.compile(r"\b(\d+)\s*(?:in stock|units?|pieces?)\b", re.I)
_NAME_QUOTED_RE = re.compile(r"[\"“']([^\"”']{3,80})[\"”']")
_NAME_CALLED_RE = re.compile(
    r"\b(?:called|named|product|item|it['’]s|its)\s+"
    r"(?:a\s+|an\s+|the\s+)?([A-Za-z0-9][^.,;\n]{2,79})",
    re.I,
)
_CATEGORY_RE = re.compile(
    r"\b(?:category|under|filed under|in)\s+(?:the\s+)?"
    r"([a-z][a-z \-&]{2,39}?)\s*(?:category)?\b(?=[.,;\n]|$)",
    re.I,
)


# WHETHER THE MERCHANT ASKED FOR IT TO GO LIVE.
#
# Default is draft, and that default is the safety property: a parser can
# misread, and a misread price that is live is buyable by an agent within
# seconds. But a merchant who says "add this as active" has made the
# decision themselves, in words, and refusing to honour that would not be
# caution — it would be the agent overriding the person it works for. The
# boundary was never "the agent must not publish"; it was "publishing is a
# person's call". Saying so out loud is that call.
_ACTIVE_RE = re.compile(
    r"\b(?:as |to |make (?:it )?)?"
    r"(?:active|live|published|publish|for sale|on sale)\b",
    re.I,
)
_DRAFT_RE = re.compile(r"\b(?:as |to )?drafts?\b", re.I)


def _paise(raw: str) -> int | None:
    try:
        return int(round(float(str(raw).replace(",", "")) * 100))
    except (TypeError, ValueError):
        return None


def parse_product(text: str, image: str | None = None) -> dict:
    """
    Pull product fields out of a sentence. Absent is absent.

    Nothing is inferred to fill a gap: if the merchant did not say a price,
    the price is missing and gets asked for. A parser that guessed would be
    setting the shelf price of real goods from a regular expression.
    """
    blob = text or ""
    found: dict = {}

    # STOCK FIRST, AND ITS DIGITS ARE THEN OFF THE TABLE.
    #
    # "for 2450, stock 12" has two numbers and only one of them is a price.
    # Claiming the stock count first and blanking it out stops the price
    # patterns wandering onto it — a shop that listed a ₹12 monitor riser
    # because the parser preferred the nearest number would be worse than
    # one that asked.
    stock = _STOCK_RE.search(blob) or _STOCK_SUFFIX_RE.search(blob)
    remaining = blob
    if stock:
        try:
            found["stock"] = int(stock.group(1))
            remaining = blob[:stock.start()] + " " + blob[stock.end():]
        except ValueError:
            pass

    money = (_PRICE_CURRENCY_RE.search(remaining)
             or _PRICE_TRAILING_RE.search(remaining)
             or _PRICE_KEYWORD_RE.search(remaining))
    if money:
        paise = _paise(money.group(1))
        if paise and paise > 0:
            found["price_paise"] = paise

    # A quoted name is unambiguous, so it wins over the looser phrasing.
    quoted = _NAME_QUOTED_RE.search(blob)
    if quoted:
        found["name"] = quoted.group(1).strip()
    else:
        called = _NAME_CALLED_RE.search(blob)
        if called:
            name = called.group(1).strip()
            # Trim a trailing price or stock clause that the loose pattern
            # will happily swallow: "a Bamboo Stand for 1290" is a name and
            # a price, not an eighteen-word product name.
            name = re.split(r"\b(?:for|at|priced|costing|stock|qty)\b", name, 1, re.I)[0]
            name = name.strip(" -–—:,")
            if len(name) >= 3:
                found["name"] = name

    category = _CATEGORY_RE.search(blob)
    if category:
        value = category.group(1).strip().lower()
        if value not in {"stock", "the store", "store", "storefront"}:
            found["category"] = value

    # Draft wins a tie: if the sentence somehow says both, the safer of the
    # two is the one that does not put goods in front of a buying agent.
    if _DRAFT_RE.search(blob):
        found["status"] = "draft"
    elif _ACTIVE_RE.search(blob):
        found["status"] = "active"

    if image:
        found["image"] = image

    return found


# ── The registry ─────────────────────────────────────────────────────────

def _execute_add_product(slots: dict) -> dict:
    from app.firebase_client import log_decision
    from app.merchant import store

    created = store.create_product({
        "name": slots.get("name"),
        "price_paise": slots.get("price_paise"),
        "stock": slots.get("stock") or 0,
        "category": slots.get("category"),
        "description": slots.get("description"),
        "image": slots.get("image"),
        # Draft unless the merchant said otherwise in words.
        "status": slots.get("status") or "draft",
    })
    if not created.get("ok"):
        return {"ok": False, "error": created.get("error")}

    product = created["product"]
    log_decision(
        action_type="merchant_product_added",
        amount_paise=int(product.get("price_paise") or 0),
        decision="allowed",
        reason=(
            f"Merchant agent created {product['name']} as a DRAFT at "
            f"₹{int(product.get('price_paise') or 0) / 100:,.2f}, stock "
            f"{product.get('stock')}. Drafts stay out of the UCP catalogue, "
            f"so no buying agent can discover or check it out until the "
            f"merchant publishes it."
        ),
    )
    return {"ok": True, "product": product}


# ── WHICH PRODUCT DID THEY MEAN? ─────────────────────────────────────────
#
# Adding a product needs no answer to this; everything else does. "Set the
# price of the desk lamp to 1200" names a product the way a person names
# one — by the words they remember, not by `cds-desk-lamp`.
#
# Resolution is by word overlap against the live catalogue, and it REFUSES
# rather than guesses. A wrong match here does not return a wrong answer,
# it changes the wrong product's price, so a near-tie has to become a
# question. That is the same rule the buying agent applies to a budget: the
# cost of being wrong decides whether a rule may guess.

_NAME_NOISE = {
    "with", "and", "the", "for", "in", "of", "a", "an", "to", "my", "our",
    "product", "item", "listing", "this", "that", "it", "levels", "level",
}


def _name_words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9%]+", (text or "").lower())
            if len(w) > 1 and w not in _NAME_NOISE}


def resolve_product(text: str) -> dict:
    """
    The product the merchant is talking about.

    Returns one of:
      {"product": {...}}                  exactly one clear match
      {"choices": [...]}                  more than one, equally good
      {"error": "..."}                    nothing in the catalogue matches
    """
    try:
        from app.merchant import store
        catalogue = store.list_products()
    except Exception as exc:
        return {"error": f"I could not read the catalogue: {exc}"}
    if not catalogue:
        return {"error": "There are no products in the store yet."}

    said = _name_words(text)
    if not said:
        return {"error": "I could not tell which product you meant."}

    scored = []
    for product in catalogue:
        words = _name_words(product.get("name"))
        if not words:
            continue
        hits = len(words & said)
        if not hits:
            continue
        # Specificity breaks ties: "stand" hits both the monitor stand and
        # the prototype stand, and the one whose name is MOSTLY matched is
        # the one that was meant.
        scored.append((hits, hits / len(words), product))

    if not scored:
        return {"error": ("Nothing in your catalogue matches that. Tell me "
                          "the product name as it appears in the storefront.")}

    scored.sort(key=lambda row: (-row[0], -row[1]))
    best = scored[0]
    # AS MANY WORDS MATCHED MEANS ASK, WHATEVER THE SPECIFICITY SAYS.
    #
    # Specificity was breaking ties on its own, and "update the stand"
    # silently picked the Unfinished Prototype Stand over the Bamboo Monitor
    # Stand because its name is shorter — one of three words beats one of
    # four. That is a real difference in a ratio and no evidence at all
    # about which one was meant: both matched exactly one word, and it was
    # the same word. Two products that matched equally well is a question,
    # and this action changes a real shop.
    rivals = [row for row in scored[1:] if row[0] == best[0]]
    if rivals:
        return {"choices": [row[2] for row in [best] + rivals][:4]}
    return {"product": best[2]}


# ── Reading an EDIT, which is shaped differently from a creation ─────────
#
# "Add a desk lamp for 1290" puts the field and its value next to each
# other. "Set the price of the desk lamp to 1200" puts the product's whole
# name between them, and the creation patterns — which allow three filler
# words at most, deliberately, so a price cannot wander onto the nearest
# number — cannot reach across it. They were right to refuse: the fix is
# not a looser price pattern, which would start reading stock counts as
# prices again, but a pattern that knows an edit names its field first and
# its value after "to".
#
# The field word anchors the left, "to"/"at"/"=" anchors the right, and the
# product name is whatever sits between them.
_EDIT_PRICE_RE = re.compile(
    r"\b(?:price[a-z]*|cost[a-z]*|sell(?:ing)?\s+price)\b[^.\n]{0,60}?"
    r"\b(?:to|at|as|=)\s*(?:₹|rs\.?|inr)?\s*([\d][\d,]*(?:\.\d{1,2})?)",
    re.I)
_EDIT_STOCK_RE = re.compile(
    r"\b(?:stock|qty|quantity|units?|pieces?|inventory)\b[^.\n]{0,60}?"
    r"\b(?:to|at|is|=)\s*(\d+)\b",
    re.I)
# "reprice the desk lamp to 1200" / "restock the desk lamp to 40" — the verb
# carries the field, so no field noun appears at all.
_EDIT_VERB_PRICE_RE = re.compile(
    r"\bre-?price\b[^.\n]{0,60}?\b(?:to|at|=)\s*(?:₹|rs\.?|inr)?\s*"
    r"([\d][\d,]*(?:\.\d{1,2})?)", re.I)
_EDIT_VERB_STOCK_RE = re.compile(
    r"\bre-?stock\b[^.\n]{0,60}?\b(?:to|at|=)\s*(\d+)\b", re.I)


def parse_edit(text: str, image: str | None = None) -> dict:
    """
    What to change, without mistaking the product's own name for a new one.

    `parse_product` reads a name out of the sentence, which is right when
    something is being created and wrong here: "rename the desk lamp" would
    be read as a name and the edit would rename it to itself. A rename is
    only accepted when the merchant said "rename … to X", which is
    unambiguous.
    """
    blob = text or ""
    found = parse_product(blob, image)
    found.pop("name", None)

    # The edit-shaped patterns win where they match: they were written for
    # exactly this sentence, and the creation patterns can only have got
    # here by reading some other number in it.
    stock = _EDIT_STOCK_RE.search(blob) or _EDIT_VERB_STOCK_RE.search(blob)
    if stock:
        try:
            found["stock"] = int(stock.group(1))
        except ValueError:
            pass

    money = _EDIT_PRICE_RE.search(blob) or _EDIT_VERB_PRICE_RE.search(blob)
    if money:
        paise = _paise(money.group(1))
        if paise and paise > 0:
            found["price_paise"] = paise

    # A NUMBER THAT IS THE STOCK IS NOT ALSO THE PRICE.
    #
    # "Change the stock of the desk lamp to 40" contains one number and two
    # patterns that would like it. The creation parser has the same rule and
    # solves it by claiming stock first and blanking the digits; here the
    # patterns run over the whole sentence, so the collision is resolved
    # afterwards instead. Stock wins, because it named itself.
    if (stock and found.get("price_paise") is not None
            and found["price_paise"] == int(found.get("stock") or -1) * 100):
        found.pop("price_paise", None)

    renamed = _RENAME_RE.search(text or "")
    if renamed:
        candidate = renamed.group(1).strip(" \"'“”.")
        if len(candidate) >= 3:
            found["name"] = candidate
    return found


_RENAME_RE = re.compile(
    r"\b(?:rename|call|retitle)\b[^.\n]*?\bto\s+[\"“']?([^\"”'.,;\n]{3,80})",
    re.I)

# The fields an edit may carry. `product_id` is not one of them — it is
# resolved from the sentence, never typed by the merchant.
_EDITABLE = ("name", "price_paise", "stock", "category", "description",
             "status", "image")


def _execute_update_product(slots: dict) -> dict:
    from app.firebase_client import log_decision
    from app.merchant import store

    fields = {f: slots[f] for f in _EDITABLE if slots.get(f) is not None}
    updated = store.update_product(slots["product_id"], fields)
    if not updated.get("ok"):
        return {"ok": False, "error": updated.get("error")}

    product = updated["product"]
    changed = updated.get("changed") or []
    # Publishing and unpublishing get their own entries, because "edited:
    # status" hides the only change on this list that decides whether a
    # buying agent can reach the product at all.
    if updated.get("published"):
        action_type, detail = "merchant_product_published", (
            f"{product['name']} published by the merchant agent — it is now "
            f"in the UCP catalogue and an AI buyer can discover and check it "
            f"out.")
    elif updated.get("unpublished"):
        action_type, detail = "merchant_product_unpublished", (
            f"{product['name']} moved back to draft by the merchant agent — "
            f"it has left the UCP catalogue and can no longer be bought.")
    else:
        action_type, detail = "merchant_product_updated", (
            f"{product['name']} edited by the merchant agent: "
            f"{', '.join(changed) or 'nothing'}.")

    log_decision(action_type=action_type,
                 amount_paise=int(product.get("price_paise") or 0),
                 decision="allowed", reason=detail)
    return {"ok": True, "product": product, "changed": changed,
            "published": updated.get("published"),
            "unpublished": updated.get("unpublished")}


def _execute_remove_product(slots: dict) -> dict:
    from app.firebase_client import log_decision
    from app.merchant import store

    removed = store.delete_product(slots["product_id"])
    if not removed.get("ok"):
        return {"ok": False, "error": removed.get("error")}

    product = removed["product"]
    retired = removed.get("retired") or []
    log_decision(
        action_type="merchant_product_removed",
        amount_paise=int(product.get("price_paise") or 0),
        decision="allowed",
        reason=(f"{product.get('name')} removed from the catalogue by the "
                f"merchant agent, on a confirmed instruction (was "
                f"{product.get('status')}, stock {product.get('stock')})."
                + (f" Also retired: {', '.join(retired)}." if retired else "")
                + " Past orders keep their own copy of the line, so nothing "
                  "already sold or reported has changed."),
    )
    return {"ok": True, "product": product, "retired": retired}


ACTIONS = {
    "add_product": {
        "label": "add a product",
        # Asked for in this order, so the questions arrive in the order a
        # person would think about the thing they are selling.
        "required": ["name", "price_paise"],
        "optional": ["stock", "category", "description", "image", "status"],
        "prompts": {
            "name": "What is the product called?",
            "price_paise": "What should it sell for?",
            "stock": "How many do you have?",
            "category": "What category does it belong in?",
        },
        "parse": parse_product,
        "execute": _execute_add_product,
        "confirm": lambda s: (
            f"I will add \"{s.get('name')}\" at "
            f"₹{int(s.get('price_paise') or 0) / 100:,.2f}"
            + (f", stock {s['stock']}" if s.get("stock") else "")
            + (f", in {s['category']}" if s.get("category") else "")
            + (", with the photo you attached" if s.get("image") else "")
            + " as a draft."
        ),
    },

    "update_product": {
        "label": "change that product",
        "required": ["product_id"],
        "optional": list(_EDITABLE),
        "prompts": {},
        "parse": parse_edit,
        # Resolved from the sentence rather than asked for: nobody knows
        # their own product ids, and asking for one would be the agent
        # making its own storage the merchant's problem.
        "resolves_product": True,
        "execute": _execute_update_product,
        # An edit with nothing to edit is not a question about a missing
        # field, it is a sentence the agent did not understand well enough
        # to act on. Saying which fields it CAN change is more use than
        # asking again in the same words.
        "ready": lambda s: (
            None if any(s.get(f) is not None for f in _EDITABLE) else
            "I found the product, but not what to change about it. I can set "
            "the price, the stock, the category, the description, the status "
            "(active or draft), or rename it."),
    },

    "remove_product": {
        "label": "remove that product",
        "required": ["product_id"],
        "optional": [],
        "prompts": {},
        "parse": lambda text, image=None: {},
        "resolves_product": True,
        # THE ONE ACTION THAT ASKS BEFORE IT ACTS.
        #
        # Adding and editing are recoverable — a wrong price is a second
        # sentence away from being right. Deleting is not, and a sentence
        # typed into a chat box is a thin thing to hang it on, so the agent
        # says what it is about to destroy and waits to be told again.
        "confirm_required": True,
        "execute": _execute_remove_product,
    },
}


# ── Recognising that an action was asked for at all ──────────────────────

_INTENTS = [
    ("add_product",
     re.compile(r"\b(add|create|list|put up|upload|new)\b[^.\n]*\b"
                r"(product|item|listing|sku|this)\b|"
                r"\b(sell|stock)\s+(this|it)\b", re.I)),
    ("remove_product",
     re.compile(r"\b(remove|delete|drop|take\s+(?:it\s+)?down|"
                r"get\s+rid\s+of|unlist|de-?list)\b", re.I)),
    # The two status verbs are here rather than in a pattern of their own:
    # people say "publish the prototype stand" far more often than they say
    # "set the status to active", and both are the same edit.
    # TWO PATTERNS, BECAUSE THE VERBS ARE NOT EQUALLY TRUSTWORTHY.
    #
    # The first list is unambiguous in a shop: nobody says "reprice" or
    # "unpublish" about anything but a product.
    ("update_product",
     re.compile(r"\b(update|change|edit|set|rename|retitle|correct|fix|"
                r"reprice|re-?price|publish|unpublish|activate|deactivate|"
                r"restock)\b", re.I)),
    # The second list is how people actually phrase a status or price
    # change — "make it active", "mark it as draft", "raise the price" —
    # and every one of those verbs is also ordinary English. "Find me an
    # opportunity to increase revenue" was read as an edit and answered
    # with "nothing in your catalogue matches that", which is the agent
    # hunting for a product in a sentence about the shop.
    #
    # So a weak verb only counts when it names something a product HAS. The
    # verb alone is not evidence; the verb plus a field is.
    ("update_product",
     re.compile(r"\b(make|mark|move|put|raise|lower|increase|decrease|"
                r"adjust|bump|drop)\b[^.\n]{0,40}?\b"
                r"(active|draft|live|unpublished|published|for\s+sale|"
                r"price|cost|stock|quantity|inventory|category|"
                r"description|name)\b", re.I)),
]


# AN INTERROGATIVE OPENING MEANS A QUESTION, NOT AN INSTRUCTION.
#
# "Which product should I raise the price of?" contains "raise" and named a
# product-changing verb, so it was read as an edit and answered with "nothing
# in your catalogue matches that" — the agent hunting for a product in a
# sentence that was asking it which product to pick.
#
# The distinction is grammar, not vocabulary, which is why it holds up: this
# closed set of words opens a request for INFORMATION. "Can you publish the
# prototype stand?" is also a question by punctuation and is not in this set,
# because "can you" opens a request to ACT. The customer-side router draws
# the same line for the same reason.
_ASKS_RATHER_THAN_TELLS = re.compile(
    r"^\s*(which|what|whats|what's|who|whose|why|when|where|how|"
    r"is|are|do|does|did|should\s+i|shall\s+i)\b",
    re.I)


def detect(text: str) -> str | None:
    """Which action is being asked for, if any."""
    blob = text or ""
    if _ASKS_RATHER_THAN_TELLS.match(blob):
        return None
    for name, pattern in _INTENTS:
        if pattern.search(blob):
            return name
    return None


def missing_fields(action: str, slots: dict) -> list[str]:
    spec = ACTIONS.get(action) or {}
    return [f for f in spec.get("required", []) if not slots.get(f)]
