"""
WHAT KIND OF MESSAGE IS THIS?

Every message used to take one of two paths: narrow the last results, or run
a new search. Anything the refiner did not recognise became a search, so
"why did you pick that one" went to eBay as a query and "how are you"
returned listings. The fork was never wrong about the two cases it knew — it
was wrong that those were the only two.

Five routes:

  refine    narrow the results on screen ("under 30000", "only black ones")
  question  answer something about them ("why that one", "is it waterproof")
  search    look for a different product
  clarify   a question about something else entirely, with nothing in it
            asking for a purchase — ask rather than guess
  aside     greetings, thanks, and questions about the agent itself

No model. One was written and measured first: a single six-token
classification did not return inside sixty seconds on this machine, which
would put a minute in front of every message a person types. That is the
same reason ranking and screening were taken off the model here — and the
same trade, because a rule that is wrong is wrong the same way every time
and can be fixed, while a model that is wrong is wrong differently each run.

Working without a model means not working from a vocabulary either, because
a list of phrasings is only a longer version of the bug this replaces.
People do not phrase things from a list. So the decision rests on structure:

  - English has a closed set of interrogatives (why, what, which, is, does)
    and a closed set of pointing words (it, that, these, the second one).
    Both are grammar, not product vocabulary, and they do not go out of date.
  - Whether a message introduces a NEW subject is already computed from data
    — the refiner compares its words against the previous search, so "find a
    kettle" is new after a phone search and "cheaper" is not. That is a
    comparison against what was actually searched for, not against a list
    anybody has to maintain.

The one genuinely enumerated category is `aside`: greetings and thanks are a
small closed class in a way that products are not.
"""
import re

from app.agent import refine

ROUTES = ("refine", "question", "search", "clarify", "aside")

# Something in the message that asks for a purchase rather than an answer:
# an imperative a shopper uses, a price, or shopping vocabulary. Its absence
# is what separates "what is a good laptop under 30000" from "what is the
# capital of France" without either being guessed at.
_COMMERCE_CUE = re.compile(
    r"\b(find|show|get|buy|buying|need|want|looking|search|order|purchase"
    r"|shop|shopping|sell|sells|recommend|suggest|deal|deals|discount|offer"
    r"|cheap|cheaper|budget|price|priced|cost|under|below|within|rs|inr"
    r"|rupees?|dollars?)\b|[₹$]|\d{3,}",
    re.IGNORECASE)

# A question opening. Closed grammatical class — every interrogative and
# auxiliary English can start a question with.
_ASKING = re.compile(
    r"^\s*(why|what|whats|what's|which|who|whom|whose|when|where|how"
    r"|is|isn't|are|aren't|was|were|does|doesn't|do|don't|did|didn't"
    r"|can|can't|could|should|shall|will|won't|would|has|hasn't|have|had"
    # "any" is not here. It opens a question far less often than it opens a
    # quantity — "any more" is a request for more results, and reading it as
    # a question turned a refinement into an answer about nothing.
    r"|tell\s+me|explain|compare|describe)\b",
    re.IGNORECASE)

# Pointing at what is already on screen. Pronouns and ordinals do most of
# the work; comparison words do the rest, because comparing implies a set
# and the only set present is the one being shown.
_REFERS_BACK = re.compile(
    r"\b(it|its|it's|that|this|these|those|them|they|their"
    r"|first|second|third|fourth|fifth|last|top|previous|above|shown|listed"
    r"|one|ones|option|options|item|items|result|results"
    r"|pick|picked|choice|chose|chosen|recommend|recommended|suggested"
    r"|both|either|each|all|other|another|rest"
    r"|better|best|worse|worst|difference|differences|differ|between|versus|vs"
    r"|cheaper|cheapest|pricier|dearest|instead\s+of"
    # Fields a listing actually has. Asking about one of these is asking
    # about what is on screen — "who is the seller" has no pronoun in it,
    # but there is only one seller it could mean. Deliberately limited to
    # transaction fields: product nouns like "camera" stay out, because
    # those name things a person might want to search for instead.
    r"|seller|sellers|price|prices|cost|costs|delivery|deliver|arrive|arrives"
    r"|shipping|postage|dispatch|condition|warranty|returns|refund|stock"
    r"|rating|ratings|review|reviews|feedback|discount|available)\b",
    re.IGNORECASE)

# Social openings, closings, and questions about the assistant itself.
# Enumerated deliberately: unlike products, this is a genuinely closed and
# short class, and matching it costs nothing.
_ASIDE = re.compile(
    r"^\s*(hi|hey+|hello|yo|howdy|sup|good\s+(morning|afternoon|evening|day|night)"
    r"|thanks?|thank\s+you|thx|ty|cheers|ok|okay|k|cool|nice|great|awesome|lol"
    r"|bye|goodbye|see\s+you|good\s?bye"
    r"|how\s+are\s+you|how's\s+it\s+going|who\s+are\s+you|what\s+are\s+you"
    r"|what\s+can\s+you\s+do|what\s+do\s+you\s+do|help|who\s+made\s+you"
    r"|are\s+you\s+(a\s+)?(bot|human|ai|real|there))"
    # "hey there", "hi all" — a greeting with someone on the end of it.
    r"(\s+(there|all|everyone|folks|again))?"
    r"[\s!.,?]*$",
    re.IGNORECASE)


# Acknowledgements longer than one word.
#
# _ASIDE anchors a SINGLE token, which meant "thanks" was an aside and
# "great, thanks" was a product search — it reached the marketplace and
# queried eBay for "great thanks". Anything a person says to be polite has
# to land in the same place regardless of how many words they used.
#
# CORE carries the social meaning; FILLER is only allowed to accompany it.
# The split matters: a message made only of filler is not an aside, and
# the words a person uses to CHOOSE something — "that", "the", "one",
# "this" — are deliberately in neither set, so "ok that's the one" stays a
# selection rather than being swallowed as politeness.
_CORE_SOCIAL = {
    "hi", "hey", "heyy", "hello", "yo", "howdy", "sup", "thanks", "thanx",
    "thankyou", "thank", "thx", "ty", "ta", "cheers", "ok", "okay", "kk",
    "cool", "nice", "great", "awesome", "amazing", "perfect", "brilliant",
    "lovely", "super", "excellent", "lol", "haha", "bye", "goodbye",
    "appreciate", "appreciated", "welcome", "worries", "job",
}
_SOCIAL_FILLER = {
    "you", "u", "so", "very", "much", "really", "a", "lot", "helpful",
    "help", "useful", "good", "again", "there", "all", "everyone", "folks",
    "mate", "man", "friend", "buddy", "indeed", "work", "works", "worked",
    "that's", "thats", "is", "was", "no", "worries", "np", "for", "your",
    "my", "well", "done", "job", "wonderful", "fine",
}
# "nice one", "good one" are idioms. "one" is otherwise a selection word,
# so it is only filler in a two-word acknowledgement.
_SHORT_IDIOM_FILLER = {"one", "stuff"}

_WORD = re.compile(r"[a-z']+")


def _all_social(text: str) -> bool:
    words = _WORD.findall((text or "").lower())
    if not words or len(words) > 6:
        return False
    if not any(w in _CORE_SOCIAL for w in words):
        return False
    # "job lot" is a real eBay listing term — a seller offloading a bundle.
    # "job" is in CORE so that "good job" is recognised as praise, and that
    # would otherwise turn a genuine search for "job lot of keyboards" into
    # small talk. The idiom is excluded by name rather than by dropping the
    # word, because both readings are real.
    if "job" in words and "lot" in words:
        return False
    allowed = _CORE_SOCIAL | _SOCIAL_FILLER
    if len(words) <= 2:
        allowed = allowed | _SHORT_IDIOM_FILLER
    return all(w in allowed for w in words)


def classify(text: str, has_results: bool = False,
             previous_query: str = "") -> dict:
    """
    Returns {"route", "reason"}.

    `reason` is carried into the trace, so somebody watching the agent take
    a wrong turn can see which rule sent it there rather than guessing.
    """
    stripped = (text or "").strip()
    if not stripped:
        return {"route": "aside", "reason": "empty message"}

    if _ASIDE.match(stripped) or _all_social(stripped):
        return {"route": "aside", "reason": "a greeting or acknowledgement"}

    asking = bool(_ASKING.match(stripped))
    refers = bool(_REFERS_BACK.search(stripped))
    parsed = refine.parse(stripped, previous_query)
    # A leftover word that points at the results is not a new subject.
    # "any reviews on that" leaves "reviews" behind, which the refiner has
    # to call novel — it was not in the search phrase — but a review is a
    # property of a listing, not another product to go and find.
    novel = [word for word in (parsed.get("residue") or [])
             if not _REFERS_BACK.fullmatch(word)]
    names_new = parsed.get("reason") == "names something new" and bool(novel)

    # Nothing on screen to narrow or ask about — but a general-knowledge
    # question is still one whether or not a search came first, and this
    # used to depend on that: the same message clarified mid-conversation
    # and searched as an opener. What a message is does not change with
    # what preceded it.
    if not has_results:
        if asking and names_new and not _COMMERCE_CUE.search(stripped):
            return {"route": "clarify",
                    "reason": "a question with nothing in it that asks for "
                              "a purchase"}
        return {"route": "search", "reason": "no results to talk about yet"}

    # Asked, and pointing at what is here. Both halves matter: "what is a
    # good laptop" opens like a question but names a subject that is not on
    # screen, which is a search.
    if asking and refers:
        return {"route": "question", "reason": "asks about the results shown"}

    # A filter in any phrasing — but only when it is not being asked as a
    # question. "under 30000" narrows; "is it under 30000" wants an answer.
    if parsed.get("refine") and parsed.get("ops") and not asking:
        return {"route": "refine", "reason": "names a filter to apply"}

    # A question about something new, with nothing in it that asks for a
    # purchase. "what is the capital of France" reached eBay as a query and
    # came back with books titled "What Is Enlightenment?" — real listings,
    # honestly ranked, and a ridiculous answer.
    #
    # Telling that apart from "what is a good laptop" needs to know that a
    # laptop is a product and a capital city is not, which is world
    # knowledge this has no source for. So it does not decide: it asks. A
    # question costs the person one line and cannot be wrong, where a guess
    # in either direction is embarrassing in one of the two cases.
    if asking and names_new and not _COMMERCE_CUE.search(stripped):
        return {"route": "clarify",
                "reason": "a question about something not on screen, with "
                          "nothing in it that asks for a purchase",
                "subject": " ".join(parsed.get("residue") or [])}

    # Introduces a subject the last search did not have.
    if names_new:
        return {"route": "search",
                "reason": "names something the last search did not: "
                          + ", ".join(parsed.get("residue") or [])}

    # A question that adds no new subject is about what is already here.
    if asking:
        return {"route": "question", "reason": "asks about the results shown"}

    # Points at the results, filters nothing, names nothing new. There is
    # only one thing such a message can be about.
    if refers:
        return {"route": "question", "reason": "refers to the results shown"}

    if parsed.get("refine"):
        return {"route": "refine", "reason": "names a filter to apply"}

    return {"route": "search", "reason": "reads as a new request"}
