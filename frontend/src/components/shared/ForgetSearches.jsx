import { useCallback, useEffect, useState } from "react";
import {
  Box, Button, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogContentText, DialogTitle, Stack, Typography,
} from "@mui/material";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlineOutlined";

import { API_BASE } from "../../config";

/**
 * Being able to tell the agent to forget something.
 *
 * The rest of this page audits what is stored. Auditing without a way to
 * act on the answer is half a promise, and a shopping agent that keeps
 * every phrase you ever typed and cannot be told to drop any of it is its
 * own kind of problem.
 *
 * Two things this deliberately makes visible. A search is stored twice —
 * the conversation and the marketplace results — and both go, because
 * reporting a search as forgotten while the words sat in another
 * collection would be worse than not offering the control. And the count
 * of rows is shown per search, so "forget" is a specific act on named data
 * rather than a button that promises something vague.
 */
export default function ForgetSearches() {
  const [state, setState] = useState({ status: "loading", data: null, error: null });
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/security/searches`);
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      setState({ status: "ready", data: await res.json(), error: null });
    } catch (err) {
      setState({ status: "error", data: null, error: String(err.message ?? err) });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const forget = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      const params = pending.all
        ? "all=true"
        : `query=${encodeURIComponent(pending.query)}`;
      const res = await fetch(`${API_BASE}/security/searches?${params}`, {
        method: "DELETE",
      });
      const body = await res.json();
      setDone(body.detail ?? "Forgotten.");
      await load();
    } catch (err) {
      setDone(`Could not forget that: ${err.message ?? err}`);
    } finally {
      setBusy(false);
      setPending(null);
    }
  };

  const { data } = state;
  const searches = data?.searches ?? [];

  return (
    <Box>
      <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.7, mb: 2 }}>
        {data?.note ??
          "What this agent remembers you looking for."}
      </Typography>

      {state.status === "error" && (
        <Typography variant="body2" sx={{ color: "error.main" }}>
          Could not read stored searches — {state.error}
        </Typography>
      )}

      {done && (
        <Typography
          variant="body2"
          sx={{
            color: "success.main", mb: 2, p: 1.25, borderRadius: 1.5,
            border: "1px solid", borderColor: "rgba(34,197,94,0.4)",
            bgcolor: "rgba(34,197,94,0.08)",
          }}
        >
          {done}
        </Typography>
      )}

      {state.status === "ready" && !searches.length && (
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          No searches are stored. Nothing to forget.
        </Typography>
      )}

      {searches.length > 0 && (
        <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2 }}>
          {searches.map((row, index) => (
            <Stack
              key={row.query}
              direction="row"
              sx={{
                px: 2, py: 1.25, gap: 2, alignItems: "center",
                borderTop: index === 0 ? "none" : "1px solid",
                borderColor: "divider",
              }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" noWrap sx={{ fontSize: 13 }}>
                  {row.query}
                </Typography>
                <Typography variant="caption" sx={{ color: "text.disabled", fontSize: 11 }}>
                  {row.runs} conversation{row.runs === 1 ? "" : "s"} ·{" "}
                  {row.scans} marketplace scan{row.scans === 1 ? "" : "s"}
                  {row.last_seen ? ` · last ${row.last_seen.slice(0, 10)}` : ""}
                </Typography>
              </Box>
              <Button
                size="small"
                startIcon={<DeleteOutlineIcon sx={{ fontSize: 16 }} />}
                onClick={() => setPending({ query: row.query, rows: row.runs + row.scans })}
                sx={{ color: "text.secondary", flexShrink: 0 }}
              >
                Forget
              </Button>
            </Stack>
          ))}
        </Box>
      )}

      {searches.length > 0 && (
        <Stack
          direction="row"
          sx={{ alignItems: "center", justifyContent: "space-between", mt: 1.5 }}
        >
          <Typography variant="caption" sx={{ color: "text.disabled" }}>
            {data.rows_held} row{data.rows_held === 1 ? "" : "s"} across{" "}
            {searches.length} search{searches.length === 1 ? "" : "es"}
          </Typography>
          <Button
            size="small"
            color="error"
            onClick={() => setPending({ all: true, rows: data.rows_held })}
          >
            Forget everything
          </Button>
        </Stack>
      )}

      <Dialog open={Boolean(pending)} onClose={() => setPending(null)}>
        <DialogTitle sx={{ fontSize: 17 }}>
          {pending?.all ? "Forget every stored search?" : "Forget this search?"}
        </DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ fontSize: 14, lineHeight: 1.7 }}>
            {pending?.all
              ? `This deletes all ${pending?.rows} stored rows — every conversation and every marketplace scan.`
              : `This deletes ${pending?.rows} row${pending?.rows === 1 ? "" : "s"} for “${pending?.query}” — the conversation and what the marketplace returned.`}
            {" "}It cannot be undone, and recommendations will stop using it on
            the next load. The audit trail will record that a deletion
            happened, but not the words — writing them there would undo it.
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setPending(null)} disabled={busy}>
            Keep it
          </Button>
          <Button onClick={forget} color="error" variant="contained" disabled={busy}>
            {busy ? <CircularProgress size={18} /> : "Forget"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
