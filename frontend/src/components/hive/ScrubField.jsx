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

  return (
    <Tooltip title={hint ?? ""} placement="top" enterDelay={600} disableHoverListener={!hint}>
      <Box
        component="label"
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 0.5,
          height: 28,
          minWidth: 0,
          pl: 0.5,
          pr: 0.75,
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
    </Tooltip>
  );
}
