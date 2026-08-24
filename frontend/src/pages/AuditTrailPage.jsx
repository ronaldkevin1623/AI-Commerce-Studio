import { Box, Table, TableHead, TableRow, TableCell, TableBody, Chip, Typography } from "@mui/material";
import { useFirestoreAudit } from "../hooks/useFirestoreAudit";

const decisionColor = { allowed: "success", escalated: "warning", blocked: "error" };

export default function AuditTrailPage() {
  const { decisions, loading } = useFirestoreAudit();

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: "auto" }}>
      <Typography variant="h2" gutterBottom>Audit trail</Typography>

      {loading && <Typography variant="body2">Connecting to live log…</Typography>}

      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Time</TableCell>
            <TableCell>Action</TableCell>
            <TableCell>Amount</TableCell>
            <TableCell>Decision</TableCell>
            <TableCell>Reason</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {decisions.map((d) => (
            <TableRow key={d.id}>
              <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>
                {d.timestamp?.toDate?.().toLocaleTimeString() ?? "—"}
              </TableCell>
              <TableCell>{d.action_type}</TableCell>
              <TableCell>₹{(d.amount_paise / 100).toFixed(2)}</TableCell>
              <TableCell>
                <Chip size="small" label={d.decision} color={decisionColor[d.decision] || "default"} />
              </TableCell>
              <TableCell sx={{ fontSize: 12 }}>{d.reason}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}