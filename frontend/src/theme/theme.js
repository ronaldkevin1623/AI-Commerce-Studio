import { createTheme } from "@mui/material/styles";

/**
 * Dark, ink-navy fintech theme matching the approved mockup —
 * deep near-black background, sharp blue accent, amber for
 * "judgment" states, green reserved for confirmed/success only.
 */
const theme = createTheme({
  palette: {
    mode: "dark",
    primary: {
      main: "#3B82F6",
      light: "#60A5FA",
      contrastText: "#FFFFFF",
    },
    background: {
      default: "#0B0F17",
      paper: "#12161F",
    },
    text: {
      primary: "#F3F4F6",
      secondary: "#9AA3B2",
    },
    success: {
      main: "#22C55E",
      light: "rgba(34,197,94,0.12)",
    },
    warning: {
      main: "#F59E0B",
      light: "rgba(245,158,11,0.12)",
    },
    error: {
      main: "#EF4444",
      light: "rgba(239,68,68,0.12)",
    },
    divider: "rgba(255,255,255,0.08)",
  },
  shape: {
    borderRadius: 10,
  },
  typography: {
    fontFamily: '"Inter", "Segoe UI", sans-serif',
    h1: { fontSize: "2.1rem", fontWeight: 600 },
    h2: { fontSize: "1.4rem", fontWeight: 600 },
    body2: { color: "#9AA3B2" },
    button: { textTransform: "none", fontWeight: 500 },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 8, paddingInline: 20 },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: "none" },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 500 },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: { backgroundColor: "#0B0F17" },
      },
    },
  },
});

export default theme;