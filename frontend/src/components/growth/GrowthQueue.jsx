import { useCallback, useEffect, useState } from "react";
import {
  Box, Button, Chip, CircularProgress, Stack, Switch, Tooltip, Typography,
} from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesomeOutlined";
import WarningIcon from "@mui/icons-material/WarningAmberOutlined";
import BlockIcon from "@mui/icons-material/BlockOutlined";
import CheckIcon from "@mui/icons-material/CheckCircleOutlineOutlined";

import { API_BASE } from "../../config";

/**
 * WHAT THE GROWTH AGENTS WANT TO DO, AND WHAT STOPPED THEM.
 *
 * A review queue, not a dashboard. Every row is a proposal that has already
 * been through the merchant-side gate, so the verdict arrives with it —
 * the merchant sees what would be given away and what was refused before
 * deciding anything.
 *
 * Two things are shown that a growth tool usually hides:
 *
 *   the cost      what this gives away if it is taken, in rupees, per row.
 *   the sample    how many observations it rests on. A recommendation from
 *                 one abandoned cart may well be right, but it is a case
 *                 and not a trend, and the row says so rather than letting
 *                 a confident headline imply otherwise.
 *
 * Escalated rows carry an Approve button. Nothing here applies itself: the
 * server re-runs the gate on apply, so a stale queue cannot sneak an action
 * past a budget that has moved since the scan.
 */

const VERDICT = {
  allowed: { label: "Within bounds", color: "success", icon: <CheckIcon sx={{ fontSize: 14 }} /> },
  escalated: { label: "Needs you", color: "warning", icon: <WarningIcon sx={{ fontSize: 14 }} /> },
  blocked: { label: "Blocked", color: "error", icon: <BlockIcon sx={{ fontSize: 14 }} /> },
};

const rupees = (paise) =>
  `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function GrowthQueue({ card }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [flash, setFlash] = useState(null);
  // The master switch lives in the hive dials. It is mirrored here
  // because a merchant reading "growth agents are switched off" on
  // every row needs the switch in front of them, not two pages away.
  const [enabled, setEnabled] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/growth/scan`);
      setData(res.ok ? await res.json() : null);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadEnabled = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/agent-settings`);
      const d = await res.json();
      setEnabled(Boolean(d?.values?.growthgate?.enabled));
    } catch {
      setEnabled(null);
    }
  }, []);

  useEffect(() => { load(); loadEnabled(); }, [load, loadEnabled]);

  const toggle = async (next) => {
    setEnabled(next);
    try {
      await fetch(`${API_BASE}/agent-settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          changes: { growthgate: { enabled: next } },
          source: "Growth page switch",
        }),
      });
    } finally {
      await load();          // verdicts change the moment the switch does
      await loadEnabled();
    }
  };

  const act = async (proposal, approve) => {
    setBusy(proposal.headline);
    setFlash(null);
    try {
      const res = await fetch(`${API_BASE}/growth/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          proposal,
          // Only ever set by a person clicking Approve. The agent cannot
          // fill this in for itself — same rule the buyer's broker follows.
          approved_by: approve ? "merchant (this browser)" : "",
        }),
      });
      const body = await res.json().catch(() => ({}));
      setFlash(res.ok
        ? { tone: "ok", text: `Applied — offer ${body.offer_id}` }
        : { tone: "warn", text: body.detail || "The gate refused it." });
      await load();
    } catch (err) {
      setFlash({ tone: "warn", text: String(err) });
    } finally {
      setBusy("");
    }
  };

  if (loading) {
    return (
      <Box sx={{ ...card, mb: 3 }}>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <CircularProgress size={14} />
          <Typography variant="caption" color="text.secondary">
            Reading the store's own records for things worth acting on…
          </Typography>
        </Stack>
      </Box>
    );
  }

  const proposals = data?.proposals ?? [];

  return (
    <Box sx={{ ...card, mb: 3 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
        <AutoAwesomeIcon sx={{ fontSize: 16, color: "text.secondary" }} />
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          What the growth agents want to do
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Tooltip title="The same dial as growthgate.enabled on the hive. Off means agents may look and propose, but nothing can be applied.">
          <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
            <Typography variant="caption" color="text.secondary">
              {enabled ? "Agents on" : "Agents off"}
            </Typography>
            <Switch
              size="small"
              checked={Boolean(enabled)}
              onChange={(e) => toggle(e.target.checked)}
            />
          </Stack>
        </Tooltip>
        <Button size="small" onClick={load} sx={{ textTransform: "none" }}>
          Re-scan
        </Button>
      </Stack>

      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2, lineHeight: 1.6 }}>
        Read from this store's own orders and checkouts. Every proposal has
        already been through the same kind of bound the buying agent's
        spending passes — nothing here has been applied.
      </Typography>

      {flash && (
        <Typography
          variant="caption"
          sx={{
            display: "block", mb: 1.5, lineHeight: 1.6,
            color: flash.tone === "ok" ? "success.main" : "warning.main",
          }}
        >
          {flash.text}
        </Typography>
      )}

      {proposals.length === 0 && (
        <Typography variant="caption" color="text.secondary">
          Nothing to act on. No abandoned checkouts and no co-purchase
          history to learn from yet — which is the honest answer on a store
          this new, not a failure.
        </Typography>
      )}

      <Stack spacing={1.25}>
        {proposals.map((p) => {
          const v = VERDICT[p.verdict] ?? VERDICT.blocked;
          const thin = p.cost_paise > 0 && p.sample_size < 3;
          return (
            <Box
              key={`${p.agent}-${p.target_id}-${p.headline}`}
              sx={{
                border: "1px solid", borderColor: "divider", borderRadius: 2, p: 1.5,
                bgcolor: p.verdict === "escalated" ? "rgba(210,153,34,0.06)" : "transparent",
              }}
            >
              <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start", mb: 0.75 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, flex: 1, minWidth: 0 }}>
                  {p.headline}
                </Typography>
                <Chip size="small" icon={v.icon} label={v.label} color={v.color}
                      variant="outlined" sx={{ height: 22, fontSize: 10.5 }} />
              </Stack>

              <Stack direction="row" spacing={1} sx={{ mb: 0.75, flexWrap: "wrap", gap: 0.75 }}>
                <Chip size="small" label={p.agent} sx={{ height: 20, fontSize: 10 }} />
                <Chip
                  size="small"
                  label={p.cost_paise ? `Costs ${rupees(p.cost_paise)} of margin` : "Costs nothing"}
                  sx={{ height: 20, fontSize: 10 }}
                />
                {/* The sample is shown on every row, not just thin ones —
                    a number that only appears when it is bad teaches people
                    to ignore it when it is absent. */}
                <Chip
                  size="small"
                  label={`${p.sample_size} observation${p.sample_size === 1 ? "" : "s"}`}
                  color={thin ? "warning" : "default"}
                  variant={thin ? "outlined" : "filled"}
                  sx={{ height: 20, fontSize: 10 }}
                />
              </Stack>

              <Typography variant="caption" color="text.secondary" sx={{ display: "block", lineHeight: 1.6 }}>
                {p.detail}
              </Typography>

              <Typography variant="caption" sx={{ display: "block", mt: 0.75, lineHeight: 1.6, color: "text.disabled" }}>
                {p.evidence_note}
              </Typography>

              <Typography
                variant="caption"
                sx={{
                  display: "block", mt: 0.75, lineHeight: 1.6,
                  color: p.verdict === "allowed" ? "text.secondary" : "warning.main",
                }}
              >
                <strong>Gate:</strong> {p.verdict_reason}
              </Typography>

              {p.verdict !== "blocked" && (
                <Stack direction="row" spacing={1} sx={{ mt: 1.25 }}>
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={Boolean(busy)}
                    onClick={() => act(p, p.verdict === "escalated")}
                    sx={{ textTransform: "none" }}
                  >
                    {busy === p.headline
                      ? "Applying…"
                      : p.verdict === "escalated"
                        ? "Approve and apply"
                        : "Apply"}
                  </Button>
                  {p.verdict === "escalated" && (
                    <Typography variant="caption" color="text.secondary" sx={{ alignSelf: "center" }}>
                      The agent cannot clear this itself.
                    </Typography>
                  )}
                </Stack>
              )}
            </Box>
          );
        })}
      </Stack>
    </Box>
  );
}
