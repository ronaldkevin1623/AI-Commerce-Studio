"""
ASSEMBLING ONE ITINERARY OUT OF THREE DATASETS.

This is the file that justifies the sector boundary. Everything the
products pipeline does is "score a list, take the top row". Nothing here
works that way, because the answer is not a row:

    the hotel must be in the city the flight lands in
    the meals must be near the hotel that won, not near the best hotel
    the budget applies to the sum, not to any leg
    a meal must be open at the hour it is placed

Each of those is a dependency between choices, and a ranker cannot express
one. So this picks in order — flight, then hotel under what is left, then
meals under what is left after that — and every later choice is
constrained by the earlier ones.

WHY NOT OPTIMISE JOINTLY

A proper joint optimisation over 300k flights x 100 hotels x 5k
restaurants is a different project. Greedy-with-constraints is honest
about being greedy: it reports what it chose, what it had left at each
step, and where it had to compromise. What it never does is present a
sequence of independent picks as if they had been chosen together.
"""
from app.sectors import trip_data
from app.sectors.base import SectorResult
from app.sectors.trip import (MEAL_SLOTS, NEARBY_KM, haversine_km,
                              opens_during, parse_when)
from app.sectors.trip_adapters import (FlightAdapter, HotelAdapter,
                                       RestaurantAdapter)

# How much of the total a flight may eat before the hotel has nothing to
# work with. Not a rule about flights — a rule about leaving room.
# Defaults. The live values are read per run from the hive dials below, so
# moving a slider changes the next itinerary rather than requiring an edit
# here — that is what makes the hive a control surface instead of a picture.
FLIGHT_SHARE = 0.55
HOTEL_SHARE = 0.75          # of what remains after the flight


def _dial(key: str, fallback):
    """One tunable, read at decision time. Falls back if settings are down."""
    try:
        from app.agent import settings
        value = settings.get("trip", key)
        return fallback if value is None else value
    except Exception:
        return fallback


def _locality_anchor(hotel: dict, city: str) -> tuple:
    """
    Approximate where the hotel is, using restaurants as landmarks.

    Hotels in this dataset have no coordinates; restaurants do. So the
    hotel's locality string is matched against restaurant localities and
    their mean position stands in for it. That is an approximation and is
    reported as one — it is why the itinerary says "near <locality>"
    rather than quoting a distance from the hotel door.
    """
    locality = (hotel.get("locality") or "").strip().lower()
    if not locality:
        return (None, None, "")
    matches = [r for r in trip_data.restaurants()
               if r["city"] == city and locality
               and locality.split()[0] in (r["locality"] or "").lower()]
    if not matches:
        return (None, None, "")
    lat = sum(r["latitude"] for r in matches if r["latitude"]) / max(1, len([r for r in matches if r["latitude"]]))
    lon = sum(r["longitude"] for r in matches if r["longitude"]) / max(1, len([r for r in matches if r["longitude"]]))
    return (lat, lon, hotel.get("locality") or "")


def assemble(need: dict) -> SectorResult:
    """Choose a flight, a hotel and meals that fit each other and the budget."""
    from_city = need.get("from_city") or ""
    to_city = need.get("to_city") or ""
    nights = max(1, int(need.get("nights") or 1))
    party = max(1, int(need.get("party_size") or 1))
    budget = int(need.get("max_price_paise") or 0)
    days_left, date_note = parse_when(need.get("when") or "")

    flight_share = float(_dial("flight_share_pct", 55)) / 100.0
    hotel_share = float(_dial("hotel_share_pct", 75)) / 100.0
    nearby_km = float(_dial("nearby_km", NEARBY_KM))
    meals_per_day = int(_dial("meals_per_day", len(MEAL_SLOTS)))
    slots = MEAL_SLOTS[:max(0, meals_per_day)]

    legs: list[dict] = []
    warnings: list[str] = []
    steps: list[dict] = []

    # ── 1. the flight, which decides which city everything else is in ──
    flights = FlightAdapter().search(
        from_city=from_city, to_city=to_city, days_left=days_left,
        max_price_paise=int(budget * flight_share) if budget else 0)
    if not flights:
        return SectorResult(
            "trip", [], narrative=(
                f"No fares in the dataset between {from_city or '?'} and "
                f"{to_city or '?'}. It covers six metros: "
                f"{', '.join(trip_data.CITIES)}."),
            warnings=["No flight, so nothing else was chosen — the "
                      "destination is what the rest depends on."])

    flight = flights[0]
    legs.append({**flight, "role": "outbound flight"})
    steps.append({"step": "flight", "considered": len(flights),
                  "chose": flight["name"],
                  "detail": f"cheapest of {len(flights)} fares within "
                            f"{days_left} days of departure"})

    spent = flight["price_paise"]
    remaining = (budget - spent) if budget else 0

    # ── 2. the hotel, in the city the flight actually reaches ──────────
    per_night_cap = int(remaining * hotel_share / nights) if remaining > 0 else 0
    hotels = HotelAdapter().search(city=to_city, max_price_paise=per_night_cap)
    if not hotels:
        warnings.append(f"No hotel rows for {to_city}.")
        hotel = None
    else:
        # Best rated that still fits. Falling back to the cheapest rather
        # than abandoning the trip, and saying which happened.
        affordable = [h for h in hotels
                      if not per_night_cap
                      or (h["price_paise"] + h["tax_paise"]) <= per_night_cap]
        if affordable:
            # Shrunk toward the city mean, not raw rating.
            #
            # Raw rating handed a 2-night stay to a dormitory scoring 4.8
            # from FOUR reviews, beating well-reviewed hotels on evidence
            # that thin. The products sector already refuses to do this to
            # seller feedback (quality.shrunk_feedback); the same argument
            # applies to a hotel and the same correction is used.
            rated = [h for h in affordable if h["rating"]]
            mean = (sum(h["rating"] for h in rated) / len(rated)) if rated else 3.5
            hotel = max(affordable, key=lambda h: _shrunk(h, mean))
            note = (f"best rated of {len(affordable)} under the nightly cap, "
                    f"shrunk toward the city mean of {mean:.1f}")
        else:
            hotel = min(hotels, key=lambda h: h["price_paise"] + h["tax_paise"])
            note = "nothing fitted the nightly cap — cheapest available instead"
            warnings.append(
                f"The budget left ₹{per_night_cap / 100:,.0f} a night after the "
                f"flight; the cheapest room in {to_city} is "
                f"₹{(hotel['price_paise'] + hotel['tax_paise']) / 100:,.0f}.")
        stay_total = (hotel["price_paise"] + hotel["tax_paise"]) * nights
        legs.append({**hotel, "role": f"{nights} night{'s' if nights > 1 else ''}",
                     "nights": nights, "price_paise": stay_total,
                     "nightly_paise": hotel["price_paise"],
                     "nightly_tax_paise": hotel["tax_paise"]})
        spent += stay_total
        remaining = (budget - spent) if budget else 0
        steps.append({"step": "hotel", "considered": len(hotels),
                      "chose": hotel["name"], "detail": note})

    # ── 3. meals, near the hotel that won and open when placed ────────
    if hotel:
        lat, lon, locality = _locality_anchor(hotel, to_city)
        pool = RestaurantAdapter().search(city=to_city)
        per_meal_cap = int(remaining / max(1, nights * max(1, len(slots)))) if remaining > 0 else 0

        placed, considered = 0, len(pool)
        for day in range(nights):
            for slot, hour in slots:
                options = []
                # Dedup on NAME, not just record_id.
                #
                # Chains have one row per outlet, so "Coal Barbecues" could
                # win day 1 lunch and day 2 lunch as two different records
                # and pass an id-based check. Technically two restaurants,
                # but an itinerary that sends you to the same brand twice
                # reads as a bug to the person holding it.
                used_names = {(l.get("name") or "").strip().lower()
                              for l in legs if l.get("leg") == "meal"}
                for row in pool:
                    if any(l.get("record_id") == row["record_id"] for l in legs):
                        continue
                    if (row.get("name") or "").strip().lower() in used_names:
                        continue
                    cost = row["price_paise"] * (1 if party <= 2 else party / 2)
                    if per_meal_cap and cost > per_meal_cap:
                        continue
                    open_now = opens_during(row["timings"], hour)
                    if open_now is False:
                        continue
                    distance = (haversine_km(lat, lon, row["latitude"], row["longitude"])
                                if lat else float("inf"))
                    if distance != float("inf") and distance > nearby_km:
                        continue
                    options.append((distance, -(row["rating"] or 0), row, open_now, cost))
                if not options:
                    continue
                # Nearest first, rating as the tie-break. An itinerary that
                # sends you across the city for half a star is a worse
                # itinerary, whatever the ranking says.
                options.sort(key=lambda o: (round(o[0], 1), o[1]))
                distance, _rank, row, open_now, cost = options[0]
                legs.append({
                    **row, "role": f"day {day + 1} {slot}",
                    "price_paise": int(cost),
                    "distance_km": None if distance == float("inf") else round(distance, 1),
                    "hours_known": open_now is True,
                })
                placed += 1
        steps.append({"step": "meals", "considered": considered,
                      "chose": f"{placed} of {nights * len(slots)}",
                      "detail": f"nearest to {locality or to_city} that were "
                                f"open and within budget"})
        if slots and placed < nights * len(slots):
            warnings.append(
                f"Placed {placed} of {nights * len(slots)} meals — the rest "
                f"had no option that was near {locality or to_city}, open at that "
                f"hour and inside what was left of the budget.")

    unknown_hours = [l for l in legs if l.get("leg") == "meal" and not l.get("hours_known")]
    if unknown_hours:
        warnings.append(
            f"{len(unknown_hours)} meal(s) kept although their opening hours "
            f"could not be parsed. Not assumed open — carried as unknown.")

    result = SectorResult(
        "trip", legs,
        narrative=_narrate(from_city, to_city, nights, legs, date_note),
        warnings=warnings,
        payable_leg=_payable(legs),
        steps=steps, date_note=date_note)
    if budget and result.total_paise > budget:
        result.warnings.insert(0, (
            f"₹{result.total_paise / 100:,.0f} is over the ₹{budget / 100:,.0f} "
            f"asked for. Shown so the gap is visible rather than silently "
            f"dropping a leg to fit."))
    return result


# How many reviews it takes before a rating is believed on its own. Below
# this, the score is pulled toward the city average in proportion to how
# little evidence there is — the same shape as the seller-feedback
# shrinkage in app/agent/quality.py.
RATING_PRIOR = 150.0


def _shrunk(hotel: dict, mean: float) -> float:
    rating = hotel.get("rating")
    if rating is None:
        return mean * 0.9          # unknown is not a selling point
    prior = float(_dial("rating_prior", RATING_PRIOR))
    votes = float(hotel.get("reviews") or 0)
    if prior <= 0:
        return float(rating)       # raw rating, dormitories and all
    return (votes * rating + prior * mean) / (votes + prior)


def _payable(legs: list[dict]) -> dict | None:
    """
    The one leg that can end in a real charge.

    Carries the hotel's own record id and its own nightly rate, because
    the charge has to be traceable to the specific row that won — not to
    a plausible-looking amount.
    """
    stay = next((l for l in legs if l.get("leg") == "hotel"), None)
    if not stay:
        return None
    return {
        "record_id": stay["record_id"],
        "name": stay["name"],
        "city": stay["city"],
        "nights": stay.get("nights", 1),
        "nightly_paise": stay.get("nightly_paise"),
        "nightly_tax_paise": stay.get("nightly_tax_paise"),
        "price_paise": stay["price_paise"],
        "via": "demo-merchant-standin",
        "disclosure": (
            "Real payment captured for a demo-merchant stand-in. This is not "
            "a booking: no room is held and no hotel is contacted. Production "
            "would require direct hotel-supplier integration. The amount is "
            "read from this hotel's own row in the supplied dataset."
        ),
    }


def _narrate(from_city, to_city, nights, legs, date_note) -> str:
    flight = next((l for l in legs if l.get("leg") == "flight"), None)
    stay = next((l for l in legs if l.get("leg") == "hotel"), None)
    meals = [l for l in legs if l.get("leg") == "meal"]
    parts = []
    if flight:
        parts.append(
            f"{flight['airline']} {flight['flight_no']} {from_city} to {to_city}, "
            f"departing in the {flight['departure_window'].replace('_', ' ').lower()} "
            f"({date_note})")
    if stay:
        parts.append(
            f"{nights} night{'s' if nights > 1 else ''} at {stay['name']} in "
            f"{stay.get('locality') or to_city}"
            + (f", rated {stay['rating']}" if stay.get("rating") else ""))
    if meals:
        parts.append(f"{len(meals)} meals nearby")
    return ". ".join(parts) + "." if parts else "Nothing could be assembled."
