import { useState } from "react";
import { Box, Button, Collapse, Stack, Typography } from "@mui/material";
// PersonOutline doesn't exist — the suffixed PersonOutlineOutlined does.
import PersonOutlineIcon from "@mui/icons-material/PersonOutlineOutlined";
import StorefrontOutlinedIcon from "@mui/icons-material/StorefrontOutlined";
import CheckIcon from "@mui/icons-material/Check";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import Inventory2OutlinedIcon from "@mui/icons-material/Inventory2Outlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";

import { BY_ID, enumLabel } from "./topology";

/**
 * Two one-click starting points, for someone who shouldn't have to know what
 * "outlier floor 45%" means before the agent is useful to them.
 *
 * Each button shows its work before it acts: pick a role and you get the
 * exact list of dials that will move, old value to new, and then you apply
 * it. That costs one extra click and buys two things — nobody is surprised
 * by what changed, and the panel doubles as an explanation of what the
 * dials do, which is the fastest way to stop needing presets at all.
 */

const ICONS = {
  // Stock in boxes, not a shopper with a basket.
  reseller: Inventory2OutlinedIcon, customer: PersonOutlineIcon, seller: StorefrontOutlinedIcon };

function show(node, value, prefix, suffix) {
  if (typeof value === "boolean" || typeof value === "string") return enumLabel(node, value);
  return `${prefix ?? ""}${value}${suffix ?? ""}`;
}

export default function RolePresets({ settings }) {
  const [previewing, setPreviewing] = useState(null);

  const names = Object.keys(settings.presets ?? {});
  if (!names.length) return null;

  const diff = previewing ? settings.previewPreset(previewing) : [];
  const preset = previewing ? settings.presets[previewing] : null;
  const busy = settings.status === "saving";

  return (
    <Box sx={{ mb: 2 }}>
      <Stack direction="row" spacing={1.5} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
        <Typography variant="overline" sx={{ letterSpacing: 1, color: "text.secondary", mr: 0.5 }}>
          Tune for
        </Typography>

        {names.map((name) => {
          const Icon = ICONS[name] ?? PersonOutlineIcon;
          const active = settings.activePreset === name;
          const open = previewing === name;
          return (
            <Button
              key={name}
              size="small"
              onClick={() => setPreviewing(open ? null : name)}
              startIcon={<Icon sx={{ fontSize: 17 }} />}
              endIcon={active ? <CheckIcon sx={{ fontSize: 15 }} /> : null}
              sx={{
                borderRadius: 2,
                px: 1.75,
                boxShadow: "none",
                "&:hover": { boxShadow: "none", bgcolor: "rgba(59,130,246,0.12)" },
                border: "1px solid",
                borderColor: active ? "success.main" : open ? "primary.main" : "divider",
                bgcolor: active
                  ? "rgba(34,197,94,0.10)"
                  : open
                    ? "rgba(59,130,246,0.12)"
                    : "transparent",
                color: active ? "success.main" : open ? "primary.light" : "text.primary",
                fontWeight: 500,
              }}
            >
              {settings.presets[name].label}
            </Button>
          );
        })}

        {/* "No particular way" is one of the choices, so it sits with the
            others rather than being buried on the individual nodes. */}
        <Button
          size="small"
          disabled={busy}
          onClick={async () => {
            // The hook owns the saving state, and `busy` above is read from
            // it — there is no local setter to call here.
            await settings.resetNode(null);
            setPreviewing(null);
          }}
          startIcon={<RestartAltIcon sx={{ fontSize: 17 }} />}
          sx={{
            borderRadius: 2,
            px: 1.75,
            boxShadow: "none",
            border: "1px solid",
            borderColor: "divider",
            color: "text.secondary",
            fontWeight: 500,
            "&:hover": { boxShadow: "none", bgcolor: "rgba(255,255,255,0.05)" },
          }}
        >
          Reset
        </Button>

        <Typography variant="caption" color="text.secondary">
          {settings.activePreset
            ? `${settings.presets[settings.activePreset].label} settings are in effect`
            : settings.editedNodes.size
              ? "Hand-tuned — no preset is fully in effect"
              : "Running on default settings"}
        </Typography>
      </Stack>

      {/* What this preset would do, before it does it. */}
      <Collapse in={Boolean(previewing)} unmountOnExit>
        <Box
          sx={{
            mt: 1.5,
            bgcolor: "background.paper",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2.5,
            p: 2,
          }}
        >
          <Typography variant="body2" sx={{ color: "text.secondary", mb: 1.5 }}>
            {preset?.blurb}
          </Typography>

          {diff.length === 0 ? (
            <Typography variant="body2" sx={{ color: "success.main", mb: 1.5 }}>
              Already applied — nothing would change.
            </Typography>
          ) : (
            <Stack spacing={0.75} sx={{ mb: 1.75 }}>
              {diff.map((change) => (
                <Stack
                  key={`${change.node}.${change.key}`}
                  direction="row"
                  spacing={1}
                  sx={{ alignItems: "baseline", flexWrap: "wrap" }}
                >
                  <Typography
                    variant="caption"
                    sx={{ color: "primary.light", width: 92, flexShrink: 0, fontWeight: 600 }}
                  >
                    {BY_ID[change.node]?.label ?? change.node}
                  </Typography>
                  <Typography variant="caption" sx={{ color: "text.secondary", width: 118, flexShrink: 0 }}>
                    {change.label}
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{ color: "text.secondary", fontVariantNumeric: "tabular-nums" }}
                  >
                    {show(change.node, change.from, change.prefix, change.suffix)}
                  </Typography>
                  <Typography variant="caption" sx={{ color: "text.secondary" }}>
                    →
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{ color: "text.primary", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}
                  >
                    {show(change.node, change.to, change.prefix, change.suffix)}
                  </Typography>
                </Stack>
              ))}
            </Stack>
          )}

          {/* The thing a preset deliberately will not touch. */}
          <Stack
            direction="row"
            spacing={1}
            sx={{
              alignItems: "flex-start",
              bgcolor: "rgba(245,158,11,0.06)",
              border: "1px solid",
              borderColor: "rgba(245,158,11,0.22)",
              borderRadius: 2,
              p: 1.25,
              mb: diff.length ? 1.75 : 0,
            }}
          >
            <LockOutlinedIcon sx={{ fontSize: 15, color: "warning.main", mt: "1px", flexShrink: 0 }} />
            <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.55 }}>
              A preset can change what the agent looks for and how it paces itself — including
              how often it may buy. It can never change how much may be spent: the per-order
              cap, the session ceiling and the trust floor stay a decision you make on purpose.
            </Typography>
          </Stack>

          {diff.length > 0 && (
            <Stack direction="row" spacing={1}>
              <Button
                size="small"
                variant="contained"
                disabled={busy}
                onClick={async () => {
                  await settings.applyPreset(previewing);
                  setPreviewing(null);
                }}
                sx={{ boxShadow: "none", "&:hover": { boxShadow: "none" } }}
              >
                {busy ? "Applying…" : `Apply ${preset?.label} settings`}
              </Button>
              <Button
                size="small"
                onClick={() => setPreviewing(null)}
                sx={{ color: "text.secondary", boxShadow: "none", "&:hover": { boxShadow: "none" } }}
              >
                Cancel
              </Button>
            </Stack>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}
