"""
SECTORS OVER HTTP: THE PICKER, THE CLASSIFIER, AND THE ONE PAYABLE LEG.

Three things live here.

  /sectors            what the `/` menu shows, read from the registry so a
                      newly registered sector appears with no front-end
                      change. That is the test of whether the plug-in
                      boundary is real: adding one must not mean editing
                      an array in a React file.

  /sectors/classify   which sector a piece of free text belongs to, or an
                      honest refusal. Running an entire pipeline against
                      the wrong sector is far worse than one extra
                      question, so a close call asks.

  /trip/plan, /trip/book
                      the trip sector's run and its single payable leg.

ON THE PAYABLE LEG — the part that is easy to fake and must not be.

The charge is for the hotel the itinerary actually chose. The client sends
a record id and nothing else that matters: the nightly rate, the tax and
the night count are re-read here from the dataset row, so a tampered or
stale price in the browser cannot become the amount charged. The Razorpay
order carries the record id in its notes, and the audit trail links

    hotel record  ->  asserted price  ->  razorpay order  ->  payment id

in one row, so afterwards it is provable which specific hotel the money
corresponded to. A stand-in that charged a plausible round number would
have looked identical on screen and been worthless as evidence.
"""
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.firebase_client import (log_decision, save_trip, list_trips,
                                 get_trip)
from app.razorpay_client import create_order
from app.sectors import registry, trip_data

router = APIRouter(tags=["sectors"])


@router.get("/sectors")
def list_sectors():
    """Everything the `/` picker needs. Straight from the registry."""
    registry.bootstrap()
    return {
        "sectors": registry.describe(),
        "count": len(registry.sectors()),
        "note": ("Sectors are plug-ins. This list is the registry, not a "
                 "hardcoded menu — registering one makes it appear here and "
                 "in the picker with no front-end change."),
    }


class ClassifyRequest(BaseModel):
    text: str


@router.post("/sectors/classify")
def classify_text(body: ClassifyRequest):
    """
    Which sector does this free text belong to?

    Returns every sector's score, not just the winner, because "why did my
    trip request run as a product search" is only answerable later if the
    runner-up was recorded at the time.
    """
    registry.bootstrap()
    return registry.classify(body.text or "")


class PlanRequest(BaseModel):
    # What the person actually typed. Fields left blank are read out of
    # this; fields sent explicitly win over it.
    text: str = ""
    # WHICH QUESTION THIS TEXT IS ANSWERING.
    #
    # Planning is a conversation: the agent asks "flying from?" and the
    # reply is "Delhi". Parsed as a fresh request that reads as a trip TO
    # Delhi, and the Kolkata the person already said is gone. When this is
    # set, the text is read only as a value for that one field and
    # everything already established is kept.
    answer_for: str = ""
    from_city: str = ""
    to_city: str = ""
    # Zero means "not stated", not "one". A default of 1 here is truthy,
    # so it silently beat the 2 that had been read out of "2 nights in
    # Mumbai" and every trip came back one night short. Absent has to be
    # distinguishable from chosen or the merge below cannot be written.
    nights: int = 0
    party_size: int = 0
    max_price_paise: int = 0
    when: str = ""
    # How the sector was chosen. Recorded so a wrong auto-classification is
    # traceable after the fact rather than indistinguishable from a
    # deliberate choice.
    sector_source: str = "explicit_slash"
    customer_id: str = ""


@router.post("/trip/plan")
def plan_trip(body: PlanRequest):
    """Assemble one itinerary and record that it happened, under which sector."""
    registry.bootstrap()
    sector = registry.get("trip")
    if not sector:
        raise HTTPException(status_code=503,
                            detail="The trip sector is not available.")

    need = body.model_dump()

    if body.text and body.answer_for:
        from app.sectors.trip import _canonical_city
        raw = body.text.strip()
        field = body.answer_for
        if field in ("to_city", "from_city"):
            city = _canonical_city(raw)
            if not city:
                return {
                    "ok": False,
                    "needs": [f.to_dict() for f in sector.intent_schema()
                              if f.name == field],
                    "detail": (f"I could not read {raw!r} as one of the cities "
                               f"in the data. Coverage is "
                               f"{', '.join(trip_data.CITIES)}."),
                }
            need[field] = city
        else:
            from app.sectors.trip import parse_intent
            answered = parse_intent(raw)
            if field in answered:
                need[field] = answered[field]
        need["when"] = need.get("when") or ""

    elif body.text:
        from app.sectors.trip import parse_intent
        parsed = parse_intent(body.text)
        # THE NEWEST MESSAGE WINS.
        #
        # These used to be filled only where the accumulated need was
        # blank, which meant "make it 4 nights" on an existing trip was
        # read and then discarded because nights was already set. What the
        # person just said is the most recent statement of what they want;
        # anything they did not mention keeps its previous value.
        for key, value in parsed.items():
            if value:
                need[key] = value
        if parsed.get("unsupported_city"):
            return {
                "ok": False,
                "needs": [],
                "unsupported_city": parsed["unsupported_city"],
                "detail": (f"{parsed['unsupported_city']} is not in the supplied "
                           f"datasets, so no fare, rate or restaurant could be "
                           f"quoted for it. Coverage is "
                           f"{', '.join(trip_data.CITIES)} — six metros, because "
                           f"that is what the data has, not a product decision."),
            }

    need["nights"] = int(need.get("nights") or 1)
    need["party_size"] = int(need.get("party_size") or 1)

    missing = [f.name for f in sector.intent_schema()
               if f.required and not need.get(f.name)]
    if missing:
        fields = {f.name: f.to_dict() for f in sector.intent_schema()}

        # SAY WHAT WAS UNDERSTOOD, then ask for the one thing missing.
        #
        # The old message announced "a trip with no destination" even when
        # the destination had been read perfectly and only the origin was
        # missing. Being lectured about a mistake you did not make, with no
        # sign that anything you typed landed, is worse than no message.
        got = []
        if need.get("to_city"):
            got.append(f"a trip to {need['to_city']}")
        if need.get("from_city"):
            got.append(f"leaving from {need['from_city']}")
        if need.get("nights"):
            nights = int(need["nights"])
            got.append(f"{nights} night{'s' if nights != 1 else ''}")
        if need.get("max_price_paise"):
            got.append(f"under ₹{int(need['max_price_paise']) / 100:,.0f}")
        if int(need.get("party_size") or 1) > 1:
            got.append(f"for {need['party_size']} people")

        asked = fields[missing[0]]["prompt"]
        detail = (f"Got {', '.join(got)}. {asked}" if got
                  else "Tell me where you are going, and where from.")
        return {
            "ok": False,
            "needs": [fields[m] for m in missing],
            "understood": {k: need.get(k) for k in
                           ("from_city", "to_city", "nights",
                            "max_price_paise", "party_size")
                           if need.get(k)},
            "detail": detail,
        }

    started = time.time()
    result = sector.assemble(need)
    payload = result.to_dict()
    payload["ok"] = True
    # Returned on success too, so the next message can refine this trip
    # rather than starting a new one.
    payload["understood"] = {
        "from_city": need.get("from_city"), "to_city": need.get("to_city"),
        "nights": need.get("nights"), "party_size": need.get("party_size"),
        "max_price_paise": need.get("max_price_paise"),
    }
    payload["took_ms"] = int((time.time() - started) * 1000)
    payload["disclosure"] = trip_data.summary()["disclosure"]

    try:
        log_decision(
            action_type="sector_run",
            amount_paise=result.total_paise,
            decision="planned",
            reason=(f"[sector=trip source={body.sector_source}] "
                    f"{need.get('from_city')}->{need.get('to_city')}, "
                    f"{need.get('nights')} night(s). "
                    f"{len(result.legs)} legs, total "
                    f"₹{result.total_paise / 100:,.0f}. "
                    f"Datasets, not live providers; no availability asserted."),
            customer_id=body.customer_id or None,
        )
    except Exception as exc:
        print(f"[sector] run not recorded: {exc}", flush=True)

    return payload


class BookRequest(BaseModel):
    # The ONLY thing that identifies what is being paid for. Everything
    # about the amount is looked up from this server-side.
    hotel_record_id: str
    nights: int = 1
    customer_id: str = ""
    sector_source: str = "explicit_slash"
    # The request the itinerary came from. Sent so the server can re-run the
    # assembly and confirm this hotel is the one that actually won it —
    # rather than taking the client's word that these two things belong
    # together. Assembly over the datasets is deterministic, so re-running
    # it is a real check and not a formality.
    text: str = ""
    from_city: str = ""
    to_city: str = ""
    when: str = ""
    max_price_paise: int = 0
    party_size: int = 0


@router.post("/trip/book")
def book_stay(body: BookRequest):
    """
    Create a real Razorpay order for the hotel the itinerary chose.

    The amount comes from the dataset row, never from the request. That is
    the whole point: the capture has to be provably the price of THAT
    hotel, not a number the browser supplied that happened to look right.
    """
    registry.bootstrap()
    record = next((h for h in trip_data.hotels()
                   if h["record_id"] == body.hotel_record_id), None)
    if not record:
        raise HTTPException(
            status_code=404,
            detail=(f"No hotel row with id {body.hotel_record_id!r}. The "
                    f"charge is derived from the dataset record, so an "
                    f"unknown id cannot be priced."))

    # Re-assemble and check the hotel being charged is the one the
    # itinerary chose. Without this the route would happily charge for any
    # row in the dataset that a caller named — the price would still be
    # honest, but the claim "this is the hotel in your itinerary" would not
    # be checked by anything.
    itinerary = None
    verified = False
    need = {}
    if body.to_city or body.text:
        from app.sectors.trip import parse_intent
        need = {"from_city": body.from_city, "to_city": body.to_city,
                "nights": body.nights, "when": body.when or body.text,
                "max_price_paise": body.max_price_paise,
                "party_size": body.party_size}
        if body.text:
            for key, value in parse_intent(body.text).items():
                if not need.get(key):
                    need[key] = value
        need["nights"] = int(need.get("nights") or 1)
        need["party_size"] = int(need.get("party_size") or 1)
        try:
            trip_sector = registry.get("trip")
            result = trip_sector.assemble(need)
            itinerary = result.to_dict()
            payable = result.payable_leg or {}
            if payable.get("record_id") != record["record_id"]:
                raise HTTPException(
                    status_code=409,
                    detail=(f"That request does not choose this hotel. Re-running "
                            f"the itinerary picks {payable.get('name')!r} "
                            f"({payable.get('record_id')}), not "
                            f"{record['name']!r} ({record['record_id']}). "
                            f"Refusing to charge for a hotel the itinerary did "
                            f"not select."))
            verified = True
        except HTTPException:
            raise
        except Exception as exc:
            print(f"[sector] re-assembly check skipped: {exc}", flush=True)

    nights = max(1, int(body.nights or 1))
    nightly = int(record["price_paise"])
    tax = int(record["tax_paise"] or 0)
    amount = (nightly + tax) * nights

    notes = {
        # Carried into Razorpay itself, so the link survives outside this
        # database and can be checked against the dashboard.
        "sector": "trip",
        "leg": "hotel",
        "hotel_record_id": record["record_id"],
        "hotel_name": record["name"][:120],
        "city": record["city"],
        "nights": str(nights),
        "nightly_paise": str(nightly),
        "tax_paise": str(tax),
        "basis": "supplied dataset row; demo-merchant stand-in, not a booking",
    }

    try:
        order = create_order(amount, f"trip-{record['record_id']}-{int(time.time())}",
                             notes=notes)
    except Exception as exc:
        raise HTTPException(status_code=502,
                            detail=f"Razorpay order could not be created: {exc}")

    try:
        log_decision(
            action_type="trip_stay_order_created",
            amount_paise=amount,
            decision="allowed",
            reason=(f"[sector=trip source={body.sector_source}] "
                    f"hotel_record={record['record_id']} "
                    f"name={record['name'][:60]!r} city={record['city']} "
                    f"nightly=₹{nightly / 100:,.0f} tax=₹{tax / 100:,.0f} "
                    f"nights={nights} -> asserted=₹{amount / 100:,.0f} "
                    f"razorpay_order={order.get('id')}. "
                    f"Amount read from the dataset row, not from the client. "
                    f"Demo-merchant stand-in: a real payment, not a booking — "
                    f"no room is held and no hotel is contacted."),
            order_id=order.get("id"),
            customer_id=body.customer_id or None,
        )
    except Exception as exc:
        print(f"[sector] stay order not recorded: {exc}", flush=True)

    try:
        from app import inflight
        from app.firebase_client import STORE_BINDING
        inflight.open_checkout(order.get("id"), store=STORE_BINDING,
                               detail=f"trip stay: {record['name'][:60]}")
    except Exception as exc:
        print(f"[inflight] open failed: {exc}", flush=True)

    trip_id = ""
    if itinerary:
        # Stored only once the trip is actually payable. A record for every
        # idle plan would be a write per keystroke-ish and would fill the
        # Trips page with things nobody booked.
        trip_id = f"trip-{uuid.uuid4().hex[:12]}"
        try:
            save_trip(trip_id, "trip", need, itinerary, order.get("id"),
                      amount, body.customer_id or None)
        except Exception as exc:
            print(f"[sector] trip not stored: {exc}", flush=True)
            trip_id = ""

    return {
        "ok": True,
        "trip_id": trip_id,
        "itinerary_verified": verified,
        "razorpay_order_id": order.get("id"),
        "amount_paise": amount,
        "hotel": {
            "record_id": record["record_id"], "name": record["name"],
            "city": record["city"], "locality": record["locality"],
            "rating": record["rating"], "reviews": record["reviews"],
        },
        "breakdown": {"nightly_paise": nightly, "tax_paise": tax,
                      "nights": nights, "total_paise": amount},
        # Shown on the checkout sheet, not buried in a docstring.
        "disclosure": (
            "Real payment captured for a demo-merchant stand-in. This is not a "
            "hotel booking: no room is held and no hotel is contacted. "
            "Production would require direct hotel-supplier integration. The "
            "amount is this hotel's own nightly rate plus tax from the "
            "supplied dataset, multiplied by the nights requested."
        ),
    }


@router.get("/trips")
def trips():
    """
    Trips that reached payment. Nothing is invented here: an empty list
    means nothing has been booked, and the UI says exactly that rather
    than showing samples.
    """
    try:
        rows = list_trips()
    except Exception as exc:
        raise HTTPException(status_code=503,
                            detail=f"The trip records could not be read: {exc}")
    return {"trips": rows, "count": len(rows)}


@router.get("/trips/{trip_id}")
def trip_detail(trip_id: str):
    row = get_trip(trip_id)
    if not row:
        raise HTTPException(status_code=404, detail="No such trip.")
    return row
