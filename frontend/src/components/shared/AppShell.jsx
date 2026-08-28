import { AppBar, Toolbar, Box, Typography, Chip, Stack, Snackbar } from "@mui/material";
import CheckIcon from "@mui/icons-material/Check";
import { Link, useLocation } from "react-router-dom";
import ShoppingCartIcon from "@mui/icons-material/ShoppingCartOutlined";
import ShoppingBagIcon from "@mui/icons-material/ShoppingBagOutlined";

import { useCart } from "../../context/CartContext";
import { useRole } from "../../context/RoleContext";
import RoleSwitcher from "./RoleSwitcher";
import AppSidebar from "./AppSidebar";

// The only element on the page that scrolls. The bar and the sidebar are
// pinned by the shell, so a long page no longer carries the navigation off
// the top of the screen with it.
//
// The scrollbar is hidden rather than removed: Firefox and WebKit need
// telling separately, and neither declaration affects wheel, trackpad,
// keyboard or touch scrolling. A permanent light gutter down the right of a
// dark page reads as a seam, not a control.
const SCROLL_PANE = {
  flex: 1,
  minWidth: 0,
  minHeight: 0,
  overflowY: "auto",
  scrollbarWidth: "none",
  msOverflowStyle: "none",
  "&::-webkit-scrollbar": { display: "none" },
};


export default function AppShell({ children }) {
  const location = useLocation();
  const { totals, setOpen: setCartOpen, lastAdded, dismissAdded } = useCart();
  const cartCount = totals.count;
  const { role } = useRole();

  // Before a side is picked the landing page IS the choice, so the bar
  // carries the mark and nothing else — a nav full of tools you have not
  // chosen a role for is just noise.
  const chosen = Boolean(role);

  // The landing page is where the role gets chosen, so it carries none of the
  // furniture that belongs to a role. A sidebar there is a menu for a side of
  // the counter you have not picked yet — and because the choice persists, it
  // was showing the previous role's tools behind the page asking you to
  // choose again.
  const onLanding = location.pathname === "/";

  // The cart is a buying instrument. A merchant still has a Console and can
  // genuinely use it, so this reappears the moment they switch back rather
  // than being hidden for good.
  const showCart = role === "customer" && !onLanding;

  // Both parties navigate from the sidebar, so the top bar keeps only the
  // mark, the cart, the role switcher and the mode chip. Duplicating the same
  // destinations in a top row as well would give every page two homes.
  const sidebarLayout = chosen && !onLanding;

  return (
    <Box
      sx={{
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        bgcolor: "background.default",
      }}
    >
      <AppBar
        position="static"
        elevation={0}
        sx={{ flexShrink: 0, borderBottom: "1px solid", borderColor: "divider" }}
      >
        <Toolbar sx={{ justifyContent: "space-between", gap: 3, minHeight: 60 }}>
          <Box
            component={Link}
            to="/"
            sx={{
              display: "flex",
              flexDirection: "row",
              alignItems: "center",
              gap: 1,
              textDecoration: "none",
              color: "inherit",
            }}
          >
            <Box
              sx={{
                width: 26,
                height: 26,
                borderRadius: "7px",
                bgcolor: "rgba(255,255,255,0.08)",
                border: "1px solid",
                borderColor: "divider",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <ShoppingCartIcon sx={{ fontSize: 14, color: "text.primary" }} />
            </Box>
            <Typography fontWeight={600} color="text.primary">AI Commerce Studio</Typography>
          </Box>

          {/* Navigation lives entirely in the sidebar, so the top bar carries
              only the cart, the role switcher and the mode chip. A duplicate
              row of the same destinations up here gave every page two homes,
              and it surfaced on the landing page — where no role is chosen
              yet and there is nothing to navigate to. */}
          <Stack direction="row" spacing={0.25} sx={{ alignItems: "center" }}>
            {showCart && (
            <Box
              component="button"
              aria-label="Cart"
              onClick={() => setCartOpen(true)}
              sx={{
                position: "relative",
                width: 32, height: 32, borderRadius: 2,
                display: "flex", alignItems: "center", justifyContent: "center",
                border: "1px solid", borderColor: "divider",
                bgcolor: "transparent", color: "text.secondary", cursor: "pointer",
                "&:hover": { bgcolor: "rgba(255,255,255,0.05)", color: "text.primary" },
              }}
            >
              <ShoppingBagIcon sx={{ fontSize: 16 }} />
              {cartCount > 0 && (
                <Box
                  sx={{
                    position: "absolute", top: -5, right: -5,
                    minWidth: 16, height: 16, px: 0.4, borderRadius: 999,
                    bgcolor: "#ECECEE", color: "#0A0A0B",
                    fontSize: 10, fontWeight: 700, lineHeight: "16px",
                  }}
                >
                  {cartCount}
                </Box>
              )}
            </Box>
            )}

            {chosen && !onLanding && <RoleSwitcher />}

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

      {sidebarLayout ? (
        <Box sx={{ flex: 1, minHeight: 0, display: "flex", alignItems: "stretch" }}>
          <AppSidebar />
          <Box sx={SCROLL_PANE}>{children}</Box>
        </Box>
      ) : (
        <Box sx={SCROLL_PANE}>{children}</Box>
      )}

      <Snackbar
        open={Boolean(lastAdded)}
        autoHideDuration={3200}
        onClose={dismissAdded}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        message={
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
            <CheckIcon sx={{ fontSize: 15, color: "success.main", flexShrink: 0 }} />
            <Typography variant="caption" noWrap sx={{ maxWidth: 260 }}>
              Added {lastAdded?.name}
            </Typography>
          </Box>
        }
        action={
          <Typography
            variant="caption"
            onClick={() => {
              dismissAdded();
              setCartOpen(true);
            }}
            sx={{ cursor: "pointer", fontWeight: 600, color: "text.primary", pr: 1 }}
          >
            View cart
          </Typography>
        }
        slotProps={{
          content: {
            sx: {
              bgcolor: "#1B1B1E",
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 2,
              backgroundImage: "none",
            },
          },
        }}
      />
    </Box>
  );
}