import { useState } from "react";
import { Box, Stack, Typography } from "@mui/material";

/**
 * Where this product is sold from, and where it would come to.
 *
 * Every mark is a listing that exists. The dots are the countries the
 * comparable listings are actually located in, sized by how many; the arc is
 * the journey this specific purchase would make; the counts come back from
 * the same search that produced the price median beside it. Hovering a
 * country tells you how many listings are there.
 *
 * There are no coastlines, and that is deliberate rather than unfinished. A
 * continent outline drawn from memory would be wrong in exactly the way
 * nobody notices — markers landing in the sea, borders in the wrong place —
 * and this panel's whole argument is that what it shows can be trusted. The
 * graticule is real: every line is a true parallel or meridian, and every
 * dot sits at its country's real coordinates. Give it a coastline dataset
 * and the same projection draws continents underneath, unchanged.
 */

// Country centroids, degrees. Reference data, not measurements — used only
// to place a dot where a country is.
const CENTROIDS = {
  IN: [22.0, 79.0], US: [39.5, -98.5], CN: [35.9, 104.2], HK: [22.3, 114.2],
  GB: [54.0, -2.0], DE: [51.2, 10.4], JP: [36.2, 138.3], CA: [56.1, -106.3],
  AU: [-25.3, 133.8], SG: [1.35, 103.8], AE: [23.4, 53.8], KR: [35.9, 127.8],
  FR: [46.2, 2.2], IT: [41.9, 12.6], ES: [40.5, -3.7], NL: [52.1, 5.3],
  PL: [51.9, 19.1], VN: [14.1, 108.3], TH: [15.9, 101.0], MY: [4.2, 101.98],
  TW: [23.7, 121.0], MX: [23.6, -102.6], BR: [-14.2, -51.9], ZA: [-30.6, 22.9],
  IL: [31.0, 34.9], TR: [39.0, 35.2], CH: [46.8, 8.2], SE: [60.1, 18.6],
  IE: [53.4, -8.2], NZ: [-40.9, 174.9], PH: [12.9, 121.8], ID: [-0.8, 113.9],
  PT: [39.4, -8.2], AT: [47.5, 14.6], BE: [50.5, 4.5], CZ: [49.8, 15.5],
  DK: [56.3, 9.5], FI: [61.9, 25.7], NO: [60.5, 8.5], RO: [45.9, 25.0],
  HU: [47.2, 19.5], GR: [39.1, 21.8], LT: [55.2, 23.9], EE: [58.6, 25.0],
  LV: [56.9, 24.6], PK: [30.4, 69.3], BD: [23.7, 90.4], LK: [7.9, 80.8],
  RU: [61.5, 105.3], UA: [48.4, 31.2],
};

const NAMES = {
  IN: "India", US: "United States", CN: "China", HK: "Hong Kong",
  GB: "United Kingdom", DE: "Germany", JP: "Japan", CA: "Canada",
  AU: "Australia", SG: "Singapore", AE: "UAE", KR: "South Korea",
  FR: "France", IT: "Italy", ES: "Spain", NL: "Netherlands", PL: "Poland",
  VN: "Vietnam", TH: "Thailand", MY: "Malaysia", TW: "Taiwan", MX: "Mexico",
  BR: "Brazil", ZA: "South Africa", IL: "Israel", TR: "Turkey",
  CH: "Switzerland", SE: "Sweden", IE: "Ireland", NZ: "New Zealand",
  PH: "Philippines", ID: "Indonesia", PT: "Portugal", AT: "Austria",
  BE: "Belgium", CZ: "Czechia", DK: "Denmark", FI: "Finland", NO: "Norway",
  RO: "Romania", HU: "Hungary", GR: "Greece", LT: "Lithuania", EE: "Estonia",
  LV: "Latvia", PK: "Pakistan", BD: "Bangladesh", LK: "Sri Lanka",
  RU: "Russia", UA: "Ukraine",
};

const W = 720, H = 340;
const MONO = '"SF Mono", "Roboto Mono", ui-monospace, Menlo, Consolas, monospace';

// Equirectangular. The simplest true projection there is: x is longitude,
// y is latitude, both linear. Nothing is distorted beyond what that implies.
const project = ([lat, lon]) => [
  ((lon + 180) / 360) * W,
  ((90 - lat) / 180) * H,
];

export default function ShippingMap({ origin, destination, origins }) {
  const [hover, setHover] = useState(null);

  const counts = origins || {};
  const plotted = Object.entries(counts)
    .filter(([code]) => CENTROIDS[code])
    .sort((a, b) => b[1] - a[1]);
  const most = Math.max(1, ...plotted.map(([, n]) => n));

  const from = CENTROIDS[origin] ? project(CENTROIDS[origin]) : null;
  const to = CENTROIDS[destination] ? project(CENTROIDS[destination]) : null;
  // Bowed upward so the route reads as a journey rather than a chord, and
  // so it does not run straight through the marker labels.
  const arc = from && to
    ? `M${from[0]},${from[1]} Q${(from[0] + to[0]) / 2},${Math.min(from[1], to[1]) - 58} ${to[0]},${to[1]}`
    : null;

  const meridians = [-150, -120, -90, -60, -30, 0, 30, 60, 90, 120, 150];
  const parallels = [-60, -40, -20, 0, 20, 40, 60];

  return (
    <Box sx={{ px: 1.5, pb: 1.5 }}>
      <Box sx={{ position: "relative", border: "1px solid rgba(255,255,255,0.07)",
                 borderRadius: 1, bgcolor: "rgba(255,255,255,0.015)", overflow: "hidden" }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ display: "block", width: "100%", height: "auto" }}>
          <defs>
            <linearGradient id="cs-route" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#F59E0B" stopOpacity="0.15" />
              <stop offset="55%" stopColor="#F59E0B" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#22C55E" stopOpacity="0.95" />
            </linearGradient>
            <radialGradient id="cs-halo">
              <stop offset="0%" stopColor="#22C55E" stopOpacity="0.5" />
              <stop offset="100%" stopColor="#22C55E" stopOpacity="0" />
            </radialGradient>
          </defs>

          {/* Graticule — real parallels and meridians, nothing invented. */}
          {meridians.map((lon) => {
            const x = ((lon + 180) / 360) * W;
            return <line key={`m${lon}`} x1={x} y1="0" x2={x} y2={H}
                         stroke="rgba(255,255,255,0.09)" strokeWidth="1" />;
          })}
          {parallels.map((lat) => {
            const y = ((90 - lat) / 180) * H;
            return (
              <line key={`p${lat}`} x1="0" y1={y} x2={W} y2={y}
                    stroke={lat === 0 ? "rgba(255,255,255,0.20)" : "rgba(255,255,255,0.09)"}
                    strokeWidth="1"
                    strokeDasharray={lat === 0 ? "none" : "2 6"} />
            );
          })}
          <text x="6" y={((90 - 0) / 180) * H - 5} fill="rgba(255,255,255,0.3)"
                style={{ fontFamily: MONO, fontSize: 8, letterSpacing: "0.1em" }}>
            EQUATOR
          </text>
          {meridians.filter((lon) => lon % 60 === 0).map((lon) => (
            <text key={`lbl${lon}`} x={((lon + 180) / 360) * W + 4} y={H - 6}
                  fill="rgba(255,255,255,0.26)"
                  style={{ fontFamily: MONO, fontSize: 7.5 }}>
              {lon === 0 ? "0°" : `${Math.abs(lon)}°${lon < 0 ? "W" : "E"}`}
            </text>
          ))}

          {/* The journey this purchase would make. */}
          {arc && (
            <>
              <path d={arc} fill="none" stroke="url(#cs-route)" strokeWidth="1.6"
                    strokeDasharray="5 5">
                <animate attributeName="stroke-dashoffset" from="20" to="0"
                         dur="1.1s" repeatCount="indefinite" />
              </path>
              <circle cx={to[0]} cy={to[1]} r="16" fill="url(#cs-halo)" />
            </>
          )}

          {/* One dot per country that actually has listings. */}
          {plotted.map(([code, n]) => {
            const [x, y] = project(CENTROIDS[code]);
            const r = 3.5 + (n / most) * 7;
            const isOrigin = code === origin;
            return (
              <g key={code}
                 onMouseEnter={() => setHover({ code, n, x, y })}
                 onMouseLeave={() => setHover(null)}
                 style={{ cursor: "pointer" }}>
                <circle cx={x} cy={y} r={r + 9} fill="transparent" />
                <circle cx={x} cy={y} r={r}
                        fill={isOrigin ? "#F59E0B" : "rgba(122,131,148,0.55)"}
                        stroke={isOrigin ? "#F59E0B" : "rgba(255,255,255,0.25)"}
                        strokeWidth={isOrigin ? 1.5 : 1}
                        opacity={hover && hover.code !== code ? 0.35 : 1}
                        style={{ transition: "opacity 160ms" }} />
                {isOrigin && (
                  <circle cx={x} cy={y} r={r} fill="none" stroke="#F59E0B" strokeWidth="1">
                    <animate attributeName="r" from={r} to={r + 13} dur="1.9s" repeatCount="indefinite" />
                    <animate attributeName="opacity" from="0.7" to="0" dur="1.9s" repeatCount="indefinite" />
                  </circle>
                )}
              </g>
            );
          })}

          {/* Destination, always drawn even when no listing sits there. */}
          {to && (
            <g>
              <circle cx={to[0]} cy={to[1]} r="4.5" fill="#22C55E" />
              <text x={to[0] + 9} y={to[1] + 3.5} fill="#22C55E"
                    style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.08em" }}>
                {NAMES[destination] ?? destination}
              </text>
            </g>
          )}

          {hover && (
            <g pointerEvents="none">
              <rect x={Math.min(hover.x + 10, W - 132)} y={hover.y - 26}
                    width="126" height="21" rx="3"
                    fill="rgba(8,9,12,0.94)" stroke="rgba(255,255,255,0.16)" />
              <text x={Math.min(hover.x + 16, W - 126)} y={hover.y - 11}
                    fill="#E7E9EE" style={{ fontFamily: MONO, fontSize: 9 }}>
                {(NAMES[hover.code] ?? hover.code).slice(0, 16)} · {hover.n} listing{hover.n === 1 ? "" : "s"}
              </text>
            </g>
          )}
        </svg>
      </Box>

      <Stack direction="row" spacing={2} sx={{ mt: 1, flexWrap: "wrap", gap: 0.5 }}>
        <Legend colour="#F59E0B" label={`Ships from ${NAMES[origin] ?? origin ?? "—"}`} />
        <Legend colour="#22C55E" label={`Delivers to ${NAMES[destination] ?? destination}`} />
        <Legend colour="rgba(122,131,148,0.55)"
                label={plotted.length === 1
                  ? "1 country selling this"
                  : `${plotted.length} countries selling this`} />
      </Stack>
      <Typography sx={{ fontSize: 10, color: "text.disabled", mt: 0.75, lineHeight: 1.6 }}>
        Dot size is how many comparable listings are in that country, counted from the
        search above. Positions are true coordinates on an equirectangular projection;
        no coastlines are drawn, because none are in the data.
      </Typography>
    </Box>
  );
}

function Legend({ colour, label }) {
  return (
    <Stack direction="row" spacing={0.6} sx={{ alignItems: "center" }}>
      <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: colour, flexShrink: 0 }} />
      <Typography sx={{ fontFamily: MONO, fontSize: 9, color: "text.secondary" }}>
        {label}
      </Typography>
    </Stack>
  );
}
