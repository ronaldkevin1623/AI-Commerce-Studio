import { useState } from "react";
import { Box, Stack, Typography } from "@mui/material";
import { Link, useLocation, useNavigate } from "react-router-dom";

import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
import LocalOfferOutlinedIcon from "@mui/icons-material/LocalOfferOutlined";
import SpeedOutlinedIcon from "@mui/icons-material/SpeedOutlined";
import BarChartOutlinedIcon from "@mui/icons-material/BarChartOutlined";
import ChatBubbleOutlineOutlinedIcon from "@mui/icons-material/ChatBubbleOutlineOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import ReplayOutlinedIcon from "@mui/icons-material/ReplayOutlined";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";

import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import FactCheckOutlinedIcon from "@mui/icons-material/FactCheckOutlined";
import ReceiptLongOutlinedIcon from "@mui/icons-material/ReceiptLongOutlined";
import FlightTakeoffOutlinedIcon from "@mui/icons-material/FlightTakeoffOutlined";
import StorefrontOutlinedIcon from "@mui/icons-material/StorefrontOutlined";

import { useConversation } from "../../context/ConversationContext";
import { useRole } from "../../context/RoleContext";

const WIDTH = 280;
const ROW_H = 32;

/**
 * One workbench, shaped to whichever side of the counter you are on.
 *
 * Both parties get the same furniture — a primary group of the tools that
 * party works in, a rule, then the accountability tools, then conversation
 * history — because the layout is not what distinguishes a buyer from a
 * seller. What distinguishes them is the top group, and that is the only
 * part that changes.
 *
 * Home is the Agent Console for both. For the customer it is obviously the
 * main event. For the merchant it stays first because the console is where
 * you watch the agent actually transact with the store, which is the thing
 * this project is for.
 *
 * ON THE COLOUR:
 * The reference is a light admin. Matching that literally would put a white
 * panel against the console's near-black, which reads as a rendering fault
 * rather than a design. The structure, grouping, iconography and active pill
 * follow the reference; the palette follows the rest of AI Commerce Studio.
 */

const PRIMARY_BY_ROLE = {
  customer: [
    { label: "Home", icon: <HomeOutlinedIcon />, path: "/console" },
    { label: "Trips", icon: <FlightTakeoffOutlinedIcon />, path: "/trips" },
    { label: "Hive", icon: <HubOutlinedIcon />, path: "/hive" },
    { label: "Approvals", icon: <FactCheckOutlinedIcon />, path: "/approvals" },
    { label: "Orders", icon: <ReceiptLongOutlinedIcon />, path: "/orders" },
  ],
  merchant: [
    { label: "Home", icon: <HomeOutlinedIcon />, path: "/console" },
    { label: "Storefront", icon: <StorefrontOutlinedIcon />, path: "/merchant/products" },
    { label: "Orders", icon: <ReceiptLongOutlinedIcon />, path: "/merchant/orders" },
    { label: "Growth", icon: <SpeedOutlinedIcon />, path: "/merchant/growth" },
    { label: "Analytics", icon: <BarChartOutlinedIcon />, path: "/merchant" },
  ],
};

// Shared, because these are not buying tools or selling tools — they are the
// record of a transaction, and both sides of one have a claim on it.
const ACCOUNTABILITY = [
  { label: "Audit trail", icon: <DescriptionOutlinedIcon />, path: "/audit" },
  { label: "Failure recovery", icon: <ReplayOutlinedIcon />, path: "/recovery" },
  { label: "Red team", icon: <ShieldOutlinedIcon />, path: "/redteam" },
  { label: "Your data", icon: <LockOutlinedIcon />, path: "/security" },
];

function Row({ item, active, onClick }) {
  const built = Boolean(item.path);

  const inner = (
    <Stack
      direction="row"
      spacing={1.25}
      sx={{
        alignItems: "center",
        height: ROW_H,
        px: 1,
        borderRadius: 1.5,
        color: active ? "text.primary" : built ? "text.secondary" : "text.disabled",
        bgcolor: active ? "rgba(255,255,255,0.08)" : "transparent",
        cursor: built ? "pointer" : "default",
        transition: "background-color 130ms, color 130ms",
        "&:hover": built
          ? { bgcolor: active ? "rgba(255,255,255,0.08)" : "rgba(255,255,255,0.04)", color: "text.primary" }
          : {},
        "& svg": { fontSize: 17 },
      }}
    >
      <Box sx={{ display: "flex", flexShrink: 0 }}>{item.icon}</Box>
      <Typography
        variant="body2"
        noWrap
        sx={{ fontSize: 13, fontWeight: active ? 600 : 500, flex: 1, minWidth: 0 }}
      >
        {item.label}
      </Typography>
      {!built && (
        <Typography
          variant="caption"
          sx={{
            fontSize: 9.5,
            fontWeight: 600,
            letterSpacing: 0.3,
            color: "text.disabled",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            px: 0.5,
            lineHeight: 1.6,
            flexShrink: 0,
          }}
        >
          SOON
        </Typography>
      )}
    </Stack>
  );

  if (!built) {
    return (
      <Box aria-disabled title={`${item.label} is not built yet`} sx={{ userSelect: "none" }}>
        {inner}
      </Box>
    );
  }

  return (
    <Box component={Link} to={item.path} onClick={onClick} sx={{ textDecoration: "none", display: "block" }}>
      {inner}
    </Box>
  );
}

function SectionHeader({ label, open, onToggle }) {
  return (
    <Stack
      component="button"
      type="button"
      direction="row"
      spacing={0.5}
      onClick={onToggle}
      sx={{
        alignItems: "center",
        height: 28,
        px: 1,
        mt: 1,
        width: "100%",
        border: "none",
        bgcolor: "transparent",
        cursor: "pointer",
        borderRadius: 1.5,
        "&:hover": { bgcolor: "rgba(255,255,255,0.04)" },
      }}
    >
      <Typography
        variant="caption"
        sx={{ fontSize: 11, fontWeight: 600, color: "text.secondary", letterSpacing: 0.2 }}
      >
        {label}
      </Typography>
      {open ? (
        <ExpandMoreIcon sx={{ fontSize: 14, color: "text.disabled" }} />
      ) : (
        <ChevronRightIcon sx={{ fontSize: 14, color: "text.disabled" }} />
      )}
    </Stack>
  );
}

export default function AppSidebar() {
  const location = useLocation();
  const { role } = useRole();
  const PRIMARY = PRIMARY_BY_ROLE[role] ?? [];
  const { sessionList, activeSessionId, openSession, newChat } = useConversation();
  const navigate = useNavigate();

  // Selecting a conversation has to land you where conversations happen.
  // These only ever changed the session, so starting a new chat from Orders
  // or Products silently swapped the transcript behind a page that does not
  // show it — the click looked like it had done nothing at all.
  const startChat = () => {
    newChat();
    navigate("/console");
  };

  const goToSession = (id) => {
    openSession(id);
    navigate("/console");
  };

  const [conversationsOpen, setConversationsOpen] = useState(true);

  // Longest matching prefix wins, so /merchant/products/new lights up
  // Products and not Analytics. A plain startsWith would light both, since
  // Analytics owns /merchant and every product route sits underneath it.
  const paths = [...PRIMARY, ...ACCOUNTABILITY]
    .map((i) => i.path)
    .filter(Boolean);
  const best = paths
    .filter((p) => location.pathname === p || location.pathname.startsWith(`${p}/`))
    .sort((a, b) => b.length - a.length)[0];

  const isActive = (item) => Boolean(item.path) && item.path === best;

  return (
    <Box
      component="nav"
      sx={{
        width: WIDTH,
        flexShrink: 0,
        height: "100%",
        borderRight: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Box
        sx={{
          flex: 1,
          px: 1,
          py: 1.25,
          // Scrollable, but the bar only appears while the pointer is over
          // the panel. A permanent chunky gutter down a navigation column
          // reads as a rendering artefact rather than an affordance.
          overflowY: "auto",
          scrollbarWidth: "thin",
          scrollbarColor: "transparent transparent",
          "&::-webkit-scrollbar": { width: 6 },
          "&::-webkit-scrollbar-track": { background: "transparent" },
          "&::-webkit-scrollbar-thumb": {
            background: "transparent",
            borderRadius: 999,
          },
          "&:hover": {
            scrollbarColor: "rgba(255,255,255,0.18) transparent",
            "&::-webkit-scrollbar-thumb": { background: "rgba(255,255,255,0.18)" },
          },
        }}
      >
        <Stack spacing={0.25}>
          {PRIMARY.map((item) => (
            <Row key={item.label} item={item} active={isActive(item)} />
          ))}
        </Stack>

        <Box sx={{ my: 1.25, borderTop: "1px solid", borderColor: "divider" }} />

        <Stack spacing={0.25}>
          {ACCOUNTABILITY.map((item) => (
            <Row key={item.label} item={item} active={isActive(item)} />
          ))}
        </Stack>

        {/* Conversation history, moved down here out of the console's own
            panel — the same place the reference admin keeps its assistant's
            past threads, and it stops the console carrying two sidebars. */}
        <SectionHeader
          label="Conversations"
          open={conversationsOpen}
          onToggle={() => setConversationsOpen((v) => !v)}
        />

        {conversationsOpen && (
          <Stack spacing={0.25}>
            <Box
              component="button"
              type="button"
              onClick={startChat}
              sx={{
                display: "flex", alignItems: "center", gap: 1.25,
                height: ROW_H, px: 1, width: "100%",
                border: "none", bgcolor: "transparent", cursor: "pointer",
                borderRadius: 1.5, color: "text.secondary",
                "&:hover": { bgcolor: "rgba(255,255,255,0.04)", color: "text.primary" },
              }}
            >
              <EditOutlinedIcon sx={{ fontSize: 17 }} />
              <Typography variant="body2" sx={{ fontSize: 13, fontWeight: 500 }}>
                New chat
              </Typography>
            </Box>

            {sessionList.length === 0 && (
              <Typography
                variant="caption"
                sx={{ color: "text.disabled", px: 1, py: 0.5, display: "block", fontSize: 11.5 }}
              >
                Nothing yet — ask the agent for something.
              </Typography>
            )}

            {sessionList.map((session) => {
              const active = session.id === activeSessionId;
              return (
                <Box
                  key={session.id}
                  component="button"
                  type="button"
                  onClick={() => goToSession(session.id)}
                  sx={{
                    display: "flex", alignItems: "center", gap: 1.25,
                    height: ROW_H, px: 1, width: "100%", minWidth: 0,
                    border: "none", cursor: "pointer", borderRadius: 1.5,
                    textAlign: "left",
                    bgcolor: active ? "rgba(255,255,255,0.08)" : "transparent",
                    color: active ? "text.primary" : "text.secondary",
                    "&:hover": {
                      bgcolor: active ? "rgba(255,255,255,0.08)" : "rgba(255,255,255,0.04)",
                      color: "text.primary",
                    },
                  }}
                >
                  <ChatBubbleOutlineOutlinedIcon sx={{ fontSize: 15, flexShrink: 0 }} />
                  <Typography
                    variant="body2"
                    noWrap
                    sx={{ fontSize: 12.5, flex: 1, minWidth: 0 }}
                  >
                    {session.query || "New chat"}
                  </Typography>
                </Box>
              );
            })}
          </Stack>
        )}
      </Box>

    </Box>
  );
}
