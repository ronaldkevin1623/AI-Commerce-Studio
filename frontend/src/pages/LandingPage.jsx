import { Box, Typography, Button, Stack, Chip } from "@mui/material";
import { Link } from "react-router-dom";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import MemoryIcon from "@mui/icons-material/Memory";
import CreditCardIcon from "@mui/icons-material/CreditCard";
import DescriptionIcon from "@mui/icons-material/Description";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutlineOutlined";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";

import heroVideo from "../assets/hero-bg.mp4";
import heroPoster from "../assets/hero-poster.jpg";

// Combined status + pillar items into one compact bottom strip
// so everything fits in a single viewport without scrolling.
const bottomStrip = [
  { icon: <MemoryIcon sx={{ fontSize: 16 }} />, label: "Reasoning engine · Connected" },
  { icon: <CreditCardIcon sx={{ fontSize: 16 }} />, label: "Razorpay · Test mode" },
  { icon: <DescriptionIcon sx={{ fontSize: 16 }} />, label: "Audit log · Recording" },
  { icon: <ChatBubbleOutlineIcon sx={{ fontSize: 16 }} />, label: "Explainable" },
  { icon: <ShieldOutlinedIcon sx={{ fontSize: 16 }} />, label: "Bounded" },
  { icon: <LockOutlinedIcon sx={{ fontSize: 16 }} />, label: "Gated" },
];

// Matches the AppBar's default MUI Toolbar height so the video
// fills exactly the remaining viewport with zero page scroll.
const NAVBAR_HEIGHT = 64;

export default function LandingPage() {
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
          An AI buyer with a conscience
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
          Every purchase reasoned, every risk checked, every action logged.
          A shopping agent that explains itself before it spends.
        </Typography>

        <Stack direction="row" spacing={2} sx={{ width: "100%", justifyContent: "center" }}>
          <Button variant="contained" component={Link} to="/console" endIcon={<ArrowForwardIcon />}>
            Open console
          </Button>
          <Button
            variant="outlined"
            component={Link}
            to="/audit"
            sx={{ borderColor: "rgba(255,255,255,0.6)", color: "#fff", backdropFilter: "blur(4px)" }}
          >
            View audit trail
          </Button>
        </Stack>
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
            alignItems="center"
            spacing={0.75}
            sx={{
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