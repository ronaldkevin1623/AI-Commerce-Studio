import { useCallback, useState } from "react";

import { API_BASE, RAZORPAY_KEY_ID } from "../config";

/**
 * "TRY AGAIN" THAT ACTUALLY TRIES AGAIN.
 *
 * The first version of this authorised a retry and then stopped — it logged
 * the decision, resolved the rails, and left the person looking at a card
 * that said "fresh attempt authorised" with no attempt anywhere. That is the
 * worst kind of button: one that reports success for having done nothing.
 *
 * This does the whole thing:
 *
 *     1. authorise   log it, and re-resolve which rail can complete
 *     2. re-order    a FRESH Razorpay order through /repick-order, which
 *                    runs the same risk gate the original purchase did
 *     3. pay         open Razorpay on the rail that actually works
 *     4. settle      verify with Razorpay, or record the new failure
 *
 * Step 2 is the important one for the claim this project makes. It is not a
 * resumption of the payment that failed and it is not a replay of an
 * authorisation: it is a new purchase attempt, gated and logged from the
 * top, exactly like the first. The agent still cannot do any of it on its
 * own — a person clicked, and a person will finish it at the bank page.
 */
export function useRetryCheckout({ onPaid, onFailed, onAuthorised } = {}) {
    const [busy, setBusy] = useState("");
    const [error, setError] = useState(null);

    const retry = useCallback(async (purchase) => {
        setBusy(purchase.id);
        setError(null);
        try {
            // 1. Authorise, and find out which rail can complete.
            const authRes = await fetch(`${API_BASE}/payment-retry`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    purchase_id: purchase.id,
                    razorpay_order_id: purchase.razorpay_order_id,
                    amount_paise: purchase.amount_paise,
                    customer_id: purchase.customer_id,
                }),
            });
            if (!authRes.ok) throw new Error(`Retry refused (${authRes.status})`);
            const authorised = await authRes.json();
            onAuthorised?.({ ...authorised, product: purchase.product });

            // 2. A fresh, separately gated order for the same item.
            const orderRes = await fetch(`${API_BASE}/repick-order`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    product: {
                        id: purchase.product?.id,
                        name: purchase.product?.name,
                        price_paise: purchase.product?.price_paise ?? purchase.amount_paise,
                        image: purchase.product?.image,
                        source: purchase.product?.source,
                        url: purchase.product?.url,
                    },
                }),
            });
            if (!orderRes.ok) {
                // A 403 here is the gate refusing the retry, which is a
                // legitimate answer and must be shown as one rather than
                // swallowed into "something went wrong".
                const detail = await orderRes.json().catch(() => ({}));
                throw new Error(detail.detail || `The gate refused this attempt (${orderRes.status})`);
            }
            const order = await orderRes.json();

            if (!window.Razorpay) {
                throw new Error("Razorpay Checkout did not load, so nothing was charged.");
            }

            // 3. Pay, on the rail the resolution picked.
            //
            // Razorpay only narrows the sheet if the OTHER methods are
            // explicitly switched off — setting one to true does nothing on
            // its own, which is why the first version of this opened on the
            // full list. So the rails this account is known to reject are
            // turned off by name, and everything unproven is left on.
            //
            // The distinction matters: hiding a door we have watched fail
            // four times is helpful; hiding one that merely has no history
            // behind it would be this screen deciding something it has no
            // evidence for.
            const rail = authorised?.resolved?.key;
            const method = {};
            for (const r of authorised?.rails ?? []) {
                if (r.verdict === "rejected") method[r.key] = false;
            }
            if (rail) method[rail] = true;
            const checkout = new window.Razorpay({
                key: RAZORPAY_KEY_ID,
                amount: order.amount_paise,
                currency: "INR",
                name: "AI Commerce Studio",
                description: order.product_name,
                order_id: order.razorpay_order_id,
                // Opened straight onto the rail that has captures behind it.
                // Not a restriction — the other methods are still there — but
                // sending someone back to the card that just failed would be
                // a strange thing for a retry to do.
                ...(Object.keys(method).length ? { method } : {}),
                handler: async (response) => {
                    try {
                        const verify = await fetch(`${API_BASE}/verify-payment`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                razorpay_payment_id: response.razorpay_payment_id,
                                razorpay_order_id: response.razorpay_order_id,
                                customer_id: order.customer_id,
                            }),
                        });
                        // The original leaves the queue now, and not a
                        // moment earlier: it is closed because it was paid,
                        // which is a fact rather than an intention.
                        if (verify.ok) {
                            await fetch(`${API_BASE}/failed-purchases/${purchase.id}/close`, {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                    outcome: "paid",
                                    note: `Retried and paid as ${response.razorpay_payment_id}.`,
                                }),
                            }).catch(() => {});
                        }
                        onPaid?.({
                            ok: verify.ok,
                            product: purchase.product,
                            amount_paise: order.amount_paise,
                            payment_id: response.razorpay_payment_id,
                            order_id: response.razorpay_order_id,
                        });
                    } catch (err) {
                        setError(String(err.message ?? err));
                    } finally {
                        setBusy("");
                    }
                },
                modal: {
                    // Closing the sheet is an abandonment, not a failure, and
                    // conflating the two would put an item back on the queue
                    // that nobody actually failed to pay for.
                    ondismiss: () => setBusy(""),
                },
                theme: { color: "#ECECEE" },
            });

            checkout.on("payment.failed", async (event) => {
                const failure = event?.error ?? {};
                try {
                    const res = await fetch(`${API_BASE}/payment-failure`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            razorpay_order_id: order.razorpay_order_id,
                            amount_paise: order.amount_paise,
                            customer_id: order.customer_id,
                            product: purchase.product,
                            error: {
                                code: failure.code, description: failure.description,
                                reason: failure.reason, step: failure.step,
                                source: failure.source,
                            },
                        }),
                    });
                    if (res.ok) {
                        // The new failure record supersedes the old one —
                        // otherwise the same item sits on the queue twice
                        // with two different reasons.
                        await fetch(`${API_BASE}/failed-purchases/${purchase.id}/close`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                outcome: "retried",
                                note: "Retried; the attempt failed again and is recorded separately.",
                            }),
                        }).catch(() => {});
                        onFailed?.(await res.json());
                    }
                } catch {
                    /* the failure still happened; the screen must not break */
                } finally {
                    setBusy("");
                }
            });

            checkout.open();
        } catch (err) {
            setError(String(err.message ?? err));
            setBusy("");
        }
    }, [onAuthorised, onFailed, onPaid]);

    return { retry, busy, error };
}
