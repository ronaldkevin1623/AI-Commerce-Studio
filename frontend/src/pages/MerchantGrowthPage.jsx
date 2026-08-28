import { useCallback, useEffect, useState } from "react";
import {
  Box, Button, Stack, Typography, TextField, MenuItem, CircularProgress, Chip,
} from "@mui/material";
import { Link } from "react-router-dom";
import SpeedOutlinedIcon from "@mui/icons-material/SpeedOutlined";
import CloseIcon from "@mui/icons-material/Close";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlineOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";

import { API_BASE } from "../config";

const DISMISS_KEY = "commerce-studio.growth.heroDismissed";

const RANGES = [
  { value: 7, label: "Last 7 days" },
  { value: 30, label: "Last 30 days" },
  { value: 90, label: "Last 90 days" },
];

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const CARD = {
  border: "1px solid",
  borderColor: "divider",
  borderRadius: 2.5,
  bgcolor: "background.paper",
  p: 2,
};

/**
 * Growth for the storefront.
 *
 * The reference admin fills this page with a campaign product waitlist, ad
 * attribution and web sessions by traffic source. This store has no ad
 * channels, no web sessions and no campaigns — so rather than draw those
 * charts with invented numbers, the same layout asks the questions this
 * store can actually answer: what did AI buyers bring in, what did they do,
 * and can they still find the shop.
 *
 * Every figure comes from /merchant/growth, which reads orders and decisions
 * already in Firestore. Where a window genuinely has no data, it says so
 * instead of drawing a flat chart that looks like a measurement.
 */
function Sparkline({ series }) {
  const points = series ?? [];
  const peak = Math.max(1, ...points.map((p) => p.created_paise));

  // A single bucket has no line to draw, and dividing by zero to place it
  // would put it at NaN.
  const step = points.length > 1 ? 100 / (points.length - 1) : 0;
  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${(i * step).toFixed(2)} ${(30 - (p.created_paise / peak) * 28).toFixed(2)}`)
    .join(" ");

  return (
    <Box sx={{ mt: 1.5, height: 40 }}>
      <Box
        component="svg"
        viewBox="0 0 100 30"
        preserveAspectRatio="none"
        sx={{ width: "100%", height: "100%", display: "block", overflow: "visible" }}
      >
        <path d={path} fill="none" stroke="currentColor" strokeWidth="0.8" opacity="0.85"
              vectorEffect="non-scaling-stroke" style={{ color: "#60A5FA" }} />
      </Box>
    </Box>
  );
}

export default function MerchantGrowthPage() {
  const [days, setDays] = useState(30);
  const [state, setState] = useState({ status: "loading", data: null, error: null });
  const [heroOpen, setHeroOpen] = useState(() => {
    try {
      return window.localStorage.getItem(DISMISS_KEY) !== "1";
    } catch {
      return true;
    }
  });

  const load = useCallback(async (windowDays) => {
    setState((s) => ({ ...s, status: "loading" }));
    try {
      const res = await fetch(`${API_BASE}/merchant/growth?days=${windowDays}`);
      if (!res.ok) throw new Error(`Store returned ${res.status}`);
      setState({ status: "ready", data: await res.json(), error: null });
    } catch (err) {
      setState({ status: "error", data: null, error: String(err.message ?? err) });
    }
  }, []);

  useEffect(() => {
    load(days);
  }, [load, days]);

  const dismissHero = () => {
    setHeroOpen(false);
    try {
      window.localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* a hero that cannot remember being dismissed is not worth failing over */
    }
  };

  const { status, data, error } = state;
  const sales = data?.sales;
  const activity = data?.activity ?? [];
  const discovery = data?.discoverability;
  const peakActivity = Math.max(1, ...activity.map((a) => a.count));

  return (
    <Box sx={{ p: 3, maxWidth: 1180, mx: "auto" }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 2.5 }}>
        <SpeedOutlinedIcon sx={{ fontSize: 18, color: "text.secondary" }} />
        <Typography variant="h6" sx={{ fontSize: 19, fontWeight: 600 }}>
          Growth
        </Typography>
      </Stack>

      {heroOpen && (
        <Box sx={{ ...CARD, position: "relative", mb: 3, p: 2.5 }}>
          <Button
            size="small"
            onClick={dismissHero}
            startIcon={<CloseIcon sx={{ fontSize: 15 }} />}
            sx={{ position: "absolute", top: 12, right: 12, color: "text.secondary" }}
          >
            Dismiss
          </Button>

          <Chip
            size="small"
            label="Live"
            sx={{
              height: 20, mb: 1.5, bgcolor: "rgba(34,197,94,0.14)", color: "success.main",
              "& .MuiChip-label": { px: 1, fontSize: 10.5, fontWeight: 700 },
            }}
          />
          <Typography sx={{ fontSize: 22, fontWeight: 700, mb: 1, maxWidth: 620 }}>
            Your shop sells to AI agents, not just to people
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary", maxWidth: 620, lineHeight: 1.7, mb: 2 }}>
            The storefront publishes a UCP discovery document, so a buying agent can find it,
            read its catalogue and pay for an order without anyone building an integration
            first. This page measures that channel.
          </Typography>

          <Stack direction="row" spacing={1.5}>
            <Button
              variant="contained"
              size="small"
              href={`${API_BASE}/merchant/.well-known/ucp`}
              target="_blank"
              rel="noopener noreferrer"
              endIcon={<OpenInNewIcon sx={{ fontSize: 14 }} />}
            >
              View discovery document
            </Button>
            <Button variant="outlined" size="small" component={Link} to="/merchant/products">
              Manage catalogue
            </Button>
          </Stack>
        </Box>
      )}

      <Stack
        direction="row"
        sx={{ alignItems: "center", justifyContent: "space-between", mb: 1.5, gap: 2 }}
      >
        <Typography sx={{ fontSize: 15, fontWeight: 600 }}>Performance</Typography>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <TextField
            select
            size="small"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            sx={{ width: 160 }}
          >
            {RANGES.map((r) => (
              <MenuItem key={r.value} value={r.value}>{r.label}</MenuItem>
            ))}
          </TextField>
          <Button size="small" component={Link} to="/merchant" sx={{ color: "text.secondary" }}>
            View details
          </Button>
        </Stack>
      </Stack>

      {status === "loading" && (
        <Stack sx={{ alignItems: "center", py: 8 }}><CircularProgress size={22} /></Stack>
      )}

      {status === "error" && (
        <Box sx={{ ...CARD, borderColor: "error.main", bgcolor: "rgba(239,68,68,0.08)" }}>
          <Typography variant="body2" sx={{ color: "error.main", fontWeight: 600 }}>
            Couldn't read growth data
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>{error}</Typography>
        </Box>
      )}

      {status === "ready" && (
        <>
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
              gap: 2,
              mb: 3,
            }}
          >
            <Box sx={CARD}>
              <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5, mb: 0.5 }}>
                Sales attributed to agents
              </Typography>
              <Stack direction="row" spacing={1} sx={{ alignItems: "baseline" }}>
                <Typography sx={{ fontSize: 26, fontWeight: 700 }}>
                  {inr(sales.captured_paise)}
                </Typography>
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  captured
                </Typography>
              </Stack>
              <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 0.25 }}>
                {inr(sales.created_paise)} of orders created across {sales.order_count}{" "}
                {sales.order_count === 1 ? "order" : "orders"} · {sales.captured_count} paid
              </Typography>

              {sales.order_count > 0 ? (
                <Sparkline series={sales.series} />
              ) : (
                <Typography variant="caption" sx={{ color: "text.disabled", display: "block", mt: 2 }}>
                  No orders in this date range.
                </Typography>
              )}
            </Box>

            <Box sx={CARD}>
              <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5, mb: 1.5 }}>
                Agent activity by type
              </Typography>

              {activity.length === 0 ? (
                <Stack sx={{ alignItems: "center", justifyContent: "center", py: 4 }}>
                  <Typography variant="body2" sx={{ color: "text.disabled" }}>
                    No data for this date range
                  </Typography>
                </Stack>
              ) : (
                <Stack spacing={1}>
                  {activity.map((row) => (
                    <Stack key={row.action} direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
                      <Typography variant="caption" sx={{ width: 168, flexShrink: 0, fontSize: 11.5 }}>
                        {row.label}
                      </Typography>
                      <Box sx={{ flex: 1, height: 6, borderRadius: 999, bgcolor: "rgba(255,255,255,0.06)" }}>
                        <Box
                          sx={{
                            width: `${(row.count / peakActivity) * 100}%`,
                            height: "100%", borderRadius: 999, bgcolor: "#60A5FA",
                          }}
                        />
                      </Box>
                      <Typography
                        variant="caption"
                        sx={{ width: 30, textAlign: "right", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}
                      >
                        {row.count}
                      </Typography>
                    </Stack>
                  ))}
                </Stack>
              )}
            </Box>
          </Box>

          <Typography sx={{ fontSize: 15, fontWeight: 600, mb: 1.5 }}>
            Discoverability
          </Typography>
          <Box sx={{ ...CARD, mb: 3 }}>
            <Stack spacing={1.5}>
              {(discovery?.checks ?? []).map((check) => (
                <Stack key={check.label} direction="row" spacing={1.25} sx={{ alignItems: "flex-start" }}>
                  {check.ok ? (
                    <CheckCircleOutlineIcon sx={{ fontSize: 16, color: "success.main", mt: "1px" }} />
                  ) : (
                    <ErrorOutlineIcon sx={{ fontSize: 16, color: "warning.main", mt: "1px" }} />
                  )}
                  <Box>
                    <Typography variant="body2" sx={{ fontSize: 13, fontWeight: 500 }}>
                      {check.label}
                    </Typography>
                    <Typography variant="caption" sx={{ color: "text.secondary" }}>
                      {check.detail}
                    </Typography>
                  </Box>
                </Stack>
              ))}
            </Stack>
          </Box>

          <Typography sx={{ fontSize: 15, fontWeight: 600, mb: 1.5 }}>
            Campaigns
          </Typography>
          <Box sx={CARD}>
            <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.7 }}>
              There are no campaigns. This store has no ad channels, no marketing spend and no
              web sessions to attribute, so there is nothing here to measure yet — and a
              campaign report drawn from numbers that do not exist would be worse than an
              empty section. Agent discovery above is the only channel currently bringing
              orders in.
            </Typography>
          </Box>
        </>
      )}
    </Box>
  );
}
