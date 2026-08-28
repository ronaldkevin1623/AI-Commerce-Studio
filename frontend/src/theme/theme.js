import { createTheme } from "@mui/material/styles";

/**
 * Neutral near-black theme.
 *
 * The palette used to be ink-navy with a saturated blue on every button,
 * badge and chat bubble. At that density the blue stopped meaning anything —
 * if the primary action, the agent's pick and the user's own message are all
 * the same colour, colour has told you nothing. So the surfaces are now
 * genuinely neutral (no blue cast in the greys), primary actions are
 * high-contrast monochrome, and colour is reserved for the states that
 * actually carry meaning: green confirmed, amber judgment, red blocked, and
 * a single restrained blue for "this is live right now".
 */

const INK = "#0A0A0B";
const SURFACE = "#141416";
const RAISED = "#1B1B1E";

const theme = createTheme({
  palette: {
    mode: "dark",
    primary: {
      // Kept for genuinely semantic accent use — active nav, focus, and the
      // hive's "running" state. Not for every button.
      main: "#4F8DF7",
      light: "#7BA9FA",
      contrastText: "#FFFFFF",
    },
    background: {
      default: INK,
      paper: SURFACE,
    },
    text: {
      primary: "#ECECEE",
      // Neutral grey rather than the old blue-grey, so body copy stops
      // reading as tinted.
      secondary: "#8E8E96",
    },
    success: { main: "#3FB950", light: "rgba(63,185,80,0.12)" },
    warning: { main: "#D29922", light: "rgba(210,153,34,0.12)" },
    error: { main: "#F85149", light: "rgba(248,81,73,0.12)" },
    divider: "rgba(255,255,255,0.09)",
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: '"Inter", "Segoe UI", sans-serif',
    h1: { fontSize: "2rem", fontWeight: 600, letterSpacing: "-0.02em" },
    h2: { fontSize: "1.35rem", fontWeight: 600, letterSpacing: "-0.01em" },
    body2: { color: "#8E8E96" },
    button: { textTransform: "none", fontWeight: 500 },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          borderRadius: 8,
          paddingInline: 18,
          boxShadow: "none",
          "&:hover": { boxShadow: "none" },
        },
        outlined: {
          borderColor: "rgba(255,255,255,0.14)",
          color: "#ECECEE",
          "&:hover": {
            borderColor: "rgba(255,255,255,0.26)",
            backgroundColor: "rgba(255,255,255,0.04)",
          },
        },
        text: { "&:hover": { backgroundColor: "rgba(255,255,255,0.05)" } },
      },
      // The `variants` API, not a `containedPrimary` style slot: this MUI
      // emits `MuiButton-contained` + `MuiButton-colorPrimary` as separate
      // classes, so the old compound slot silently matches nothing and the
      // override is dropped without any warning.
      //
      // The primary action is the highest-contrast thing on screen rather
      // than the most saturated — which is what makes a monochrome dark UI
      // read as considered rather than loud.
      variants: [
        {
          props: { variant: "contained", color: "primary" },
          style: {
            backgroundColor: "#ECECEE",
            color: INK,
            "&:hover": { backgroundColor: "#FFFFFF" },
            "&.Mui-disabled": {
              backgroundColor: "rgba(255,255,255,0.09)",
              color: "rgba(255,255,255,0.32)",
            },
          },
        },
      ],
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: "none" },
        outlined: { borderColor: "rgba(255,255,255,0.09)" },
      },
    },
    MuiChip: { styleOverrides: { root: { fontWeight: 500 } } },
    MuiAppBar: {
      styleOverrides: {
        root: { backgroundColor: INK, backgroundImage: "none" },
      },
    },
    MuiDrawer: {
      styleOverrides: { paper: { backgroundImage: "none" } },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: RAISED,
          border: "1px solid rgba(255,255,255,0.09)",
          fontSize: 11.5,
          fontWeight: 400,
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        notchedOutline: { borderColor: "rgba(255,255,255,0.12)" },
      },
    },
  },
});

export default theme;
