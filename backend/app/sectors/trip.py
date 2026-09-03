"""
THE TRIP SECTOR — WHERE THE PLUG-IN BOUNDARY EARNS ITS KEEP.

Products ranks: given a list, pick the best row. Trip assembles: given
three lists, choose a flight AND a hotel AND meals that fit each other, a
date, and one budget. That is a different problem, and it is the reason
this sector exists rather than a products category called "travel".

What it does that products cannot:

  multi-leg spend      the cap is checked against flight + (rate+tax)x
                       nights + meals, as one number. Gating the last leg
                       looked at would be the classic way to charge
                       someone for a flight and forget the hotel.
  date fit             a chosen date is mapped onto the flight file's
                       `days_left`, and meals are placed inside opening
                       hours that are actually parsed, not assumed.
  sequencing           meals are ordered by distance from the hotel's
                       locality rather than by rating, because an itinerary
                       that sends you across the city and back is worse
                       than one that does not, whatever the reviews say.

WHAT IS REAL AND WHAT IS A STAND-IN — stated here and shown in the UI:

  Real: every fare, nightly rate, tax and meal cost comes from the supplied
  datasets. The assembly, the totals and the ranking are genuine work over
  those numbers.

  Snapshot, not live: no availability is asserted for any date. Prices do
  not move. Departure is a WINDOW ("Evening"), never a time.

  The payable leg is a stand-in: the chosen hotel's own nightly rate is
  charged through the demo merchant, so a real Razorpay capture happens
  and is tied to that specific hotel record. It is NOT a booking with the
  hotel. Nobody is holding a room. Production would need direct supplier
  integration, and the UI says so on the card, not only here.
"""
import math
import re
from datetime import date, datetime

from app.sectors import trip_data
from app.sectors.base import Criterion, IntentField, SectorResult, Template

# Meals per day the assembler will place, and the windows it aims for.
MEAL_SLOTS = (("lunch", 13), ("dinner", 20))

# How far a meal may be from the hotel's locality before it stops looking
# like part of the same day. Locality-level, because hotels in this
# dataset have no coordinates — stated rather than hidden.
NEARBY_KM = 8.0


class TripSector:
    """Assembling a trip out of real flight, hotel and restaurant records."""

    sector_id = "trip"
    name = "Trip"
    icon = "flight"
    description = "Plan a trip across flights, hotels and places to eat"
    # True, but only for the one payable leg, and the UI labels it as a
    # demo-merchant stand-in rather than a hotel booking.
    can_transact = True

    # ── the plug-in surface ─────────────────────────────────────────────

    def intent_schema(self):
        # Destination is required in a way no products field is: a trip
        # with no destination is not an under-specified search, it is not
        # a search. The core asks rather than guessing.
        return [
            IntentField("to_city", "city", required=True,
                        prompt="Where are you going?", example="Mumbai"),
            IntentField("from_city", "city", required=True,
                        prompt="Flying from?", example="Delhi"),
            IntentField("nights", "int",
                        prompt="How many nights?", example="2"),
            IntentField("depart_date", "date",
                        prompt="Roughly when?", example="in 3 weeks"),
            IntentField("max_price_paise", "money",
                        prompt="Total budget for the trip?", example="under ₹20000"),
            IntentField("party_size", "int",
                        prompt="How many of you?", example="2"),
        ]

    def adapters(self):
        # Registered privately to this sector. Deliberately NOT added to
        # app.adapters.registry: a flight appearing in a search for
        # earbuds would be the clearest sign the boundary had leaked.
        from app.sectors.trip_adapters import (FlightAdapter, HotelAdapter,
                                               RestaurantAdapter)
        return [FlightAdapter(), HotelAdapter(), RestaurantAdapter()]

    def evaluation_criteria(self):
        return [
            Criterion("total_cost", 0.35, "lower_is_better",
                      "Flight + (rate + tax) x nights + meals, as one number"),
            Criterion("logistics", 0.25, "higher_is_better",
                      "Meals near the hotel; fewer stops on the flight"),
            Criterion("date_fit", 0.20, "higher_is_better",
                      "Departure window matches, meals fall inside real "
                      "opening hours"),
            Criterion("reputation", 0.20, "higher_is_better",
                      "Hotel and restaurant ratings, weighted by review count"),
        ]

    def templates(self):
        """
        None, deliberately.

        Products has templates because a shopper is often browsing — "show
        me a good deal" is a real starting point, and `/deal` saves typing
        a phrase the parser already understands.

        A trip is the opposite. By the time someone opens this they know
        where they are going, who with, and roughly when. Offering
        "3 nights in Kolkata" to a person planning Chennai is not a
        shortcut, it is a wrong answer they have to clear before they can
        start. So this sector asks for the sentence instead, the same way
        the product search does, and the ranking does the work: rating,
        review count, price, opening hours and distance from the hotel.

        The interface allows this on purpose — sectors are not required to
        look alike, and one returning nothing here is the cheapest possible
        proof of that.
        """
        return []

    _TRAVEL = re.compile(
        r"\b(trip|travel|holiday|vacation|getaway|itinerary|flight|fly|flying|"
        r"hotel|stay|stays|night|nights|weekend|tour|visit|book\s+a\s+room|"
        r"check\s?in|check\s?out|business\s+trip)\b", re.I)
    _CITY = re.compile("|".join(rf"\b{c}\b" for c in trip_data.CITIES), re.I)
    _ROUTE = re.compile(r"\b(from|to)\b\s+(" +
                        "|".join(trip_data.CITIES) + r")\b", re.I)

    def classify(self, text: str) -> float:
        blob = (text or "").lower()
        if not blob.strip():
            return 0.0
        score = 0.0
        travel = len(set(w.lower() for w in self._TRAVEL.findall(blob)))
        score += min(0.55, travel * 0.25)
        cities = len(set(c.lower() for c in self._CITY.findall(blob)))
        score += min(0.3, cities * 0.18)
        # "from X to Y" is the strongest single signal there is — nobody
        # phrases a product search that way.
        if self._ROUTE.search(blob):
            score += 0.25
        return min(1.0, score)

    # ── the part products has no equivalent for ─────────────────────────

    def assemble(self, need: dict) -> SectorResult:
        """
        Choose a flight, a hotel and meals that fit together.

        Not three independent searches stapled together: the hotel is
        chosen in the destination the flight actually reaches, the meals
        are chosen near the hotel that won, and the budget is checked
        against the sum rather than any single leg.
        """
        from app.sectors import trip_eval
        return trip_eval.assemble(need)


# ── shared helpers, used by the evaluator and the adapters ──────────────

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Straight-line distance. Good enough to tell 'nearby' from 'across town'."""
    if None in (lat1, lon1, lat2, lon2):
        return float("inf")
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return radius * 2 * math.asin(math.sqrt(a))


_TIME = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|noon|midnight)?", re.I)


def opens_during(timings: str, hour: int) -> bool | None:
    """
    Is a place open at this hour, according to its own text?

    Returns None when the text cannot be parsed rather than guessing —
    "probably open" is not a fact, and an itinerary that quietly assumes
    it would be asserting something the data never said. Roughly 70% of
    these strings parse; the rest are carried as unknown and disclosed.
    """
    text = (timings or "").strip()
    if not text:
        return None
    found = _TIME.findall(text.lower())
    if len(found) < 2:
        return None
    hours = []
    for value, _minute, suffix in found[:4]:
        try:
            clock = int(value)
        except ValueError:
            continue
        suffix = (suffix or "").lower()
        if suffix == "pm" and clock < 12:
            clock += 12
        elif suffix == "midnight":
            clock = 24
        elif suffix == "noon":
            clock = 12
        hours.append(clock)
    if len(hours) < 2:
        return None
    start, end = hours[0], hours[1]
    if end <= start:            # closes after midnight
        end += 24
    return start <= hour <= end


def parse_when(text: str) -> tuple[int, str]:
    """
    Turn a stated date into days-before-departure, which is what the
    flight file actually indexes on.

    Returns (days_left, how_it_was_read). The second half matters: the
    dataset has no calendar, so this is an interpretation and the UI says
    which one it made.
    """
    blob = (text or "").lower()
    # Plural alternatives first: 'day|days' matches the singular inside
    # 'days' and reports '3 day' back to the person who typed '3 days'.
    match = re.search(r"in\s+(\d+)\s*(days|day|weeks|week|months|month)", blob)
    if match:
        count = int(match.group(1))
        unit = match.group(2)
        days = count * (7 if unit.startswith("week") else 30 if unit.startswith("month") else 1)
        return max(1, min(49, days)), f"“in {count} {unit}” → {days} days ahead"
    if "tomorrow" in blob:
        return 1, "“tomorrow” → 1 day ahead"
    if "next week" in blob:
        return 7, "“next week” → 7 days ahead"
    if "next month" in blob:
        return 30, "“next month” → 30 days ahead"
    if "this weekend" in blob or "weekend" in blob:
        return 3, "“weekend” → 3 days ahead"
    for pattern in (r"(\d{4})-(\d{2})-(\d{2})", r"(\d{1,2})/(\d{1,2})/(\d{4})"):
        hit = re.search(pattern, blob)
        if hit:
            try:
                parts = [int(p) for p in hit.groups()]
                when = date(parts[0], parts[1], parts[2]) if pattern.startswith("(\\d{4})" ) \
                    else date(parts[2], parts[1], parts[0])
                days = (when - date.today()).days
                if days >= 0:
                    return max(1, min(49, days)), f"{when.isoformat()} → {days} days ahead"
            except (ValueError, IndexError):
                pass
    # No date given. 21 days is the middle of the file's range, and this
    # says so rather than presenting a default as a choice.
    return 21, "no date given — assumed about 3 weeks ahead"


# ── free text → the fields the assembler needs ──────────────────────────

_NIGHTS = re.compile(r"(\d+)\s*night", re.I)
_DAYS = re.compile(r"(\d+)\s*day", re.I)
_PARTY = re.compile(r"(?:for|with)\s+(\d+)\s*(?:people|of us|adults|guests)", re.I)
# "budget to 20000" and "raise it to 20000" are how people actually revise a
# number mid-conversation. The first version only accepted "budget of", so a
# refinement was read, found nothing, and silently kept the old figure —
# which looks like the agent ignoring you.
_BUDGET = re.compile(
    r"(?:under|below|within|budget(?:\s+(?:of|to))?|max(?:imum)?|upto|"
    r"up\s+to|raise\s+(?:it\s+)?to|increase\s+(?:it\s+)?to)\s*"
    r"(?:₹|rs\.?|inr)?\s*([\d,]+)\s*(k|thousand)?", re.I)
# "<city> to ..." — the origin stated without the word "from".
_CITY_TO = re.compile(
    r"\b(" + "|".join(list(trip_data.CITIES)
                       + list(trip_data.CITY_ALIASES)) + r")\s+to\s+", re.I)
_FROM = re.compile(r"\bfrom\s+([A-Za-z ]+?)\b(?=\s*(?:,|$|to\b|for\b|under\b|in\b|next\b|this\b|with\b))", re.I)
_TO = re.compile(r"\b(?:to|in|at|visit(?:ing)?)\s+([A-Za-z ]+?)\b(?=\s*(?:,|$|from\b|for\b|under\b|next\b|this\b|with\b))", re.I)


def _canonical_city(text: str) -> str:
    """Map whatever was typed onto a city the datasets actually contain."""
    blob = (text or "").strip().lower()
    if not blob:
        return ""
    if blob in trip_data.CITY_ALIASES:
        return trip_data.CITY_ALIASES[blob]
    for city in trip_data.CITIES:
        if city.lower() == blob or city.lower() in blob:
            return city
    for alias, city in trip_data.CITY_ALIASES.items():
        if alias in blob:
            return city
    return ""


def parse_intent(text: str) -> dict:
    """
    Pull the trip fields out of a sentence.

    Returns what it found and nothing it did not — a field it cannot read
    is left absent so the route asks for it, rather than being filled with
    a default that would look like the person had chosen it.
    """
    blob = (text or "").strip()
    found: dict = {}

    # Cities. "from X" and "to Y" are read first because they are stated;
    # only if that fails are bare city names taken positionally.
    from_hit = _FROM.search(blob)
    to_hit = _TO.search(blob)
    if from_hit:
        found["from_city"] = _canonical_city(from_hit.group(1))

    # "Chennai to Chikmagalur" — the city BEFORE "to" is the origin.
    #
    # Without this the sentence had no origin, the destination was
    # unrecognised, and the positional fallback below then promoted Chennai
    # to be the destination. The person asked to fly out of Chennai and was
    # shown a trip INTO it: not a missing answer, a different one.
    pair = _CITY_TO.search(blob)
    if pair and not found.get("from_city"):
        found["from_city"] = _canonical_city(pair.group(1))

    stated_destination = to_hit.group(1).strip() if to_hit else ""
    if stated_destination:
        found["to_city"] = _canonical_city(stated_destination)

    named = []
    for city in trip_data.CITIES:
        match = re.search(rf"\b{city}\b", blob, re.I)
        if match:
            named.append((match.start(), city))
    for alias, city in trip_data.CITY_ALIASES.items():
        match = re.search(rf"\b{alias}\b", blob, re.I)
        if match and city not in [c for _, c in named]:
            named.append((match.start(), city))
    named.sort()
    ordered = [c for _, c in named]

    # A DESTINATION THAT WAS STATED AND IS NOT COVERED ENDS IT HERE.
    #
    # Falling through to "some other city in the sentence" is how
    # "Chennai to Chikmagalur" became "a trip to Chennai". If someone named
    # where they are going and the data does not have it, the honest answer
    # is to say so — not to quietly substitute somewhere else and ask them
    # to confirm the rest of a trip they never asked for.
    if stated_destination and not found.get("to_city"):
        found["unsupported_city"] = stated_destination.title()
        found["when"] = blob
        return found

    if not found.get("to_city") and ordered:
        # With no "to", the first city named is the destination — people
        # say "Mumbai for 2 nights" far more often than they lead with
        # where they are leaving. Never reuse the stated origin.
        remaining = [c for c in ordered if c != found.get("from_city")]
        if remaining:
            found["to_city"] = remaining[0]
    if not found.get("from_city"):
        rest = [c for c in ordered if c != found.get("to_city")]
        if rest:
            found["from_city"] = rest[0]

    nights = _NIGHTS.search(blob)
    if nights:
        found["nights"] = max(1, int(nights.group(1)))
    else:
        days = _DAYS.search(blob)
        if days:
            # A 3-day trip is 2 nights. Saying so beats charging for three.
            found["nights"] = max(1, int(days.group(1)) - 1)

    party = _PARTY.search(blob)
    if party:
        found["party_size"] = max(1, int(party.group(1)))

    money = _BUDGET.search(blob)
    if money:
        amount = int(money.group(1).replace(",", ""))
        if money.group(2):
            amount *= 1000
        found["max_price_paise"] = amount * 100

    # A city that was clearly named but is not in the six the datasets
    # cover. Without this, someone who typed "weekend in Goa" is asked
    # "where are you going?" — which reads as though they had not said.
    if not found.get("to_city") and to_hit:
        named_place = to_hit.group(1).strip()
        if named_place and not _canonical_city(named_place):
            found["unsupported_city"] = named_place.title()

    found["when"] = blob      # parse_when reads the date out of it itself
    return found
