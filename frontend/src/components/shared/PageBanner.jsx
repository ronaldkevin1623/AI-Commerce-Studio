import { Box, Typography } from "@mui/material";

// Same real, free-to-use Unsplash photo as the landing hero, reused
// at low opacity across every internal page for visual consistency.
const BANNER_IMAGE =
  "https://images.unsplash.com/photo-1460925895917-afdab827c52f?fm=jpg&q=80&w=2000&auto=format&fit=crop";

export default function PageBanner({ title, subtitle, action }) {
  return (
    <Box
      sx={{
        position: "relative",
        px: 3,
        py: 5,
        overflow: "hidden",
        borderBottom: "1px solid",
        borderColor: "divider",
      }}
    >
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          backgroundImage: `url(${BANNER_IMAGE})`,
          backgroundSize: "cover",
          backgroundPosition: "center 30%",
          opacity: 0.12,
        }}
      />
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          background: "linear-gradient(180deg, transparent 0%, #0B0F17 100%)",
        }}
      />

      <Box
        sx={{
          position: "relative",
          maxWidth: 1000,
          mx: "auto",
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 2,
        }}
      >
        <Box>
          <Typography variant="h2" gutterBottom>{title}</Typography>
          {subtitle && (
            <Typography variant="body2" color="text.secondary">{subtitle}</Typography>
          )}
        </Box>
        {action}
      </Box>
    </Box>
  );
}