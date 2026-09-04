import { useEffect, useMemo, useRef, useState } from "react";
import {
  Box, Button, Checkbox, IconButton, InputBase, Menu, MenuItem,
  Stack, Tooltip, Typography,
} from "@mui/material";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import RefreshIcon from "@mui/icons-material/Refresh";
import SearchIcon from "@mui/icons-material/SearchOutlined";
import ContentCopyIcon from "@mui/icons-material/ContentCopyOutlined";

/**
 * A LOG CONSOLE, NOT A LIST OF CARDS.
 *
 * Modelled on the CloudWatch log-events view, because that layout has been
 * beaten into shape by people reading real incidents: a fixed timestamp
 * column, one dense message line per row, and a disclosure triangle that
 * opens the full record UNDER the row you clicked rather than in a drawer
 * that hides its neighbours. When you are trying to work out what happened
 * at 16:31:42, the rows either side are most of the answer.
 *
 * What this adds over a plain log viewer, because these are money
 * decisions rather than application traces:
 *
 *   the verdict is a colour and a word, on every row, because "did it go
 *   through" is the first question anyone asks;
 *
 *   the amount is right-aligned in its own column so a column of rupees
 *   can be scanned without reading any prose;
 *
 *   the expanded record shows the FULL reason, never truncated. The
 *   reasoning is the point of this log — a "…" in the middle of why an
 *   agent refused a payment would defeat the whole feature.
 */

const VERDICT = {
  allowed: { fg: "#4ADE80", label: "allowed" },
  recorded: { fg: "#4ADE80", label: "recorded" },
  planned: { fg: "#7DD3FC", label: "planned" },
  accrued: { fg: "#7DD3FC", label: "accrued" },
  flagged: { fg: "#FBBF24", label: "flagged" },
  escalated: { fg: "#FBBF24", label: "escalated" },
  blocked: { fg: "#F87171", label: "blocked" },
};

const RANGES = [
  { key: "1m", label: "1m", ms: 60_000 },
  { key: "30m", label: "30m", ms: 30 * 60_000 },
  { key: "1h", label: "1h", ms: 60 * 60_000 },
  { key: "12h", label: "12h", ms: 12 * 60 * 60_000 },
  { key: "all", label: "All", ms: null },
];

const MONO = '"Cascadia Mono", "SF Mono", Consolas, "Liberation Mono", monospace';

function whenOf(row) {
  const stamp = row.timestamp;
  if (!stamp) return null;
  if (typeof stamp.toDate === "function") return stamp.toDate();
  if (stamp instanceof Date) return stamp;
  return null;
}

function stamp(date) {
  if (!date) return "—";
  const pad = (n, w = 2) => String(n).padStart(w, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}` +
    `.${pad(date.getMilliseconds(), 3)}`
  );
}

const rupees = (paise) =>
  paise ? `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—";

function Field({ label, value, mono }) {
  if (value === undefined || value === null || value === "" || value === "None") return null;
  return (
    <Stack direction="row" spacing={2} sx={{ py: 0.4, alignItems: "flex-start" }}>
      <Typography
        variant="caption"
        sx={{ width: 128, flexShrink: 0, color: "text.disabled", fontSize: 11.5 }}
      >
        {label}
      </Typography>
      <Typography
        variant="caption"
        sx={{
          fontSize: 12, lineHeight: 1.7, color: "text.secondary",
          fontFamily: mono ? MONO : undefined, wordBreak: "break-word",
        }}
      >
        {String(value)}
      </Typography>
    </Stack>
  );
}

function Row({ row, index, open, onToggle }) {
  const when = whenOf(row);
  const verdict = VERDICT[row.decision] ?? { fg: "#9CA3AF", label: row.decision || "—" };
  const zebra = index % 2 === 1;

  return (
    <>
      <Box
        onClick={onToggle}
        sx={{
          display: "grid",
          gridTemplateColumns: "28px 176px 150px 1fr 96px 78px",
          alignItems: "center",
          gap: 1,
          px: 1, py: 0.55,
          cursor: "pointer",
          bgcolor: open ? "rgba(125,211,252,0.07)" : zebra ? "rgba(255,255,255,0.015)" : "transparent",
          borderTop: "1px solid",
          borderColor: "rgba(255,255,255,0.05)",
          "&:hover": { bgcolor: "rgba(255,255,255,0.05)" },
        }}
      >
        <Box sx={{ display: "flex", color: "text.disabled" }}>
          {open ? <ExpandMoreIcon sx={{ fontSize: 17 }} /> : <ChevronRightIcon sx={{ fontSize: 17 }} />}
        </Box>
        <Typography sx={{ fontFamily: MONO, fontSize: 11.5, color: "text.secondary" }}>
          {stamp(when)}
        </Typography>
        <Typography sx={{ fontFamily: MONO, fontSize: 11.5, color: "text.primary" }} noWrap>
          {row.action_type || "—"}
        </Typography>
        <Typography
          sx={{ fontSize: 12, color: "text.secondary", minWidth: 0 }}
          noWrap
        >
          {row.reason || "—"}
        </Typography>
        <Typography
          sx={{
            fontFamily: MONO, fontSize: 11.5, textAlign: "right",
            color: row.amount_paise ? "text.primary" : "text.disabled",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {rupees(row.amount_paise)}
        </Typography>
        <Typography
          sx={{ fontFamily: MONO, fontSize: 11, color: verdict.fg, textAlign: "right" }}
        >
          {verdict.label}
        </Typography>
      </Box>

      {/* Opens UNDER the row it belongs to, so the neighbouring events stay
          on screen. That adjacency is usually most of the answer. */}
      {open && (
        <Box
          sx={{
            px: 1, pl: 5.5, py: 1.25,
            bgcolor: "rgba(125,211,252,0.04)",
            borderTop: "1px solid", borderColor: "rgba(255,255,255,0.05)",
          }}
        >
          <Field label="Timestamp" value={when ? when.toISOString() : "—"} mono />
          <Field label="Action" value={row.action_type} mono />
          <Field label="Decision" value={row.decision} mono />
          <Field label="Amount" value={rupees(row.amount_paise)} mono />
          <Field label="Order" value={row.order_id} mono />
          <Field label="Customer" value={row.customer_id} mono />
          {/* Never truncated. The reasoning is the point of this log. */}
          <Field label="Reason" value={row.reason} />
          <Box sx={{ mt: 1 }}>
            <Button
              size="small"
              startIcon={<ContentCopyIcon sx={{ fontSize: 14 }} />}
              onClick={(e) => {
                e.stopPropagation();
                navigator.clipboard?.writeText(JSON.stringify(row, null, 2));
              }}
              sx={{ textTransform: "none", fontSize: 11.5 }}
            >
              Copy record
            </Button>
          </Box>
        </Box>
      )}
    </>
  );
}

export default function LogConsole({ rows, onRefresh, loading }) {
  const [query, setQuery] = useState("");
  const [range, setRange] = useState("all");
  const [openIds, setOpenIds] = useState(() => new Set());
  const [asText, setAsText] = useState(false);
  const [menu, setMenu] = useState(null);
  const listRef = useRef(null);

  const visible = useMemo(() => {
    const now = Date.now();
    const span = RANGES.find((r) => r.key === range)?.ms;
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (span) {
        const when = whenOf(row);
        if (!when || now - when.getTime() > span) return false;
      }
      if (!needle) return true;
      return [row.action_type, row.decision, row.reason, row.order_id,
              row.customer_id, String(row.amount_paise ?? "")]
        .some((v) => String(v ?? "").toLowerCase().includes(needle));
    });
  }, [rows, query, range]);

  // Collapsing everything when the filter changes stops a row staying open
  // that is no longer on screen, which reads as a stuck panel.
  useEffect(() => setOpenIds(new Set()), [query, range]);

  const toggle = (id) =>
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const textView = useMemo(
    () => visible.map((r) => {
      const when = whenOf(r);
      return `${when ? when.toISOString() : "—"}  ${(r.action_type || "").padEnd(28)}` +
        `${(r.decision || "").padEnd(11)}${rupees(r.amount_paise).padStart(12)}  ${r.reason || ""}`;
    }).join("\n"),
    [visible]);

  return (
    <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2,
               bgcolor: "background.paper", overflow: "hidden" }}>
      {/* ── toolbar ─────────────────────────────────────────────── */}
      <Box sx={{ px: 1.5, py: 1.25, borderBottom: "1px solid", borderColor: "divider" }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.25, flexWrap: "wrap", gap: 1 }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>Log events</Typography>
          <Box sx={{ flex: 1 }} />
          <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
            <Checkbox size="small" checked={asText} onChange={(e) => setAsText(e.target.checked)} />
            <Typography variant="caption" color="text.secondary">View as text</Typography>
          </Stack>
          <Tooltip title="Re-read the log">
            <span>
              <IconButton size="small" onClick={onRefresh} disabled={loading}>
                <RefreshIcon sx={{ fontSize: 17 }} />
              </IconButton>
            </span>
          </Tooltip>
          <Button size="small" onClick={(e) => setMenu(e.currentTarget)}
                  sx={{ textTransform: "none" }} endIcon={<ExpandMoreIcon sx={{ fontSize: 15 }} />}>
            Actions
          </Button>
          <Menu anchorEl={menu} open={Boolean(menu)} onClose={() => setMenu(null)}>
            <MenuItem onClick={() => { setOpenIds(new Set(visible.map((r) => r.id))); setMenu(null); }}>
              Expand all shown
            </MenuItem>
            <MenuItem onClick={() => { setOpenIds(new Set()); setMenu(null); }}>
              Collapse all
            </MenuItem>
            <MenuItem onClick={() => {
              navigator.clipboard?.writeText(textView); setMenu(null);
            }}>
              Copy shown events
            </MenuItem>
          </Menu>
        </Stack>

        <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", gap: 1 }}>
          <Stack direction="row" spacing={1}
                 sx={{ alignItems: "center", flex: 1, minWidth: 220,
                       border: "1px solid", borderColor: "divider",
                       borderRadius: 1.5, px: 1, height: 32 }}>
            <SearchIcon sx={{ fontSize: 16, color: "text.disabled" }} />
            <InputBase
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter events — action, reason, order id, amount"
              sx={{ fontSize: 12.5, flex: 1 }}
            />
          </Stack>
          <Button size="small" onClick={() => { setQuery(""); setRange("all"); }}
                  sx={{ textTransform: "none", minWidth: 0 }}>
            Clear
          </Button>
          <Stack direction="row" sx={{ border: "1px solid", borderColor: "divider",
                                       borderRadius: 1.5, overflow: "hidden" }}>
            {RANGES.map((r) => (
              <Box
                key={r.key}
                component="button"
                type="button"
                onClick={() => setRange(r.key)}
                sx={{
                  px: 1.25, height: 32, border: "none", cursor: "pointer",
                  bgcolor: range === r.key ? "rgba(255,255,255,0.10)" : "transparent",
                  color: range === r.key ? "text.primary" : "text.secondary",
                  fontSize: 11.5, fontWeight: range === r.key ? 700 : 500,
                }}
              >
                {r.label}
              </Box>
            ))}
          </Stack>
        </Stack>
      </Box>

      {/* ── column heads ────────────────────────────────────────── */}
      {!asText && (
        <Box sx={{
          display: "grid",
          gridTemplateColumns: "28px 176px 150px 1fr 96px 78px",
          gap: 1, px: 1, py: 0.75,
          borderBottom: "1px solid", borderColor: "divider",
          bgcolor: "rgba(255,255,255,0.02)",
        }}>
          <Box />
          {["Timestamp", "Action", "Message", "Amount", "Decision"].map((h, i) => (
            <Typography key={h} variant="caption"
                        sx={{ fontSize: 10.5, letterSpacing: 0.5, fontWeight: 700,
                              color: "text.disabled",
                              textAlign: i >= 3 ? "right" : "left" }}>
              {h.toUpperCase()}
            </Typography>
          ))}
        </Box>
      )}

      {/* ── events ──────────────────────────────────────────────── */}
      <Box ref={listRef} sx={{ maxHeight: 560, overflowY: "auto" }}>
        <Typography variant="caption"
                    sx={{ display: "block", textAlign: "center", py: 1,
                          color: "text.disabled", fontSize: 11.5 }}>
          {rows.length
            ? "No older events at this moment."
            : "No events recorded yet."}
        </Typography>

        {asText ? (
          <Box component="pre" sx={{
            m: 0, px: 2, py: 1, fontFamily: MONO, fontSize: 11.5,
            color: "text.secondary", whiteSpace: "pre-wrap", wordBreak: "break-word",
          }}>
            {textView || "—"}
          </Box>
        ) : visible.length === 0 ? (
          <Typography variant="caption"
                      sx={{ display: "block", textAlign: "center", py: 4, color: "text.secondary" }}>
            Nothing matches that filter.
          </Typography>
        ) : (
          visible.map((row, i) => (
            <Row key={row.id ?? i} row={row} index={i}
                 open={openIds.has(row.id)} onToggle={() => toggle(row.id)} />
          ))
        )}

        <Typography variant="caption"
                    sx={{ display: "block", textAlign: "center", py: 1,
                          color: "text.disabled", fontSize: 11.5,
                          borderTop: "1px solid", borderColor: "rgba(255,255,255,0.05)" }}>
          {/* This log is a live Firestore subscription, so there is no
              polling to resume — saying so is more useful than copying a
              control that would do nothing here. */}
          Live — new events appear as the agent writes them.
        </Typography>
      </Box>

      <Box sx={{ px: 1.5, py: 0.75, borderTop: "1px solid", borderColor: "divider" }}>
        <Typography variant="caption" color="text.disabled" sx={{ fontSize: 11 }}>
          Showing {visible.length} of {rows.length} event{rows.length === 1 ? "" : "s"}
          {range !== "all" && ` · last ${RANGES.find((r) => r.key === range)?.label}`}
        </Typography>
      </Box>
    </Box>
  );
}
