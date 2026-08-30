import { useEffect, useState } from "react";
import { Box, Stack, Typography } from "@mui/material";

import PageBanner from "../components/shared/PageBanner";
import LoadingState from "../components/shared/LoadingState";
import ChartCard from "../components/growth/ChartCard";
import { BarChart, HBarChart, Legend, SERIES } from "../components/growth/charts";

import { API_BASE } from "../config";

const rupees = (paise) => `₹${Math.round((paise ?? 0) / 100).toLocaleString("en-IN")}`;

const NOTE_TONE = {
  blocked: { color: "#EF4444", bg: "rgba(239,68,68,0.07)", border: "rgba(239,68,68,0.25)" },
  warn: { color: "#F59E0B", bg: "rgba(245,158,11,0.07)", border: "rgba(245,158,11,0.25)" },
  thin: { color: "#9AA3B2", bg: "rgba(255,255,255,0.03)", border: "rgba(255,255,255,0.10)" },
  ok: { color: "#22C55E", bg: "rgba(34,197,94,0.06)", border: "rgba(34,197,94,0.20)" },
};

/**
 * A headline number. Proportional figures, not tabular — equal-width digits
 * make a large standalone number look loose.
 */
function StatTile({ label, value, sub, tone }) {
  return (
    <Box
      sx={{
        p: 2,
        borderRadius: 2.5,
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
        // A tinted rule where the number carries a verdict, nothing where it
        // is just a count — so the eye lands on the one that matters.
        borderTop: "2px solid",
        borderTopColor: tone ?? "divider",
      }}
    >
      <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 0.75 }}>
        {label}
      </Typography>
      <Typography
        sx={{
          fontSize: 26,
          fontWeight: 700,
          lineHeight: 1.1,
          letterSpacing: "-0.015em",
          fontVariantNumeric: "tabular-nums",
          color: tone ?? "text.primary",
        }}
      >
        {value}
      </Typography>
      <Typography variant="caption" sx={{ color: "text.disabled", display: "block", mt: 0.5 }}>
        {sub}
      </Typography>
    </Box>
  );
}

function SectionTitle({ children, sub }) {
  return (
    <Box sx={{ mb: 2, mt: 4 }}>
      <Typography variant="overline" sx={{ letterSpacing: 1, color: "text.secondary" }}>
        {children}
      </Typography>
      {sub && (
        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 0.25 }}>
          {sub}
        </Typography>
      )}
    </Box>
  );
}

export default function MerchantPage() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/growth-insights`);
        if (!res.ok) throw new Error("bad status");
        const json = await res.json();
        if (live) {
          setData(json);
          setStatus("ready");
        }
      } catch {
        if (live) setStatus("error");
      }
    })();
    return () => {
      live = false;
    };
  }, []);

  if (status === "loading") {
    return (
      <Box>
        <PageBanner title="Storefront analytics" subtitle="Loading…" />
        <Box sx={{ maxWidth: 1000, mx: "auto", px: 3, py: 4 }}>
          <LoadingState label="Reading Firestore" />
        </Box>
      </Box>
    );
  }

  if (status === "error") {
    return (
      <Box>
        <PageBanner title="Storefront analytics" subtitle="Couldn't load insights" />
        <Box sx={{ maxWidth: 1000, mx: "auto", px: 3, py: 4 }}>
          <Typography variant="body2" sx={{ color: "error.main" }}>
            Couldn't reach /growth-insights. Check that uvicorn is running on port 8000.
          </Typography>
        </Box>
      </Box>
    );
  }

  const { summary, funnel, daily, block_reasons, abandon_stages, market, notes } = data;
  const enough = market.enough_data;

  const dailySeries = [
    { key: "attempts", name: "Purchase attempts" },
    { key: "abandoned", name: "Abandoned by the person" },
  ];

  return (
    <Box>
      <PageBanner
        title="Storefront analytics"
        subtitle="Every figure here is computed from decisions, orders and searches already logged in Firestore. Nothing is estimated or projected."
      />

      <Box sx={{ maxWidth: 1000, mx: "auto", px: 3, py: 4 }}>
        {/* ── Headline ─────────────────────────────────────────────── */}
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" },
            gap: 2,
          }}
        >
          <StatTile
            label="Order value created"
            value={rupees(summary.order_value_paise)}
            sub={`${summary.orders} Razorpay orders`}
          />
          <StatTile
            label="Revenue captured"
            value={rupees(summary.captured_paise)}
            sub={`${summary.orders_paid} of ${summary.orders} paid`}
            tone={summary.captured_paise ? "#22C55E" : "#EF4444"}
          />
          <StatTile
            label="Abandonment rate"
            value={summary.abandonment_rate != null ? `${summary.abandonment_rate}%` : "—"}
            sub={`${summary.abandoned} runs ended by the person`}
            tone={summary.abandonment_rate >= 25 ? "#F59E0B" : undefined}
          />
          <StatTile
            label="Listings seen"
            value={market.listings_seen.toLocaleString("en-IN")}
            sub={`across ${market.scans} searches`}
          />
        </Box>

        {/* ── What the numbers say ─────────────────────────────────── */}
        <SectionTitle>Read of the data</SectionTitle>
        <Stack spacing={1.25}>
          {notes.map((note, i) => {
            const tone = NOTE_TONE[note.tone] ?? NOTE_TONE.ok;
            return (
              <Box
                key={i}
                sx={{
                  p: 1.75,
                  borderRadius: 2,
                  bgcolor: tone.bg,
                  border: "1px solid",
                  borderColor: tone.border,
                  borderLeft: "3px solid",
                  borderLeftColor: tone.border,
                }}
              >
                {note.headline && (
                  <Typography
                    variant="body2"
                    sx={{ fontWeight: 600, fontSize: 13.5, mb: 0.5, color: "text.primary" }}
                  >
                    {note.headline}
                  </Typography>
                )}
                <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.65,
                                                  fontSize: 13 }}>
                  {note.text}
                </Typography>
              </Box>
            );
          })}
        </Stack>

        {/* ── Funnel ───────────────────────────────────────────────── */}
        <SectionTitle sub="Each step counts real logged rows, not a modelled drop-off.">
          Where runs end up
        </SectionTitle>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
          <ChartCard
            title="Purchase funnel"
            columns={["Stage", "Count"]}
            rows={funnel.map((f) => [f.stage, f.count])}
          >
            <HBarChart
              rows={funnel.map((f) => ({
                label: f.stage,
                value: f.count,
                // The terminal step is a status, not a series: zero captures
                // is the finding, so it gets the status colour and a label.
                color: f.stage === "Payments captured" && f.count === 0 ? "#EF4444" : SERIES[0],
              }))}
              labelWidth={132}
            />
          </ChartCard>

          <ChartCard
            title="Where people abandoned"
            columns={["Stage", "Runs"]}
            rows={abandon_stages.map((a) => [a.stage, a.count])}
            sample={summary.abandoned}
          >
            {abandon_stages.length ? (
              <HBarChart
                rows={abandon_stages.map((a) => ({ label: a.stage, value: a.count }))}
                labelWidth={132}
              />
            ) : (
              <Typography variant="caption" color="text.secondary">
                No abandonments logged yet.
              </Typography>
            )}
          </ChartCard>
        </Box>

        {block_reasons.length > 0 && (
          <Box sx={{ mt: 2 }}>
            <ChartCard
              title="Why the gate blocked a purchase"
              columns={["Reason", "Count"]}
              rows={block_reasons.map((b) => [b.reason, b.count])}
              sample={summary.blocked}
            >
              <HBarChart
                rows={block_reasons.map((b) => ({ label: b.reason, value: b.count, color: "#EF4444" }))}
                labelWidth={280}
              />
            </ChartCard>
          </Box>
        )}

        {/* ── Activity ─────────────────────────────────────────────── */}
        <SectionTitle sub="Configuration changes are logged separately and excluded — tuning the hive isn't commerce.">
          Activity by day
        </SectionTitle>
        <ChartCard
          title="Purchase attempts and abandonments"
          columns={["Day", "Attempts", "Abandoned", "Orders"]}
          rows={daily.map((d) => [d.day, d.attempts, d.abandoned, d.orders])}
        >
          <Legend series={dailySeries} />
          <BarChart
            data={daily.map((d) => ({
              label: d.day.slice(5),
              attempts: d.attempts,
              abandoned: d.abandoned,
            }))}
            series={dailySeries}
          />
        </ChartCard>

        {/* ── Market ───────────────────────────────────────────────── */}
        <SectionTitle
          sub={
            enough
              ? `Real eBay listings AI Commerce Studio has actually seen — the whole result set of every search, not just the item bought.`
              : `Needs at least ${data.min_sample} observed listings.`
          }
        >
          Prices and discounts in the market
        </SectionTitle>

        {enough ? (
          <>
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" },
                gap: 2,
                mb: 2,
              }}
            >
              <StatTile
                label="Median asking price"
                value={rupees(market.price_paise.median)}
                sub={`${rupees(market.price_paise.p25)} – ${rupees(market.price_paise.p75)} middle half`}
              />
              <StatTile
                label="Listings discounted"
                value={`${market.discounted_share}%`}
                sub={`${market.discount_sample} of ${market.listings_seen}`}
              />
              <StatTile
                label="Median discount"
                value={
                  market.discount_percentiles.median != null
                    ? `${market.discount_percentiles.median}%`
                    : "—"
                }
                sub={`up to ${market.discount_percentiles.max}% off`}
              />
              <StatTile
                label="Flagged by Trust"
                value={`${market.flagged_share}%`}
                sub="price outliers and weak sellers"
              />
            </Box>

            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
              <ChartCard
                title="Asking price spread"
                hint="Every listing seen, bucketed by price."
                sample={market.sample}
                columns={["Price band (₹)", "Listings"]}
                rows={market.price_buckets.map((b) => [b.label, b.count])}
              >
                <BarChart
                  data={market.price_buckets.map((b) => ({ label: b.label, count: b.count }))}
                  series={[{ key: "count", name: "Listings" }]}
                  height={170}
                />
              </ChartCard>

              <ChartCard
                title="Discount depth"
                hint="Only listings eBay reports a discount on."
                sample={market.discount_sample}
                columns={["Discount (%)", "Listings"]}
                rows={market.discount_buckets.map((b) => [b.label, b.count])}
              >
                <BarChart
                  data={market.discount_buckets.map((b) => ({ label: b.label, count: b.count }))}
                  series={[{ key: "count", name: "Listings" }]}
                  height={170}
                />
              </ChartCard>
            </Box>

            <Box sx={{ mt: 2 }}>
              <ChartCard
                title="Discounted listings by search"
                hint="How often each category actually carries a deal."
                columns={["Search", "Listings", "Discounted", "Median price"]}
                rows={market.by_query.map((q) => [
                  q.query,
                  q.listings,
                  q.discounted,
                  rupees(q.median_price_paise),
                ])}
              >
                <HBarChart
                  rows={market.by_query.map((q) => ({
                    label: q.query,
                    value: q.discounted,
                  }))}
                  labelWidth={168}
                />
              </ChartCard>
            </Box>
          </>
        ) : (
          <Box
            sx={{
              bgcolor: "background.paper",
              border: "1px dashed",
              borderColor: "divider",
              borderRadius: 2.5,
              p: 3,
              textAlign: "center",
            }}
          >
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Only {market.sample} listings observed so far. Run a few searches from the console —
              every search records its whole result set, so these charts fill in quickly.
            </Typography>
          </Box>
        )}

        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 4 }}>
          Chart colours were validated for colour-vision deficiency against this surface. Every
          chart has a table view, and no value on this page is encoded by colour alone.
        </Typography>
      </Box>
    </Box>
  );
}
