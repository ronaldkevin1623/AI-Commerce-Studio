import { useState } from "react";
import { Box, Button, Stack, Typography } from "@mui/material";
import TableRowsOutlinedIcon from "@mui/icons-material/TableRowsOutlined";
import BarChartOutlinedIcon from "@mui/icons-material/BarChartOutlined";

/**
 * A chart in a card, with a table view behind a toggle.
 *
 * The table isn't decoration: it's the WCAG-clean twin, so no value on this
 * page is reachable only by reading a bar's height or hovering it.
 */
export default function ChartCard({ title, hint, columns, rows, children, sample }) {
  const [asTable, setAsTable] = useState(false);
  const canToggle = Boolean(columns && rows?.length);

  return (
    <Box
      sx={{
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2.5,
        p: 2.5,
      }}
    >
      <Stack
        direction="row"
        sx={{ alignItems: "flex-start", justifyContent: "space-between", gap: 2, mb: hint ? 0.5 : 2 }}
      >
        <Typography variant="body2" fontWeight={600}>
          {title}
        </Typography>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexShrink: 0 }}>
          {sample != null && (
            <Typography variant="caption" sx={{ color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
              n={sample}
            </Typography>
          )}
          {canToggle && (
            <Button
              size="small"
              onClick={() => setAsTable((t) => !t)}
              startIcon={
                asTable ? (
                  <BarChartOutlinedIcon sx={{ fontSize: 15 }} />
                ) : (
                  <TableRowsOutlinedIcon sx={{ fontSize: 15 }} />
                )
              }
              sx={{
                color: "text.secondary",
                fontSize: 11.5,
                minWidth: 0,
                boxShadow: "none",
                "&:hover": { boxShadow: "none" },
              }}
            >
              {asTable ? "Chart" : "Table"}
            </Button>
          )}
        </Stack>
      </Stack>

      {hint && (
        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 2 }}>
          {hint}
        </Typography>
      )}

      {asTable ? (
        <Box component="table" sx={{ width: "100%", borderCollapse: "collapse" }}>
          <Box component="thead">
            <Box component="tr">
              {columns.map((col, i) => (
                <Box
                  key={col}
                  component="th"
                  sx={{
                    textAlign: i === 0 ? "left" : "right",
                    py: 0.75,
                    borderBottom: "1px solid",
                    borderColor: "divider",
                    fontSize: 11.5,
                    fontWeight: 600,
                    color: "text.secondary",
                  }}
                >
                  {col}
                </Box>
              ))}
            </Box>
          </Box>
          <Box component="tbody">
            {rows.map((row, r) => (
              <Box component="tr" key={r}>
                {row.map((cell, i) => (
                  <Box
                    key={i}
                    component="td"
                    sx={{
                      textAlign: i === 0 ? "left" : "right",
                      py: 0.75,
                      borderBottom: "1px solid",
                      borderColor: "divider",
                      fontSize: 12.5,
                      color: i === 0 ? "text.secondary" : "text.primary",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {cell}
                  </Box>
                ))}
              </Box>
            ))}
          </Box>
        </Box>
      ) : (
        children
      )}
    </Box>
  );
}
