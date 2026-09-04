import { Box, Stack, Typography } from "@mui/material";
import { Link, useLocation } from "react-router-dom";
import SpeedOutlinedIcon from "@mui/icons-material/SpeedOutlined";

/**
 * THE SHARED FURNITURE FOR EVERY GROWTH PAGE.
 *
 * Growth had grown into one page holding six unrelated things: a queue of
 * proposals, a campaign orchestrator, an attribution report, a relationship
 * graph, a performance chart and a discoverability checklist. Each was
 * defensible on its own and together they were a scroll, not a screen — you
 * could not answer "what is waiting on me" without passing four things that
 * were not it.
 *
 * So Growth is now a section rather than a page, and this holds the parts
 * every page in it shares: one heading, one breadcrumb, one section rhythm,
 * one empty state. The point of the shared components is not that they save
 * code — there is barely any — it is that four pages built from them cannot
 * drift into four different-looking pages.
 *
 * The rule for what belongs on which page is one question per page:
 *
 *     Agents          what wants to happen to my margin
 *     Campaigns       what is running
 *     Attribution     what came of it
 *     Relationships   what any of it is reasoning from
 *
 * A thing that answers two of those belongs on neither and needs splitting.
 */

export const CARD = {
  border: "1px solid",
  borderColor: "divider",
  borderRadius: 2.5,
  bgcolor: "background.paper",
  p: 2,
};

export const TABS = [
  { label: "Overview", path: "/merchant/growth" },
  { label: "Agents", path: "/merchant/growth/agents" },
  { label: "Campaigns", path: "/merchant/growth/campaigns" },
  { label: "Attribution", path: "/merchant/growth/attribution" },
  { label: "Relationships", path: "/merchant/growth/relationships" },
];

/**
 * A section heading with an optional control on the right.
 *
 * The control sits at the SECTION rather than the page, because a date range
 * that visibly belongs to one block cannot be mistaken for one that governs
 * everything below it — which is exactly what a page-level range control on
 * a page of unrelated blocks implies.
 */
export function Section({ title, note, action, children, sx }) {
  return (
    <Box sx={{ mb: 3.5, ...sx }}>
      <Stack
        direction="row"
        sx={{ alignItems: "flex-end", justifyContent: "space-between", mb: 1.5, gap: 2 }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: 15, fontWeight: 600 }}>{title}</Typography>
          {note && (
            <Typography
              variant="caption"
              sx={{ color: "text.secondary", display: "block", mt: 0.25, lineHeight: 1.6 }}
            >
              {note}
            </Typography>
          )}
        </Box>
        {action && <Box sx={{ flexShrink: 0 }}>{action}</Box>}
      </Stack>
      {children}
    </Box>
  );
}

/**
 * One empty state, worded the same way everywhere.
 *
 * Deliberately says which KIND of nothing this is. "No data for this date
 * range" and "nothing has been built to produce data here" look identical on
 * screen and mean completely different things to whoever is reading — one is
 * a filter to widen and the other is a limit of the build.
 */
export function Empty({ children, height = 132 }) {
  return (
    <Stack
      sx={{
        alignItems: "center", justifyContent: "center", textAlign: "center",
        minHeight: height, px: 3,
      }}
    >
      <Typography variant="body2" sx={{ color: "text.disabled", maxWidth: 460, lineHeight: 1.7 }}>
        {children}
      </Typography>
    </Stack>
  );
}

/**
 * The page frame: breadcrumb, title, and the tab strip.
 *
 * The tabs repeat what the sidebar shows. That is on purpose — the sidebar
 * says where you are in the app, the strip says what else lives in this
 * section, and on a narrow window the sidebar's sub-items are the first
 * thing to get scrolled out of sight.
 */
export default function GrowthPage({ title, subtitle, action, children }) {
  const { pathname } = useLocation();

  return (
    <Box sx={{ p: 3, maxWidth: 1180, mx: "auto" }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
        <SpeedOutlinedIcon sx={{ fontSize: 16, color: "text.disabled" }} />
        <Typography variant="caption" sx={{ color: "text.disabled" }}>
          Growth
        </Typography>
      </Stack>

      <Stack
        direction="row"
        sx={{ alignItems: "flex-start", justifyContent: "space-between", gap: 2, mb: 2 }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: 20, fontWeight: 700, letterSpacing: "-0.01em" }}>
            {title}
          </Typography>
          {subtitle && (
            <Typography
              variant="body2"
              sx={{ color: "text.secondary", mt: 0.5, maxWidth: 720, lineHeight: 1.65 }}
            >
              {subtitle}
            </Typography>
          )}
        </Box>
        {action && <Box sx={{ flexShrink: 0 }}>{action}</Box>}
      </Stack>

      <Stack
        direction="row"
        spacing={0.5}
        sx={{
          mb: 3, borderBottom: "1px solid", borderColor: "divider",
          overflowX: "auto",
          // The strip must not become a second horizontal scrollbar on the
          // page; it scrolls inside itself when the window is narrow.
          "&::-webkit-scrollbar": { display: "none" },
          scrollbarWidth: "none",
        }}
      >
        {TABS.map((tab) => {
          const active = pathname === tab.path;
          return (
            <Box
              key={tab.path}
              component={Link}
              to={tab.path}
              sx={{
                px: 1.5, py: 1, flexShrink: 0,
                textDecoration: "none",
                fontSize: 13,
                fontWeight: active ? 600 : 500,
                color: active ? "text.primary" : "text.secondary",
                borderBottom: "2px solid",
                borderColor: active ? "primary.main" : "transparent",
                mb: "-1px",
                "&:hover": { color: "text.primary" },
              }}
            >
              {tab.label}
            </Box>
          );
        })}
      </Stack>

      {children}
    </Box>
  );
}
