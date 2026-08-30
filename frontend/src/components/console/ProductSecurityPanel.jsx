import { useEffect, useRef, useState } from "react";
import { Box, Button, Stack, Typography, CircularProgress } from "@mui/material";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import CheckIcon from "@mui/icons-material/CheckCircleOutlineOutlined";
import WarnIcon from "@mui/icons-material/ReportProblemOutlined";
import FailIcon from "@mui/icons-material/ErrorOutlineOutlined";
import UnknownIcon from "@mui/icons-material/HelpOutlineOutlined";
import ReplayIcon from "@mui/icons-material/Replay";

import { API_BASE } from "../../config";
import ShippingMap from "./ShippingMap";

/**
 * One listing, put through the checks, in an operations-console register.
 *
 * The look is borrowed; the numbers are not. Every figure on this panel
 * comes back from the run that produced it — the median is of listings
 * fetched at that moment, the seller percentages are eBay's own, the timing
 * is measured. There is no gauge here whose needle was chosen to look busy,
 * because a security panel that decorates itself with invented telemetry is
 * exactly the thing it claims to protect people from.
 *
 * That constraint is also why there is no live threat counter, and why the
 * map shows shipping origins rather than attacks. A globe with hostile
 * traffic arcing across it would look magnificent and would be entirely
 * invented; where the listings actually are is real, and turns out to be
 * the more useful thing to know before paying.
 */

const VERDICT = {
  clear: {
    line: "NOTHING FLAGGED",
    body: "Every check this can run came back clean.",
    color: "#22C55E", glow: "rgba(34,197,94,0.18)", track: "rgba(34,197,94,0.30)",
  },
  caution: {
    line: "LOOK BEFORE BUYING",
    body: "Some checks could not be completed, or came back worth reading.",
    color: "#F59E0B", glow: "rgba(245,158,11,0.16)", track: "rgba(245,158,11,0.30)",
  },
  high_risk: {
    line: "DO NOT BUY BLIND",
    body: "At least one check failed outright. The detail is below.",
    color: "#EF4444", glow: "rgba(239,68,68,0.16)", track: "rgba(239,68,68,0.32)",
  },
};

const STATUS = {
  pass: { icon: CheckIcon, color: "#22C55E", word: "PASS" },
  warn: { icon: WarnIcon, color: "#F59E0B", word: "NOTE" },
  fail: { icon: FailIcon, color: "#EF4444", word: "FAIL" },
  unknown: { icon: UnknownIcon, color: "#7A8394", word: "N/A" },
};

const MONO = '"SF Mono", "Roboto Mono", ui-monospace, Menlo, Consolas, monospace';

/**
 * Passed-out-of-total, as an arc.
 *
 * A ring rather than a bar because the number it carries is a proportion of
 * a whole that is known and small — seven checks, not an open-ended count.
 * The arc is drawn to the real fraction; there is no minimum sweep to make
 * a bad result look less bad.
 */
function VerdictRing({ passed, total, tone }) {
  const size = 132, stroke = 8, radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const fraction = total ? passed / total : 0;

  return (
    <Box sx={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none"
                stroke="rgba(255,255,255,0.07)" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none"
          stroke={tone.color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - fraction)}
          style={{ transition: "stroke-dashoffset 700ms cubic-bezier(0.22,1,0.36,1)" }}
        />
      </svg>
      <Box sx={{ position: "absolute", inset: 0, display: "flex",
                 flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <Typography sx={{ fontFamily: MONO, fontSize: 30, fontWeight: 700,
                          lineHeight: 1, color: tone.color }}>
          {passed}<Box component="span" sx={{ opacity: 0.35, fontSize: 18 }}>/{total}</Box>
        </Typography>
        <Typography sx={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.16em",
                          color: "text.disabled", mt: 0.5 }}>
          CHECKS PASSED
        </Typography>
      </Box>
    </Box>
  );
}

/** A figure the run actually measured, in the console's register. */
function Readout({ label, value, tone }) {
  return (
    <Box sx={{ flex: 1, minWidth: 88, px: 1.25, py: 1,
               border: "1px solid", borderColor: "rgba(255,255,255,0.08)",
               borderRadius: 1, bgcolor: "rgba(255,255,255,0.02)" }}>
      <Typography sx={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: "0.14em",
                        color: "text.disabled" }}>
        {label}
      </Typography>
      <Typography sx={{ fontFamily: MONO, fontSize: 15, fontWeight: 700,
                        color: tone || "text.primary", mt: 0.25,
                        fontVariantNumeric: "tabular-nums" }}>
        {value}
      </Typography>
    </Box>
  );
}

function CheckRow({ check, index }) {
  const meta = STATUS[check.status] ?? STATUS.unknown;
  const Icon = meta.icon;
  return (
    <Box
      sx={{
        display: "flex", gap: 1.25, alignItems: "flex-start",
        px: 1.5, py: 1.25,
        borderLeft: "2px solid", borderLeftColor: meta.color,
        bgcolor: check.status === "pass" ? "transparent" : "rgba(255,255,255,0.025)",
        borderBottom: "1px solid", borderBottomColor: "rgba(255,255,255,0.05)",
        animation: `cs-check-in 320ms ${index * 55}ms both`,
      }}
    >
      <Icon sx={{ fontSize: 16, color: meta.color, mt: "1px", flexShrink: 0 }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "baseline" }}>
          <Typography sx={{ fontSize: 12.5, fontWeight: 600, flex: 1 }}>
            {check.label}
          </Typography>
          <Typography sx={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.1em",
                            color: meta.color, flexShrink: 0 }}>
            {meta.word}
          </Typography>
        </Stack>
        <Typography sx={{ fontSize: 11.5, lineHeight: 1.6, color: "text.secondary", mt: 0.4 }}>
          {check.detail}
        </Typography>
      </Box>
    </Box>
  );
}

export default function ProductSecurityPanel({ product, onClose }) {
  const [report, setReport] = useState(null);
  const [state, setState] = useState("running"); // running | done | error
  const [error, setError] = useState(null);
  // Runs once per open, and again only when asked. A check that re-fired on
  // every render would spend eBay calls to tell nobody anything.
  const startedFor = useRef(null);

  const run = async () => {
    setState("running");
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/product-check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setState("error");
        setError(typeof data.detail === "string" ? data.detail : "The check could not run.");
        return;
      }
      setReport(data);
      setState("done");
    } catch {
      setState("error");
      setError("Couldn't reach the backend.");
    }
  };

  useEffect(() => {
    if (!product?.id || startedFor.current === product.id) return;
    startedFor.current = product.id;
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [product?.id]);

  const tone = VERDICT[report?.verdict] ?? VERDICT.caution;
  const failed = report?.checks.filter((c) => c.status === "fail").length ?? 0;
  const noted = report?.checks.filter(
    (c) => c.status === "warn" || c.status === "unknown").length ?? 0;

  return (
    <Box sx={{ bgcolor: "#08090C", minHeight: "100%" }}>
      <style>{`
        @keyframes cs-check-in {
          from { opacity: 0; transform: translateX(-6px); }
          to   { opacity: 1; transform: none; }
        }
        @keyframes cs-scan {
          0%   { transform: translateY(-100%); opacity: 0; }
          40%  { opacity: 1; }
          100% { transform: translateY(320px); opacity: 0; }
        }
      `}</style>

      {/* Header */}
      <Box sx={{ px: 2, py: 1.5, borderBottom: "1px solid rgba(255,255,255,0.08)",
                 display: "flex", alignItems: "center", gap: 1 }}>
        <ShieldOutlinedIcon sx={{ fontSize: 16, color: "text.secondary" }} />
        <Typography sx={{ fontFamily: MONO, fontSize: 10.5, letterSpacing: "0.16em",
                          color: "text.secondary", flex: 1 }}>
          LISTING SECURITY CHECK
        </Typography>
        <Button size="small" onClick={onClose}
                sx={{ fontFamily: MONO, fontSize: 10, color: "text.disabled", minWidth: 0 }}>
          CLOSE
        </Button>
      </Box>

      {state === "running" && (
        <Box sx={{ position: "relative", overflow: "hidden", px: 3, py: 7,
                   textAlign: "center" }}>
          <Box sx={{ position: "absolute", left: 0, right: 0, height: 1,
                     bgcolor: "rgba(34,197,94,0.5)",
                     boxShadow: "0 0 12px 2px rgba(34,197,94,0.35)",
                     animation: "cs-scan 1.4s linear infinite" }} />
          <CircularProgress size={22} sx={{ color: "#22C55E" }} />
          <Typography sx={{ fontFamily: MONO, fontSize: 11, color: "text.secondary", mt: 2 }}>
            RE-READING THE LISTING FROM EBAY
          </Typography>
          <Typography sx={{ fontSize: 11, color: "text.disabled", mt: 0.75, maxWidth: 300, mx: "auto" }}>
            Live price, comparable listings, seller record and listing text.
            Nothing here is cached.
          </Typography>
        </Box>
      )}

      {state === "error" && (
        <Box sx={{ px: 2.5, py: 4, textAlign: "center" }}>
          <FailIcon sx={{ fontSize: 26, color: "#EF4444" }} />
          <Typography sx={{ fontSize: 12.5, color: "text.secondary", mt: 1.5 }}>{error}</Typography>
          <Button onClick={run} startIcon={<ReplayIcon sx={{ fontSize: 15 }} />}
                  sx={{ mt: 2, fontSize: 12 }}>
            Try again
          </Button>
        </Box>
      )}

      {state === "done" && report && (
        <>
          {/* Verdict */}
          <Box sx={{ px: 2.5, py: 2.5, bgcolor: tone.glow,
                     borderBottom: "1px solid", borderBottomColor: tone.track }}>
            <Stack direction="row" spacing={2.5} sx={{ alignItems: "center" }}>
              <VerdictRing passed={report.passed} total={report.total} tone={tone} />
              <Box sx={{ minWidth: 0 }}>
                <Typography sx={{ fontFamily: MONO, fontSize: 15, fontWeight: 700,
                                  letterSpacing: "0.06em", color: tone.color }}>
                  {tone.line}
                </Typography>
                <Typography sx={{ fontSize: 12, color: "text.secondary",
                                  mt: 0.75, lineHeight: 1.6 }}>
                  {tone.body}
                </Typography>
              </Box>
            </Stack>

            <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
              <Readout label="FAILED" value={failed}
                       tone={failed ? "#EF4444" : undefined} />
              <Readout label="NOTED" value={noted}
                       tone={noted ? "#F59E0B" : undefined} />
              <Readout label="RUN TIME" value={`${(report.took_ms / 1000).toFixed(1)}s`} />
            </Stack>
          </Box>

          <Box>
            {report.checks.map((check, i) => (
              <Box key={check.id}>
                <CheckRow check={check} index={i} />
                {/* The map belongs to the check it illustrates, so the
                    countries on it are the ones that row is talking about. */}
                {check.id === "origin" && check.evidence?.origins && (
                  <ShippingMap
                    origin={check.evidence.origin}
                    destination={check.evidence.destination || "IN"}
                    origins={check.evidence.origins}
                  />
                )}
              </Box>
            ))}
          </Box>

          {/* The limit, stated where it cannot be missed. */}
          <Box sx={{ px: 2.5, py: 2 }}>
            <Typography sx={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.14em",
                              color: "text.disabled" }}>
              WHAT THIS DOES NOT PROVE
            </Typography>
            <Typography sx={{ fontSize: 11.5, lineHeight: 1.75, color: "text.secondary", mt: 0.75 }}>
              These are the signals that can be verified from outside a
              listing: whether it still exists, what comparable ones cost,
              what eBay says about the seller, and whether the text is
              addressed to the agent. They cannot tell you the item in the
              box is genuine, and a clean result is not a promise that a
              purchase will go well — it means nothing was found by the
              checks that ran, which is a smaller claim and the only honest
              one.
            </Typography>
            <Button onClick={run} startIcon={<ReplayIcon sx={{ fontSize: 15 }} />}
                    sx={{ mt: 1.5, fontSize: 11.5, color: "text.secondary" }}>
              Run the checks again
            </Button>
          </Box>
        </>
      )}
    </Box>
  );
}
