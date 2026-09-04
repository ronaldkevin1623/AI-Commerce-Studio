"""
WHICH PAYMENT RAILS ACTUALLY WORK ON THIS ACCOUNT, AND HOW WE KNOW.

When a payment fails, the useful next question is not "shall I try again" but
"is there any way for this to succeed". An agent that retries the same dead
rail three times is not persistent, it is stuck — and on somebody's real
card, three attempts is three attempts.

So this resolves the rails from EVIDENCE rather than from a config file: it
reads what this Razorpay account has actually done. A rail that has captured
money works. A rail that has only ever failed, with the same error every
time, does not — and the error text is quoted rather than paraphrased.

THE ANSWER THIS PROJECT HAS TO GIVE HONESTLY

"Try every method and complete the payment" is what a merchant wants to
hear, and on this account no agent can deliver it. Cards are rejected before
they reach a bank; UPI is not enabled; netbanking completes, and netbanking
puts a human on a bank page by design. So the honest capability is:

    the agent enumerates the rails, says which are dead and why, resolves to
    the one that can complete, and hands over at the point where a person is
    genuinely required.

That is a smaller claim than "the agent pays" and it is the true one. It is
also the more interesting one: knowing which door is locked before pulling
the handle is most of what separates an agent from a retry loop.
"""
import collections

# The rails this integration would use, in the order an agent should try
# them: cheapest and least friction first. Presence here is not a claim that
# any of them works — that is decided below, by what the account has done.
KNOWN = [
    ("upi", "UPI"),
    ("card", "Card"),
    ("netbanking", "Netbanking"),
    ("wallet", "Wallet"),
]

# Netbanking completes, but only with somebody on the bank's own page. No
# rail on this account can be driven end to end by an agent alone, and the
# payload says so rather than letting "usable" be read as "automatic".
NEEDS_A_PERSON = {"netbanking", "card", "upi", "wallet"}


def status() -> dict:
    """Every rail, its verdict, and the evidence behind the verdict."""
    try:
        from app.razorpay_client import client
        payments = client.payment.all({"count": 100}).get("items", [])
    except Exception as exc:
        return {
            "rails": [],
            "resolved": None,
            "note": (f"Razorpay could not be reached, so no rail can be "
                     f"verified from history right now: {exc}"),
            "reachable": False,
        }

    attempts = collections.defaultdict(list)
    for payment in payments:
        attempts[(payment.get("method") or "unknown").lower()].append(payment)

    rails = []
    for key, label in KNOWN:
        rows = attempts.get(key, [])
        captured = [p for p in rows if p.get("status") in ("captured", "refunded")]
        failed = [p for p in rows if p.get("status") == "failed"]

        if captured:
            verdict, headline = "works", (
                f"{len(captured)} payment{'' if len(captured) == 1 else 's'} "
                f"captured on this rail")
        elif failed:
            verdict, headline = "rejected", (
                f"{len(failed)} attempt{'' if len(failed) == 1 else 's'}, "
                f"none captured")
        else:
            verdict, headline = "untried", "never attempted on this account"

        # Quoted, not paraphrased. The reason a card fails here is the
        # account's own configuration, and Razorpay says it better than a
        # summary would.
        reason = ""
        if failed:
            reason = str(failed[0].get("error_description") or "").strip()

        rails.append({
            "key": key,
            "label": label,
            "verdict": verdict,
            "headline": headline,
            "attempts": len(rows),
            "captured": len(captured),
            "failed": len(failed),
            "error": reason,
            "needs_a_person": key in NEEDS_A_PERSON,
        })

    working = [r for r in rails if r["verdict"] == "works"]
    resolved = working[0] if working else None

    if resolved:
        note = (
            f"{resolved['label']} is the only rail with a capture behind it, "
            f"so it is the one to use. It still needs a person at the bank "
            f"page — no rail on this account completes unattended, and the "
            f"agent hands over there rather than pretending otherwise."
            if len(working) == 1 else
            f"{len(working)} rails have captured money on this account."
        )
    else:
        note = ("No rail on this account has ever captured a payment. There "
                "is nothing to fall back to.")

    return {
        "rails": rails,
        "resolved": resolved,
        "reachable": True,
        "payments_read": len(payments),
        "note": note,
        # The sentence that stops "resolved" being read as "automated".
        "disclosure": ("Read from this Razorpay account's own payment "
                       "history, not from a configuration file. A rail is "
                       "'works' only if money has actually been captured on "
                       "it."),
    }
