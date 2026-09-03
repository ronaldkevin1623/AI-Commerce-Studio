import { useCallback, useEffect, useState } from "react";
import {
  Box, Button, Chip, LinearProgress, MenuItem, Stack, TextField, Typography,
} from "@mui/material";
import CampaignIcon from "@mui/icons-material/CampaignOutlined";

import { API_BASE } from "../../config";

/**
 * CAMPAIGNS — A PROGRAMME WITH AN END, SHOWN AS ONE.
 *
 * The envelope is the important thing on screen, so it is a progress bar
 * rather than a number in a list: a merchant should be able to see how much
 * of a commitment is gone at a glance, and watch it move when they tick.
 *
 * Three honesty rules this panel follows:
 *
 *   Nothing here runs on a timer, and it says so. `tick` is a button. A
 *   panel implying an unattended cadence this build does not have would be
 *   the easiest lie in the feature.
 *
 *   A finished campaign shows WHY it finished, not just that it did —
 *   budget spent, window closed, paused, or an envelope too small to buy
 *   anything.
 *
 *   Measurement reports counts and the sample behind them. No uplift, no
 *   "influenced revenue": there is no control group here, and a number that
 *   implies one would be the most flattering thing on the page.
 */

const STATE = {
  running: { label: "Running", color: "success" },
  paused: { label: "Paused", color: "default" },
  finished: { label: "Finished", color: "warning" },
};

const rupees = (paise) =>
  `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

export default function CampaignPanel({ card }) {
  const [rows, setRows] = useState([]);
  const [agents, setAgents] = useState([]);
  const [busy, setBusy] = useState("");
  const [flash, setFlash] = useState(null);
  const [measured, setMeasured] = useState({});
  const [draft, setDraft] = useState({
    goal: "Recover abandoned carts",
    budget_inr: 500,
    window_hours: 24,
    agent: "recovery",
  });

  const load = useCallback(async () => {
    try {
      const [c, a] = await Promise.all([
        fetch(`${API_BASE}/growth/campaigns`).then((r) => r.json()),
        fetch(`${API_BASE}/growth/agents`).then((r) => r.json()),
      ]);
      setRows(c.campaigns || []);
      setAgents(a.agents || []);
    } catch {
      setRows([]);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const call = async (path, body) => {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const parsed = await res.json().catch(() => ({}));
    return { ok: res.ok, body: parsed };
  };

  const open = async () => {
    setBusy("open");
    setFlash(null);
    const { ok, body } = await call("/growth/campaigns", {
      goal: draft.goal,
      budget_paise: Math.round(Number(draft.budget_inr) * 100),
      window_hours: Number(draft.window_hours),
      agent_ids: [draft.agent],
    });
    setFlash(ok
      ? { tone: "ok", text: `Opened ${body.campaign_id}` }
      : { tone: "warn", text: body.detail || "Could not open it." });
    await load();
    setBusy("");
  };

  const act = async (id, verb) => {
    setBusy(id + verb);
    setFlash(null);
    const { ok, body } = await call(`/growth/campaigns/${id}/${verb}`);
    if (verb === "tick") {
      setFlash(ok
        ? {
          tone: "ok",
          text: body.applied?.length
            ? `Applied ${body.applied.length} action(s), ${rupees(body.remaining_paise)} left`
            : `Nothing to apply this pass${body.escalated?.length ? ` — ${body.escalated.length} waiting on you` : ""}`,
        }
        : { tone: "warn", text: body.detail || "That tick was refused." });
    }
    await load();
    setBusy("");
  };

  const measure = async (id) => {
    setBusy(id + "measure");
    try {
      const res = await fetch(`${API_BASE}/growth/campaigns/${id}/measure`);
      // Resolved BEFORE the state updater: the updater is not async, so an
      // await inside it is a syntax error rather than a wait.
      const body = await res.json();
      setMeasured((m) => ({ ...m, [id]: body }));
    } finally {
      setBusy("");
    }
  };

  return (
    <Box sx={{ ...card, mb: 3 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
        <CampaignIcon sx={{ fontSize: 16, color: "text.secondary" }} />
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          Campaigns
        </Typography>
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2, lineHeight: 1.6 }}>
        A goal, an envelope and a window. The envelope sits inside the growth
        bounds rather than replacing them, so whichever binds first wins.
        Nothing runs on a timer — a campaign advances when you tick it.
      </Typography>

      {flash && (
        <Typography
          variant="caption"
          sx={{
            display: "block", mb: 1.5,
            color: flash.tone === "ok" ? "success.main" : "warning.main",
          }}
        >
          {flash.text}
        </Typography>
      )}

      <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: "wrap", gap: 1 }}>
        <TextField
          size="small" label="Goal" value={draft.goal}
          onChange={(e) => setDraft({ ...draft, goal: e.target.value })}
          sx={{ minWidth: 210 }}
        />
        <TextField
          size="small" label="Envelope" type="number" value={draft.budget_inr}
          onChange={(e) => setDraft({ ...draft, budget_inr: e.target.value })}
          slotProps={{ input: { startAdornment: <span style={{ marginRight: 4 }}>₹</span> } }}
          sx={{ width: 120 }}
        />
        <TextField
          size="small" label="Window" type="number" value={draft.window_hours}
          onChange={(e) => setDraft({ ...draft, window_hours: e.target.value })}
          slotProps={{ input: { endAdornment: <span style={{ marginLeft: 4 }}>h</span> } }}
          sx={{ width: 110 }}
        />
        <TextField
          size="small" select label="Agent" value={draft.agent}
          onChange={(e) => setDraft({ ...draft, agent: e.target.value })}
          sx={{ minWidth: 150 }}
        >
          {agents.map((a) => (
            <MenuItem key={a.agent_id} value={a.agent_id}>{a.name}</MenuItem>
          ))}
        </TextField>
        <Button
          variant="outlined" size="small" onClick={open}
          disabled={busy === "open"}
          sx={{ textTransform: "none" }}
        >
          {busy === "open" ? "Opening…" : "Open campaign"}
        </Button>
      </Stack>

      {rows.length === 0 && (
        <Typography variant="caption" color="text.secondary">
          No campaigns yet.
        </Typography>
      )}

      <Stack spacing={1.25}>
        {rows.map((c) => {
          const state = STATE[c.state] ?? STATE.finished;
          const spent = c.spent_paise || 0;
          const budget = c.budget_paise || 1;
          const pct = Math.min(100, (spent / budget) * 100);
          const m = measured[c.campaign_id];
          return (
            <Box key={c.campaign_id}
                 sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2, p: 1.5 }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.75 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, flex: 1, minWidth: 0 }}>
                  {c.goal}
                </Typography>
                <Chip size="small" label={state.label} color={state.color}
                      variant="outlined" sx={{ height: 20, fontSize: 10 }} />
              </Stack>

              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                {rupees(spent)} of {rupees(budget)} committed · {c.ticks || 0} tick
                {c.ticks === 1 ? "" : "s"} · {(c.agent_ids || []).join(", ")}
              </Typography>
              <LinearProgress
                variant="determinate" value={pct}
                sx={{ height: 5, borderRadius: 999, mb: 1 }}
              />

              {/* Why it ended, not just that it did. */}
              {c.state === "finished" && c.stopped_reason && (
                <Typography variant="caption" sx={{ display: "block", color: "warning.main", mb: 0.75 }}>
                  Finished — {c.stopped_reason}.
                </Typography>
              )}

              {m && (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75, lineHeight: 1.6 }}>
                  <strong>{m.offers_placed} offer(s) placed, {m.converted} converted.</strong>{" "}
                  Margin committed {rupees(m.margin_committed_paise)}; revenue
                  recovered {rupees(m.revenue_recovered_paise)}. {m.note}
                </Typography>
              )}

              <Stack direction="row" spacing={1}>
                {c.state === "running" && (
                  <Button size="small" variant="outlined" sx={{ textTransform: "none" }}
                          disabled={Boolean(busy)}
                          onClick={() => act(c.campaign_id, "tick")}>
                    {busy === c.campaign_id + "tick" ? "Ticking…" : "Tick"}
                  </Button>
                )}
                {c.state === "running" && (
                  <Button size="small" sx={{ textTransform: "none" }}
                          disabled={Boolean(busy)}
                          onClick={() => act(c.campaign_id, "pause")}>
                    Pause
                  </Button>
                )}
                {c.state === "paused" && (
                  <Button size="small" sx={{ textTransform: "none" }}
                          disabled={Boolean(busy)}
                          onClick={() => act(c.campaign_id, "resume")}>
                    Resume
                  </Button>
                )}
                <Button size="small" sx={{ textTransform: "none" }}
                        disabled={Boolean(busy)}
                        onClick={() => measure(c.campaign_id)}>
                  {busy === c.campaign_id + "measure" ? "Measuring…" : "Measure"}
                </Button>
              </Stack>
            </Box>
          );
        })}
      </Stack>
    </Box>
  );
}
