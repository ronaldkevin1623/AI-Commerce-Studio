import { useMemo, useState } from "react";
import { Box, Typography, Button } from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";

import { useFirestoreAudit } from "../hooks/useFirestoreAudit";
import PageBanner from "../components/shared/PageBanner";
import FilterBar from "../components/audit/FilterBar";
import AuditTable from "../components/audit/AuditTable";

function exportToCSV(decisions) {
  const headers = ["time", "action_type", "amount_paise", "decision", "reason", "order_id"];
  const rows = decisions.map((d) => [
    d.timestamp?.toDate?.().toISOString() ?? "",
    d.action_type ?? "",
    d.amount_paise ?? "",
    d.decision ?? "",
    `"${(d.reason ?? "").replace(/"/g, '""')}"`,
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
  const { decisions, loading } = useFirestoreAudit();
  const [activeFilter, setActiveFilter] = useState("all");

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

      <Box sx={{ maxWidth: 1000, mx: "auto", px: 3, py: 4 }}>
        {loading ? (
          <Typography variant="body2" color="text.secondary">Connecting to live log…</Typography>
        ) : (
          <>
            <FilterBar decisions={decisions} activeFilter={activeFilter} onChange={setActiveFilter} />
            <Box sx={{ bgcolor: "background.paper", border: "1px solid", borderColor: "divider", borderRadius: 2.5, overflow: "hidden" }}>
              <AuditTable decisions={filtered} />
            </Box>
          </>
        )}
      </Box>
    </Box>
  );
}