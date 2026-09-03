"""
TRIP PROVIDERS, SCOPED TO THE TRIP SECTOR.

These satisfy the same shape as the venue adapters — `name`, `kind`,
`can_fulfil`, `available()`, `search()` — so the core treats them the same
way. What they deliberately do NOT do is call
`app.adapters.registry.register`. They are returned by `TripSector.adapters()`
and reachable no other way.

That is the whole isolation guarantee, and it is one line of discipline in
three files. If any of these ever appeared in the global registry, a search
for wireless earbuds would start returning flights to Kolkata — which is
the single most obvious way this refactor could have broken the thing it
was supposed to leave alone.

`can_fulfil` is False on all three. None of them can hold a seat, a room or
a table. The one payable leg goes through the demo merchant instead, and is
labelled there as a stand-in.
"""
from app.sectors import trip_data


class _DatasetAdapter:
    """Shared behaviour: read the file, filter, hand back listing-shaped rows."""

    leg = ""
    kind = "dataset"
    can_fulfil = False

    def available(self) -> bool:
        try:
            return bool(trip_data.available().get(self._dataset_key))
        except Exception:
            return False

    def _rows(self) -> list[dict]:
        raise NotImplementedError


class FlightAdapter(_DatasetAdapter):
    name = "trip-flights"
    label = "Flights (supplied dataset)"
    leg = "flight"
    _dataset_key = "flights"

    def search(self, query: str = "", *, from_city: str = "", to_city: str = "",
               days_left: int = 21, travel_class: str = "Economy",
               max_price_paise: int = 0, limit: int = 40) -> list[dict]:
        """
        Fares on one route, near the requested lead time.

        `days_left` is matched with a widening tolerance rather than
        exactly: the file is dense at some lead times and sparse at
        others, and refusing to return anything because nothing sits on
        precisely day 21 would report an empty market that isn't.
        """
        rows = [r for r in trip_data.flights()
                if r["from_city"] == from_city and r["to_city"] == to_city]
        if travel_class:
            classed = [r for r in rows
                       if r["travel_class"].lower() == travel_class.lower()]
            rows = classed or rows
        if max_price_paise:
            affordable = [r for r in rows if r["price_paise"] <= max_price_paise]
            rows = affordable or rows

        for tolerance in (0, 1, 2, 4, 7, 14, 999):
            near = [r for r in rows if abs(r["days_left"] - days_left) <= tolerance]
            if near:
                for row in near:
                    row = dict(row)
                return sorted(near, key=lambda r: r["price_paise"])[:limit]
        return []


class HotelAdapter(_DatasetAdapter):
    name = "trip-hotels"
    label = "Hotels (supplied dataset)"
    leg = "hotel"
    _dataset_key = "hotels"

    def search(self, query: str = "", *, city: str = "",
               max_price_paise: int = 0, limit: int = 40) -> list[dict]:
        """
        Nightly rates in one city.

        The ceiling here is per night, not the trip total — the total is
        the assembler's job, and a hotel adapter that tried to reason
        about the flight would be sector logic in the wrong file.
        """
        rows = [r for r in trip_data.hotels() if r["city"] == city]
        if max_price_paise:
            affordable = [r for r in rows
                          if r["price_paise"] + r["tax_paise"] <= max_price_paise]
            rows = affordable or rows
        return sorted(rows, key=lambda r: -(r["rating"] or 0))[:limit]


class RestaurantAdapter(_DatasetAdapter):
    name = "trip-restaurants"
    label = "Restaurants (supplied dataset)"
    leg = "meal"
    _dataset_key = "restaurants"

    def search(self, query: str = "", *, city: str = "", cuisine: str = "",
               max_price_paise: int = 0, limit: int = 120) -> list[dict]:
        rows = [r for r in trip_data.restaurants() if r["city"] == city]
        if cuisine:
            want = cuisine.strip().lower()
            matched = [r for r in rows if want in (r["cuisines"] or "").lower()]
            rows = matched or rows
        if max_price_paise:
            affordable = [r for r in rows if r["price_paise"] <= max_price_paise]
            rows = affordable or rows
        # Rated first, but only where enough people voted for the rating to
        # mean anything — the same shrinkage argument the products sector
        # makes about seller feedback.
        rows = [r for r in rows if (r["votes"] or 0) >= 20] or rows
        return sorted(rows, key=lambda r: -((r["rating"] or 0) * 100 + min(r["votes"] or 0, 500) / 100))[:limit]
