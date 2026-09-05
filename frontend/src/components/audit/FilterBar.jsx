import { Box, Typography } from "@mui/material";

const FILTERS = [
  // "Latest", not "All". The page subscribes to the most recent 50
  // decisions; the log holds hundreds. A chip reading "All 50" told the
  // reader they were looking at the whole trail and that the whole trail
  // was fifty rows long — both untrue, and the second one flattering.
  // Export reads the complete collection separately.
  { key: "all", label: "Latest", dotColor: null },
  { key: "allowed", label: "Allowed", dotColor: "#22C55E" },
  { key: "escalated", label: "Escalated", dotColor: "#F59E0B" },
  { key: "blocked", label: "Blocked", dotColor: "#EF4444" },
];

export default function FilterBar({ decisions, activeFilter, onChange }) {
  const countFor = (key) =>
    key === "all" ? decisions.length : decisions.filter((d) => d.decision === key).length;

  return (
    <Box
      sx={{
        display: "inline-flex",
        p: 0.5,
        borderRadius: 2.5,
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
        mb: 3,
      }}
    >
      {FILTERS.map((f) => {
        const isActive = activeFilter === f.key;
        return (
          <Box
            key={f.key}
            onClick={() => onChange(f.key)}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 0.75,
              px: 1.75,
              py: 0.75,
              borderRadius: 2,
              cursor: "pointer",
              userSelect: "none",
              bgcolor: isActive ? "background.default" : "transparent",
              transition: "background-color 0.15s",
              "&:hover": { bgcolor: isActive ? "background.default" : "action.hover" },
            }}
          >
            {f.dotColor && (
              <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: f.dotColor }} />
            )}
            <Typography
              variant="body2"
              sx={{
                fontWeight: isActive ? 600 : 400,
                color: isActive ? "text.primary" : "text.secondary",
              }}
            >
              {f.label}
            </Typography>
            <Typography
              variant="caption"
              sx={{
                color: "text.secondary",
                bgcolor: "background.default",
                borderRadius: 999,
                px: 0.75,
                minWidth: 20,
                textAlign: "center",
              }}
            >
              {countFor(f.key)}
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
}