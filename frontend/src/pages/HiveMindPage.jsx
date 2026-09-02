import { useState } from "react";
import { Box, Stack, Switch, Typography } from "@mui/material";

import PageBanner from "../components/shared/PageBanner";
import HiveCanvas from "../components/hive/HiveCanvas";
import RolePresets from "../components/hive/RolePresets";
import { SPECIALISTS, TUNABLE } from "../components/hive/topology";
import { useHiveSettings } from "../context/HiveSettingsContext";

/**
 * The hive as a map: every capability AI Commerce Studio has, and every one it
 * doesn't have yet, in the same frame. Clicking a node opens its tune card;
 * the role buttons above set several of those dials at once.
 */

export default function HiveMindPage() {
  const settings = useHiveSettings();
  const built = SPECIALISTS.filter((s) => s.state !== "planned").length;
  // Defaults to the nodes that have something to turn, because that is what
  // this page is for. The rest are real parts of the system with no
  // parameter to set, and they are one switch away rather than gone.
  const [onlyTunable, setOnlyTunable] = useState(true);
  const tunable = SPECIALISTS.filter((s) => TUNABLE.has(s.id)).length;

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
          <Stack
            direction="row"
            spacing={1}
            sx={{ alignItems: "center", justifyContent: "flex-end", mb: 0.5 }}
          >
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              {onlyTunable
                ? `Showing the ${tunable} agents you can tune`
                : "Showing every part of the system"}
            </Typography>
            <Switch
              size="small"
              checked={onlyTunable}
              onChange={(e) => setOnlyTunable(e.target.checked)}
              slotProps={{ input: { "aria-label": "Show only tunable agents" } }}
            />
          </Stack>
          <HiveCanvas mode="map" onlyTunable={onlyTunable} />
        </Box>

        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
          {onlyTunable
            ? "These are the agents with dials that change what the agent does — each one's "
              + "settings are read at run time by the code that makes the decision. Turn the "
              + "switch off to see the rest of the system, including the parts that take no "
              + "parameter and the ones not built yet."
            : "Nodes drawn with a dashed outline don't exist in the codebase yet. They're on "
              + "the canvas so the shape of the system is honest about what's missing — not "
              + "to imply capability that isn't there."}
        </Typography>
      </Box>
    </Box>
  );
}
