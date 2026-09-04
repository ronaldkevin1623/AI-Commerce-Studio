import { useEffect, useState } from "react";
import { Box, Stack, Typography } from "@mui/material";
import TrendingUpOutlinedIcon from "@mui/icons-material/TrendingUpOutlined";

import { API_BASE } from "../../config";

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

/**
 * DID THE GROWTH AGENTS EARN THEIR MARGIN?
 *
 * The closing half of the loop. Everything else on this page is about what
 * the agents want to do; this is the only place that says what came of it.
 *
 * Two decisions here are deliberate and slightly unflattering:
 *
 * Margin spent sits NEXT TO revenue attributed, at the same size. Every
 * dashboard of this kind shows the revenue large and the cost in a footnote,
 * and the resulting number reads as profit when it is nothing of the sort.
 *
 * And there is no conversion rate anywhere, at any sample size. A percentage
 * computed from one or two conversions is a number with no information in
 * it, and printing it would undo the honesty of everything above.
 */
export default function AttributionPanel({ card }) {
  const [state, setState] = useState({ status: "loading", data: null, error: null });

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/growth/attribution?days=30`);
        if (!res.ok) throw new Error(`Store returned ${res.status}`);
        const data = await res.json();
        if (live) setState({ status: "ready", data, error: null });
      } catch (err) {
        if (live) setState({ status: "error", data: null, error: String(err.message ?? err) });
      }
    })();
    return () => { live = false; };
  }, []);

  if (state.status !== "ready") {
    return (
      <Box sx={{ ...card, mb: 3 }}>
        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5, mb: 0.5 }}>
          Revenue attributed to the agents
        </Typography>
        <Typography variant="caption" sx={{ color: state.error ? "error.main" : "text.secondary" }}>
          {state.error ? `Couldn't read attribution: ${state.error}` : "Reading applied actions…"}
        </Typography>
      </Box>
    );
  }

  const d = state.data;
  const earned = d.attributed_revenue_paise;

  return (
    <Box sx={{ ...card, mb: 3 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.5 }}>
        <TrendingUpOutlinedIcon sx={{ fontSize: 17, color: "text.secondary" }} />
        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5 }}>
          Revenue attributed to the agents
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Typography variant="caption" sx={{ color: "text.disabled" }}>
          last {d.window_days} days
        </Typography>
      </Stack>

      {/* Cost and return at the same weight. Putting the margin in small
          print is how an attributed number starts reading as a profit. */}
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 2, mb: 2 }}>
        {[
          { label: "Attributed revenue", value: inr(earned),
            colour: earned ? "#4ADE80" : "text.disabled" },
          { label: "Margin given away", value: inr(d.margin_spent_paise),
            colour: d.margin_spent_paise ? "#FBBF24" : "text.disabled" },
          { label: "Actions applied", value: String(d.actions_applied),
            colour: "text.primary" },
        ].map((tile) => (
          <Box key={tile.label}>
            <Typography variant="caption"
                        sx={{ color: "text.secondary", display: "block", mb: 0.5, fontSize: 11 }}>
              {tile.label}
            </Typography>
            <Typography sx={{ fontSize: 22, fontWeight: 700, lineHeight: 1.1, color: tile.colour }}>
              {tile.value}
            </Typography>
          </Box>
        ))}
      </Box>

      <Typography variant="body2"
                  sx={{ color: "text.secondary", fontSize: 13, lineHeight: 1.65, mb: 1.5 }}>
        {d.headline}
      </Typography>

      {d.conversions.length > 0 && (
        <Stack spacing={0.75} sx={{ mb: 1.5 }}>
          {d.conversions.map((c, i) => (
            <Stack key={i} direction="row" spacing={1.25}
                   sx={{ alignItems: "baseline", px: 1.25, py: 0.9, borderRadius: 1.5,
                         bgcolor: "rgba(74,222,128,0.06)", border: "1px solid",
                         borderColor: "rgba(74,222,128,0.18)" }}>
              <Typography sx={{ fontSize: 13, fontWeight: 700, color: "#4ADE80",
                                fontVariantNumeric: "tabular-nums" }}>
                {inr(c.revenue_paise)}
              </Typography>
              <Typography variant="caption" sx={{ color: "text.secondary", flex: 1, lineHeight: 1.55 }}>
                {c.why}
              </Typography>
            </Stack>
          ))}
        </Stack>
      )}

      <Typography variant="caption"
                  sx={{ color: "text.disabled", display: "block", lineHeight: 1.65,
                        borderTop: "1px solid", borderColor: "divider", pt: 1.25 }}>
        {d.caveat}
      </Typography>
    </Box>
  );
}
