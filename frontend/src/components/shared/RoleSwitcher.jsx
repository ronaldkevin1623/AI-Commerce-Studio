import { Box, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";

import { ROLES, useRole } from "../../context/RoleContext";

/**
 * A segmented control, deliberately not a switch.
 *
 * A switch means on/off — one thing, present or absent, and the "off" state
 * reads as the absence of the "on" one. Customer and merchant are opposing
 * options of equal standing, and neither is the negation of the other. The
 * component guidance is explicit about this, and it matters here beyond
 * pedantry: rendering the seller as "buyer, switched off" would misstate the
 * whole architecture the merchant side was built to demonstrate.
 *
 * Switching moves you to that party's home rather than trying to hold your
 * place. There is no meaningful equivalent of /orders on the seller's side,
 * and inventing one to preserve position would be worse than a clean landing.
 */
export default function RoleSwitcher() {
  const { role, setRole } = useRole();
  const navigate = useNavigate();

  if (!role) return null;

  const change = (next) => {
    if (next === role) return;
    setRole(next);
    navigate(ROLES[next].home);
  };

  return (
    <Stack
      direction="row"
      spacing={0}
      role="group"
      aria-label="Which side of the transaction you are on"
      sx={{
        p: "2px",
        borderRadius: 2,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "rgba(255,255,255,0.03)",
      }}
    >
      {Object.values(ROLES).map((option) => {
        const active = option.id === role;
        return (
          <Box
            key={option.id}
            component="button"
            type="button"
            aria-pressed={active}
            onClick={() => change(option.id)}
            sx={{
              px: 1.25,
              py: 0.4,
              border: "none",
              borderRadius: 1.5,
              cursor: active ? "default" : "pointer",
              bgcolor: active ? "rgba(255,255,255,0.10)" : "transparent",
              transition: "background-color 140ms, color 140ms",
              "&:hover": {
                bgcolor: active ? "rgba(255,255,255,0.10)" : "rgba(255,255,255,0.05)",
              },
            }}
          >
            <Typography
              variant="caption"
              sx={{
                fontSize: 11.5,
                fontWeight: active ? 700 : 500,
                color: active ? "text.primary" : "text.secondary",
                whiteSpace: "nowrap",
              }}
            >
              {option.label}
            </Typography>
          </Box>
        );
      })}
    </Stack>
  );
}
