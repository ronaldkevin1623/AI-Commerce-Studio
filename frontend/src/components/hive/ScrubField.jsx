import { useRef, useState } from "react";
import { Box, Tooltip } from "@mui/material";

/**
 * A number field you can scrub.
 *
 * Three ways in, because different values want different precision:
 *   drag the label sideways   — coarse, for finding the right neighbourhood
 *   hold ⇧ while dragging     — ten times finer, for landing on a figure
 *   ↑ / ↓ (⇧ for ×10), or type — exact
 *
 * Sensitivity scales with the range rather than being fixed, so a ceiling
 * that runs to ₹10,00,000 and a percentage that runs to 100 both feel right
 * under the same gesture.
 */
export default function ScrubField({
  label,
  value,
  onChange,
  min,
  max,
  prefix,
  suffix,
  active,
  disabled,
  hint,
}) {
  const drag = useRef(null);
  const [scrubbing, setScrubbing] = useState(false);
  const [typing, setTyping] = useState(null);

  // Held key-repeat fires faster than React re-renders, so stepping can't
  // read `value` out of its own closure — five quick presses would all
  // compute from the same starting number and land one step away. The ref
  // is advanced immediately on each step and re-synced on every render, so
  // it tracks both a fast burst and any change arriving from outside.
  const latest = useRef(value);
  latest.current = value;

  const step = (delta) => {
    const next = clamp(latest.current + delta);
    latest.current = next;
    onChange(next);
  };

  const clamp = (v) => Math.min(max, Math.max(min, Math.round(v)));
  const perPixel = Math.max((max - min) / 300, 1);

  const commitTyped = () => {
    if (typing === null) return;
    const digits = typing.replace(/[^\d]/g, "");
    if (digits !== "") onChange(clamp(Number(digits)));
    setTyping(null);
  };

  const shown = typing ?? value?.toLocaleString("en-IN");

  // Where this setting sits between its own bounds. Not a value in its own
  // right — just the position of the real one, which is why the number
  // beside it stays in ₹ or seconds or per cent rather than becoming a
  // second scale to reconcile.
  const span = (max ?? 100) - (min ?? 0);
  const share = span > 0
    ? Math.min(1, Math.max(0, ((Number(value ?? 0)) - (min ?? 0)) / span))
    : 0;

  /** The value under the pointer, snapped to whole units. */
  const fromTrack = (event) => {
    const box = event.currentTarget.getBoundingClientRect();
    if (!box.width) return Number(value ?? 0);
    const ratio = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    return clamp(Math.round((min ?? 0) + ratio * span));
  };

  return (
    <Tooltip title={hint ?? ""} placement="top" enterDelay={600} disableHoverListener={!hint}>
      <Box
        component="label"
        sx={{
          display: "block",
          minWidth: 0,
          px: 0.75,
          pt: 0.4,
          pb: 0.75,
          borderRadius: 1.5,
          bgcolor: active ? "rgba(59,130,246,0.14)" : "rgba(255,255,255,0.05)",
          boxShadow: scrubbing
            ? "0 0 0 1px #3B82F6"
            : active
              ? "0 0 0 1px rgba(59,130,246,0.45)"
              : "none",
          opacity: disabled ? 0.45 : 1,
          transition: "background-color 200ms, box-shadow 200ms",
        }}
      >
        {/* Row one: the label you can still scrub, and the exact number. */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, height: 22, minWidth: 0 }}>
        {/* The label is the scrub handle. */}
        <Box
          component="span"
          role="slider"
          aria-label={label}
          aria-valuenow={value}
          aria-valuemin={min}
          aria-valuemax={max}
          tabIndex={disabled ? -1 : 0}
          onPointerDown={(e) => {
            if (disabled) return;
            e.preventDefault();
            e.currentTarget.setPointerCapture(e.pointerId);
            drag.current = { x: e.clientX, v: value };
            setScrubbing(true);
          }}
          onPointerMove={(e) => {
            if (!drag.current) return;
            const fine = e.shiftKey ? 0.1 : 1;
            onChange(clamp(drag.current.v + (e.clientX - drag.current.x) * perPixel * fine));
          }}
          onPointerUp={() => {
            drag.current = null;
            setScrubbing(false);
          }}
          onPointerCancel={() => {
            drag.current = null;
            setScrubbing(false);
          }}
          onKeyDown={(e) => {
            if (disabled) return;
            const stepBy = (e.shiftKey ? 10 : 1) * (perPixel > 1 ? Math.round(perPixel) : 1);
            if (e.key === "ArrowUp" || e.key === "ArrowRight") {
              e.preventDefault();
              step(stepBy);
            } else if (e.key === "ArrowDown" || e.key === "ArrowLeft") {
              e.preventDefault();
              step(-stepBy);
            }
          }}
          sx={{
            display: "flex",
            alignItems: "center",
            height: "100%",
            flexShrink: 0,
            px: 0.5,
            borderRadius: 1,
            cursor: disabled ? "default" : "ew-resize",
            touchAction: "none",
            userSelect: "none",
            fontSize: 11.5,
            whiteSpace: "nowrap",
            color: scrubbing ? "primary.light" : "text.secondary",
            "&:hover": { color: disabled ? "text.secondary" : "text.primary" },
            "&:focus-visible": { outline: "none", color: "primary.light" },
          }}
        >
          {label}
        </Box>

        {prefix && (
          <Box component="span" sx={{ fontSize: 11.5, color: "text.secondary", flexShrink: 0 }}>
            {prefix}
          </Box>
        )}

        <Box
          component="input"
          inputMode="numeric"
          disabled={disabled}
          value={shown}
          onChange={(e) => setTyping(e.target.value)}
          onBlur={commitTyped}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commitTyped();
              e.currentTarget.blur();
            }
          }}
          aria-label={`${label} value`}
          sx={{
            minWidth: 0,
            flex: 1,
            width: "100%",
            bgcolor: "transparent",
            border: "none",
            outline: "none",
            p: 0,
            fontFamily: "inherit",
            fontSize: 12,
            fontVariantNumeric: "tabular-nums",
            textAlign: "right",
            color: "text.primary",
          }}
        />

        {suffix && (
          <Box component="span" sx={{ fontSize: 11, color: "text.secondary", flexShrink: 0 }}>
            {suffix}
          </Box>
        )}
        </Box>

        {/* The same value, as something that obviously slides.
​
            Scrubbing a label sideways is precise and completely invisible —
            nobody discovers it, so the dials read as captions rather than
            controls. The track spans this dial's REAL range: left is its
            minimum, right is its maximum, and the fill is where the setting
            actually sits between them. There is no separate 0–100 number,
            because a percentage that mapped onto ₹ or seconds would be a
            second figure to reconcile and the first one people misread. */}
        <Box
          role="slider"
          aria-label={`${label} slider`}
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={Number(value ?? 0)}
          onPointerDown={(e) => {
            if (disabled) return;
            e.currentTarget.setPointerCapture(e.pointerId);
            setScrubbing(true);
            onChange(fromTrack(e));
          }}
          onPointerMove={(e) => {
            if (disabled || !e.currentTarget.hasPointerCapture?.(e.pointerId)) return;
            onChange(fromTrack(e));
          }}
          onPointerUp={(e) => {
            e.currentTarget.releasePointerCapture?.(e.pointerId);
            setScrubbing(false);
          }}
          sx={{
            mt: 0.9, height: 14, display: "flex", alignItems: "center",
            cursor: disabled ? "default" : "pointer", touchAction: "none",
          }}
        >
          <Box sx={{ position: "relative", width: "100%", height: 4, borderRadius: 2,
                     bgcolor: "rgba(255,255,255,0.09)" }}>
            <Box sx={{
              position: "absolute", left: 0, top: 0, bottom: 0,
              width: `${share * 100}%`, borderRadius: 2,
              bgcolor: disabled ? "rgba(255,255,255,0.2)"
                : scrubbing ? "primary.light" : "primary.main",
              transition: scrubbing ? "none" : "width 120ms ease",
            }} />
            <Box sx={{
              position: "absolute", top: "50%", left: `${share * 100}%`,
              transform: "translate(-50%, -50%)",
              width: scrubbing ? 13 : 10, height: scrubbing ? 13 : 10,
              borderRadius: "50%",
              bgcolor: disabled ? "rgba(255,255,255,0.25)" : "primary.light",
              border: "2px solid", borderColor: "background.paper",
              transition: "width 120ms ease, height 120ms ease",
            }} />
          </Box>
        </Box>
      </Box>
    </Tooltip>
  );
}
