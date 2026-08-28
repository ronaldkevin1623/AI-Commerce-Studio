import { useState } from "react";
import { Box, Stack, Typography } from "@mui/material";

/**
 * Plain-SVG charts. No charting dependency, per the project's rule.
 *
 * PALETTE NOTE: the two series colours below were run through the dataviz
 * validator against this app's #12161F chart surface. The obvious choice —
 * the theme's own green and amber — failed: #22C55E against #F59E0B is
 * ΔE 5.7 under protanopia, i.e. the two bars are near-indistinguishable to
 * a red-blind reader, and both sit outside the dark-mode lightness band.
 * Blue with a darker step of the same amber hue passes every check, so
 * that's what multi-series charts use. Single-series charts use one hue and
 * sidestep the question entirely, which is why most of them do.
 */

export const SERIES = ["#3B82F6", "#D97706"];
const GRID = "rgba(255,255,255,0.07)";
const AXIS_TEXT = "#5B6474";

/** Bars are anchored to the baseline, so only the data end is rounded. */
function topRounded(x, y, w, h, r) {
  const radius = Math.min(r, w / 2, h);
  if (h <= 0) return "";
  return [
    `M ${x} ${y + h}`,
    `L ${x} ${y + radius}`,
    `Q ${x} ${y} ${x + radius} ${y}`,
    `L ${x + w - radius} ${y}`,
    `Q ${x + w} ${y} ${x + w} ${y + radius}`,
    `L ${x + w} ${y + h}`,
    "Z",
  ].join(" ");
}

function niceCeiling(value) {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / magnitude) * magnitude;
}

function Tooltip({ point }) {
  if (!point) return null;
  return (
    <Box
      sx={{
        position: "absolute",
        left: `${point.left}%`,
        top: point.top,
        transform: "translate(-50%, -100%)",
        pointerEvents: "none",
        bgcolor: "#0B0F17",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1.5,
        px: 1.25,
        py: 0.75,
        whiteSpace: "nowrap",
        zIndex: 2,
        boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
      }}
    >
      <Typography variant="caption" sx={{ color: "text.secondary", display: "block", fontSize: 10.5 }}>
        {point.label}
      </Typography>
      {point.rows.map((row) => (
        <Stack key={row.name} direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
          <Box sx={{ width: 7, height: 7, borderRadius: "2px", bgcolor: row.color, flexShrink: 0 }} />
          <Typography variant="caption" sx={{ color: "text.primary", fontSize: 11.5 }}>
            {row.name}: <strong>{row.value}</strong>
          </Typography>
        </Stack>
      ))}
    </Box>
  );
}

/**
 * Vertical bars. One or two series — never more, because a third would push
 * the categorical palette past what validates on this surface.
 */
export function BarChart({ data, series, height = 190, formatValue = (v) => v }) {
  const [hover, setHover] = useState(null);

  const W = 760;
  const H = height;
  const PAD = { top: 12, right: 8, bottom: 26, left: 40 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const max = niceCeiling(
    Math.max(1, ...data.flatMap((d) => series.map((s) => d[s.key] ?? 0)))
  );
  const ticks = [0, max / 2, max];

  const slot = plotW / Math.max(data.length, 1);
  const groupGap = 2; // the 2px surface gap between adjacent fills
  const barW = Math.max((slot - 10 - groupGap * (series.length - 1)) / series.length, 3);

  return (
    <Box sx={{ position: "relative" }}>
      <Box component="svg" viewBox={`0 0 ${W} ${H}`} sx={{ width: "100%", height: "auto", display: "block" }}>
        {ticks.map((tick) => {
          const y = PAD.top + plotH - (tick / max) * plotH;
          return (
            <g key={tick}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} stroke={GRID} strokeWidth="1" />
              <text
                x={PAD.left - 8}
                y={y + 3.5}
                textAnchor="end"
                fill={AXIS_TEXT}
                style={{ fontSize: 10, fontVariantNumeric: "tabular-nums" }}
              >
                {formatValue(tick)}
              </text>
            </g>
          );
        })}

        {data.map((row, i) => {
          const slotX = PAD.left + i * slot;
          const groupW = barW * series.length + groupGap * (series.length - 1);
          const startX = slotX + (slot - groupW) / 2;

          return (
            <g key={row.label}>
              {/* Full-height hit target — bigger than the mark, per spec. */}
              <rect
                x={slotX}
                y={PAD.top}
                width={slot}
                height={plotH}
                fill="transparent"
                onMouseEnter={() =>
                  setHover({
                    left: ((slotX + slot / 2) / W) * 100,
                    top: PAD.top + 4,
                    label: row.label,
                    rows: series.map((s, si) => ({
                      name: s.name,
                      color: SERIES[si],
                      value: formatValue(row[s.key] ?? 0),
                    })),
                  })
                }
                onMouseLeave={() => setHover(null)}
              />
              {series.map((s, si) => {
                const value = row[s.key] ?? 0;
                const h = (value / max) * plotH;
                const x = startX + si * (barW + groupGap);
                return (
                  <path
                    key={s.key}
                    d={topRounded(x, PAD.top + plotH - h, barW, h, 4)}
                    fill={SERIES[si]}
                    opacity={hover && hover.label !== row.label ? 0.45 : 1}
                    style={{ transition: "opacity 120ms" }}
                  />
                );
              })}
              <text
                x={slotX + slot / 2}
                y={H - 8}
                textAnchor="middle"
                fill={AXIS_TEXT}
                style={{ fontSize: 10 }}
              >
                {row.label}
              </text>
            </g>
          );
        })}

        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={PAD.top + plotH}
          y2={PAD.top + plotH}
          stroke={GRID}
          strokeWidth="1"
        />
      </Box>

      <Tooltip point={hover} />
    </Box>
  );
}

/**
 * Horizontal bars for ranked categories. Values are direct-labelled at the
 * bar end, so nothing here is encoded by colour alone.
 */
export function HBarChart({ rows, formatValue = (v) => v, labelWidth = 168 }) {
  const max = Math.max(1, ...rows.map((r) => r.value));

  return (
    <Stack spacing={1.25}>
      {rows.map((row) => (
        <Stack key={row.label} direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <Typography
            variant="caption"
            sx={{
              width: labelWidth,
              flexShrink: 0,
              color: "text.secondary",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={row.label}
          >
            {row.label}
          </Typography>

          <Box sx={{ flex: 1, minWidth: 0, height: 10, position: "relative" }}>
            <Box
              sx={{
                position: "absolute",
                inset: 0,
                borderRadius: 1,
                bgcolor: "rgba(255,255,255,0.04)",
              }}
            />
            <Box
              sx={{
                position: "absolute",
                left: 0,
                top: 0,
                bottom: 0,
                width: `${Math.max((row.value / max) * 100, row.value > 0 ? 2 : 0)}%`,
                borderRadius: 1,
                bgcolor: row.color ?? SERIES[0],
              }}
            />
          </Box>

          <Typography
            variant="caption"
            sx={{
              width: 64,
              flexShrink: 0,
              textAlign: "right",
              color: "text.primary",
              fontWeight: 600,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {formatValue(row.value)}
          </Typography>
        </Stack>
      ))}
    </Stack>
  );
}

export function Legend({ series }) {
  if (series.length < 2) return null;
  return (
    <Stack direction="row" spacing={2} sx={{ mb: 1.5 }}>
      {series.map((s, i) => (
        <Stack key={s.key} direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
          <Box sx={{ width: 8, height: 8, borderRadius: "2px", bgcolor: SERIES[i] }} />
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            {s.name}
          </Typography>
        </Stack>
      ))}
    </Stack>
  );
}
