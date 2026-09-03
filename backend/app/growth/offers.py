"""
TESTS DISCOUNTS — AND REFUSES TO CALL A COIN FLIP A RESULT.

An A/B test on a store with three orders is not an experiment, it is a
coincidence with a percentage sign. This agent runs the test honestly and,
crucially, reports what it does NOT yet know.

HOW IT WORKS

Offers already applied by the other growth agents carry a discount level.
This reads what happened to them — did the cart they were attached to get
paid — and groups the outcomes by level. Two things come out:

  a proposal   try the level that is winning, on a cart that has none
  a verdict    whether the difference between levels means anything yet

WHY THE SECOND MATTERS MORE

The obvious version of this feature reports "12% converts 40% better" from
five carts and lets a merchant believe it. The difference between two arms
of five is noise, and acting on it is how a store gives away margin it did
not need to.

So significance is computed and stated in words rather than implied by a
confident number. Below the threshold, the honest output is "not enough to
tell them apart yet", and the proposal that goes with it says so — the gate
then escalates it anyway on the evidence floor, which is the same rule
applied twice on purpose.

WHAT THIS IS NOT

Not a bandit, not a bayesian optimiser. Those need traffic this store does
not have, and a demo that ships one is showing arithmetic on imaginary
volume. This is a counter, a comparison, and an honest label.
"""
import collections

from app.growth.base import Proposal

AGENT_ID = "offers"

# Below this many outcomes in an arm, no comparison is worth making. It is
# not a p-value — with numbers this small a p-value would itself be
# theatre. It is a floor under which the agent declines to have an opinion.
MIN_PER_ARM = 5

# The gap two arms must show before the difference is called anything other
# than noise, once both are above the floor.
MEANINGFUL_GAP_PCT = 15


class DiscountExperimentAgent:
    agent_id = AGENT_ID
    name = "Tests discounts"
    what = ("Groups applied offers by discount level and compares how many "
            "converted. Reports whether the difference means anything yet "
            "instead of ranking levels on a handful of outcomes.")
    spends_margin = True

    def detect(self) -> list[dict]:
        """Outcomes of offers already applied, grouped by discount level."""
        try:
            from app.firebase_client import db
            from app.merchant import store
            offers = [d.to_dict() or {}
                      for d in db.collection("growth_offers").stream()]
            sessions = {s.get("id"): s for s in
                        [d.to_dict() or {}
                         for d in store.db.collection(store.SESSIONS).stream()]}
        except Exception as exc:
            print(f"[growth] discount test could not read data: {exc}", flush=True)
            return []

        arms = collections.defaultdict(lambda: {"shown": 0, "converted": 0})
        for offer in offers:
            if offer.get("kind") != "recover_cart":
                continue
            level = int((offer.get("params") or {}).get("discount_pct") or 0)
            session = sessions.get(offer.get("target_id")) or {}
            arms[level]["shown"] += 1
            if (session.get("status") or "") == "paid":
                arms[level]["converted"] += 1

        return [{"arms": dict(arms)}]

    def propose(self, signals: list[dict]) -> list[Proposal]:
        if not signals:
            return []
        arms = signals[0]["arms"]
        if not arms:
            return []

        total = sum(a["shown"] for a in arms.values())
        ranked = sorted(
            ((level, a) for level, a in arms.items() if a["shown"]),
            key=lambda kv: -(kv[1]["converted"] / kv[1]["shown"]))
        if not ranked:
            return []

        best_level, best = ranked[0]
        best_rate = best["converted"] / best["shown"] * 100
        readable, verdict = self._read(ranked, total)

        lines = [f"{level}% off — {a['converted']} of {a['shown']} paid"
                 for level, a in ranked]

        return [Proposal(
            agent=AGENT_ID,
            kind="test_discount",
            headline=(f"Discount levels so far: {readable}"),
            detail=(
                "Outcomes of recovery offers already applied, grouped by the "
                "level they carried:\n  " + "\n  ".join(lines)
                + f"\n\n{verdict}"),
            # Reporting costs nothing. Acting on the result is a separate
            # proposal the recovery agent makes, and that one is priced.
            cost_paise=0,
            target_kind="experiment",
            target_id="discount_levels",
            sample_size=total,
            evidence_note=(
                f"{total} applied offer{'s' if total != 1 else ''} across "
                f"{len(ranked)} level{'s' if len(ranked) != 1 else ''}. "
                + (f"At least {MIN_PER_ARM} per level are needed before the "
                   f"comparison is worth reading."
                   if any(a["shown"] < MIN_PER_ARM for _, a in ranked)
                   else "Every level is above the reporting floor.")),
            params={"best_level_pct": best_level,
                    "best_rate_pct": round(best_rate, 1),
                    "conclusive": verdict.startswith("Enough")},
        )]

    def _read(self, ranked: list, total: int) -> tuple:
        """Turn the arms into a sentence that does not overclaim."""
        thin = [f"{level}%" for level, a in ranked if a["shown"] < MIN_PER_ARM]
        if thin:
            return (
                "not enough data to compare",
                f"NOT A RESULT YET. {', '.join(thin)} "
                f"{'has' if len(thin) == 1 else 'have'} fewer than "
                f"{MIN_PER_ARM} outcomes, so the levels cannot be told apart. "
                f"Any ranking at this size is noise with a percentage sign on "
                f"it, and nothing here should be acted on as a preference.")

        best_level, best = ranked[0]
        worst_level, worst = ranked[-1]
        gap = (best["converted"] / best["shown"]
               - worst["converted"] / worst["shown"]) * 100
        if len(ranked) < 2:
            return ("one level tested so far",
                    "Only one discount level has been used, so there is "
                    "nothing to compare it against.")
        if gap < MEANINGFUL_GAP_PCT:
            return (
                "levels look the same so far",
                f"NOT SEPARABLE. {best_level}% and {worst_level}% differ by "
                f"{gap:.0f} points, under the {MEANINGFUL_GAP_PCT}-point gap "
                f"this treats as meaningful at these volumes. Prefer the "
                f"cheaper level: it costs less margin for the same outcome.")
        return (
            f"{best_level}% is ahead",
            f"Enough separation to act on: {best_level}% converted "
            f"{best['converted']}/{best['shown']} against {worst_level}% at "
            f"{worst['converted']}/{worst['shown']}, a {gap:.0f}-point gap.")
