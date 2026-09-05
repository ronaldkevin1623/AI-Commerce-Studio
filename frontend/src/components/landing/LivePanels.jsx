import { useEffect, useState } from "react";
import { Box, Stack, Typography } from "@mui/material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlineOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";

import { API_BASE } from "../../config";
import { Counter, Item, Stagger } from "./motion";

/**
 * THE PANELS THAT SHOW REAL NUMBERS.
 *
 * A landing page for a commerce product is the single most tempting place
 * in a codebase to write "₹4.82L" into a mockup, and every product page on
 * the internet has done it. This one reads the live endpoints the product
 * actually serves — `/merchant/analytics` and `/transaction-policy` — so the
 * dashboard preview is the dashboard.
 *
 * When the backend is not running, the labels stay and the figures become
 * em dashes with a line saying why. That is a worse-looking screenshot and
 * the only defensible behaviour: a placeholder number on a marketing page is
 * indistinguishable from a claim, and this project's whole argument is that
 * it does not make claims it cannot show you the source of.
 */

const ACCENT = "#4F8DF7";

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

export function Surface({ children, sx, label }) {
  return (
    <Box
      sx={{
        position: "relative",
        border: "1px solid rgba(255,255,255,0.09)",
        bgcolor: "rgba(255,255,255,0.018)",
        backdropFilter: "blur(8px)",
        borderRadius: 2,
        overflow: "hidden",
        ...sx,
      }}
    >
      {label && (
        <Stack direction="row" spacing={1}
               sx={{ alignItems: "center", px: 2, py: 1.25,
                     borderBottom: "1px solid rgba(255,255,255,0.07)" }}>
          <Box sx={{ display: "flex", gap: 0.6 }}>
            {["#F85149", "#D29922", "#3FB950"].map((c) => (
              <Box key={c} sx={{ width: 7, height: 7, borderRadius: "50%",
                                 bgcolor: c, opacity: 0.5 }} />
            ))}
          </Box>
          <Typography sx={{ fontSize: 11, color: "#8E8E96", letterSpacing: "0.02em" }}>
            {label}
          </Typography>
        </Stack>
      )}
      {children}
    </Box>
  );
}

/** The merchant command centre preview, from `/merchant/analytics`. */
export function CommandCentre() {
  const [data, setData] = useState(null);
  const [reachable, setReachable] = useState(true);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/merchant/analytics?days=30`);
        if (!res.ok) throw new Error();
        if (live) setData(await res.json());
      } catch {
        if (live) setReachable(false);
      }
    })();
    return () => { live = false; };
  }, []);

  const kpis = Object.fromEntries((data?.kpis ?? []).map((k) => [k.key, k]));
  const tiles = [
    { label: "Total sales", value: kpis.total_sales?.value,
      format: (n) => inr(n), delta: kpis.total_sales?.delta_pct },
    { label: "Orders", value: kpis.orders?.value,
      format: (n) => String(Math.round(n)), delta: kpis.orders?.delta_pct },
    { label: "Average order value", value: kpis.aov?.value,
      format: (n) => inr(n), delta: kpis.aov?.delta_pct },
    { label: "Returning customers", value: kpis.returning?.value,
      format: (n) => `${n.toFixed(0)}%`, delta: null },
  ];

  return (
    <Surface label="merchant analytics">
      <Box sx={{ p: { xs: 2, sm: 2.5 } }}>
        <Stagger step={0.06}>
          <Box sx={{ display: "grid", gap: 1.5,
                     gridTemplateColumns: { xs: "1fr 1fr", sm: "repeat(4, 1fr)" } }}>
            {tiles.map((tile) => (
              <Item key={tile.label}>
                <Box sx={{ px: 1.5, py: 1.4, borderRadius: 1.5,
                           border: "1px solid rgba(255,255,255,0.07)",
                           bgcolor: "rgba(255,255,255,0.02)" }}>
                  <Typography sx={{ fontSize: 10.5, color: "#8E8E96", mb: 0.5 }}>
                    {tile.label}
                  </Typography>
                  <Typography sx={{ fontSize: 19, fontWeight: 650, lineHeight: 1.1,
                                    letterSpacing: "-0.02em", color: "#ECECEE",
                                    fontVariantNumeric: "tabular-nums" }}>
                    <Counter value={tile.value ?? null} format={tile.format} />
                  </Typography>
                  <Typography sx={{ fontSize: 10.5, mt: 0.35,
                                    color: tile.delta == null ? "#5A5A62"
                                      : tile.delta >= 0 ? "#3FB950" : "#F85149" }}>
                    {tile.delta == null ? "—"
                      : `${tile.delta >= 0 ? "↑" : "↓"} ${Math.abs(tile.delta)}%`}
                  </Typography>
                </Box>
              </Item>
            ))}
          </Box>
        </Stagger>

        <Typography sx={{ fontSize: 10.5, color: "#5A5A62", mt: 1.5, lineHeight: 1.6 }}>
          {reachable
            ? "Live from this build's own analytics endpoint, over the last 30 days, "
              + "against the window before it. Not a mockup."
            : "The analytics endpoint is not reachable from here, so these are "
              + "empty rather than filled in with example figures."}
        </Typography>
      </Box>
    </Surface>
  );
}

/**
 * The gate, from `/transaction-policy`.
 *
 * The worked example uses the REAL spending bound, so the "within policy"
 * tick is arithmetic rather than a caption. If somebody moves the limit, the
 * example moves with it.
 */
export function PolicyTrace() {
  const [limitPaise, setLimitPaise] = useState(null);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/transaction-policy`);
        if (!res.ok) throw new Error();
        const data = await res.json();
        const bound = (data.bounds ?? []).find((b) => b.key === "max_transaction_inr");
        if (live && bound) setLimitPaise(bound.value * 100);
      } catch {
        /* the row renders without a figure rather than with a made-up one */
      }
    })();
    return () => { live = false; };
  }, []);

  const amount = 279900;
  const within = limitPaise != null && amount <= limitPaise;

  const steps = [
    { k: "Intent", v: "Running shoes, black, size 9, under ₹3,000", tone: "plain" },
    { k: "Agent decision", v: "Best match at ₹2,799 — ₹201 under the stated ceiling", tone: "plain" },
    { k: "Policy check", v: limitPaise == null
        ? "Reading the live spending bound…"
        : `₹2,799 against a ₹${(limitPaise / 100).toLocaleString("en-IN")} bound`,
      tone: within ? "ok" : limitPaise == null ? "plain" : "warn" },
    { k: "Human approval", v: within
        ? "Not required below the bound — and the agent cannot clear its own escalation"
        : "Required — the agent cannot clear its own escalation", tone: "gate" },
    { k: "Payment", v: "Authorised through Razorpay, one attempt per decision", tone: "plain" },
    { k: "Audit event", v: "Written with the reason verbatim, refusals included", tone: "ok" },
  ];

  return (
    <Surface label="gate trace">
      <Stagger step={0.08}>
        <Box>
          {steps.map((step, i) => (
            <Item key={step.k}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={{ xs: 0.35, sm: 2 }}
                     sx={{ px: 2, py: 1.35,
                           borderTop: i === 0 ? "none" : "1px solid rgba(255,255,255,0.055)",
                           alignItems: { sm: "baseline" } }}>
                <Typography sx={{ fontSize: 11, color: "#8E8E96", width: { sm: 128 },
                                  flexShrink: 0, letterSpacing: "0.01em" }}>
                  {step.k}
                </Typography>
                <Stack direction="row" spacing={0.85} sx={{ alignItems: "center", minWidth: 0 }}>
                  {step.tone === "ok" && (
                    <CheckCircleOutlineIcon sx={{ fontSize: 14, color: "#3FB950", flexShrink: 0 }} />
                  )}
                  {step.tone === "gate" && (
                    <LockOutlinedIcon sx={{ fontSize: 13, color: ACCENT, flexShrink: 0 }} />
                  )}
                  <Typography sx={{ fontSize: 12.5, lineHeight: 1.55,
                                    color: step.tone === "plain" ? "#ECECEE" : "#ECECEE" }}>
                    {step.v}
                  </Typography>
                </Stack>
              </Stack>
            </Item>
          ))}
        </Box>
      </Stagger>
      <Typography sx={{ fontSize: 10.5, color: "#5A5A62", px: 2, pb: 1.75, pt: 1,
                        lineHeight: 1.6 }}>
        The bound in the policy check is read live from this build. Change it
        and this example changes with it.
      </Typography>
    </Surface>
  );
}

/**
 * The buyer conversation. Scripted copy, real product shape — and it says so.
 *
 * Driven by ONE observer on the container rather than one per turn. Seven
 * separate `whileInView` elements inside a panel is both seven observers to
 * pay for and a reliability problem: the last turns were reaching opacity 0
 * and staying there, because an observer registered against an element whose
 * ancestor is still animating does not always fire. A single stagger cannot
 * have that bug, and it is the cheaper implementation anyway.
 */
export function BuyerChat() {
  const turns = [
    { who: "user", text: "Find me black running shoes, size 9, under ₹3,000." },
    { who: "agent", text: "Three match. Two were set aside — one was an accessory, one had a foreign-card-only seller." },
    { who: "cards" },
    { who: "user", text: "I prefer the best value." },
    { who: "agent", text: "The second: best price against rating, and it clears your ceiling by ₹201. Proceed to checkout?" },
    { who: "user", text: "Yes." },
    { who: "agent", text: "Gated, signed, and handed to Razorpay. You finish at the bank page — that step is yours, not mine.", tone: "ok" },
  ];

  return (
    <Surface label="ai buyer">
      <Stagger step={0.09}>
        <Stack spacing={1.5} sx={{ p: { xs: 2, sm: 2.5 } }}>
          {turns.map((turn, i) => {
            if (turn.who === "cards") {
              return (
                <Item key="cards">
                  <Box sx={{ display: "grid", gap: 1,
                             gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" } }}>
                    {[
                      { n: "Trail Runner GT", p: "₹2,940", r: "4.3 · 210" },
                      { n: "Velocity Lite 2", p: "₹2,799", r: "4.6 · 388", best: true },
                      { n: "Standard Road 5", p: "₹2,650", r: "3.9 · 74" },
                    ].map((card) => (
                      <Box key={card.n}
                           sx={{ p: 1.35, borderRadius: 1.5, border: "1px solid",
                                 borderColor: card.best ? "rgba(79,141,247,0.4)" : "rgba(255,255,255,0.08)",
                                 bgcolor: card.best ? "rgba(79,141,247,0.06)" : "rgba(255,255,255,0.02)" }}>
                        <Typography sx={{ fontSize: 11.5, fontWeight: 600, color: "#ECECEE" }}>
                          {card.n}
                        </Typography>
                        <Typography sx={{ fontSize: 13, fontWeight: 700, mt: 0.3,
                                          color: card.best ? ACCENT : "#ECECEE" }}>
                          {card.p}
                        </Typography>
                        <Typography sx={{ fontSize: 10, color: "#8E8E96", mt: 0.2 }}>
                          {card.r}
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                </Item>
              );
            }
            const mine = turn.who === "user";
            return (
              <Item key={i} style={{ alignSelf: mine ? "flex-end" : "flex-start",
                                     maxWidth: "84%" }}>
                <Box sx={{
                  px: 1.6, py: 1.1, borderRadius: 1.5,
                  border: "1px solid",
                  borderColor: mine ? "rgba(255,255,255,0.12)"
                    : turn.tone === "ok" ? "rgba(63,185,80,0.3)" : "rgba(255,255,255,0.07)",
                  bgcolor: mine ? "rgba(255,255,255,0.05)"
                    : turn.tone === "ok" ? "rgba(63,185,80,0.06)" : "rgba(255,255,255,0.02)",
                }}>
                  <Typography sx={{ fontSize: 12.5, lineHeight: 1.6, color: "#ECECEE" }}>
                    {turn.text}
                  </Typography>
                </Box>
              </Item>
            );
          })}
        </Stack>
      </Stagger>
      <Typography sx={{ fontSize: 10.5, color: "#5A5A62", px: 2.5, pb: 2, lineHeight: 1.6 }}>
        An illustration of the flow. The console runs the same shape against
        live marketplace listings — this one is written out so it reads in
        one pass.
      </Typography>
    </Surface>
  );
}
