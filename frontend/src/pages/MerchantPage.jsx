import { useCallback, useEffect, useState } from "react";
import { Box, Chip, CircularProgress, Stack, Tooltip, Typography } from "@mui/material";
import BarChartOutlinedIcon from "@mui/icons-material/BarChartOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import { API_BASE } from "../config";
import DateRangePicker from "../components/growth/DateRangePicker";
import {
  BarList, CARD, Card, CohortGrid, Delta, LineChart, MetricLabel, inr, inrShort,
} from "../components/analytics/parts";

/**
 * ANALYTICS.
 *
 * Built to the shape of the reference admin's analytics page — a range
 * control, a comparison period, a row of headline tiles, then cards — but
 * with roughly a third of its cards, and that reduction is the design
 * decision rather than a shortcut.
 *
 * The cards that are gone are the WEB TRAFFIC ones: sessions over time,
 * conversion rate, sessions by landing page, by social referrer, by
 * referring channel. This shop has no theme, no visitors and no referrers,
 * so every one of those resolves to "No data for this date range" forever.
 * A page that is two-thirds empty teaches a merchant to stop reading it,
 * and a page that fills those cards with invented numbers is worse. They
 * are absent, and the page says so once, plainly, at the bottom.
 *
 * Cohort retention IS here, because it needs customers and orders rather
 * than sessions, and this shop has both. It is the one card on the page
 * whose sample is small enough to mislead, so it prints its cohort sizes.
 *
 * What is here is everything the shop's own records can answer, each with a
 * comparison against the preceding window of equal length — because a
 * number without a comparison is not yet information.
 */

const SHORT_MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** `2026-09-03` or `2026-09-03T14` into an axis label. */
function axisLabel(at, granularity) {
  if (granularity === "hour") {
    const hour = Number(at.slice(11, 13));
    const suffix = hour < 12 ? "AM" : "PM";
    const twelve = hour % 12 === 0 ? 12 : hour % 12;
    return `${twelve} ${suffix}`;
  }
  const [, month, day] = at.split("-");
  return `${SHORT_MONTH[Number(month) - 1]} ${Number(day)}`;
}

/**
 * The label the hover readout shows: the whole moment, not the axis tick.
 *
 * An axis says "Sep 3" because it has to fit six of them across a card. A
 * tooltip is answering "which point exactly is this", so it spells the
 * moment out — including the year, because the comparison series is a
 * different window and on a January range the two rows differ only by it.
 */
function fullLabel(at, granularity) {
  const [year, month, rest] = at.split("-");
  const day = Number(rest.slice(0, 2));
  const stamp = `${SHORT_MONTH[Number(month) - 1]} ${day}, ${year}`;
  if (granularity !== "hour") return stamp;
  const hour = Number(at.slice(11, 13));
  const suffix = hour < 12 ? "AM" : "PM";
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return `${stamp}, ${twelve}:00 ${suffix}`;
}

/** How a whole window is named under the chart. */
function windowLabel(window) {
  if (!window) return null;
  return window.from === window.to
    ? fullLabel(window.from, "day")
    : `${fullLabel(window.from, "day")} – ${fullLabel(window.to, "day")}`;
}

const toPoints = (series, granularity) =>
  (series ?? []).map((p) => ({
    at: p.at,
    value: p.sales_paise,
    label: axisLabel(p.at, granularity),
    full: fullLabel(p.at, granularity),
  }));

function Kpi({ kpi }) {
  const value =
    kpi.unit === "paise" ? inr(kpi.value)
      : kpi.unit === "percent" ? (kpi.value === null ? "—" : `${kpi.value}%`)
      : String(kpi.value ?? 0);

  return (
    <Box sx={{ ...CARD, py: 1.75 }}>
      <MetricLabel>{kpi.label}</MetricLabel>
      <Stack direction="row" spacing={1.25} sx={{ alignItems: "baseline", mt: 1 }}>
        <Typography sx={{ fontSize: 22, fontWeight: 700, lineHeight: 1.1,
                          letterSpacing: "-0.01em" }}>
          {value}
        </Typography>
        <Delta pct={kpi.delta_pct} />
      </Stack>
      {kpi.note && (
        <Typography variant="caption"
                    sx={{ color: "text.disabled", display: "block", mt: 0.5, fontSize: 11 }}>
          {kpi.note}
        </Typography>
      )}
    </Box>
  );
}

export default function MerchantPage() {
  const [range, setRange] = useState(null);
  const [state, setState] = useState({ status: "loading", data: null, error: null });

  const load = useCallback(async (selected) => {
    setState((s) => ({ ...s, status: "loading" }));
    const query = !selected || selected.rolling
      ? `days=${selected?.days ?? 30}`
      : `start=${selected.startISO}&end=${selected.endISO}`;
    try {
      const res = await fetch(`${API_BASE}/merchant/analytics?${query}`);
      if (!res.ok) throw new Error(`Store returned ${res.status}`);
      setState({ status: "ready", data: await res.json(), error: null });
    } catch (err) {
      setState({ status: "error", data: null, error: String(err.message ?? err) });
    }
  }, []);

  useEffect(() => { load(range); }, [load, range]);

  const { status, data, error } = state;

  const grain = data?.window?.granularity ?? "day";
  const points = toPoints(data?.sales_over_time?.series, grain);
  const comparePoints = toPoints(data?.sales_over_time?.compare_series, grain);
  const aovPoints = (data?.sales_over_time?.series ?? []).map((p) => ({
    at: p.at,
    value: p.orders ? Math.round(p.sales_paise / p.orders) : 0,
    label: axisLabel(p.at, grain),
    full: fullLabel(p.at, grain),
  }));

  return (
    <Box sx={{ p: 3, maxWidth: 1320, mx: "auto" }}>
      <Stack direction="row"
             sx={{ alignItems: "center", justifyContent: "space-between", mb: 2, gap: 2 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <BarChartOutlinedIcon sx={{ fontSize: 20, color: "text.secondary" }} />
          <Typography sx={{ fontSize: 20, fontWeight: 700, letterSpacing: "-0.01em" }}>
            Analytics
          </Typography>
        </Stack>
      </Stack>

      {/* ── controls ─────────────────────────────────────────────────── */}
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 3, flexWrap: "wrap", gap: 1 }}>
        <DateRangePicker value={range} onChange={setRange} />

        {/* The comparison period is stated, not chosen. It is always the
            window immediately before this one, of equal length — offering a
            choice would imply the others are supported, and "the same days
            last month" is a different number of weekends and therefore not
            a comparison at all. */}
        <Tooltip title="Always the window immediately before this one, of equal length.">
          <Chip
            size="small"
            icon={<InfoOutlinedIcon sx={{ fontSize: 14 }} />}
            label={data ? `vs ${data.compare.from} – ${data.compare.to}` : "vs previous period"}
            sx={{ height: 30, borderRadius: 1.5, fontSize: 12.5,
                  bgcolor: "transparent", border: "1px solid", borderColor: "divider" }}
          />
        </Tooltip>

        <Chip
          size="small"
          label="INR ₹"
          sx={{ height: 30, borderRadius: 1.5, fontSize: 12.5,
                bgcolor: "transparent", border: "1px solid", borderColor: "divider" }}
        />

        {data && (
          <Typography variant="caption" sx={{ color: "text.disabled", ml: 0.5 }}>
            {data.window.from} to {data.window.to} · by {data.window.granularity}
          </Typography>
        )}
      </Stack>

      {status === "loading" && (
        <Stack sx={{ alignItems: "center", py: 10 }}><CircularProgress size={24} /></Stack>
      )}

      {status === "error" && (
        <Box sx={{ ...CARD, borderColor: "error.main", bgcolor: "rgba(239,68,68,0.08)" }}>
          <Typography variant="body2" sx={{ color: "error.main", fontWeight: 600, mb: 0.5 }}>
            Couldn't read analytics
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>{error}</Typography>
        </Box>
      )}

      {status === "ready" && (
        <Stack spacing={2}>
          {/* ── headline tiles ───────────────────────────────────────── */}
          <Box sx={{ display: "grid", gap: 2,
                     gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" } }}>
            {data.kpis.map((kpi) => <Kpi key={kpi.key} kpi={kpi} />)}
          </Box>

          {/* ── sales over time + the breakdown ──────────────────────── */}
          <Box sx={{ display: "grid", gap: 2,
                     gridTemplateColumns: { xs: "1fr", lg: "1.9fr 1fr" } }}>
            <Card
              title="Total sales over time"
              help="Order value created in this window, bucketed by day — or by hour when the window is a day or two."
            >
              <Stack direction="row" spacing={1.25} sx={{ alignItems: "baseline", mb: 2 }}>
                <Typography sx={{ fontSize: 24, fontWeight: 700 }}>
                  {inr(data.kpis[0].value)}
                </Typography>
                <Delta pct={data.kpis[0].delta_pct} size={12.5} />
              </Stack>
              <LineChart
                series={points}
                compareSeries={comparePoints}
                height={210}
                title="Total sales"
                seriesLabel={windowLabel(data.window)}
                compareLabel={windowLabel(data.compare)}
              />
            </Card>

            <Card
              title="Total sales breakdown"
              help="Gross less what was given away and returned, plus anything carried on the listing."
            >
              <Stack spacing={0}>
                {data.breakdown.map((row) => (
                  <Stack
                    key={row.label}
                    direction="row"
                    sx={{
                      justifyContent: "space-between", alignItems: "center", gap: 2,
                      px: 1, py: 1.05, borderRadius: 1,
                      bgcolor: row.strong ? "rgba(255,255,255,0.045)" : "transparent",
                    }}
                  >
                    <Tooltip title={row.note ?? ""} placement="left">
                      <Typography
                        variant="body2"
                        sx={{ fontSize: 12.5,
                              fontWeight: row.strong ? 700 : 500,
                              color: row.strong ? "text.primary" : "text.secondary",
                              cursor: row.note ? "help" : "default" }}
                      >
                        {row.label}
                      </Typography>
                    </Tooltip>
                    <Stack direction="row" spacing={1.25} sx={{ alignItems: "baseline" }}>
                      <Typography
                        variant="body2"
                        sx={{ fontSize: 12.5, fontWeight: row.strong ? 700 : 600,
                              fontVariantNumeric: "tabular-nums",
                              color: row.value < 0 ? "#FBBF24" : "text.primary" }}
                      >
                        {inr(row.value)}
                      </Typography>
                      <Box sx={{ width: 52, textAlign: "right" }}>
                        <Delta pct={row.delta_pct} size={11} />
                      </Box>
                    </Stack>
                  </Stack>
                ))}
              </Stack>

              {/* Named rather than silently missing, so nobody wonders
                  whether the page forgot them. */}
              <Stack spacing={0.5} sx={{ mt: 1.5, pt: 1.5, borderTop: "1px solid",
                                         borderColor: "divider" }}>
                {data.breakdown_omitted.map((row) => (
                  <Typography key={row.label} variant="caption"
                              sx={{ color: "text.disabled", fontSize: 10.5, lineHeight: 1.55 }}>
                    <b>{row.label}</b> — {row.why}
                  </Typography>
                ))}
              </Stack>
            </Card>
          </Box>

          {/* ── channel, AOV, product ────────────────────────────────── */}
          <Box sx={{ display: "grid", gap: 2,
                     gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" } }}>
            <Card
              title="Total sales by channel"
              help="The four ways into this shop: the agent console, the storefront over UCP or ACP, and the trip sector."
            >
              <BarList
                rows={data.by_channel.map((c) => ({
                  label: c.label, value: c.value,
                  sub: c.pct !== null ? `${c.pct}%` : null,
                }))}
                empty="No sales in this date range."
              />
            </Card>

            <Card
              title="Average order value over time"
              help="Order value divided by orders, per bucket. Buckets with no orders sit at zero rather than being interpolated."
            >
              <Stack direction="row" spacing={1.25} sx={{ alignItems: "baseline", mb: 1.5 }}>
                <Typography sx={{ fontSize: 20, fontWeight: 700 }}>
                  {inr(data.kpis[2].value)}
                </Typography>
                <Delta pct={data.kpis[2].delta_pct} />
              </Stack>
              <LineChart series={aovPoints} height={132} format={inrShort}
                         title="Average order value" />
            </Card>

            <Card
              title="Total sales by product"
              help="Line items across every channel, largest first."
            >
              <BarList
                rows={data.by_product.map((p) => ({
                  label: p.label, value: p.value,
                  sub: `${p.units} ${p.units === 1 ? "unit" : "units"}`,
                }))}
                empty="No products sold in this date range."
              />
            </Card>
          </Box>

          {/* ── retention, and what the payments did ─────────────────── */}
          <Box sx={{ display: "grid", gap: 2,
                     gridTemplateColumns: { xs: "1fr", lg: "2fr 1fr" } }}>
            <Card
              title="Customer cohort analysis"
              help="Each row is everyone whose first paid order landed in that month. Each cell is the share of them who ordered again that many months later."
            >
              <CohortGrid cohorts={data.cohorts} />
            </Card>

            <Card
              title="Payments"
              help="What happened at the moment money was supposed to move."
            >
              <Stack spacing={1.25}>
                {[
                  { label: "Captured", value: data.payments.captured, colour: "#4ADE80" },
                  { label: "Failed", value: data.payments.failed, colour: "#F87171" },
                  { label: "Refused as unverifiable", value: data.payments.refused_unverifiable,
                    colour: "#FBBF24" },
                ].map((row) => (
                  <Stack key={row.label} direction="row"
                         sx={{ justifyContent: "space-between", alignItems: "baseline" }}>
                    <Typography variant="body2" sx={{ fontSize: 12.5, color: "text.secondary" }}>
                      {row.label}
                    </Typography>
                    <Typography sx={{ fontSize: 17, fontWeight: 700, color: row.colour,
                                      fontVariantNumeric: "tabular-nums" }}>
                      {row.value}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
              <Typography variant="caption"
                          sx={{ color: "text.disabled", display: "block", mt: 1.5,
                                lineHeight: 1.6, fontSize: 10.5 }}>
                A payment refused as unverifiable is the store declining to mark an
                order paid on an id Razorpay would not confirm. That is a refusal
                working, not a failure.
              </Typography>
            </Card>
          </Box>

          {/* ── what this page does not claim ────────────────────────── */}
          <Box sx={{ ...CARD, bgcolor: "transparent" }}>
            <Stack spacing={0.75}>
              {data.notes.map((note, i) => (
                <Typography key={i} variant="caption"
                            sx={{ color: "text.secondary", lineHeight: 1.7, fontSize: 11.5 }}>
                  {note}
                </Typography>
              ))}
            </Stack>
          </Box>
        </Stack>
      )}
    </Box>
  );
}
