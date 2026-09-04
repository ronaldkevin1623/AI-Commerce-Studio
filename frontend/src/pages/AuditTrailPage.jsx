import { useMemo, useState } from "react";
import { Box, Typography, Button } from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";

import { useFirestoreAudit } from "../hooks/useFirestoreAudit";
import PageBanner from "../components/shared/PageBanner";
import FilterBar from "../components/audit/FilterBar";
import LogConsole from "../components/audit/LogConsole";

function exportToCSV(decisions) {
  const headers = ["time", "action_type", "amount_paise", "decision", "reason", "order_id"];
  const rows = decisions.map((d) => [
    d.timestamp?.toDate?.().toISOString() ?? "",
    d.action_type ?? "",
    d.amount_paise ?? "",
    d.decision ?? "",
    '"' + (d.reason ?? "").replace(/"/g, '""') + '"',
    d.order_id ?? "",
  ]);
  const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `commerce-studio-audit-log-${Date.now()}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

export default function AuditTrailPage() {
  const { decisions, loading, error } = useFirestoreAudit();
  const [activeFilter, setActiveFilter] = useState("all");
  // Bumping this remounts nothing — the Firestore subscription is already
  // live — so the refresh control exists to say "you are looking at now",
  // not to fetch. It re-runs the client-side window instead of pretending.
  const [, setTick] = useState(0);

  const filtered = useMemo(() => {
    if (activeFilter === "all") return decisions;
    return decisions.filter((d) => d.decision === activeFilter);
  }, [decisions, activeFilter]);

  return (
    <Box>
      <PageBanner
        title="Audit trail"
        subtitle="Every action the agent has taken, with the reasoning behind it"
        action={
          <Button
            variant="outlined"
            size="small"
            startIcon={<DownloadIcon />}
            onClick={() => exportToCSV(decisions)}
            disabled={decisions.length === 0}
            sx={{ borderColor: "rgba(255,255,255,0.2)" }}
          >
            Export log
          </Button>
        }
      />

      <Box sx={{ maxWidth: 1220, mx: "auto", px: 3, py: 4 }}>
        {loading ? (
          <Typography variant="body2" color="text.secondary">Connecting to live log…</Typography>
        ) : error ? (
          <Box
            sx={{
              p: 2.5,
              borderRadius: 2,
              border: "1px solid",
              borderColor: "warning.dark",
              bgcolor: "rgba(245,158,11,0.08)",
            }}
          >
            <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
              The live log could not be read
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.65 }}>
              The agent is still recording every decision — this page just cannot
              reach them right now, so what you see below is nothing rather than
              everything. Firestore reported: {error}
            </Typography>
          </Box>
        ) : (
          <>
            <FilterBar decisions={decisions} activeFilter={activeFilter} onChange={setActiveFilter} />
            <LogConsole
              rows={filtered}
              loading={loading}
              onRefresh={() => setTick((n) => n + 1)}
            />
          </>
        )}
      </Box>
    </Box>
  );
}

