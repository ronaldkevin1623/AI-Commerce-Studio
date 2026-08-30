import { useEffect, useState } from "react";
import { Box, Button, Stack, Typography, CircularProgress } from "@mui/material";
import CheckIcon from "@mui/icons-material/CheckCircleOutlineOutlined";
import WarnIcon from "@mui/icons-material/ReportProblemOutlined";
import FailIcon from "@mui/icons-material/ErrorOutlineOutlined";
import UnknownIcon from "@mui/icons-material/HelpOutlineOutlined";
import ReplayIcon from "@mui/icons-material/Replay";
import CloseIcon from "@mui/icons-material/Close";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";

import { API_BASE } from "../../config";
import ShippingMap from "../console/ShippingMap";

/**
 * One listing, audited, as a board of cards.
 *
 * Every card is one check, and every number on it came back from the run
 * that drew it — the median is of listings fetched at that moment, the
 * seller percentages are eBay's, the origin counts are counted. Cards whose
 * check has a figure worth seeing show it large; cards whose check is a
 * yes-or-no say so in a word. None of them show a metric that was chosen to
 * fill the space, which is why the grid is not uniform: some checks simply
 * have less to report than others, and padding them out would be inventing.
 */

const STATUS = {
  pass: { icon: CheckIcon, color: "#22C55E", tint: "rgba(34,197,94,0.10)",
          edge: "rgba(34,197,94,0.28)", word: "PASS" },
  warn: { icon: WarnIcon, color: "#F59E0B", tint: "rgba(245,158,11,0.10)",
          edge: "rgba(245,158,11,0.30)", word: "NOTE" },
  fail: { icon: FailIcon, color: "#EF4444", tint: "rgba(239,68,68,0.10)",
          edge: "rgba(239,68,68,0.32)", word: "FAIL" },
  unknown: { icon: UnknownIcon, color: "#7A8394", tint: "rgba(255,255,255,0.03)",
             edge: "rgba(255,255,255,0.10)", word: "N/A" },
};

const VERDICT = {
  clear: { line: "Nothing flagged", color: "#22C55E" },
  caution: { line: "Look before buying", color: "#F59E0B" },
  high_risk: { line: "Do not buy blind", color: "#EF4444" },
};

const MONO = '"SF Mono", "Roboto Mono", ui-monospace, Menlo, Consolas, monospace';

const inr = (paise) => `₹${Math.round((paise ?? 0) / 100).toLocaleString("en-IN")}`;

const CARD = {
  border: "1px solid",
  borderColor: "divider",
  borderRadius: 2.5,
  bgcolor: "background.paper",
  p: 2,
};

/**
 * The headline figure a check produced, when it has one.
 *
 * Only four of the checks measure something — the price against the market,
 * the seller's record, how many countries sell it, and the suite's standing.
 * The rest return a verdict and nothing else, and are drawn without a number
 * rather than given one.
 */
function headline(check) {
  const e = check.evidence || {};
  if (check.id === "price" && e.median_paise) {
    return { value: inr(e.median_paise), unit: "market median",
             foot: `${e.comparables} comparable listings` };
  }
  if (check.id === "seller" && e.feedback != null) {
    return { value: `${e.feedback}%`, unit: "positive feedback",
             foot: `${(e.count ?? 0).toLocaleString("en-IN")} ratings` };
  }
  if (check.id === "origin" && e.origins) {
    const n = Object.keys(e.origins).length;
    return { value: String(n), unit: n === 1 ? "country selling it" : "countries selling it",
             foot: e.origin ? `this one ships from ${e.origin}` : null };
  }
  if (check.id === "suite" && e.total) {
    return { value: `${e.held}/${e.total}`, unit: "attacks blocked",
             foot: "on the agent, not this listing" };
  }
  return null;
}

function CheckCard({ check, wide }) {
  const meta = STATUS[check.status] ?? STATUS.unknown;
  const Icon = meta.icon;
  const figure = headline(check);

  return (
    <Box
      sx={{
        ...CARD,
        gridColumn: wide ? { xs: "auto", md: "span 2" } : "auto",
        borderColor: meta.edge,
        position: "relative",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        "&::before": {
          content: '""', position: "absolute", inset: 0,
          background: `radial-gradient(120% 100% at 0% 0%, ${meta.tint}, transparent 60%)`,
          pointerEvents: "none",
        },
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.25 }}>
        <Icon sx={{ fontSize: 17, color: meta.color }} />
        <Typography sx={{ fontSize: 13, fontWeight: 600, flex: 1, lineHeight: 1.35 }}>
          {check.label}
        </Typography>
        <Typography
          sx={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.1em",
                color: meta.color, border: "1px solid", borderColor: meta.edge,
                borderRadius: 1, px: 0.7, py: 0.2, flexShrink: 0 }}
        >
          {meta.word}
        </Typography>
      </Stack>

      {figure && (
        <Box sx={{ mb: 1.25 }}>
          <Typography sx={{ fontSize: 26, fontWeight: 700, lineHeight: 1.05,
                            fontVariantNumeric: "tabular-nums", color: meta.color }}>
            {figure.value}
          </Typography>
          <Typography sx={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.12em",
                            color: "text.disabled", mt: 0.4 }}>
            {figure.unit.toUpperCase()}
          </Typography>
          {figure.foot && (
            <Typography sx={{ fontSize: 10.5, color: "text.disabled", mt: 0.3 }}>
              {figure.foot}
            </Typography>
          )}
        </Box>
      )}

      <Typography sx={{ fontSize: 11.5, lineHeight: 1.65, color: "text.secondary" }}>
        {check.detail}
      </Typography>
    </Box>
  );
}

export default function ProductAuditBoard({ product, onClear }) {
  const [report, setReport] = useState(null);
  // Idle until asked. Auditing on arrival spent eBay calls before anyone had
  // looked at the listing, and put a verdict on screen next to a product the
  // person had not yet decided they were considering — the result read as
  // something the page already knew rather than something it went and found.
  const [state, setState] = useState("idle");
  const [error, setError] = useState(null);

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
        setError(typeof data.detail === "string" ? data.detail : "The audit could not run.");
        return;
      }
      setReport(data);
      setState("done");
    } catch {
      setState("error");
      setError("Couldn't reach the backend.");
    }
  };

  // A different listing is a different question: drop the previous answer
  // rather than showing one listing's verdict above another's name.
  useEffect(() => {
    setReport(null);
    setState("idle");
    setError(null);
  }, [product?.id]);

  const tone = VERDICT[report?.verdict] ?? VERDICT.caution;
  const originCheck = report?.checks.find((c) => c.id === "origin");
  const failed = report?.checks.filter((c) => c.status === "fail").length ?? 0;
  const noted = report?.checks.filter(
    (c) => c.status === "warn" || c.status === "unknown").length ?? 0;

  return (
    <Box sx={{ mb: 3 }}>
      <style>{`
        @keyframes cs-card-in {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: none; }
        }
      `}</style>

      {/* Which listing is on the bench */}
      <Box sx={{ ...CARD, mb: 2, p: 1.75 }}>
        <Stack direction="row" spacing={1.75} sx={{ alignItems: "center" }}>
          {product.image && (
            <Box component="img" src={product.image} alt=""
                 sx={{ width: 46, height: 46, borderRadius: 1.5, objectFit: "cover",
                       flexShrink: 0, bgcolor: "rgba(255,255,255,0.04)" }} />
          )}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.14em",
                              color: "text.disabled" }}>
              LISTING UNDER AUDIT
            </Typography>
            <Typography sx={{ fontSize: 13.5, fontWeight: 600, mt: 0.25,
                              overflow: "hidden", textOverflow: "ellipsis",
                              whiteSpace: "nowrap" }}>
              {product.name}
            </Typography>
            <Typography sx={{ fontSize: 12, color: "text.secondary" }}>
              {inr(product.price_paise)}
              {product.condition ? ` · ${product.condition}` : ""}
            </Typography>
          </Box>
          <Button size="small" onClick={onClear} startIcon={<CloseIcon sx={{ fontSize: 15 }} />}
                  sx={{ color: "text.secondary", fontSize: 11.5, flexShrink: 0 }}>
            Clear
          </Button>
        </Stack>
      </Box>

      {state === "idle" && (
        <Box sx={{ ...CARD, textAlign: "center", py: 4.5 }}>
          <ShieldOutlinedIcon sx={{ fontSize: 26, color: "text.secondary" }} />
          <Typography sx={{ fontSize: 14, fontWeight: 600, mt: 1.25 }}>
            Nothing has been checked yet
          </Typography>
          <Typography sx={{ fontSize: 12, color: "text.secondary", mt: 0.75,
                            maxWidth: 460, mx: "auto", lineHeight: 1.7 }}>
            Eight checks are ready to run against this listing: whether it is
            still live at that price, how it prices against comparable
            listings on sale right now, what eBay says about the seller,
            whether the listing contradicts itself, whether its text is
            addressed to the agent, and where it ships from. Each one reads
            live data at the moment you press the button.
          </Typography>
          <Button
            variant="contained"
            onClick={run}
            startIcon={<PlayArrowIcon sx={{ fontSize: 18 }} />}
            sx={{ mt: 2.5, py: 1, px: 2.5 }}
          >
            Run the security check
          </Button>
        </Box>
      )}

      {state === "running" && (
        <Box sx={{ ...CARD, textAlign: "center", py: 5 }}>
          <CircularProgress size={22} sx={{ color: "#22C55E" }} />
          <Typography sx={{ fontFamily: MONO, fontSize: 11, color: "text.secondary", mt: 2 }}>
            AUDITING THIS LISTING
          </Typography>
          <Typography sx={{ fontSize: 11.5, color: "text.disabled", mt: 0.75 }}>
            Re-reading it from eBay, pricing it against comparable listings,
            reading the seller's record and scanning the text.
          </Typography>
        </Box>
      )}

      {state === "error" && (
        <Box sx={{ ...CARD, textAlign: "center", py: 4 }}>
          <FailIcon sx={{ fontSize: 24, color: "#EF4444" }} />
          <Typography sx={{ fontSize: 12.5, color: "text.secondary", mt: 1.5 }}>{error}</Typography>
          <Button onClick={run} startIcon={<ReplayIcon sx={{ fontSize: 15 }} />} sx={{ mt: 1.5 }}>
            Try again
          </Button>
        </Box>
      )}

      {state === "done" && report && (
        <>
          {/* The verdict, and the two counts that qualify it */}
          <Box
            sx={{
              display: "grid", gap: 1.5, mb: 1.5,
              gridTemplateColumns: { xs: "1fr", sm: "2fr 1fr 1fr 1fr" },
            }}
          >
            <Box sx={{ ...CARD, borderColor: tone.color + "55",
                       background: `linear-gradient(135deg, ${tone.color}1A, transparent 70%)` }}>
              <Typography sx={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.14em",
                                color: "text.disabled" }}>
                VERDICT
              </Typography>
              <Typography sx={{ fontSize: 20, fontWeight: 700, color: tone.color, mt: 0.5 }}>
                {tone.line}
              </Typography>
              <Typography sx={{ fontSize: 11.5, color: "text.secondary", mt: 0.5 }}>
                {report.passed} of {report.total} checks passed, in{" "}
                {(report.took_ms / 1000).toFixed(1)}s.
              </Typography>
            </Box>
            <Stat label="PASSED" value={report.passed} colour="#22C55E" />
            <Stat label="FAILED" value={failed} colour={failed ? "#EF4444" : undefined} />
            <Stat label="NOTED" value={noted} colour={noted ? "#F59E0B" : undefined} />
          </Box>

          {/* One card per check */}
          <Box
            sx={{
              display: "grid", gap: 1.5,
              gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", lg: "1fr 1fr 1fr" },
            }}
          >
            {report.checks.map((check, i) => (
              <Box key={check.id} sx={{ animation: `cs-card-in 340ms ${i * 60}ms both`,
                                        display: "contents" }}>
                <CheckCard check={check} />
              </Box>
            ))}
          </Box>

          {/* The map earns a full-width card of its own */}
          {originCheck?.evidence?.origins && (
            <Box sx={{ ...CARD, mt: 1.5, p: 0, pt: 2 }}>
              <Typography sx={{ fontSize: 13, fontWeight: 600, px: 2, mb: 0.5 }}>
                Where this product is sold from
              </Typography>
              <ShippingMap
                origin={originCheck.evidence.origin}
                destination={originCheck.evidence.destination || "IN"}
                origins={originCheck.evidence.origins}
              />
            </Box>
          )}

          <Stack direction="row" spacing={1} sx={{ mt: 1.5, alignItems: "center" }}>
            <Button onClick={run} startIcon={<ReplayIcon sx={{ fontSize: 15 }} />}
                    sx={{ fontSize: 12, color: "text.secondary" }}>
              Audit again
            </Button>
            <Typography sx={{ fontSize: 11, color: "text.disabled" }}>
              Nothing here is cached — every run re-reads the listing.
            </Typography>
          </Stack>
        </>
      )}
    </Box>
  );
}

function Stat({ label, value, colour }) {
  return (
    <Box sx={{ ...CARD }}>
      <Typography sx={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.14em",
                        color: "text.disabled" }}>
        {label}
      </Typography>
      <Typography sx={{ fontSize: 26, fontWeight: 700, mt: 0.4,
                        fontVariantNumeric: "tabular-nums",
                        color: colour || "text.primary" }}>
        {value}
      </Typography>
    </Box>
  );
}
