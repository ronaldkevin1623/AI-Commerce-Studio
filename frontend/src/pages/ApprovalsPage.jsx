import { useCallback, useEffect, useState } from "react";
import { Box, Button, Chip, Stack, Typography } from "@mui/material";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";

import PageBanner from "../components/shared/PageBanner";
import LoadingState from "../components/shared/LoadingState";
import { inr } from "../components/orders/format";

import { API_BASE } from "../config";

/**
 * The human end of the external-agent boundary.
 *
 * An agent connected over MCP can search and propose, but anything the risk
 * gate escalates parks here and cannot move until a person rules on it. The
 * agent has no tool that reaches this page — that asymmetry is the point,
 * so the page states what the agent asked for and what the gate objected to,
 * rather than presenting a bare approve button.
 */
export default function ApprovalsPage() {
  const [proposals, setProposals] = useState([]);
  const [status, setStatus] = useState("loading");
  const [busy, setBusy] = useState(null);
  const [outcome, setOutcome] = useState({});

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/proposals/pending`);
      const data = await res.json();
      setProposals(data.proposals ?? []);
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    load();
    // An agent may park something while this page is open.
    const poll = setInterval(load, 8000);
    return () => clearInterval(poll);
  }, [load]);

  const decide = async (id, approved) => {
    setBusy(id);
    try {
      await fetch(`${API_BASE}/proposals/${id}/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved }),
      });

      if (approved) {
        // Finish it here rather than making the person wait for the agent
        // to poll. Same broker call, same re-verification.
        const res = await fetch(`${API_BASE}/proposals/${id}/confirm`, { method: "POST" });
        const result = await res.json();
        setOutcome((o) => ({ ...o, [id]: result }));
      } else {
        setOutcome((o) => ({ ...o, [id]: { ok: true, status: "denied" } }));
      }
      await load();
    } catch {
      setOutcome((o) => ({ ...o, [id]: { ok: false, error: "Request failed" } }));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Box>
      <PageBanner
        title="Approvals"
        subtitle="Purchases an external agent proposed that the risk gate escalated. Nothing here proceeds until you decide — the agent cannot approve its own request."
      />

      <Box sx={{ maxWidth: 860, mx: "auto", px: 3, py: 4 }}>
        {status === "loading" && <LoadingState label="Loading proposals" />}

        {status === "error" && (
          <Typography variant="body2" sx={{ color: "error.main" }}>
            Couldn't reach the backend. Check that uvicorn is running on port 8000.
          </Typography>
        )}

        {status === "ready" && proposals.length === 0 && (
          <Box
            sx={{
              border: "1px dashed",
              borderColor: "divider",
              borderRadius: 2.5,
              p: 4,
              textAlign: "center",
            }}
          >
            <Typography variant="body2" color="text.secondary">
              Nothing waiting on you. When an agent proposes a purchase above the auto-approve
              limit, it appears here.
            </Typography>
          </Box>
        )}

        <Stack spacing={2}>
          {proposals.map((p) => {
            const result = outcome[p.id];
            return (
              <Box
                key={p.id}
                sx={{
                  bgcolor: "background.paper",
                  border: "1px solid",
                  borderColor: "rgba(245,158,11,0.35)",
                  borderRadius: 2.5,
                  overflow: "hidden",
                }}
              >
                <Stack
                  direction="row"
                  spacing={1}
                  sx={{
                    alignItems: "center",
                    px: 2.5,
                    py: 1.25,
                    bgcolor: "rgba(245,158,11,0.07)",
                    borderBottom: "1px solid",
                    borderColor: "divider",
                  }}
                >
                  <SmartToyOutlinedIcon sx={{ fontSize: 16, color: "warning.main" }} />
                  <Typography variant="caption" sx={{ color: "warning.main", fontWeight: 600 }}>
                    An external agent wants to buy this
                  </Typography>
                  <Box sx={{ flex: 1 }} />
                  <Chip
                    size="small"
                    label={p.source === "mcp" ? "via MCP" : p.source}
                    sx={{
                      height: 20,
                      bgcolor: "rgba(255,255,255,0.06)",
                      color: "text.secondary",
                      "& .MuiChip-label": { px: 0.9, fontSize: 10.5 },
                    }}
                  />
                </Stack>

                <Box sx={{ p: 2.5 }}>
                  <Stack direction="row" spacing={2} sx={{ alignItems: "flex-start", mb: 2 }}>
                    {p.product.image ? (
                      <Box
                        component="img"
                        src={p.product.image}
                        alt=""
                        sx={{ width: 64, height: 64, borderRadius: 2, objectFit: "cover", bgcolor: "#fff", flexShrink: 0 }}
                      />
                    ) : (
                      <Box sx={{ width: 64, height: 64, borderRadius: 2, bgcolor: "rgba(255,255,255,0.05)", flexShrink: 0 }} />
                    )}
                    <Box sx={{ minWidth: 0, flex: 1 }}>
                      <Typography variant="body2" fontWeight={600} sx={{ lineHeight: 1.4 }}>
                        {p.product.name}
                      </Typography>
                      <Stack direction="row" spacing={1.5} sx={{ mt: 0.5, flexWrap: "wrap" }}>
                        <Typography variant="caption" color="text.secondary">
                          {p.product.condition ?? "Condition not stated"}
                        </Typography>
                        {p.product.seller_feedback != null && (
                          <Typography variant="caption" color="text.secondary">
                            seller {p.product.seller_feedback}%
                          </Typography>
                        )}
                        {p.product.url && (
                          <Box
                            component="a"
                            href={p.product.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            sx={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 0.4,
                              fontSize: 11.5,
                              color: "text.secondary",
                              textDecoration: "none",
                              "&:hover": { color: "primary.light" },
                            }}
                          >
                            View listing <OpenInNewIcon sx={{ fontSize: 12 }} />
                          </Box>
                        )}
                      </Stack>
                    </Box>
                    <Typography
                      variant="body2"
                      fontWeight={700}
                      sx={{ fontVariantNumeric: "tabular-nums", flexShrink: 0 }}
                    >
                      {inr(p.product.price_paise)}
                    </Typography>
                  </Stack>

                  {/* Why the gate stopped it — the actual decision content */}
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{
                      alignItems: "flex-start",
                      bgcolor: "rgba(245,158,11,0.06)",
                      border: "1px solid",
                      borderColor: "rgba(245,158,11,0.22)",
                      borderRadius: 2,
                      p: 1.5,
                      mb: 2,
                    }}
                  >
                    <WarningAmberOutlinedIcon sx={{ fontSize: 15, color: "warning.main", mt: "1px", flexShrink: 0 }} />
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="caption" sx={{ color: "text.primary", display: "block", fontWeight: 600 }}>
                        {p.reason}
                      </Typography>
                      {p.budget && (
                        <Typography variant="caption" sx={{ color: "text.secondary" }}>
                          {p.budget}
                        </Typography>
                      )}
                    </Box>
                  </Stack>

                  {result ? (
                    <Typography
                      variant="body2"
                      sx={{ color: result.ok ? "success.main" : "error.main", fontWeight: 600 }}
                    >
                      {result.status === "ordered"
                        ? `Approved — order ${result.order_id} created`
                        : result.status === "denied"
                          ? "Denied. The agent cannot retry this proposal."
                          : result.error ?? result.status}
                    </Typography>
                  ) : (
                    <Stack direction="row" spacing={1}>
                      <Button
                        size="small"
                        variant="contained"
                        disabled={busy === p.id}
                        onClick={() => decide(p.id, true)}
                        sx={{ boxShadow: "none", "&:hover": { boxShadow: "none" } }}
                      >
                        {busy === p.id ? "Working…" : "Approve and order"}
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={busy === p.id}
                        onClick={() => decide(p.id, false)}
                        sx={{
                          boxShadow: "none",
                          "&:hover": { boxShadow: "none" },
                          borderColor: "divider",
                          color: "text.secondary",
                        }}
                      >
                        Deny
                      </Button>
                    </Stack>
                  )}

                  <Typography
                    variant="caption"
                    sx={{ color: "text.secondary", display: "block", mt: 1.5, fontFamily: "monospace", fontSize: 10.5 }}
                  >
                    {p.id} · requested by {p.customer_email}
                  </Typography>
                </Box>
              </Box>
            );
          })}
        </Stack>
      </Box>
    </Box>
  );
}
