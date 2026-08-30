"""
SEARCH BY PHOTOGRAPH

Find products from a picture, without ever guessing what the picture is of.

There are two ways to build this. The tempting one is to hand the photo to a
vision model, let it say "Samsung Galaxy S22 Ultra", and search for that
string. It demos well and it is exactly the failure this project spends its
time avoiding: a model that reads S22 off a picture of an S23 produces a
search that is confidently wrong, and nothing downstream can tell, because
by then the mistake is just a query like any other.

So the matching is eBay's. `search_by_image` compares the photograph against
eBay's own catalogue and returns the listings it resembles. The agent never
names the product, never describes it, and makes no claim about what was
photographed — the only assertion on screen is eBay's own, and it is
attributed to eBay in the response.

What runs afterwards is the pipeline a typed search gets: trust flags,
product reviews, quality scoring, ranked by the same value key.

The relevance screen is where the two paths differ, and the split is not
where it first looks. Keyword matching is genuinely impossible — it compares
a title against the words a person used, and there are none; inventing some
would mean screening against the agent's guess at the photo, the one thing
this file refuses to make.

But half of that screen never needed the query. A title reading "Battery
Cover Rear Door Panel Housing Case Parts for Nothing CMF Phone 2 Pro"
announces that it fits a product rather than is one, in its own words. That
half runs, because photographing a phone returns the phone alongside every
housing and case moulded to its back — all of them honest visual matches,
and only one of them what anyone meant. They are moved to the end rather
than removed: the photo might have been of a case.
"""
import base64
import binascii

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent import ebay_client, quality
# The accessory test reads a listing's own title, so it needs no query —
# which is what makes it the one screen an image search can still run.
from app.agent.ollama_agent import (
    is_accessory_for, query_terms, screen_relevance,
)
from app.agent.trust_agent import assess as trust_assess

router = APIRouter()

# eBay accepts a base64 image; this bound is ours, so an oversized upload
# fails here in milliseconds with a sentence a person can act on, rather
# than after a slow round trip to a rejection nobody can read.
MAX_IMAGE_BYTES = 4 * 1024 * 1024

# The first bytes of the formats a camera or a screenshot produces. A file
# that is not one of these is rejected before it costs an API call.
_MAGIC = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp",
    b"BM": "bmp",
}


class ImageSearch(BaseModel):
    image_b64: str
    # Anything typed alongside the photo. Only the budget is read from it,
    # by the same rule-based parser a typed search uses — so "under 5000"
    # bounds an image search exactly as it bounds a text one, and the
    # ceiling still comes from what the person wrote rather than a model.
    note: str = ""
    max_price_paise: int = 0
    limit: int = 24
    # The conversation these results belong to. Without it a photo search is
    # a dead end: the follow-up finds no previous result set, decides the
    # person has changed subject, and searches afresh — which is how "under
    # 30000" after a phone search returned a 30,000 lb towing hitch.
    session_id: str = ""


def _decoded(image_b64: str) -> bytes:
    payload = image_b64.split(",", 1)[-1].strip()  # tolerate a data: URL
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="That does not decode as an image.")
    if not raw:
        raise HTTPException(status_code=400, detail="The image was empty.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(f"That image is {len(raw) / 1_048_576:.1f} MB. "
                    f"The limit is {MAX_IMAGE_BYTES // 1_048_576} MB."))
    if not any(raw.startswith(sig) for sig in _MAGIC):
        raise HTTPException(
            status_code=400,
            detail="That file is not a JPEG, PNG, GIF, WebP or BMP image.")
    return raw


@router.post("/image-search")
async def image_search(req: ImageSearch):
    raw = _decoded(req.image_b64)
    clean_b64 = base64.b64encode(raw).decode()

    ceiling = req.max_price_paise
    if not ceiling and req.note.strip():
        from app.agent.ollama_agent import fast_intent
        intent = fast_intent(req.note)
        # Only a budget the person actually typed. fast_intent hands back a
        # default ceiling when none was stated, and taking it here was the
        # bug behind "mobile phone" returning phone cases: the words carried
        # no price, a silent ₹5,000 cap went to eBay, and the only things
        # under it were back covers and spare glass. A typed search can lean
        # on that default because it also has a query to find the product
        # with; here it would quietly answer a different question.
        # Compared against what an empty request parses to, rather than
        # matched against the wording of budget_source — the number is the
        # fact; the sentence describing it is prose that may be reworded.
        default_ceiling = fast_intent("").get("max_price_paise")
        stated = intent.get("max_price_paise")
        ceiling = stated if stated != default_ceiling else 0

    try:
        candidates = ebay_client.search_by_image(
            clean_b64, ceiling, min(req.limit, 50))
    except Exception as exc:
        # Say which service failed and stop. A fallback to a text search
        # would silently answer a different question from the one asked.
        raise HTTPException(
            status_code=502,
            detail=f"eBay's image search could not be reached ({type(exc).__name__}).")

    steps = []

    if not candidates:
        return {
            "candidates": [],
            "steps": ["eBay's image search found no listings resembling this photo."
                      + (f" The ₹{ceiling / 100:,.0f} ceiling from your note was applied."
                         if ceiling else "")],
            "matched_by": "ebay_image_search",
            "screened": False,
        }

    steps.append(f"eBay's image search returned {len(candidates)} listings that "
                 f"resemble this photo. The match is eBay's — the agent has not "
                 f"identified what is in the picture."
                 + (f" Your ₹{ceiling / 100:,.0f} ceiling was applied to the search."
                    if ceiling else ""))

    # Words the person typed are words. Screen against them.
    #
    # This was the real gap: a note was read for its budget and then thrown
    # away, so someone who pasted a phone and typed "mobile phone" got back
    # iPhone cases — the agent had been told what it was looking at and did
    # not use it. Screening a title against the person's own words is not a
    # guess about the photo; it is the one thing here that is not a guess.
    #
    # Same screen the typed pipeline runs, including its stand-down: if
    # nothing survives, it returns everything rather than emptying the page,
    # on the grounds that the rule is likelier wrong than the whole market.
    if query_terms(req.note):
        screened = screen_relevance(candidates, req.note, budget_paise=ceiling)
        if screened["candidates"]:
            candidates = screened["candidates"]
            steps.append(screened["summary"])
        else:
            # The screen is entitled to conclude a typed search found only
            # accessories and say so. Here that would throw away eBay's
            # visual matches — the actual answer to what was asked — and
            # leave a blank page. So the words stop filtering and start
            # ordering, and the trace says which happened.
            steps.append(
                f"Nothing among these matches the words “{req.note.strip()}”. "
                f"Showing eBay's visual matches instead, with parts and cases last.")

    trust = trust_assess(candidates)
    candidates = trust["candidates"]
    if trust["flagged"]:
        steps.append(trust["summary"])

    try:
        candidates = ebay_client.enrich_reviews(candidates, 8)
    except Exception as exc:
        print(f"[image-search] review lookup skipped: {exc}", flush=True)

    quality.annotate(candidates)
    reviewed = sum(1 for c in candidates if (c.get("review_count") or 0) > 0)
    steps.append(
        f"Read product reviews on {reviewed} of {len(candidates)} listings — the "
        f"rest are judged on seller record and condition alone."
        if reviewed else
        "None of these listings carry product reviews, so quality is judged on "
        "seller record and condition.")

    # The same key a typed search ranks by, so the two paths cannot disagree
    # about what a better listing is.
    candidates.sort(key=lambda p: quality.value_key(p, ceiling, "neutral"))

    # Parts and cases last.
    #
    # A photograph of a phone brings back the phone and also every battery
    # cover, housing and case shaped like its back — they genuinely resemble
    # it, so eBay is not wrong to return them. Which of the two a person
    # meant is the one thing the picture cannot say.
    #
    # This is decided from the listing's own title, never from a guess at
    # the photo: "Battery Cover ... for Nothing CMF Phone 2 Pro" announces
    # that it fits the product rather than being it. Same test the typed
    # pipeline uses, and it stays gated on the note — write "case" beside
    # the photo and cases stop being demoted.
    #
    # Demoted rather than dropped, because the photo might BE of a case. A
    # filter that guessed wrong would delete exactly the listings the person
    # wanted and leave nothing to notice; an ordering that guesses wrong
    # costs them a scroll.
    itself, fits_it = [], []
    for candidate in candidates:
        target = fits_it if is_accessory_for(candidate.get("name") or "", req.note) \
            else itself
        target.append(candidate)

    if fits_it and itself:
        candidates = itself + fits_it
        steps.append(
            f"{len(fits_it)} of {len(candidates)} are parts or cases whose own "
            f"titles say they fit this item rather than are it — moved to the "
            f"end, not removed, since a photo cannot say which you meant.")
    elif fits_it and not itself:
        # Worth stating: it probably means the photo was of a part.
        steps.append(
            f"All {len(fits_it)} matches are parts or accessories by their own "
            f"titles, so nothing was reordered.")

    # Said plainly, because it is a real limit: with no words there is
    # nothing to screen a listing's title against.
    steps.append("No keyword screen ran on these — there are no words to screen "
                 "against. They are ordered by seller record, condition and "
                 "reviews.")

    # Hand these to the conversation, so the next message can narrow them.
    #
    # The typed pipeline already does this and the refiner already reads it:
    # "under 30000" parses to a price operation with no new subject, which
    # narrows the last result set. It only misfired because a photo search
    # left that set empty, so the follow-up looked like a fresh request and
    # went looking for anything priced 30000 — hitches, water filters.
    #
    # The stored query is the note, which is also what decides later whether
    # a follow-up is still about this: words the person already used read as
    # them restating their subject, anything else as a new one.
    if req.session_id:
        from app.routes.agent_routes import _remember
        from app.agent.ollama_agent import fast_intent

        intent = fast_intent(req.note)
        intent["max_price_paise"] = ceiling or intent["max_price_paise"]
        if req.note.strip():
            intent["category"] = req.note.strip()
        _remember(req.session_id, req.note.strip(), intent, candidates)

    return {
        "candidates": candidates,
        "steps": steps,
        "matched_by": "ebay_image_search",
        "screened": False,
        "flagged": trust["flagged"],
        "max_price_paise": ceiling,
    }
