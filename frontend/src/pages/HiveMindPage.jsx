import { Box, Typography } from "@mui/material";

import PageBanner from "../components/shared/PageBanner";
import HiveCanvas from "../components/hive/HiveCanvas";
import RolePresets from "../components/hive/RolePresets";
import { SPECIALISTS } from "../components/hive/topology";
import { useHiveSettings } from "../context/HiveSettingsContext";

/**
 * The hive as a map: every capability AI Commerce Studio has, and every one it
 * doesn't have yet, in the same frame. Clicking a node opens its tune card;
 * the role buttons above set several of those dials at once.
 */

export default function HiveMindPage() {
  const settings = useHiveSettings();
  const built = SPECIALISTS.filter((s) => s.state !== "planned").length;

  return (
    <Box>
      <PageBanner
        title="Hive mind"
        subtitle={`${built} of ${SPECIALISTS.length} specialist agents are wired to real services. Pick a role below to set several dials at once, or click any node to tune it yourself. Drag nodes to rearrange.`}
      />

      <Box sx={{ maxWidth: 1000, mx: "auto", px: 3, py: 3 }}>
        <RolePresets settings={settings} />

        <Box
          sx={{
            bgcolor: "background.paper",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2.5,
            p: 2,
          }}
        >
          <HiveCanvas mode="map" />
        </Box>

        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
          Nodes drawn with a dashed outline don't exist in the codebase yet. They're on the
          canvas so the shape of the system is honest about what's missing — not to imply
          capability that isn't there.
        </Typography>
      </Box>
    </Box>
  );
}
