"""
PICK A LISTING, AND SAY WHY — from the same numbers, in one pass.

The explanation used to be written by the model: one free sentence, shown
next to the product, checked against nothing. It never invented a product —
the chosen id was validated — but it repeatedly invented the *relationship*
between real numbers. "Slightly over budget" about a ₹649 item under a ₹800
ceiling is the whole failure mode in one phrase: every figure in the
sentence is real, and the claim is still false.

That class of error cannot be caught by grounding checks, because nothing in
it is ungrounded. It can only be removed by not generating the claim.

So the pick and the sentence are computed together here. Each clause is
emitted only by a rule that has already established the fact it states, and
superlatives are verified against the candidate set before they are uttered
rather than asserted and hoped for. The agent cannot say the cheapest one is
cheapest unless it is.

The model still screens listings for relevance, which is a judgement about
meaning and genuinely needs one. Deciding which of several screened listings
wins on price is arithmetic, and arithmetic should not be delegated to a
language model.
"""

PRIORITIES = ("value", "price", "rating", "discount", "delivery_days")


def _num(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _score(product: dict, priority: str, budget_paise: int = 0,
           bias: str = "neutral") -> tuple:
    """Lower sorts first. Mirrors the ranking the request asked for."""
    from app.agent import quality

    price = _num(product.get("price_paise"))
    if priority == "price":
        return (price,)
    if priority == "discount":
        return (-_num(product.get("discount_percent")), price)
    if priority == "delivery_days":
        return (_num(product.get("delivery_days"), 99), price)
    if priority == "rating":
        # The quality of the product, not the reputation of the seller.
        assessment = product.get("quality") or quality.assess(product)
        score = assessment.get("score")
        return (-(score if score is not None else -1), price)
    # value: the best thing this budget reaches.
    return quality.value_key(product, budget_paise, bias)


def _matched_requirements(product: dict, requirements) -> list[str]:
    """Only the requirements literally present in the listing's own title."""
    name = (product.get("name") or "").lower()
    found = []
    for req in requirements or []:
        text = str(req).strip().lower()
        # Multi-word requirements ("good camera quality") are judgements, not
        # facts about the title, and are left to the relevance screen.
        if text and len(text.split()) <= 2 and text in name:
            found.append(str(req))
    return found


def _clauses(chosen: dict, others: list[dict], priority: str,
             budget_paise: int, requirements) -> list[str]:
    """Every true thing worth saying about why this one won."""
    said = []
    price = _num(chosen.get("price_paise"))
    pool = [chosen] + list(others)

    # What they asked for, if the title actually says so.
    matched = _matched_requirements(chosen, requirements)
    if matched:
        said.append("matches " + " and ".join(matched))

    # The venue difference, which decides whether anything can be delivered.
    if chosen.get("source") == "merchant":
        others_merchant = [o for o in others if o.get("source") == "merchant"]
        if not others_merchant:
            said.append(f"the only one {chosen.get('merchant_name') or 'the store'} "
                        f"can actually deliver")
        else:
            said.append(f"sold directly by {chosen.get('merchant_name') or 'the store'}")

    # Quality, cited with the evidence behind it rather than asserted.
    if priority in ("value", "rating"):
        from app.agent import quality
        assessment = chosen.get("quality") or quality.assess(chosen)
        if assessment.get("basis"):
            best = all(
                (assessment.get("score") or 0)
                >= ((o.get("quality") or quality.assess(o)).get("score") or 0)
                for o in others
            )
            lead = "the best-reviewed of the " + str(len(pool)) if best \
                else "well reviewed"
            said.append(f"{lead} — {'; '.join(assessment['basis'][:2])}")

    # The superlative, stated only when it is one.
    if priority == "price" and pool:
        if all(price <= _num(o.get("price_paise")) for o in others):
            said.append(f"the cheapest of the {len(pool)} that matched")
    elif priority == "rating":
        feedback = _num(chosen.get("seller_feedback"))
        if feedback and all(feedback >= _num(o.get("seller_feedback")) for o in others):
            said.append(f"the highest seller feedback at {feedback:g}%")
    elif priority == "discount":
        cut = _num(chosen.get("discount_percent"))
        if cut and all(cut >= _num(o.get("discount_percent")) for o in others):
            said.append(f"the biggest discount at {cut:g}% off")
    elif priority == "delivery_days":
        days = _num(chosen.get("delivery_days"), 99)
        if days < 99 and all(days <= _num(o.get("delivery_days"), 99) for o in others):
            said.append(f"the fastest delivery at {days:g} days")

    # The budget, described by comparison rather than by adjective.
    if budget_paise and price:
        if price <= budget_paise:
            headroom = budget_paise - price
            if headroom >= budget_paise * 0.2:
                said.append(f"₹{price / 100:,.0f}, comfortably under your "
                            f"₹{budget_paise / 100:,.0f}")
            else:
                said.append(f"₹{price / 100:,.0f}, just under your "
                            f"₹{budget_paise / 100:,.0f}")
        else:
            said.append(f"₹{price / 100:,.0f}, over your "
                        f"₹{budget_paise / 100:,.0f}")

    # Condition, when it is not the ordinary case.
    condition = str(chosen.get("condition") or "").strip()
    if condition and condition.lower() not in ("new", "brand new", ""):
        said.append(f"{condition.lower()} condition")

    return said


def build_reason(chosen: dict, others: list[dict], priority: str,
                 budget_paise: int = 0, requirements=None,
                 unmet: list = None) -> str:
    """
    The reason alone — the listing's name is the caller's to add.

    Every consumer already has the product and prints its name next to this
    ("I'd go with the X — ..."), so naming it here produced the name twice in
    one sentence. What belongs here is only the part that answers "why".
    """
    said = _clauses(chosen, others, priority, budget_paise, requirements)

    # An attribute nobody offered. Stating it on the recommendation matters
    # more than stating it in the reasoning stream: this is the sentence
    # printed beside the product, and a 1.7-litre kettle answering a request
    # for 1.5 litres should say which part of the request went unmet.
    for missing in unmet or []:
        said.append(f"no listing offered {missing}, so this is the closest available")

    if not said:
        # No distinguishing fact survived, and inventing one is the failure
        # this module exists to prevent.
        return (f"the closest match to what you asked for, "
                f"ranked by {priority.replace('_', ' ')}")

    if len(said) == 1:
        return said[0]
    return ", ".join(said[:-1]) + ", and " + said[-1]


def _completeness(candidates: list[dict], user_text: str) -> dict:
    """
    0 for listings echoing every word of the request, 1 for the rest.

    Lower sorts first, matching the convention of the other keys. Returns a
    map keyed by identity so the caller's sort stays a single pass, and an
    empty map when there is nothing to compare — no request text, or every
    listing equally complete, in which case this must not disturb the order.
    """
    from app.agent.ollama_agent import query_terms, matches_request

    terms = query_terms(user_text)
    if not terms or len(terms) < 2:
        return {}

    scores = {}
    for candidate in candidates:
        hits = matches_request(candidate.get("name") or "", terms)[1]
        scores[id(candidate)] = 0 if hits >= len(terms) else 1

    # If they are all the same there is nothing to separate, and returning
    # the map anyway would be a no-op with extra work.
    return {} if len(set(scores.values())) < 2 else scores


def choose(candidates: list[dict], priority: str, budget_paise: int = 0,
           requirements=None, unmet: list = None, user_text: str = "",
           bias: str = "neutral") -> dict:
    """
    The pick and its explanation, from one computation.

    Ordering is stable, so any upstream ordering — the relevance screen, the
    buyer's own purchase history — survives as the tie-break it was meant to
    be, and this only decides between listings that ranking left equal.
    """
    if not candidates:
        return {"product": None, "reason": "No listings matched.", "priority": priority}

    if priority not in PRIORITIES:
        priority = "rating"

    # Listings that answer the whole request first, then the ranking the
    # request asked for. Stable, so this only separates listings the ranking
    # would otherwise leave equal — and a full match is never overtaken by a
    # partial one with a nicer seller.
    complete = _completeness(candidates, user_text)
    ordered = sorted(
        candidates,
        key=lambda c: (complete.get(id(c), 0),
                       _score(c, priority, budget_paise, bias)),
    )
    chosen = ordered[0]
    others = ordered[1:]

    return {
        "product": chosen,
        "reason": build_reason(chosen, others, priority, budget_paise,
                               requirements, unmet),
        "priority": priority,
        "derived": True,
    }
