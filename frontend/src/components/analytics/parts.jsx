import { useState } from "react";
import { Box, Stack, Tooltip, Typography } from "@mui/material";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";

/**
 * THE PIECES THE ANALYTICS PAGE IS BUILT FROM.
 *
 * Kept together because their job is consistency: eleven cards drawn by
 * eleven bits of bespoke JSX become eleven slightly different cards, and on
 * a page whose whole purpose is comparison, "slightly different" is a cost.
 *
 * The one rule running through all of them: a number that has no honest
 * comparison shows no comparison. Not 0%, not ∞%, not a grey arrow pointing
 * sideways — nothing, because growth from zero is not a percentage and
 * printing one is the most common lie in commerce dashboards.
 */

export const CARD = {
  border: "1px solid",
  borderColor: "divider",
  borderRadius: 2.5,
  bgcolor: "background.paper",
  p: 2,
};

export const INK = "#60A5FA";
export const INK_COMPARE = "#5B6472";

export const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export const inrShort = (paise) => {
  const rupees = (paise ?? 0) / 100;
  if (Math.abs(rupees) >= 100000) return `₹${(rupees / 100000).toFixed(1)}L`;
  if (Math.abs(rupees) >= 1000) return `₹${(rupees / 1000).toFixed(1)}K`;
  return `₹${Math.round(rupees)}`;
};

/** A dotted-underline label, as the reference uses for a defined metric. */
export function MetricLabel({ children, help }) {
  const label = (
    <Typography
      component="span"
      sx={{
        fontSize: 13, fontWeight: 600, color: "text.primary",
        borderBottom: "1px dotted", borderColor: "rgba(255,255,255,0.28)",
        cursor: help ? "help" : "default",
      }}
    >
      {children}
    </Typography>
  );
  return help ? <Tooltip title={help} placement="top-start">{label}</Tooltip> : label;
}

/**
 * The change against the comparison period.
 *
 * `null` renders an em dash rather than a zero. The distinction matters:
 * "no change" and "nothing to compare against" look identical as 0% and are
 * completely different facts about the business.
 */
export function Delta({ pct, size = 12 }) {
  if (pct === null || pct === undefined) {
    return (
      <Typography component="span" sx={{ fontSize: size, color: "text.disabled" }}>
        —
      </Typography>
    );
  }
  const up = pct >= 0;
  const colour = pct === 0 ? "text.secondary" : up ? "#4ADE80" : "#F87171";
  const Icon = up ? ArrowUpwardIcon : ArrowDownwardIcon;
  return (
    <Stack component="span" direction="row" spacing={0.15}
           sx={{ alignItems: "center", color: colour }}>
      {pct !== 0 && <Icon sx={{ fontSize: size + 1 }} />}
      <Typography component="span"
                  sx={{ fontSize: size, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
        {Math.abs(pct)}%
      </Typography>
    </Stack>
  );
}

/**
 * A line chart with an optional comparison series behind it, and a readout
 * under the pointer.
 *
 * The comparison is dashed and grey and drawn FIRST, so it sits behind the
 * period you are actually looking at. Two solid lines of equal weight make
 * the reader work out which one is now.
 *
 * WHY THE HOVER LAYER IS NOT OPTIONAL HERE
 *
 * A line's shape answers "is it going up". Almost every other question a
 * merchant has is about one point on it — what was Tuesday, what happened at
 * 11am — and without a readout the only way to answer that is to squint at a
 * gridline and guess. The crosshair snaps to the nearest bucket rather than
 * following the pointer freely, because a tooltip that reports a value
 * between two buckets is reporting a number that was never measured.
 *
 * Both series are read at the same index and shown together, since the whole
 * reason the comparison is drawn is to be compared AT a moment.
 */
export function LineChart({ series, compareSeries, height = 200, showAxis = true,
                            format = inrShort, labelEvery, title = "Total sales",
                            seriesLabel, compareLabel }) {
  const points = series ?? [];
  const compare = compareSeries ?? [];
  const [hover, setHover] = useState(null);
  if (points.length === 0) return null;

  const peak = Math.max(1, ...points.map((p) => p.value),
                        ...compare.map((p) => p.value));
  const W = 100;
  const H = 100;

  // Where a value sits vertically, as a percentage of the plot box. The SVG
  // is drawn with preserveAspectRatio="none" over the same box, so the two
  // coordinate systems agree and the dot lands on the line.
  const yPct = (value) => 100 - (value / peak) * (H - 6);
  const xPct = (i) => (points.length > 1 ? (i / (points.length - 1)) * 100 : 50);

  const path = (rows) => {
    if (rows.length === 0) return "";
    if (rows.length === 1) {
      const y = H - (rows[0].value / peak) * (H - 6);
      return `M 0 ${y.toFixed(2)} L ${W} ${y.toFixed(2)}`;
    }
    const step = W / (rows.length - 1);
    return rows
      .map((p, i) => `${i === 0 ? "M" : "L"} ${(i * step).toFixed(2)} ${(H - (p.value / peak) * (H - 6)).toFixed(2)}`)
      .join(" ");
  };

  const every = labelEvery ?? Math.max(1, Math.ceil(points.length / 6));

  const track = (event) => {
    const box = event.currentTarget.getBoundingClientRect();
    if (!box.width) return;
    const ratio = (event.clientX - box.left) / box.width;
    const index = Math.round(ratio * (points.length - 1));
    setHover(Math.max(0, Math.min(points.length - 1, index)));
  };

  const at = hover !== null ? points[hover] : null;
  const atCompare = hover !== null ? compare[hover] : null;
  // Flip the card to the left of the crosshair once there is not room for it
  // on the right, rather than letting it hang off the card.
  const flip = hover !== null && xPct(hover) > 62;

  return (
    <Box>
      <Box
        sx={{ position: "relative", height, cursor: "crosshair" }}
        onMouseMove={track}
        onMouseLeave={() => setHover(null)}
      >
        {/* Gridlines and the peak value, so the line has a scale rather
            than only a shape. */}
        {[0, 0.5, 1].map((t) => (
          <Box key={t} sx={{
            position: "absolute", left: 0, right: 0, top: `${t * 100}%`,
            borderTop: "1px solid", borderColor: "rgba(255,255,255,0.06)",
          }} />
        ))}
        <Typography sx={{ position: "absolute", left: 0, top: -6, fontSize: 10,
                          color: "text.disabled" }}>
          {format(peak)}
        </Typography>

        <Box component="svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
             sx={{ width: "100%", height: "100%", display: "block", overflow: "visible",
                   pointerEvents: "none" }}>
          {compare.length > 0 && (
            <path d={path(compare)} fill="none" stroke={INK_COMPARE} strokeWidth="1"
                  strokeDasharray="3 3" vectorEffect="non-scaling-stroke" opacity="0.9" />
          )}
          <path d={path(points)} fill="none" stroke={INK} strokeWidth="1.6"
                vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        </Box>

        {hover !== null && (
          <>
            <Box sx={{
              position: "absolute", top: 0, bottom: 0, left: `${xPct(hover)}%`,
              width: 0, borderLeft: "1px solid", borderColor: "rgba(255,255,255,0.28)",
              pointerEvents: "none",
            }} />
            {atCompare && (
              <Box sx={{
                position: "absolute", left: `${xPct(hover)}%`,
                top: `${yPct(atCompare.value)}%`,
                width: 7, height: 7, borderRadius: "50%", bgcolor: INK_COMPARE,
                transform: "translate(-50%, -50%)", pointerEvents: "none",
              }} />
            )}
            <Box sx={{
              position: "absolute", left: `${xPct(hover)}%`, top: `${yPct(at.value)}%`,
              width: 9, height: 9, borderRadius: "50%", bgcolor: INK,
              border: "2px solid", borderColor: "background.paper",
              transform: "translate(-50%, -50%)", pointerEvents: "none",
            }} />

            <Box sx={{
              position: "absolute", left: `${xPct(hover)}%`, top: 4,
              transform: flip ? "translateX(calc(-100% - 12px))" : "translateX(12px)",
              minWidth: 172, px: 1.5, py: 1.25, borderRadius: 2,
              bgcolor: "background.paper", border: "1px solid", borderColor: "divider",
              boxShadow: "0 8px 26px rgba(0,0,0,0.5)",
              pointerEvents: "none", zIndex: 3,
            }}>
              <Typography sx={{ fontSize: 12, fontWeight: 700, mb: 0.75 }}>
                {title}
              </Typography>
              <Stack spacing={0.6}>
                <Stack direction="row" spacing={0.85} sx={{ alignItems: "center" }}>
                  <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: INK,
                             flexShrink: 0 }} />
                  <Typography sx={{ fontSize: 11, color: "text.secondary", flex: 1 }}>
                    {at.full ?? at.label}
                  </Typography>
                  <Typography sx={{ fontSize: 11.5, fontWeight: 700,
                                    fontVariantNumeric: "tabular-nums" }}>
                    {format(at.value)}
                  </Typography>
                </Stack>
                {atCompare && (
                  <Stack direction="row" spacing={0.85} sx={{ alignItems: "center" }}>
                    <Box sx={{ width: 7, height: 7, borderRadius: "50%",
                               bgcolor: INK_COMPARE, flexShrink: 0 }} />
                    <Typography sx={{ fontSize: 11, color: "text.disabled", flex: 1 }}>
                      {atCompare.full ?? atCompare.label}
                    </Typography>
                    <Typography sx={{ fontSize: 11.5, fontWeight: 600,
                                      color: "text.secondary",
                                      fontVariantNumeric: "tabular-nums" }}>
                      {format(atCompare.value)}
                    </Typography>
                  </Stack>
                )}
              </Stack>
            </Box>
          </>
        )}
      </Box>

      {showAxis && (
        <Stack direction="row" sx={{ justifyContent: "space-between", mt: 0.75 }}>
          {points.map((p, i) =>
            i % every === 0 || i === points.length - 1 ? (
              <Typography key={p.at} sx={{ fontSize: 10, color: "text.disabled" }}>
                {p.label}
              </Typography>
            ) : null)}
        </Stack>
      )}

      {(seriesLabel || compareLabel) && (
        <Stack direction="row" spacing={2.5}
               sx={{ justifyContent: "center", mt: 1.25, flexWrap: "wrap", gap: 1 }}>
          {seriesLabel && (
            <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
              <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: INK }} />
              <Typography sx={{ fontSize: 10.5, color: "text.secondary" }}>
                {seriesLabel}
              </Typography>
            </Stack>
          )}
          {compareLabel && compare.length > 0 && (
            <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
              <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: INK_COMPARE }} />
              <Typography sx={{ fontSize: 10.5, color: "text.disabled" }}>
                {compareLabel}
              </Typography>
            </Stack>
          )}
        </Stack>
      )}
    </Box>
  );
}

/** A ranked list drawn as bars — used for channels and products. */
export function BarList({ rows, empty }) {
  if (!rows || rows.length === 0) {
    return (
      <Stack sx={{ alignItems: "center", justifyContent: "center", minHeight: 140 }}>
        <Typography variant="body2" sx={{ color: "text.disabled", textAlign: "center" }}>
          {empty}
        </Typography>
      </Stack>
    );
  }
  const peak = Math.max(1, ...rows.map((r) => r.value));
  return (
    <Stack spacing={1.25}>
      {rows.map((row) => (
        <Box key={row.label}>
          <Stack direction="row" sx={{ justifyContent: "space-between", mb: 0.5, gap: 2 }}>
            <Typography variant="caption" noWrap
                        sx={{ fontSize: 11.5, color: "text.secondary", minWidth: 0 }}>
              {row.label}
            </Typography>
            <Stack direction="row" spacing={1} sx={{ flexShrink: 0, alignItems: "baseline" }}>
              {row.sub && (
                <Typography variant="caption" sx={{ fontSize: 10.5, color: "text.disabled" }}>
                  {row.sub}
                </Typography>
              )}
              <Typography variant="caption"
                          sx={{ fontSize: 11.5, fontWeight: 600,
                                fontVariantNumeric: "tabular-nums" }}>
                {inr(row.value)}
              </Typography>
            </Stack>
          </Stack>
          <Box sx={{ height: 6, borderRadius: 999, bgcolor: "rgba(255,255,255,0.06)" }}>
            <Box sx={{ width: `${(row.value / peak) * 100}%`, height: "100%",
                       borderRadius: 999, bgcolor: INK }} />
          </Box>
        </Box>
      ))}
    </Stack>
  );
}

/** A titled card with the standard heading treatment. */
export function Card({ title, help, right, children, sx }) {
  return (
    <Box sx={{ ...CARD, display: "flex", flexDirection: "column", ...sx }}>
      <Stack direction="row"
             sx={{ alignItems: "center", justifyContent: "space-between", mb: 1.5, gap: 1 }}>
        <MetricLabel help={help}>{title}</MetricLabel>
        {right}
      </Stack>
      <Box sx={{ flex: 1 }}>{children}</Box>
    </Box>
  );
}

/**
 * CUSTOMER COHORT ANALYSIS.
 *
 * Rows are everyone whose first paid order landed in that month; cells are
 * the share of them who bought again in each later month. Triangular,
 * because a cohort cannot have a result for a month that has not happened —
 * an empty cell and a 0% cell are different facts, and the shape is what
 * keeps them apart.
 *
 * THE COHORT SIZE IS PRINTED ON EVERY ROW.
 *
 * The reference grid does not show it, and that is how a retention heatmap
 * becomes misleading: over one customer, every cell is 0% or 100% with
 * nothing possible in between, so the grid is a coin toss rendered as a
 * finding — and it is the most authoritative-looking card on any analytics
 * page. Printing `n` beside each row is what stops "100%" being read as
 * retention rather than as one person's decision.
 *
 * Months with no new customers keep their row rather than being dropped.
 * Closing the gap would slide the diagonal and quietly misalign every
 * cohort against its own month.
 */
export function CohortGrid({ cohorts }) {
  const rows = cohorts?.rows ?? [];
  const months = cohorts?.months ?? [];
  if (rows.length === 0) {
    return (
      <Stack sx={{ alignItems: "center", justifyContent: "center", minHeight: 160 }}>
        <Typography variant="body2" sx={{ color: "text.disabled" }}>
          No paying customers yet, so there are no cohorts to follow.
        </Typography>
      </Stack>
    );
  }

  const CELL = 58;
  const LABEL = 104;

  return (
    <Box>
      <Box sx={{ overflowX: "auto", pb: 0.5 }}>
        <Box sx={{ minWidth: LABEL + months.length * CELL }}>
          <Stack direction="row" sx={{ mb: 0.75 }}>
            <Typography variant="caption"
                        sx={{ width: LABEL, flexShrink: 0, fontSize: 10.5,
                              color: "text.disabled", fontWeight: 600 }}>
              Cohort
            </Typography>
            <Typography variant="caption"
                        sx={{ fontSize: 10.5, color: "text.disabled", fontWeight: 600 }}>
              Months since first order
            </Typography>
          </Stack>

          {/* The column heads are OFFSETS, not calendar months: every row
              starts at its own month zero, so a shared calendar header
              would be wrong for every row but the first. */}
          <Stack direction="row" sx={{ mb: 0.5 }}>
            <Box sx={{ width: LABEL, flexShrink: 0 }} />
            {months.map((_, i) => (
              <Typography key={i} variant="caption"
                          sx={{ width: CELL, flexShrink: 0, textAlign: "center",
                                fontSize: 10, color: "text.disabled" }}>
                {i}
              </Typography>
            ))}
          </Stack>

          <Stack spacing={0.5}>
            {rows.map((row) => (
              <Stack key={row.cohort} direction="row" sx={{ alignItems: "stretch" }}>
                <Stack sx={{ width: LABEL, flexShrink: 0, justifyContent: "center", pr: 1 }}>
                  <Typography variant="caption"
                              sx={{ fontSize: 11.5,
                                    color: row.size ? "text.secondary" : "text.disabled" }}>
                    {row.label}
                  </Typography>
                  <Typography variant="caption"
                              sx={{ fontSize: 10, color: "text.disabled" }}>
                    {row.size
                      ? `${row.size} customer${row.size === 1 ? "" : "s"}`
                      : "no new customers"}
                  </Typography>
                </Stack>

                {row.cells.length === 0 ? (
                  <Box sx={{ flex: 1, minHeight: 34, borderRadius: 1,
                             bgcolor: "rgba(255,255,255,0.012)" }} />
                ) : (
                  row.cells.map((cell) => (
                    <Tooltip
                      key={cell.offset}
                      placement="top"
                      title={`${cell.count} of ${row.size} bought again`}
                    >
                      <Box
                        sx={{
                          width: CELL, flexShrink: 0, minHeight: 34,
                          display: "flex", alignItems: "center", justifyContent: "center",
                          // Tinted by the value rather than a flat fill, so
                          // the diagonal decay a healthy shop shows is
                          // visible as a gradient rather than as text.
                          bgcolor: `rgba(96,165,250,${0.06 + (cell.pct / 100) * 0.28})`,
                          borderRadius: 1,
                          mr: "2px",
                        }}
                      >
                        <Typography
                          sx={{ fontSize: 11, fontWeight: cell.pct ? 600 : 500,
                                fontVariantNumeric: "tabular-nums",
                                color: cell.pct ? "text.primary" : "text.disabled" }}
                        >
                          {cell.pct}%
                        </Typography>
                      </Box>
                    </Tooltip>
                  ))
                )}
              </Stack>
            ))}
          </Stack>
        </Box>
      </Box>

      <Typography variant="caption"
                  sx={{ color: "text.disabled", display: "block", mt: 1.5,
                        lineHeight: 1.65, fontSize: 10.5 }}>
        {cohorts.note}
      </Typography>
    </Box>
  );
}
