import { useEffect, useState } from "react";
import { Box, Typography, Stack, Chip } from "@mui/material";
import { useNavigate } from "react-router-dom";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import MemoryIcon from "@mui/icons-material/Memory";
import CreditCardIcon from "@mui/icons-material/CreditCard";
import DescriptionIcon from "@mui/icons-material/Description";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutlineOutlined";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import StorefrontOutlinedIcon from "@mui/icons-material/StorefrontOutlined";
import PersonOutlineOutlinedIcon from "@mui/icons-material/PersonOutlineOutlined";

import { ROLES, useRole } from "../context/RoleContext";
import { API_BASE } from "../config";

import heroVideo from "../assets/hero-bg.mp4";
import heroPoster from "../assets/hero-poster.jpg";

// Combined status + pillar items into one compact bottom strip
// so everything fits in a single viewport without scrolling.
const buildStrip = (probeCount) => [
  { icon: <MemoryIcon sx={{ fontSize: 16 }} />, label: "Reasoning engine · Connected" },
  { icon: <CreditCardIcon sx={{ fontSize: 16 }} />, label: "Razorpay · Test mode" },
  { icon: <DescriptionIcon sx={{ fontSize: 16 }} />, label: "Audit log · Recording" },
  { icon: <ChatBubbleOutlineIcon sx={{ fontSize: 16 }} />, label: "Explainable" },
  {
    icon: <ShieldOutlinedIcon sx={{ fontSize: 16 }} />,
    // No number unless the suite answered for itself.
    label: probeCount ? `Attack-tested · ${probeCount} probes` : "Attack-tested",
  },
  { icon: <LockOutlinedIcon sx={{ fontSize: 16 }} />, label: "Human-gated above the limit" },
];

// Matches the AppBar's default MUI Toolbar height so the video
// fills exactly the remaining viewport with zero page scroll.
const NAVBAR_HEIGHT = 64;

const ROLE_ICONS = {
  customer: <PersonOutlineOutlinedIcon sx={{ fontSize: 20 }} />,
  merchant: <StorefrontOutlinedIcon sx={{ fontSize: 20 }} />,
};

export default function LandingPage() {
  const { setRole } = useRole();
  const navigate = useNavigate();
  const [probeCount, setProbeCount] = useState(null);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/redteam/corpus`);
        if (!res.ok) return;
        const data = await res.json();
        if (live) setProbeCount(data.count ?? null);
      } catch {
        // Backend down, or the page opened standalone. The strip simply
        // makes the weaker claim.
      }
    })();
    return () => { live = false; };
  }, []);

  const bottomStrip = buildStrip(probeCount);

  // Picking a side is a decision, not a setting, so it gets two doors rather
  // than a switch on one. It is also the honest shape of the thing: the buyer
  // discovers the merchant over UCP as a separate party, and a control that
  // implied one was a mode of the other would contradict the architecture.
  const enter = (id) => {
    setRole(id);
    navigate(ROLES[id].home);
  };

  return (
    <Box
      sx={{
        position: "relative",
        height: `calc(100vh - ${NAVBAR_HEIGHT}px)`,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Video plays at full natural brightness — no dimming filter */}
      <Box
        component="video"
        autoPlay
        muted
        loop
        playsInline
        poster={heroPoster}
        sx={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
        }}
      >
        <source src={heroVideo} type="video/mp4" />
      </Box>

      {/* Very light overlay — just enough for text legibility, not a dark tint */}
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          background: "rgba(0,0,0,0.25)",
        }}
      />

      {/* MAIN CONTENT — centered in the remaining space */}
      <Box
        sx={{
          position: "relative",
          zIndex: 1,
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          px: 2,
        }}
      >
        <Chip
          icon={<AutoAwesomeIcon sx={{ fontSize: 16 }} />}
          label="Agentic commerce, built on Razorpay"
          size="small"
          sx={{
            bgcolor: "rgba(59,130,246,0.25)",
            color: "#fff",
            mb: 2.5,
            backdropFilter: "blur(4px)",
            "& .MuiChip-icon": { color: "#fff" },
          }}
        />

        <Typography
          variant="h1"
          sx={{ mb: 1.5, color: "#fff", textShadow: "0 2px 20px rgba(0,0,0,0.8)" }}
        >
          A safety kernel for agent commerce
        </Typography>

        <Typography
          variant="body1"
          sx={{
            mb: 3,
            maxWidth: 560,
            lineHeight: 1.6,
            color: "rgba(255,255,255,0.9)",
            textShadow: "0 1px 14px rgba(0,0,0,0.9)",
          }}
        >
          Agents can search, negotiate and pay here — through a gate they cannot
          talk their way past. Both sides of the transaction are real, and every
          bound is enforced in code that reads no seller's text.
        </Typography>

        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          sx={{ justifyContent: "center", alignItems: "stretch", width: "100%", maxWidth: 720 }}
        >
          {Object.values(ROLES).map((option) => (
            <Box
              key={option.id}
              component="button"
              type="button"
              onClick={() => enter(option.id)}
              sx={{
                flex: 1,
                minWidth: 0,
                textAlign: "left",
                cursor: "pointer",
                p: 2,
                borderRadius: 2.5,
                border: "1px solid rgba(255,255,255,0.22)",
                bgcolor: "rgba(0,0,0,0.45)",
                backdropFilter: "blur(8px)",
                color: "#fff",
                transition: "border-color 160ms, background-color 160ms, transform 160ms",
                "&:hover": {
                  borderColor: "rgba(255,255,255,0.5)",
                  bgcolor: "rgba(0,0,0,0.58)",
                  transform: "translateY(-2px)",
                },
              }}
            >
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.75 }}>
                <Box sx={{ display: "flex", color: "rgba(255,255,255,0.85)" }}>
                  {ROLE_ICONS[option.id]}
                </Box>
                <Typography sx={{ fontWeight: 700, fontSize: 15, color: "#fff" }}>
                  {option.tagline}
                </Typography>
                <ArrowForwardIcon sx={{ fontSize: 15, ml: "auto", opacity: 0.75 }} />
              </Stack>
              <Typography
                variant="caption"
                sx={{ color: "rgba(255,255,255,0.82)", lineHeight: 1.6, display: "block" }}
              >
                {option.blurb}
              </Typography>
            </Box>
          ))}
        </Stack>

        <Typography
          variant="caption"
          sx={{ mt: 2, color: "rgba(255,255,255,0.7)", textShadow: "0 1px 10px rgba(0,0,0,0.9)" }}
        >
          Both sides are real and talk to each other over UCP — discovery, catalogue and
          checkout. You can switch at any time.
        </Typography>
      </Box>

      {/* BOTTOM STRIP — compact, single row, replaces the two large sections
          so the whole page fits one viewport with no scroll */}
      <Box
        sx={{
          position: "relative",
          zIndex: 1,
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: 1,
          px: 2,
          pb: 2.5,
        }}
      >
        {bottomStrip.map((item) => (
          <Stack
            key={item.label}
            direction="row"
            spacing={0.75}
            sx={{
              alignItems: "center",
              bgcolor: "rgba(0,0,0,0.45)",
              backdropFilter: "blur(6px)",
              color: "#fff",
              px: 1.5,
              py: 0.6,
              borderRadius: 999,
              fontSize: 12,
            }}
          >
            <Box sx={{ display: "flex", color: "rgba(255,255,255,0.85)" }}>{item.icon}</Box>
            <Typography variant="caption" sx={{ color: "#fff", whiteSpace: "nowrap" }}>
              {item.label}
            </Typography>
          </Stack>
        ))}
      </Box>
    </Box>
  );
}