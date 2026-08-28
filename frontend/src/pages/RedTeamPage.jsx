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

  const rows = report?.results ?? corpus.map((a) => ({ ...a, held: undefined }));
  const clean = report && report.breached === 0;

  return (
    <Box sx={{ p: 3, maxWidth: 1080, mx: "auto" }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1 }}>
        <ShieldOutlinedIcon sx={{ fontSize: 19, color: "text.secondary" }} />
        <Typography variant="h6" sx={{ fontSize: 19, fontWeight: 600 }}>
          Adversarial evaluation
        </Typography>
      </Stack>

      <Typography variant="body2" sx={{ color: "text.secondary", maxWidth: "68ch", lineHeight: 1.75, mb: 2.5 }}>
        AI Commerce Studio reads text it does not control — seller-written titles and descriptions
        go into the same model that parses intent and ranks results. That is the surface
        indirect prompt injection targets, and in commerce the attack is a hostile listing.
        These run against the live pipeline: real gate, real merchant, real mandate verifier.
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
          {running ? "Attacking…" : "Run the suite"}
        </Button>

        {report && (
          <Stack direction="row" spacing={2.5} sx={{ alignItems: "baseline" }}>
            <Box>
              <Typography sx={{ fontSize: 22, fontWeight: 700, lineHeight: 1,
                                color: clean ? "success.main" : "error.main" }}>
                {report.held}/{report.total}
              </Typography>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                invariants held
              </Typography>
            </Box>
            <Box>
              <Typography sx={{ fontSize: 22, fontWeight: 700, lineHeight: 1 }}>
                {report.critical_held}/{report.critical_total}
              </Typography>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                critical held
              </Typography>
            </Box>
            <Typography variant="caption" sx={{ color: "text.disabled" }}>
              {report.duration_s}s
            </Typography>
          </Stack>
        )}
      </Stack>

      {error && (
        <Box sx={{ ...CARD, p: 2, mb: 2, borderColor: "error.main", bgcolor: "rgba(239,68,68,0.08)" }}>
          <Typography variant="caption" sx={{ color: "error.main" }}>{error}</Typography>
        </Box>
      )}

      <Box sx={{ ...CARD, overflow: "hidden" }}>
        {rows.map((row, index) => {
          const tone = SEVERITY[row.severity] ?? SEVERITY.moderate;
          const expanded = Boolean(open[row.id]);
          return (
            <Box
              key={row.id}
              sx={{ borderTop: index === 0 ? "none" : "1px solid", borderColor: "divider" }}
            >
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
          );
        })}
      </Box>

      {history.length > 0 && (
        <Box sx={{ ...CARD, p: 2, mt: 2.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5, mb: 1.25 }}>
            Past runs
          </Typography>
          <Stack spacing={0.75}>
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
    </Box>
  );
}
