import { useCallback, useEffect, useState } from "react";
import {
  Box, Button, Stack, Typography, CircularProgress, Collapse,
} from "@mui/material";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlineOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import { API_BASE } from "../config";
import ProductAuditBoard from "../components/redteam/ProductAuditBoard";

const CARD = {
  border: "1px solid",
  borderColor: "divider",
  borderRadius: 2.5,
  bgcolor: "background.paper",
};

const SEVERITY = {
  critical: { label: "Critical", color: "#EF4444", bg: "rgba(239,68,68,0.12)" },
  high: { label: "High", color: "#F59E0B", bg: "rgba(245,158,11,0.12)" },
  moderate: { label: "Moderate", color: "#9AA3B2", bg: "rgba(255,255,255,0.06)" },
};

/**
 * One severity, with how many of its attacks held.
 *
 * A count is not a chart. Three numbers with a tinted rule read faster than
 * any plot of them would, and the rule carries the severity so the tile is
 * legible before the label is read.
 */
function SeverityTile({ label, tone, total, held, ran }) {
  return (
    <Box
      sx={{
        flex: 1, minWidth: 132, p: 1.75, borderRadius: 2,
        bgcolor: "background.paper", border: "1px solid", borderColor: "divider",
        borderTop: "2px solid", borderTopColor: tone,
      }}
    >
      <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 0.5 }}>
        {label}
      </Typography>
      <Typography
        sx={{
          fontSize: 24, fontWeight: 700, lineHeight: 1.1,
          fontVariantNumeric: "tabular-nums",
          color: ran ? (held === total ? "success.main" : "error.main") : "text.primary",
        }}
      >
        {ran ? held : total}
        {ran && <Box component="span" sx={{ opacity: 0.4 }}>/{total}</Box>}
      </Typography>
      <Typography variant="caption" sx={{ color: "text.disabled", display: "block", mt: 0.25 }}>
        {ran ? "held" : `${total === 1 ? "attack" : "attacks"} ready`}
      </Typography>
    </Box>
  );
}

/**
 * What each family of attack targets, and how it fared.
 *
 * The bar is the only real chart on the page, so its length has to carry
 * something that varies. Held-over-total does not: every family holds, so
 * every bar would run the full width and the chart would say nothing. The
 * magnitude here is how many attacks target the family — 4, 4, 3, 3, 3, 2,
 * 1, 1, 1 — and that is what the length encodes, scaled against the largest.
 *
 * Outcome then rides inside that length: the held share painted, the
 * remainder left as the track so a breach shortens a bar visibly instead of
 * only recolouring it. The count is stated in text beside it, so neither
 * length nor colour is ever the only way to read the row.
 */
function FamilyBar({ family, total, held, ran, maxTotal }) {
  const magnitude = maxTotal ? total / maxTotal : 0;
  const outcome = total ? (ran ? held / total : 1) : 0;
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", py: 0.55 }}>
      <Typography
        variant="caption"
        sx={{ width: 148, flexShrink: 0, color: "text.secondary", fontSize: 11.5 }}
      >
        {family}
      </Typography>
      <Box sx={{ flex: 1, minWidth: 60 }}>
        <Box
          sx={{
            width: `${magnitude * 100}%`, height: 6, borderRadius: 3,
            bgcolor: "rgba(255,255,255,0.06)", overflow: "hidden",
          }}
        >
          <Box
            sx={{
              width: `${outcome * 100}%`, height: "100%", borderRadius: 3,
              bgcolor: !ran ? "rgba(255,255,255,0.16)" : "success.main",
              transition: "width 320ms ease",
            }}
          />
        </Box>
      </Box>
      <Typography
        variant="caption"
        sx={{ width: 42, flexShrink: 0, textAlign: "right", fontSize: 11,
              fontVariantNumeric: "tabular-nums",
              color: ran ? (held === total ? "success.main" : "error.main") : "text.disabled" }}
      >
        {ran ? `${held}/${total}` : total}
      </Typography>
    </Stack>
  );
}

/**
 * Held-per-run across the stored history.
 *
 * One series, so no legend — the heading names it. The endpoint is
 * emphasised rather than every point being marked, and each run carries a
 * native tooltip so a reader can get the exact figures without a chart
 * library. Oldest on the left, which is the only direction time reads in.
 */
function RunTrend({ runs }) {
  const series = [...runs].sort((a, b) => (a.ran_at ?? 0) - (b.ran_at ?? 0)).slice(-30);
  if (series.length < 2) return null;

  const W = 1000, H = 42, PAD = 3;
  const step = (W - PAD * 2) / (series.length - 1);
  const ratio = (r) => (r.total ? r.held / r.total : 0);
  // A fixed 0–1 domain: rescaling to the data would turn a flat perfect
  // record into dramatic peaks, which would be a chart telling a lie.
  const y = (v) => PAD + (1 - v) * (H - PAD * 2);
  const points = series.map((r, i) => [PAD + i * step, y(ratio(r))]);
  const path = points.map(([x, py], i) => `${i ? "L" : "M"}${x.toFixed(1)},${py.toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  const lastRun = series[series.length - 1];
  const allClean = series.every((r) => (r.breached ?? 0) === 0);

  return (
    <Box sx={{ mt: 1 }}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           style={{ display: "block", width: "100%", height: "auto",
                    aspectRatio: `${W} / ${H}` }}
           aria-label={`Invariants held across the last ${series.length} runs`}>
        <line x1={PAD} y1={y(1)} x2={W - PAD} y2={y(1)}
              stroke="rgba(255,255,255,0.10)" strokeWidth="1" strokeDasharray="3 3" />
        <path d={path} fill="none" strokeWidth="2" strokeLinejoin="round"
              strokeLinecap="round" stroke={allClean ? "#22C55E" : "#F59E0B"} />
        <circle cx={last[0]} cy={last[1]} r="4"
                fill={(lastRun.breached ?? 0) === 0 ? "#22C55E" : "#EF4444"} />
        {series.map((r, i) => (
          <rect key={r.ran_at ?? i} x={points[i][0] - step / 2} y="0"
                width={Math.max(step, 6)} height={H} fill="transparent">
            <title>
              {`${new Date((r.ran_at ?? 0) * 1000).toLocaleString("en-IN", {
                day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
 — ${r.held}/${r.total} held, ${r.duration_s}s`}
            </title>
          </rect>
        ))}
      </svg>
      <Typography variant="caption" sx={{ color: "text.disabled", display: "block" }}>
        {series.length} runs · the line rides the top when every invariant holds
      </Typography>
    </Box>
  );
}

/**
 * What a shopper is protected from, in their own words.
 *
 * Each promise names a consequence somebody can care about — being charged
 * twice, being overcharged, having a limit raised behind their back — and
 * lists the attack families that test it. The families are the join: the
 * counts beside each promise are computed from the corpus, so the plain
 * sentence and the technical evidence can never disagree.
 */
const PROTECTIONS = [
  {
    id: "approval",
    promise: "Only you can approve a purchase",
    plain: "The agent cannot approve its own spending, and no text on a product page can stand in for you.",
    families: ["Authority escalation", "Gate bypass"],
  },
  {
    id: "budget",
    promise: "Your spending limit cannot be raised",
    plain: "The limit comes from what you typed. Nothing written in a listing can push it higher.",
    families: ["Mandate tampering", "Spending velocity"],
  },
  {
    id: "price",
    promise: "You pay the price you were shown",
    plain: "The amount charged is taken from the shop's own record, never from the words in a listing.",
    families: ["Price manipulation"],
  },
  {
    id: "double",
    promise: "You are never charged twice",
    plain: "If a request is repeated, you get your original order back instead of a second one.",
    families: ["Settlement fraud"],
  },
  {
    id: "sellers",
    promise: "Sellers cannot game the results",
    plain: "Stock is checked against the shop, and no listing can talk its way into being recommended.",
    families: ["Inventory manipulation", "Ranking manipulation"],
  },
  {
    id: "privacy",
    promise: "Your details stay here",
    plain: "The agent has no tool that can send your information anywhere else.",
    families: ["Data exfiltration"],
  },
];

/**
 * Bucket the corpus into the promises, dropping nothing.
 *
 * A promise list that quietly lost an attack would understate what was run,
 * which is the one failure this page cannot afford — so whatever PROTECTIONS
 * does not name is collected into a visible row of its own.
 */
function byPromise(rows) {
  const claimed = new Set();
  const groups = PROTECTIONS.map((p) => {
    const attacks = rows.filter((r) => p.families.includes(r.family));
    attacks.forEach((a) => claimed.add(a.id));
    return { ...p, attacks };
  }).filter((g) => g.attacks.length > 0);

  const rest = rows.filter((r) => !claimed.has(r.id));
  if (rest.length) {
    groups.push({
      id: "other",
      promise: "Other checks",
      plain: [...new Set(rest.map((r) => r.family))].join(", "),
      attacks: rest,
    });
  }
  return groups;
}

/**
 * One promise, with the attacks that tested it.
 *
 * The state is carried by an icon and by the words beside it, never by
 * colour alone: "6 attempts, all blocked" reads the same to someone who
 * cannot see the green.
 */
function SafetyRow({ group, ran }) {
  const total = group.attacks.length;
  const held = group.attacks.filter((a) => a.held === true).length;
  const clean = held === total;
  return (
    <Stack direction="row" spacing={1.75} sx={{ alignItems: "flex-start", py: 1.4 }}>
      <Box sx={{ width: 20, flexShrink: 0, pt: 0.2 }}>
        {!ran && <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "text.disabled", m: "6px 6px" }} />}
        {ran && clean && <CheckCircleOutlineIcon sx={{ fontSize: 19, color: "success.main" }} />}
        {ran && !clean && <ErrorOutlineIcon sx={{ fontSize: 19, color: "error.main" }} />}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontSize: 14, fontWeight: 600, mb: 0.25 }}>
          {group.promise}
        </Typography>
        <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 12.5, lineHeight: 1.6 }}>
          {group.plain}
        </Typography>
      </Box>
      <Typography
        variant="caption"
        sx={{
          flexShrink: 0, fontSize: 11.5, textAlign: "right", width: 128, pt: 0.3,
          color: !ran ? "text.disabled" : clean ? "success.main" : "error.main",
        }}
      >
        {!ran
          ? `${total} ${total === 1 ? "test" : "tests"}`
          : clean
            ? `${total} tried, all blocked`
            : `${total - held} of ${total} got through`}
      </Typography>
    </Stack>
  );
}

/**
 * Adversarial evaluation, shown in the product.
 *
 * The corpus loads on open so the page says what it will try before anyone
 * runs it; the run happens against the live pipeline on demand. Nothing here
 * is precomputed — press the button and the attacks execute for real, which
 * is the only version of this page worth having. A security claim nobody can
 * re-run in front of you is a marketing claim.
 */
export default function RedTeamPage() {
  const [corpus, setCorpus] = useState([]);
  const [report, setReport] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState({});
  const [history, setHistory] = useState([]);
  // The evidence is folded, not removed: a shopper gets the promises,
  // anyone assessing the system is one click from every payload.
  const [detail, setDetail] = useState(false);

  // A listing handed over from the product drawer. Read once on open: the
  // page is equally valid without one, and a missing product means the
  // person came here to look at the suite rather than at a purchase.
  const [audited, setAudited] = useState(() => {
    try {
      const raw = sessionStorage.getItem("commerce-studio.audit-product");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });

  const clearAudited = useCallback(() => {
    try {
      sessionStorage.removeItem("commerce-studio.audit-product");
    } catch {
      /* nothing to clear */
    }
    setAudited(null);
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/redteam/history`);
      if (res.ok) setHistory((await res.json()).runs ?? []);
    } catch {
      /* history is context, not the point of the page */
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/redteam/corpus`);
        if (res.ok) setCorpus((await res.json()).attacks ?? []);
      } catch {
        /* the run button still works; the preview is a convenience */
      }
    })();
    loadHistory();
  }, [loadHistory]);

  const run = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/redteam/run`, { method: "POST" });
      if (!res.ok) throw new Error(`Suite returned ${res.status}`);
      setReport(await res.json());
      loadHistory();
    } catch (err) {
      setError(String(err.message ?? err));
    } finally {
      setRunning(false);
    }
  }, [loadHistory]);

  const ORDER = { critical: 0, high: 1, moderate: 2 };
  // Grouped by what each attack targets, gravest first inside a group.
  const rows = [...(report?.results ?? corpus.map((a) => ({ ...a, held: undefined })))]
    .sort((a, b) =>
      a.targets === b.targets
        ? (ORDER[a.severity] ?? 9) - (ORDER[b.severity] ?? 9)
        : String(a.targets).localeCompare(String(b.targets)));
  const clean = report && report.breached === 0;

  return (
    <Box sx={{ p: 3, maxWidth: 1080, mx: "auto" }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1 }}>
        <ShieldOutlinedIcon sx={{ fontSize: 19, color: "text.secondary" }} />
        <Typography variant="h6" sx={{ fontSize: 19, fontWeight: 600 }}>
          Can this agent be tricked?
        </Typography>
      </Stack>

      <Typography variant="body2" sx={{ color: "text.secondary", maxWidth: "68ch", lineHeight: 1.75, mb: 2.5 }}>
        The agent reads product pages written by sellers, and a seller could write
        instructions into one — hidden text telling the agent to raise your budget, skip
        your approval, or pick their product. So we attack it ourselves, on purpose.
        Press the button and{corpus.length ? ` ${corpus.length} of ` : " "}those attacks run
        for real against the live checkout, right now, in front of you.
      </Typography>

      <Stack direction="row" spacing={2} sx={{ alignItems: "center", mb: 3 }}>
        <Button
          variant="contained"
          onClick={run}
          disabled={running}
          startIcon={running
            ? <CircularProgress size={14} color="inherit" />
            : <PlayArrowIcon sx={{ fontSize: 18 }} />}
        >
          {running ? "Attacking…" : "Run the safety checks"}
        </Button>

      </Stack>

      {report && (
        <Box
          sx={{
            ...CARD,
            mb: 3,
            p: 0,
            overflow: "hidden",
            borderColor: clean ? "rgba(34,197,94,0.35)" : "rgba(239,68,68,0.4)",
          }}
        >
          {/* The verdict, stated before the evidence. */}
          <Box
            sx={{
              px: 2.5, py: 2,
              bgcolor: clean ? "rgba(34,197,94,0.07)" : "rgba(239,68,68,0.07)",
              borderBottom: "1px solid", borderColor: "divider",
            }}
          >
            <Stack direction="row" spacing={4} sx={{ alignItems: "flex-end", flexWrap: "wrap" }}>
              <Box>
                <Typography
                  sx={{ fontSize: 40, fontWeight: 800, lineHeight: 1,
                        letterSpacing: "-0.02em",
                        fontVariantNumeric: "tabular-nums",
                        color: clean ? "success.main" : "error.main" }}
                >
                  {report.held}<Box component="span" sx={{ opacity: 0.45 }}>/{report.total}</Box>
                </Typography>
                <Typography variant="caption" sx={{ color: "text.secondary", mt: 0.5, display: "block" }}>
                  attacks blocked
                </Typography>
              </Box>

              <Box sx={{ flex: 1, minWidth: 180 }}>
                <Typography variant="body2" sx={{ fontSize: 13, lineHeight: 1.6,
                                                  color: clean ? "success.main" : "error.main",
                                                  fontWeight: 600 }}>
                  {clean
                    ? "Nothing reached your money."
                    : `${report.breached} attack${report.breached === 1 ? "" : "s"} got through.`}
                </Typography>
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  {report.total} attacks run against the real checkout · took {report.duration_s} seconds
                </Typography>
              </Box>
            </Stack>
          </Box>
        </Box>
      )}

      {error && (
        <Box sx={{ ...CARD, p: 2, mb: 2, borderColor: "error.main", bgcolor: "rgba(239,68,68,0.08)" }}>
          <Typography variant="caption" sx={{ color: "error.main" }}>{error}</Typography>
        </Box>
      )}

      {/* The answer to the only question a shopper actually has. Before a
          run these are the promises being tested; after one, each carries
          how many attacks tried it and how many got anywhere. */}
      {audited && (
        <ProductAuditBoard product={audited} onClear={clearAudited} />
      )}

      {!audited && rows.length > 0 && (
        <Box sx={{ ...CARD, p: 2.5, mb: 2.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 14.5, mb: 0.5 }}>
            What you are protected from
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 12.5, display: "block", mb: 1 }}>
            {report
              ? "Each line was attacked directly in the run above."
              : "Each line is tested by real attacks when you press the button."}
          </Typography>
          <Stack divider={<Box sx={{ borderTop: "1px solid", borderColor: "divider" }} />}>
            {byPromise(rows).map((group) => (
              <SafetyRow key={group.id} group={group} ran={Boolean(report)} />
            ))}
          </Stack>
        </Box>
      )}

      {/* Outside the fold on purpose — the limit is the part people need
          most, and burying it in a technical panel would be the quiet kind
          of dishonesty this whole page exists to avoid. */}
      <Box sx={{ ...CARD, p: 2.5, mb: 2.5 }}>
        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 14, mb: 0.75 }}>
          What this does not promise
        </Typography>
        <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 12.5, lineHeight: 1.8, display: "block" }}>
          It does not promise the AI itself can never be fooled by clever wording. No one can
          promise that today, and we are not going to pretend otherwise. What these checks
          show is that fooling it does not reach anything that costs you money — the price,
          the stock, your budget, your approval and the payment are each decided by ordinary
          code that never reads a seller's text at all.
        </Typography>
      </Box>

      {/* Everything an assessor wants, one click away and nothing removed. */}
      <Button
        onClick={() => setDetail((d) => !d)}
        size="small"
        sx={{ mb: 2, color: "text.secondary", textTransform: "none", fontWeight: 500 }}
        endIcon={
          <ExpandMoreIcon
            sx={{ fontSize: 18, transform: detail ? "rotate(180deg)" : "none",
                  transition: "transform 160ms" }}
          />
        }
      >
        {detail ? "Hide the technical detail" : "Show the technical detail"}
      </Button>

      <Collapse in={detail} unmountOnExit>
      {(corpus.length > 0 || report) && (
        <Stack direction="row" spacing={1.5} sx={{ mb: 2, flexWrap: "wrap", gap: 1.5 }}>
          {["critical", "high", "moderate"].map((sev) => {
            const inSev = rows.filter((r) => r.severity === sev);
            if (!inSev.length) return null;
            return (
              <SeverityTile
                key={sev}
                label={SEVERITY[sev].label}
                tone={SEVERITY[sev].color}
                total={inSev.length}
                held={inSev.filter((r) => r.held === true).length}
                ran={Boolean(report)}
              />
            );
          })}
        </Stack>
      )}

      {rows.length > 0 && (
        <Box sx={{ ...CARD, p: 2, mb: 2.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5, mb: 1.25 }}>
            What is being defended
          </Typography>
          {Object.entries(
            rows.reduce((acc, r) => {
              const key = r.family || "Other";
              acc[key] = acc[key] || { total: 0, held: 0 };
              acc[key].total += 1;
              if (r.held === true) acc[key].held += 1;
              return acc;
            }, {})
          )
            .sort((a, b) => b[1].total - a[1].total || a[0].localeCompare(b[0]))
            .map(([family, counts], _i, all) => (
              <FamilyBar
                key={family}
                family={family}
                total={counts.total}
                held={counts.held}
                ran={Boolean(report)}
                maxTotal={Math.max(...all.map(([, c]) => c.total))}
              />
            ))}
        </Box>
      )}

      <Box sx={{ ...CARD, overflow: "hidden" }}>
        {rows.map((row, index) => {
          // A heading each time the target changes, so the list reads as
          // "what is being defended" rather than twenty-two flat rows.
          const newGroup = index === 0 || rows[index - 1].targets !== row.targets;
          const tone = SEVERITY[row.severity] ?? SEVERITY.moderate;
          const expanded = Boolean(open[row.id]);
          return (
            <Box key={row.id}>
              {newGroup && (
                <Typography
                  variant="caption"
                  sx={{
                    display: "block", px: 2, py: 0.9,
                    bgcolor: "rgba(255,255,255,0.025)",
                    borderTop: index === 0 ? "none" : "1px solid",
                    borderBottom: "1px solid", borderColor: "divider",
                    color: "text.disabled", fontSize: 10.5,
                    fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
                  }}
                >
                  {row.targets}
                </Typography>
              )}
              <Box sx={{ borderTop: newGroup ? "none" : "1px solid", borderColor: "divider",
                         borderLeft: "3px solid", borderLeftColor: tone.color }}>
              <Stack
                direction="row"
                spacing={1.5}
                onClick={() => setOpen((s) => ({ ...s, [row.id]: !s[row.id] }))}
                sx={{ px: 2, py: 1.5, alignItems: "center", cursor: "pointer",
                      "&:hover": { bgcolor: "rgba(255,255,255,0.02)" } }}
              >
                <Box sx={{ width: 20, flexShrink: 0, display: "flex" }}>
                  {row.held === true && (
                    <CheckCircleOutlineIcon sx={{ fontSize: 17, color: "success.main" }} />
                  )}
                  {row.held === false && (
                    <ErrorOutlineIcon sx={{ fontSize: 17, color: "error.main" }} />
                  )}
                  {row.held === undefined && (
                    <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "text.disabled", m: "5px" }} />
                  )}
                </Box>

                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontSize: 13.5, fontWeight: 500 }}>
                    {row.family} — {row.technique}
                  </Typography>
                  <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 11.5 }}>
                    {row.invariant}
                  </Typography>
                </Box>

                <Typography
                  variant="caption"
                  sx={{ fontSize: 10.5, fontWeight: 700, px: 0.9, py: 0.3, borderRadius: 1,
                        color: tone.color, bgcolor: tone.bg, flexShrink: 0 }}
                >
                  {tone.label}
                </Typography>

                <ExpandMoreIcon
                  sx={{ fontSize: 17, color: "text.disabled", flexShrink: 0,
                        transform: expanded ? "rotate(180deg)" : "none",
                        transition: "transform 160ms" }}
                />
              </Stack>

              <Collapse in={expanded} unmountOnExit>
                <Box sx={{ px: 2, pb: 2, pl: 6.5 }}>
                  <Typography variant="caption" sx={{ color: "text.disabled", display: "block", mb: 0.5 }}>
                    Payload sent
                  </Typography>
                  <Box
                    sx={{
                      fontFamily: "monospace", fontSize: 11.5, lineHeight: 1.6,
                      color: "text.secondary", bgcolor: "rgba(255,255,255,0.03)",
                      border: "1px solid", borderColor: "divider",
                      borderRadius: 1.5, p: 1.25, mb: 1.5,
                      whiteSpace: "pre-wrap", wordBreak: "break-word",
                    }}
                  >
                    {row.payload}
                  </Box>

                  {row.observed && (
                    <>
                      <Typography variant="caption" sx={{ color: "text.disabled", display: "block", mb: 0.5 }}>
                        What actually happened
                      </Typography>
                      <Typography variant="body2" sx={{ fontSize: 12.5, color: "text.primary" }}>
                        {row.observed}
                      </Typography>
                    </>
                  )}
                </Box>
              </Collapse>
              </Box>
            </Box>
          );
        })}
      </Box>

      {history.length > 0 && (
        <Box sx={{ ...CARD, p: 2, mt: 2.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5, mb: 0.5 }}>
            Past runs
          </Typography>
          <RunTrend runs={history} />
          <Stack spacing={0.75} sx={{ mt: 1.5 }}>
            {history.map((run) => {
              const ok = run.breached === 0;
              return (
                <Stack
                  key={run.ran_at}
                  direction="row"
                  spacing={1.5}
                  sx={{ alignItems: "center", fontSize: 12.5 }}
                >
                  <Typography variant="caption" sx={{ color: "text.secondary", width: 132, flexShrink: 0,
                                                      fontVariantNumeric: "tabular-nums" }}>
                    {new Date((run.ran_at ?? 0) * 1000).toLocaleString("en-IN", {
                      day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
                    })}
                  </Typography>
                  <Typography variant="caption" sx={{ fontWeight: 700, width: 54, flexShrink: 0,
                                                      color: ok ? "success.main" : "error.main",
                                                      fontVariantNumeric: "tabular-nums" }}>
                    {run.held}/{run.total}
                  </Typography>
                  <Typography variant="caption" sx={{ color: "text.secondary", flex: 1, minWidth: 0 }}>
                    {ok
                      ? "all invariants held"
                      : `breached: ${(run.breached_ids ?? []).join(", ")}`}
                  </Typography>
                  <Typography variant="caption" sx={{ color: "text.disabled", flexShrink: 0,
                                                      fontVariantNumeric: "tabular-nums" }}>
                    {run.duration_s}s
                  </Typography>
                </Stack>
              );
            })}
          </Stack>
        </Box>
      )}

      <Box sx={{ ...CARD, p: 2, mt: 2.5 }}>
        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5, mb: 0.75 }}>
          What this does and doesn't claim
        </Typography>
        <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.75, display: "block" }}>
          It does not claim the language model is immune to injection — it isn't, and the
          field's position is that it may never be. What it measures is what a successful
          injection can <em>reach</em>. Pricing, stock, publication status, the signed
          budget, human approval and settlement are all enforced in deterministic code
          that reads no listing text, so persuading the model does not move any of them.
          Ranking is the soft edge: it is scored separately as moderate because a swayed
          recommendation is a nuisance, not a route to anyone's money.
        </Typography>
        <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.75, display: "block", mt: 1.25 }}>
          The budget check exists because this harness broke it. An injected sentence
          turned a typed ₹1,000 ceiling into a signed ₹5,000 one, so the ceiling is now
          read from the request by rule and the smallest match wins — injected text can
          only ever lower it.
        </Typography>
      </Box>
      </Collapse>
    </Box>
  );
}
