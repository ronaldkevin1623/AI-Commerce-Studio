import { AppBar, Toolbar, Box, Typography, Chip, Stack } from "@mui/material";
import { Link, useLocation } from "react-router-dom";
import ShoppingCartIcon from "@mui/icons-material/ShoppingCartOutlined";

const NAV_ITEMS = [
  { label: "Console", path: "/console" },
  { label: "Audit trail", path: "/audit" },
  { label: "Failure recovery", path: "/recovery" },
];

export default function AppShell({ children }) {
  const location = useLocation();

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar
        position="static"
        elevation={0}
        sx={{ borderBottom: "1px solid", borderColor: "divider" }}
      >
        <Toolbar sx={{ justifyContent: "space-between" }}>
          <Stack
            direction="row"
            alignItems="center"
            spacing={1}
            component={Link}
            to="/"
            sx={{ textDecoration: "none", color: "inherit" }}
          >
            <Box
              sx={{
                width: 28,
                height: 28,
                borderRadius: "8px",
                bgcolor: "primary.main",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <ShoppingCartIcon sx={{ fontSize: 16, color: "#fff" }} />
            </Box>
            <Typography fontWeight={600} color="text.primary">CartPilot</Typography>
          </Stack>

          <Stack direction="row" spacing={3} alignItems="center">
            {NAV_ITEMS.map((item) => (
              <Typography
                key={item.path}
                component={Link}
                to={item.path}
                variant="body2"
                sx={{
                  textDecoration: "none",
                  color: location.pathname === item.path ? "primary.light" : "text.secondary",
                  fontWeight: location.pathname === item.path ? 600 : 400,
                }}
              >
                {item.label}
              </Typography>
            ))}
            <Chip
              size="small"
              label="Test mode"
              sx={{
                bgcolor: "success.light",
                color: "success.main",
                "& .MuiChip-label": { px: 1.2 },
              }}
              icon={
                <Box
                  sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: "success.main", ml: 1 }}
                />
              }
            />
          </Stack>
        </Toolbar>
      </AppBar>

      <Box>{children}</Box>
    </Box>
  );
}