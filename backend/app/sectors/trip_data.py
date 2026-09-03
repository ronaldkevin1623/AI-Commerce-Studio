"""
THE TRIP DATASETS, LOADED ONCE AND HELD IN MEMORY.

Three supplied CSVs, ~173 MB raw, covering the same six Indian metros:

    flights       Clean_Dataset.csv          300,153 rows, real fares
    hotels        <city>.csv x 6                 580 rows, real rates + tax
    restaurants   zomato_restaurants_in_India   31,314 rows in those cities

WHAT IS REAL AND WHAT IS NOT — the honest inventory, because a dataset is
easy to describe as if it were an API.

  Real: every fare, rate, tax, cuisine, rating and opening time below is a
  value from the supplied files. Nothing is generated, averaged into
  existence, or filled in when missing.

  Not live: these are snapshots. Prices do not move, and no availability
  is asserted for any date. A hotel row is a RATE, not an inventory — the
  dataset cannot answer "is that room free on the 14th" and this module
  never pretends it can.

  Coarse in one place: flights carry `days_left` and a time bucket
  ("Evening"), not timestamps. A chosen travel date is mapped onto
  `days_left`; the result is a departure WINDOW and is labelled as one.

  Missing in one place: hotels have a locality and a distance to a
  landmark, but no coordinates. Restaurant sequencing is geographic;
  hotel placement is locality-level, and the difference is disclosed
  rather than smoothed over.

Loading is lazy and cached: the zomato file is 110 MB and is filtered to
the six cities on first use, which is the only reason holding this in
memory is reasonable at all.
"""
import csv
import os
import re
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))

RAW = Path(__file__).resolve().parents[2] / "data" / "trip" / "raw"

CITIES = ("Bangalore", "Chennai", "Delhi", "Hyderabad", "Kolkata", "Mumbai")

# The restaurant file names Delhi differently from the flight and hotel
# files. One alias, written down rather than silently normalised, so the
# join is visible to anyone checking whether the cities really line up.
CITY_ALIASES = {
    "new delhi": "Delhi",
    "bengaluru": "Bangalore",
}

_cache: dict = {}


def _money(value) -> int:
    """'7,567' -> 756700 paise. Blank or unparseable -> 0."""
    if value is None:
        return 0
    text = re.sub(r"[^\d.]", "", str(value))
    if not text:
        return 0
    try:
        return int(round(float(text) * 100))
    except ValueError:
        return 0


def _canonical_city(name: str) -> str:
    key = (name or "").strip().lower()
    if key in CITY_ALIASES:
        return CITY_ALIASES[key]
    for city in CITIES:
        if key == city.lower():
            return city
    return ""


def available() -> dict:
    """Which datasets are actually present, for honest degradation."""
    return {
        "flights": (RAW / "Clean_Dataset.csv").exists(),
        "hotels": all((RAW / f"{c.lower()}.csv").exists() for c in CITIES),
        "restaurants": (RAW / "zomato_restaurants_in_India.csv").exists(),
    }


# ── hotels ───────────────────────────────────────────────────────────────

def hotels() -> list[dict]:
    """
    580 hotels across six cities, with the rate and tax as supplied.

    `record_id` is the thing the audit trail will point at later: the
    charge for a stay has to be traceable to the exact row that won the
    evaluation, not to a price that merely resembles it.
    """
    if "hotels" in _cache:
        return _cache["hotels"]

    rows = []
    for city in CITIES:
        path = RAW / f"{city.lower()}.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8", errors="replace") as handle:
            for index, raw in enumerate(csv.DictReader(handle)):
                name = (raw.get("Hotel Name") or "").strip()
                price = _money(raw.get("Price"))
                if not name or not price:
                    continue
                # Names in this file sometimes carry an embedded newline
                # and a trailing "Like a 3" marker from the source page.
                name = " ".join(name.split())
                name = re.sub(r"\s*Like a \d\s*$", "", name).strip()
                rows.append({
                    "record_id": f"hotel:{city.lower()}:{index}",
                    "source": "trip-hotels",
                    "leg": "hotel",
                    "name": name,
                    "city": city,
                    "locality": (raw.get("Location") or "").strip(),
                    "landmark": (raw.get("Nearest Landmark") or "").strip(),
                    "landmark_distance": (raw.get("Distance to Landmark") or "").strip(),
                    "price_paise": price,          # per night, as listed
                    "tax_paise": _money(raw.get("Tax")),
                    "rating": _num(raw.get("Rating")),
                    "rating_text": (raw.get("Rating Description") or "").strip(),
                    "reviews": int(_num(raw.get("Reviews")) or 0),
                    "star_rating": _num(raw.get("Star Rating")),
                })
    _cache["hotels"] = rows
    return rows


def _num(value):
    try:
        text = re.sub(r"[^\d.]", "", str(value or ""))
        return float(text) if text else None
    except ValueError:
        return None


# ── flights ──────────────────────────────────────────────────────────────

def flights() -> list[dict]:
    """
    Real fares between the six metros.

    `days_left` is days before departure, not a date. `departure_time` is
    a bucket. Both are carried through unchanged and labelled at the point
    of display, because turning "Evening" into "18:30" would be inventing
    a departure time nobody supplied.
    """
    if "flights" in _cache:
        return _cache["flights"]

    path = RAW / "Clean_Dataset.csv"
    rows = []
    if path.exists():
        with path.open(encoding="utf-8", errors="replace") as handle:
            for index, raw in enumerate(csv.DictReader(handle)):
                price = _money(raw.get("price"))
                src = _canonical_city(raw.get("source_city"))
                dst = _canonical_city(raw.get("destination_city"))
                if not price or not src or not dst or src == dst:
                    continue
                rows.append({
                    "record_id": f"flight:{index}",
                    "source": "trip-flights",
                    "leg": "flight",
                    "name": f"{raw.get('airline')} {raw.get('flight')}",
                    "airline": (raw.get("airline") or "").strip(),
                    "flight_no": (raw.get("flight") or "").strip(),
                    "from_city": src,
                    "to_city": dst,
                    "departure_window": (raw.get("departure_time") or "").strip(),
                    "arrival_window": (raw.get("arrival_time") or "").strip(),
                    "stops": (raw.get("stops") or "").strip(),
                    "travel_class": (raw.get("class") or "").strip(),
                    "duration_hours": _num(raw.get("duration")),
                    "days_left": int(_num(raw.get("days_left")) or 0),
                    "price_paise": price,
                })
    _cache["flights"] = rows
    return rows


# ── restaurants ──────────────────────────────────────────────────────────

def restaurants() -> list[dict]:
    """
    Restaurants in the same six cities, with coordinates and real hours.

    The only leg with both lat/lon and opening times, which is what makes
    genuine sequencing possible at all rather than a list in a plausible
    order.
    """
    if "restaurants" in _cache:
        return _cache["restaurants"]

    path = RAW / "zomato_restaurants_in_India.csv"
    rows = []
    if path.exists():
        with path.open(encoding="utf-8", errors="replace") as handle:
            for index, raw in enumerate(csv.DictReader(handle)):
                city = _canonical_city(raw.get("city"))
                if not city:
                    continue
                cost = _money(raw.get("average_cost_for_two"))
                name = (raw.get("name") or "").strip()
                if not name or not cost:
                    continue
                rows.append({
                    "record_id": f"restaurant:{raw.get('res_id') or index}",
                    "source": "trip-restaurants",
                    "leg": "meal",
                    "name": name,
                    "city": city,
                    "locality": (raw.get("locality") or "").strip(),
                    "latitude": _num(raw.get("latitude")),
                    "longitude": _num(raw.get("longitude")),
                    "cuisines": (raw.get("cuisines") or "").strip(),
                    "timings": (raw.get("timings") or "").strip(),
                    "price_paise": cost,           # for two, as supplied
                    "rating": _num(raw.get("aggregate_rating")),
                    "votes": int(_num(raw.get("votes")) or 0),
                    "establishment": (raw.get("establishment") or "").strip(),
                })
    _cache["restaurants"] = rows
    return rows


def summary() -> dict:
    """Counts, for the honesty panel and the sector's availability check."""
    present = available()
    return {
        "present": present,
        "cities": list(CITIES),
        "flights": len(flights()) if present["flights"] else 0,
        "hotels": len(hotels()) if present["hotels"] else 0,
        "restaurants": len(restaurants()) if present["restaurants"] else 0,
        "disclosure": (
            "Supplied datasets, not live provider APIs. Fares, nightly rates "
            "and meal costs are real values from those files; none of them is "
            "a live quote, and no availability is asserted for any date."
        ),
    }
