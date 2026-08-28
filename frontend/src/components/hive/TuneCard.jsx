import { useEffect, useState } from "react";
import { Box, Button, Chip, Popover, Stack, Typography } from "@mui/material";
import CheckIcon from "@mui/icons-material/Check";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";

import { BY_ID, CLUSTERS, SPECIALISTS, TOOLS, dependentsOf, enumLabel } from "./topology";
import ScrubField from "./ScrubField";
import { SegmentedToggle, SelectField } from "./TuneControls";

/**
 * The tune card — what opens when you click a node.
 *
 * It is a control surface, not a legend. Every dial here maps to a parameter
 * the corresponding agent genuinely reads at run time, and the spec it
 * renders from is fetched from the backend, so a control can't exist for
 * something the pipeline doesn't consume.
 *
 * Edits are held locally until Apply. A scrub that PATCHed per pixel would
 * bury the audit trail in noise, and — for the bounds that decide how much
 * money moves unattended — committing should be a deliberate act anyway.
 */

const STATIC = {
  you: {
    label: "You",
    what: "Every run starts with a free-text request from here, and both pauses — choosing the product, approving an escalated purchase — come back to here before any money moves.",
  },
  hive: {
    label: "Hive",
    what: "The orchestrator. It decides nothing itself: it sequences the specialists, carries their findings forward, and stops the run the moment one of them blocks.",
  },
};

function Section({ label, children, sx }) {
  return (
    <Box sx={{ px: 2, py: 1.5, borderTop: "1px solid", borderColor: "divider", ...sx }}>
      {label && (
        <Typography
          variant="overline"
          sx={{ letterSpacing: 1, color: "text.secondary", display: "block", mb: 1, fontSize: 10 }}
        >
          {label}
        </Typography>
      )}
      {children}
    </Box>
  );
}

/** One row: the control on the right, its name carried by the control itself. */
function Control({ node, param, spec, value, defaultValue, onChange, disabled }) {
  const active = value !== defaultValue;

  if (spec.kind === "bool") {
    return (
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", gap: 1.5 }}>
        <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 11.5, minWidth: 0 }}>
          {spec.label}
        </Typography>
        <SegmentedToggle value={Boolean(value)} onChange={onChange} disabled={disabled} />
      </Stack>
    );
  }

  if (spec.kind === "enum") {
    return (
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", gap: 1.5 }}>
        <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 11.5, minWidth: 0 }}>
          {spec.label}
        </Typography>
        <SelectField
          value={value}
          choices={spec.choices}
          onChange={onChange}
          format={(v) => enumLabel(node, v)}
          disabled={disabled}
        />
      </Stack>
    );
  }

  return (
    <ScrubField
      label={spec.label}
      value={Number(value ?? 0)}
      onChange={onChange}
      min={spec.min}
      max={spec.max}
      prefix={spec.prefix}
      suffix={spec.suffix}
      active={active}
      disabled={disabled}
      hint={spec.note}
    />
  );
}

export default function TuneCard({
  nodeId,
  anchorEl,
  onClose,
  mode,
  runState,
  toolUsed,
  onNavigate,
  settings,
}) {
  // Which control's note to show. Hooks stay above the early returns so the
  // hook order never changes between an open and a closed card.
  const [activeNote, setActiveNote] = useState(null);
  useEffect(() => setActiveNote(null), [nodeId]);

  const open = Boolean(nodeId && anchorEl);
  if (!nodeId) return null;

  const node = BY_ID[nodeId] ?? STATIC[nodeId];
  if (!node) return null;

  const isSpecialist = SPECIALISTS.some((s) => s.id === nodeId);
  const isTool = TOOLS.some((t) => t.id === nodeId);
  const isCluster = CLUSTERS.some((c) => c.id === nodeId);
  const planned = node.state === "planned";

  const params = settings.spec?.[nodeId] ?? {};
  const paramKeys = planned ? [] : Object.keys(params);
  const hasControls = paramKeys.length > 0;
  const hasFinancial = paramKeys.some((k) => params[k].financial);

  const edited = settings.editedNodes.has(nodeId);
  const dirty = settings.dirtyNodes.has(nodeId);
  const busy = settings.status === "saving";

  return (
    <Popover
      open={open}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: "center", horizontal: "right" }}
      transformOrigin={{ vertical: "center", horizontal: "left" }}
      slotProps={{
        paper: {
          sx: {
            width: 316,
            ml: 1.5,
            bgcolor: "background.paper",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2.5,
            backgroundImage: "none",
            boxShadow: "0 18px 44px rgba(0,0,0,0.55)",
            overflow: "visible",
            animation: "commerce-studio-pop-in 220ms cubic-bezier(0.23,1,0.32,1) both",
          },
        },
      }}
    >
      {/* ── Header ─────────────────────────────────────────────────── */}
      <Stack
        direction="row"
        sx={{ alignItems: "center", justifyContent: "space-between", gap: 1, px: 2, py: 1.5 }}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", minWidth: 0 }}>
          {node.glyph && (
            <Box component="span" sx={{ fontSize: 13, color: "primary.light", flexShrink: 0 }}>
              {node.glyph}
            </Box>
          )}
          <Typography variant="body2" fontWeight={600} noWrap>
            {node.label}
          </Typography>
        </Stack>

        {planned ? (
          <Chip
            size="small"
            label="Not built yet"
            sx={{
              height: 20,
              bgcolor: "rgba(255,255,255,0.06)",
              color: "text.secondary",
              "& .MuiChip-label": { px: 1, fontSize: 10.5 },
            }}
          />
        ) : dirty ? (
          <Typography
            variant="caption"
            sx={{ color: "warning.main", fontWeight: 600, fontSize: 11.5, flexShrink: 0 }}
          >
            Unsaved
          </Typography>
        ) : edited ? (
          <Stack
            direction="row"
            spacing={0.5}
            sx={{
              alignItems: "center",
              flexShrink: 0,
              animation: "commerce-studio-pop-in 250ms cubic-bezier(0.23,1,0.32,1) both",
            }}
          >
            <CheckIcon sx={{ fontSize: 12, color: "success.main" }} />
            <Typography variant="caption" sx={{ color: "success.main", fontWeight: 600, fontSize: 11.5 }}>
              Edited
            </Typography>
          </Stack>
        ) : hasControls ? (
          <Typography
            variant="caption"
            sx={{
              fontWeight: 600,
              fontSize: 11.5,
              flexShrink: 0,
              background:
                "linear-gradient(90deg, #3B82F6 35%, #93C5FD 50%, #3B82F6 65%)",
              backgroundSize: "200% 100%",
              WebkitBackgroundClip: "text",
              backgroundClip: "text",
              color: "transparent",
              animation: "commerce-studio-shimmer 1.6s linear infinite",
            }}
          >
            Adjust
          </Typography>
        ) : null}
      </Stack>

      {/* ── What it does ───────────────────────────────────────────── */}
      <Section>
        <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.65, display: "block" }}>
          {node.what}
        </Typography>

        {isSpecialist && (
          <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap", mt: 1.25 }}>
            {node.tools?.length ? (
              node.tools.map((t) => (
                <Chip
                  key={t}
                  size="small"
                  label={BY_ID[t]?.label ?? t}
                  sx={{
                    height: 20,
                    bgcolor: "rgba(59,130,246,0.10)",
                    color: "primary.light",
                    "& .MuiChip-label": { px: 0.9, fontSize: 10.5 },
                  }}
                />
              ))
            ) : (
              <Typography variant="caption" sx={{ color: "text.secondary", fontStyle: "italic" }}>
                Calls nothing — pure logic over what Scout already fetched.
              </Typography>
            )}
          </Stack>
        )}

        {isTool && (
          <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap", mt: 1.25 }}>
            {dependentsOf(nodeId).map((s) => (
              <Chip
                key={s.id}
                size="small"
                label={s.label}
                sx={{
                  height: 20,
                  bgcolor: "rgba(255,255,255,0.05)",
                  color: "text.secondary",
                  "& .MuiChip-label": { px: 0.9, fontSize: 10.5 },
                }}
              />
            ))}
          </Stack>
        )}
      </Section>

      {/* ── This run (live mode only — never invented) ─────────────── */}
      {mode === "live" && (isSpecialist || isTool) && (
        <Section label="This run">
          {isTool ? (
            <Typography variant="caption" sx={{ color: toolUsed ? "text.primary" : "text.secondary" }}>
              {toolUsed ? "Exercised this turn." : "Not exercised in this turn."}
            </Typography>
          ) : runState?.summary ? (
            <Typography
              variant="caption"
              sx={{ fontFamily: "monospace", fontSize: 11.5, color: "text.primary", lineHeight: 1.6 }}
            >
              {runState.summary}
            </Typography>
          ) : (
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              {runState ? "Ran, but reported no summary." : "Did not run in this turn."}
            </Typography>
          )}
        </Section>
      )}

      {/* ── Controls ───────────────────────────────────────────────── */}
      {hasControls && (
        <Section label="Tune">
          <Stack spacing={1.25} onMouseLeave={() => setActiveNote(null)}>
            {paramKeys.map((key) => (
              <Box
                key={key}
                onMouseEnter={() => setActiveNote(key)}
                onFocusCapture={() => setActiveNote(key)}
              >
                <Control
                  node={nodeId}
                  param={key}
                  spec={params[key]}
                  value={settings.valueOf(nodeId, key)}
                  defaultValue={settings.defaults?.[nodeId]?.[key]}
                  disabled={busy}
                  onChange={(v) => settings.setLocal(nodeId, key, v)}
                />
              </Box>
            ))}
          </Stack>

          {/* Explains whichever control you're on. Reserved height, so
              moving between controls doesn't make the card jump. */}
          <Typography
            variant="caption"
            sx={{
              color: "text.secondary",
              display: "block",
              mt: 1.25,
              minHeight: 32,
              fontSize: 10.5,
              lineHeight: 1.5,
            }}
          >
            {params[activeNote ?? paramKeys[0]]?.note}
          </Typography>
        </Section>
      )}

      {/* ── Financial disclosure ───────────────────────────────────── */}
      {hasFinancial && (
        <Section sx={{ bgcolor: "rgba(245,158,11,0.06)" }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
            <ShieldOutlinedIcon sx={{ fontSize: 15, color: "warning.main", mt: "1px", flexShrink: 0 }} />
            <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 10.5, lineHeight: 1.55 }}>
              This node holds a bound on how much can move without a human. Applying a change
              writes the old and new value to the audit trail.
            </Typography>
          </Stack>
        </Section>
      )}

      {/* ── Nothing to tune, and why ───────────────────────────────── */}
      {!hasControls && !planned && settings.noTunables?.[nodeId] && (
        <Section label="Tune">
          <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.6 }}>
            {settings.noTunables[nodeId]}
          </Typography>
        </Section>
      )}

      {/* ── Actions ────────────────────────────────────────────────── */}
      {(hasControls || isCluster) && (
        <Section sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1 }}>
          {hasControls ? (
            <>
              <Button
                size="small"
                disabled={(!edited && !dirty) || busy}
                onClick={() => (dirty ? settings.discard(nodeId) : settings.resetNode(nodeId))}
                startIcon={<RestartAltIcon sx={{ fontSize: 15 }} />}
                sx={{
                  color: "text.secondary",
                  fontSize: 12,
                  boxShadow: "none",
                  "&:hover": { boxShadow: "none" },
                }}
              >
                {dirty ? "Discard" : "Reset"}
              </Button>
              <Button
                size="small"
                variant="contained"
                disabled={!dirty || busy}
                onClick={() => settings.commit(nodeId)}
                sx={{ boxShadow: "none", "&:hover": { boxShadow: "none" }, fontSize: 12 }}
              >
                {busy ? "Applying…" : "Apply"}
              </Button>
            </>
          ) : (
            <Button
              size="small"
              variant={planned ? "outlined" : "contained"}
              disabled={planned}
              endIcon={<ArrowForwardIcon sx={{ fontSize: 15 }} />}
              onClick={() => onNavigate(node.route)}
              sx={{ boxShadow: "none", "&:hover": { boxShadow: "none" }, fontSize: 12 }}
            >
              {planned ? "Nothing to open yet" : `Open ${node.label}`}
            </Button>
          )}
        </Section>
      )}

      {/* A cluster that also has controls still needs its door. */}
      {isCluster && hasControls && !planned && (
        <Section sx={{ pt: 1 }}>
          <Button
            size="small"
            variant="contained"
            fullWidth
            endIcon={<ArrowForwardIcon sx={{ fontSize: 15 }} />}
            onClick={() => onNavigate(node.route)}
            sx={{ boxShadow: "none", "&:hover": { boxShadow: "none" }, fontSize: 12 }}
          >
            Open {node.label}
          </Button>
        </Section>
      )}

      <style>{`
        @keyframes commerce-studio-pop-in {
          from { opacity: 0; transform: scale(0.96); }
          to   { opacity: 1; transform: scale(1); }
        }
        @keyframes commerce-studio-shimmer {
          from { background-position: 200% 0; }
          to   { background-position: -200% 0; }
        }
      `}</style>
    </Popover>
  );
}
