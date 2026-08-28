import { useState } from "react";
import { Box, Typography, Stack, Tooltip, Collapse } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import CheckIcon from "@mui/icons-material/Check";
import SearchIcon from "@mui/icons-material/Search";
import ShieldIcon from "@mui/icons-material/ShieldOutlined";
import ReceiptLongIcon from "@mui/icons-material/ReceiptLong";

const DECISION_COLOR = { allowed: "#22C55E", escalated: "#F59E0B", blocked: "#EF4444" };

function ToolRow({ icon, label, chip, detail, isOpen, onToggle }) {
  return (
    <Box>
      <Stack
        direction="row"
        spacing={1}
        onClick={onToggle}
        sx={{
          alignItems: "center",
          cursor: "pointer",
          borderRadius: 1.5,
          px: 0.75,
          py: 0.5,
          mx: -0.75,
          "&:hover": { bgcolor: "action.hover" },
        }}
      >
        <Box sx={{ color: "text.secondary", display: "flex" }}>{icon}</Box>
        <Typography variant="body2" fontWeight={600} sx={{ flexShrink: 0 }}>{label}</Typography>
        <Box
          sx={{
            bgcolor: "background.default",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 999,
            px: 1,
            py: 0.15,
            minWidth: 0,
          }}
        >
          <Typography
            variant="caption"
            sx={{ fontFamily: "monospace", color: "text.secondary", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", display: "block" }}
          >
            {chip}
          </Typography>
        </Box>
      </Stack>

      <Collapse in={isOpen}>
        <Box sx={{ ml: 3.5, mt: 0.5, mb: 0.5, borderLeft: "1px solid", borderColor: "divider", pl: 1.5 }}>
          {detail.map((line, i) => (
            <Typography key={i} variant="caption" color="text.secondary" sx={{ display: "block", lineHeight: 1.8 }}>
              {line}
            </Typography>
          ))}
        </Box>
      </Collapse>
    </Box>
  );
}

export default function ToolChips({ candidates, product, riskGate, orderInfo }) {
  const [openRows, setOpenRows] = useState(new Set());
  const [summaryOpen, setSummaryOpen] = useState(true);

  const toggleRow = (key) => {
    setOpenRows((current) => {
      const next = new Set(current);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const hasResults = candidates && candidates.length > 0;
  if (!hasResults) return null;

  const rows = [
    {
      key: "search",
      icon: <SearchIcon sx={{ fontSize: 15 }} />,
      label: "Search catalog",
      chip: `${candidates.length} candidates found`,
      detail: candidates.slice(0, 3).map((c) => `${c.name} — ₹${(c.price_paise / 100).toLocaleString("en-IN")}`),
    },
  ];

  if (riskGate?.state && riskGate.state !== "idle") {
    rows.push({
      key: "risk",
      icon: <ShieldIcon sx={{ fontSize: 15 }} />,
      label: "Risk check",
      chip: riskGate.state,
      detail: [riskGate.reason],
    });
  }

  if (orderInfo) {
    rows.push({
      key: "order",
      icon: <ReceiptLongIcon sx={{ fontSize: 15 }} />,
      label: "Create order",
      chip: `₹${(orderInfo.amount_paise / 100).toLocaleString("en-IN")}`,
      detail: [`Razorpay order: ${orderInfo.razorpay_order_id}`],
    });
  }

  return (
    <Box>
      <Stack
        direction="row"
        spacing={0.75}
        onClick={() => setSummaryOpen((o) => !o)}
        sx={{ alignItems: "center", cursor: "pointer", mb: 1, userSelect: "none" }}
      >
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1 }}>
          {rows.length} tool calls
        </Typography>
        <ExpandMoreIcon
          sx={{
            fontSize: 15,
            color: "text.secondary",
            transform: summaryOpen ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s",
          }}
        />
      </Stack>

      <Collapse in={summaryOpen}>
        <Stack spacing={0.5} sx={{ mb: 1.5 }}>
          {rows.map((row) => (
            <ToolRow
              key={row.key}
              icon={row.icon}
              label={row.label}
              chip={row.chip}
              detail={row.detail}
              isOpen={openRows.has(row.key)}
              onToggle={() => toggleRow(row.key)}
            />
          ))}
        </Stack>

        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", pt: 1, borderTop: "1px solid", borderColor: "divider" }}>
          {product && (
            <Tooltip title={`${product.name} · ₹${(product.price_paise / 100).toLocaleString("en-IN")}`} arrow>
              <Box sx={{ bgcolor: "background.default", border: "1px solid", borderColor: "divider", borderRadius: 999, px: 1.25, py: 0.4, cursor: "default" }}>
                <Typography variant="caption" sx={{ fontFamily: "monospace" }}>{product.name.slice(0, 22)}</Typography>
              </Box>
            </Tooltip>
          )}
          {riskGate?.state && riskGate.state !== "idle" && (
            <Tooltip title={riskGate.reason} arrow>
              <Box sx={{ bgcolor: "background.default", border: "1px solid", borderColor: "divider", borderRadius: 999, px: 1.25, py: 0.4, display: "flex", alignItems: "center", gap: 0.6, cursor: "default" }}>
                <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: DECISION_COLOR[riskGate.state] || "#9AA3B2" }} />
                <Typography variant="caption" sx={{ fontFamily: "monospace" }}>{riskGate.state}</Typography>
              </Box>
            </Tooltip>
          )}
          {orderInfo && (
            <Tooltip title={orderInfo.razorpay_order_id} arrow>
              <Box sx={{ bgcolor: "background.default", border: "1px solid", borderColor: "divider", borderRadius: 999, px: 1.25, py: 0.4, display: "flex", alignItems: "center", gap: 0.5, cursor: "default" }}>
                <CheckIcon sx={{ fontSize: 12, color: "success.main" }} />
                <Typography variant="caption" sx={{ fontFamily: "monospace" }}>order created</Typography>
              </Box>
            </Tooltip>
          )}
        </Stack>
      </Collapse>
    </Box>
  );
}