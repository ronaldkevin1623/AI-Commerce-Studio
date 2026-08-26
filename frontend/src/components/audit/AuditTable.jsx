import { Box, Typography, Collapse } from "@mui/material";
import { useState, Fragment } from "react";

const DECISION_STYLE = {
  allowed: { color: "#22C55E", bg: "rgba(34,197,94,0.12)" },
  escalated: { color: "#F59E0B", bg: "rgba(245,158,11,0.12)" },
  blocked: { color: "#EF4444", bg: "rgba(239,68,68,0.12)" },
};

function formatTime(timestamp) {
  if (!timestamp?.toDate) return "—";
  return timestamp.toDate().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatAmount(amountPaise) {
  if (amountPaise == null) return "—";
  return `₹${(amountPaise / 100).toLocaleString("en-IN")}`;
}

function DecisionPill({ decision }) {
  const style = DECISION_STYLE[decision] || { color: "#9AA3B2", bg: "rgba(154,163,178,0.12)" };
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.75,
        px: 1.25,
        py: 0.4,
        borderRadius: 999,
        bgcolor: style.bg,
      }}
    >
      <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: style.color }} />
      <Typography variant="caption" sx={{ color: style.color, fontWeight: 600, textTransform: "capitalize" }}>
        {decision}
      </Typography>
    </Box>
  );
}

const COLUMNS = [
  { key: "time", label: "Time", width: "14%" },
  { key: "action", label: "Action", width: "22%" },
  { key: "amount", label: "Amount", width: "13%", align: "right" },
  { key: "decision", label: "Decision", width: "16%" },
  { key: "reason", label: "Reason", width: "35%" },
];

export default function AuditTable({ decisions }) {
  const [expandedId, setExpandedId] = useState(null);

  if (decisions.length === 0) {
    return (
      <Box sx={{ py: 8, textAlign: "center" }}>
        <Typography variant="body2" color="text.secondary">
          No actions logged yet — decisions will appear here the moment the agent makes one.
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ display: "flex", px: 2.5, py: 1.5, borderBottom: "1px solid", borderColor: "divider" }}>
        {COLUMNS.map((col) => (
          <Box key={col.key} sx={{ width: col.width, textAlign: col.align || "left" }}>
            <Typography
              variant="caption"
              sx={{ color: "text.secondary", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", fontSize: 11 }}
            >
              {col.label}
            </Typography>
          </Box>
        ))}
      </Box>

      {decisions.map((d) => {
        const isExpanded = expandedId === d.id;
        return (
          <Fragment key={d.id}>
            <Box
              onClick={() => setExpandedId(isExpanded ? null : d.id)}
              sx={{
                display: "flex",
                alignItems: "center",
                px: 2.5,
                py: 1.75,
                cursor: "pointer",
                borderBottom: "1px solid",
                borderColor: "divider",
                transition: "background-color 0.12s",
                "&:hover": { bgcolor: "action.hover" },
              }}
            >
              <Box sx={{ width: COLUMNS[0].width }}>
                <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: 12.5, color: "text.secondary" }}>
                  {formatTime(d.timestamp)}
                </Typography>
              </Box>
              <Box sx={{ width: COLUMNS[1].width }}>
                <Typography variant="body2" sx={{ fontWeight: 500 }}>{d.action_type}</Typography>
              </Box>
              <Box sx={{ width: COLUMNS[2].width, textAlign: "right" }}>
                <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums", fontWeight: 500 }}>
                  {formatAmount(d.amount_paise)}
                </Typography>
              </Box>
              <Box sx={{ width: COLUMNS[3].width }}>
                <DecisionPill decision={d.decision} />
              </Box>
              <Box sx={{ width: COLUMNS[4].width }}>
                <Typography
                  variant="body2"
                  sx={{ color: "text.secondary", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                >
                  {d.reason}
                </Typography>
              </Box>
            </Box>

            <Collapse in={isExpanded}>
              <Box sx={{ px: 2.5, py: 2, bgcolor: "background.paper", borderBottom: "1px solid", borderColor: "divider" }}>
                <Typography
                  variant="caption"
                  sx={{ color: "text.secondary", textTransform: "uppercase", letterSpacing: "0.06em", display: "block", mb: 0.75 }}
                >
                  Full reasoning
                </Typography>
                <Typography variant="body2" sx={{ mb: 1 }}>{d.reason}</Typography>
                <Box sx={{ display: "flex", gap: 3 }}>
                  {d.order_id && (
                    <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>
                      order: {d.order_id}
                    </Typography>
                  )}
                  {d.customer_id && (
                    <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>
                      customer: {d.customer_id}
                    </Typography>
                  )}
                </Box>
              </Box>
            </Collapse>
          </Fragment>
        );
      })}
    </Box>
  );
}