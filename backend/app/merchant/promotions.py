"""
RETAIL MEDIA: WHAT A MERCHANT CAN BUY, AND WHAT IT CANNOT.

The reference deck puts retail media on the map of entry points a shopping
agent has to cope with. Once an agent is choosing on the shopper's behalf,
sponsorship stops being a banner and becomes a claim on the agent's
judgement — so the interesting question is not "can this project show a
sponsored card" but "what exactly is a merchant allowed to purchase from an
agent that is supposed to be working for the buyer".

The answer this implements, and the whole of it:

  A promotion buys CANDIDACY. A promoted product is considered for queries
  in its category that the store's own keyword search would have missed
  entirely. That is a real advantage and it is the merchant's to buy.

  A promotion buys a LABEL if the product then wins a place. Every
  surfaced placement is marked sponsored, on the card and in the reasoning.

  A promotion buys NOTHING in the ranking. The sort key that orders results
  reads quality, price, stock, approval and how many have sold. It does not
  read this file. A promoted product beats an organic one only by being
  better on those measures, and is dropped by relevance, condition, trust or
  precision exactly as an organic one is — the drop is recorded here so the
  merchant can see it happen rather than wonder.

  A promotion buys NO EXEMPTION anywhere else. Same risk gate, same mandate,
  same stock check at checkout.

That is a deliberately narrow product. It is narrow because the alternative
— paid rank — makes the recommendation unfalsifiable, and an agent whose
answer can be bought is not worth putting a mandate behind.

ON THE MONEY:
Spend is accrued per placement against a daily budget the merchant sets, and
written to the decision log like every other financial event in this project.
It is NOT billed: there is no rail here that charges a merchant, and both the
merchant UI and this docstring say so rather than implying an invoice exists.
The accrual is real arithmetic over real placements; the collection is not
built.
"""
from datetime import datetime, timezone

from firebase_admin import firestore

from app.firebase_client import db, log_decision
from app.merchant import store

PROMOTIONS = "merchant_promotions"

# How many sponsored candidates may enter one search, at most. A cap rather
# than a ratio: the pool this draws from is one small store, and a rule
# expressed as "20% of results" would silently mean "all of them" whenever a
# search returned few. Placements still have to survive every screen, so this
# is a ceiling on candidacy and not a promise of slots.
MAX_PLACEMENTS = 2

# Floor on a bid, so a promotion cannot be created that accrues nothing and
# therefore never exhausts its budget.
MIN_BID_PAISE = 100


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _doc(product_id: str):
    return db.collection(PROMOTIONS).document(product_id)


def _spent_today(promo: dict) -> int:
    return int((promo.get("spend") or {}).get(_today()) or 0)


def _shape(promo: dict) -> dict:
    """A promotion as the API and the merchant UI read it."""
    budget = int(promo.get("daily_budget_paise") or 0)
    spent = _spent_today(promo)
    return {
        "product_id": promo.get("product_id"),
        "bid_paise": int(promo.get("bid_paise") or 0),
        "daily_budget_paise": budget,
        "spent_today_paise": spent,
        "remaining_today_paise": max(0, budget - spent),
        "active": bool(promo.get("active")),
        # Exhausted is not the same as switched off, and a merchant looking
        # at a promotion that has stopped running deserves to know which.
        "exhausted": bool(promo.get("active")) and spent >= budget > 0,
        "considered": int(promo.get("considered") or 0),
        "screened_out": int(promo.get("screened_out") or 0),
        "placed": int(promo.get("placed") or 0),
        "chosen": int(promo.get("chosen") or 0),
        "last_screened_out_at": promo.get("last_screened_out_stage"),
    }


def set_promotion(product_id: str, *, bid_paise: int,
                  daily_budget_paise: int, active: bool = True) -> dict:
    """
    Create or update a promotion on a product the store actually stocks.

    Refuses a product that does not exist rather than accepting a promotion
    that could never run — a merchant who mistypes an id should be told, not
    left watching a counter that stays at zero.
    """
    product = store.get_product(product_id)
    if not product:
        return {"ok": False, "error": f"No product with id {product_id!r}."}

    bid_paise = int(bid_paise or 0)
    daily_budget_paise = int(daily_budget_paise or 0)
    if bid_paise < MIN_BID_PAISE:
        return {"ok": False,
                "error": f"Bid must be at least ₹{MIN_BID_PAISE / 100:.2f} "
                         f"per placement."}
    if daily_budget_paise < bid_paise:
        return {"ok": False,
                "error": "Daily budget has to cover at least one placement."}

    ref = _doc(product_id)
    existing = ref.get()
    record = {
        "product_id": product_id,
        "product_name": product.get("name"),
        "bid_paise": bid_paise,
        "daily_budget_paise": daily_budget_paise,
        "active": bool(active),
        "merchant_id": store.MERCHANT_ID,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    if existing.exists:
        ref.update(record)
        merged = {**existing.to_dict(), **record}
    else:
        # Counters start on the document rather than being created lazily,
        # so a promotion that has never run reads as zeroes instead of as
        # missing keys the UI then has to guess at.
        record.update({"spend": {}, "considered": 0, "screened_out": 0,
                       "placed": 0, "chosen": 0,
                       "created_at": firestore.SERVER_TIMESTAMP})
        ref.set(record)
        merged = record

    return {"ok": True, "promotion": _shape(merged)}


def remove(product_id: str) -> bool:
    ref = _doc(product_id)
    if not ref.get().exists:
        return False
    ref.delete()
    return True


def get(product_id: str) -> dict | None:
    doc = _doc(product_id).get()
    return _shape(doc.to_dict()) if doc.exists else None


def list_all() -> list[dict]:
    return [_shape(d.to_dict()) for d in db.collection(PROMOTIONS).get()]


def eligible() -> list[dict]:
    """
    Promotions that may enter a search right now.

    Four things have to hold, and each is a reason a merchant would want to
    see: the promotion is on, today's budget still covers a placement, the
    product is active, and it is in stock. Promoting something unbuyable is
    a way to spend a budget on a card that the precision screen will drop
    anyway, so it is refused up front.
    """
    out = []
    for doc in db.collection(PROMOTIONS).get():
        promo = doc.to_dict() or {}
        if not promo.get("active"):
            continue
        bid = int(promo.get("bid_paise") or 0)
        budget = int(promo.get("daily_budget_paise") or 0)
        if bid <= 0 or _spent_today(promo) + bid > budget:
            continue
        product = store.get_product(promo.get("product_id") or "")
        if not product:
            continue
        if (product.get("status") or "active") != "active":
            continue
        if int(product.get("stock") or 0) <= 0:
            continue
        out.append({**promo, "product": product})

    # The auction, such as it is. Highest bid enters first when more want in
    # than MAX_PLACEMENTS allows — which decides who is CONSIDERED and
    # nothing further. Two promoted products that both survive the screens
    # are ranked against each other on merit, not on what they paid.
    out.sort(key=lambda p: -int(p.get("bid_paise") or 0))
    return out


def note_considered(product_ids) -> None:
    """A promoted product entered a search's candidate pool. Free."""
    for product_id in set(product_ids or []):
        try:
            _doc(product_id).update({"considered": firestore.Increment(1)})
        except Exception as exc:
            print(f"[promotions] could not count consideration for "
                  f"{product_id}: {exc}", flush=True)


def note_screened_out(product_id: str, stage: str) -> None:
    """
    A promoted product was dropped by the same screen that drops organic
    ones. Recorded, not charged: the merchant paid for consideration and the
    product did not survive it, which is the arrangement working.
    """
    try:
        _doc(product_id).update({
            "screened_out": firestore.Increment(1),
            "last_screened_out_stage": stage,
        })
    except Exception as exc:
        print(f"[promotions] could not count screen-out for "
              f"{product_id}: {exc}", flush=True)


def settle_placements(shown: list[dict], chosen_id: str = None,
                      customer_id: str = None) -> list[dict]:
    """
    Charge for the sponsored cards that actually reached the shopper.

    Called once, where results are emitted — not where they are ranked, so
    a promoted product that is considered and then dropped costs nothing.
    Returns what was charged so the caller can put it in the run's record.
    """
    charged = []
    for item in shown or []:
        if not item.get("sponsored"):
            continue
        product_id = item.get("id")
        doc = _doc(product_id).get()
        if not doc.exists:
            continue
        promo = doc.to_dict() or {}

        bid = int(promo.get("bid_paise") or 0)
        budget = int(promo.get("daily_budget_paise") or 0)
        remaining = max(0, budget - _spent_today(promo))
        # Eligibility already required room for a full bid, but a second
        # search can start before the first one settles. Charging the
        # remainder rather than the bid keeps the total inside the budget
        # the merchant set, which is the number they actually agreed to.
        amount = min(bid, remaining)
        if amount <= 0:
            continue

        was_chosen = product_id == chosen_id
        update = {
            f"spend.{_today()}": firestore.Increment(amount),
            "placed": firestore.Increment(1),
        }
        if was_chosen:
            update["chosen"] = firestore.Increment(1)
        try:
            _doc(product_id).update(update)
        except Exception as exc:
            print(f"[promotions] could not settle {product_id}: {exc}",
                  flush=True)
            continue

        # Every financial event in this project is written to the decision
        # log, including the ones no rail collects.
        log_decision(
            action_type="sponsored_placement",
            amount_paise=amount,
            decision="accrued",
            reason=(f"Sponsored placement for {promo.get('product_name')!r} "
                    f"shown to the shopper"
                    + (" and chosen on merit" if was_chosen else "")
                    + f". ₹{amount / 100:.2f} accrued against the merchant's "
                      f"₹{budget / 100:.2f} daily budget. Not billed — this "
                      f"build has no rail that charges a merchant."),
            customer_id=customer_id,
        )
        charged.append({"product_id": product_id, "amount_paise": amount,
                        "chosen": was_chosen, "billed": False})

    return charged


class PlacementRun:
    """
    Follows the promoted candidates through one search.

    The point of this class is that a merchant can see WHERE a placement
    died. "Considered 12, shown 3" invites the reading that the agent is
    arbitrary; "dropped at relevance" and "dropped at precision — reported
    out of stock" are answerable facts, and the second one is a bug in the
    merchant's own catalogue that they can go and fix.

    Nothing here decides anything. It watches a pipeline it cannot influence
    and writes down what that pipeline did.
    """

    def __init__(self, candidates: list[dict]):
        self.entered = {c.get("id") for c in candidates or [] if c.get("sponsored")}
        self.live = set(self.entered)
        self.fate: dict = {}

    def after(self, stage: str, candidates: list[dict]) -> None:
        still = {c.get("id") for c in candidates or [] if c.get("sponsored")}
        for gone in self.live - still:
            self.fate[gone] = stage
        self.live = still

    def settle(self, shown: list[dict], chosen_id: str = None,
               customer_id: str = None) -> dict:
        """Write down what happened, and charge only for what was shown."""
        shown_ids = {str(item.get("id")) for item in shown or []}
        for product_id, stage in self.fate.items():
            # A product dropped from the ranked answer and then offered in
            # the complement strip was not screened out of the shopper's
            # view — it is about to be charged for as a placement, and
            # counting it in both columns would make the two disagree.
            if str(product_id) in shown_ids:
                continue
            note_screened_out(product_id, stage)
        charged = settle_placements(shown, chosen_id, customer_id)
        return {
            "considered": len(self.entered),
            "screened_out": len(self.fate),
            "shown": len(charged),
            "stages": dict(self.fate),
            "charged": charged,
            "accrued_paise": sum(c["amount_paise"] for c in charged),
            # Said in the payload, not just in a docstring, so the surface
            # that renders this cannot imply an invoice that does not exist.
            "billed": False,
            "billing_note": ("Accrued against the merchant's daily budget. "
                             "No rail in this build charges a merchant."),
        }

    def __bool__(self) -> bool:
        return bool(self.entered)
