import { useState } from "react";
import { Box, Menu, MenuItem, Typography } from "@mui/material";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";

/**
 * The two non-numeric controls the tune card needs. Both are built from
 * plain MUI so they inherit the dark theme rather than introducing a
 * second visual language beside it.
 */

/** Two-state track with a thumb that slides between the options. */
export function SegmentedToggle({ value, onChange, labels = ["Off", "On"], disabled }) {
  return (
    <Box
      sx={{
        position: "relative",
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        p: "2px",
        borderRadius: 1.5,
        bgcolor: "rgba(255,255,255,0.05)",
        opacity: disabled ? 0.45 : 1,
        width: 108,
        flexShrink: 0,
      }}
    >
      <Box
        aria-hidden
        sx={{
          position: "absolute",
          top: 2,
          bottom: 2,
          left: 2,
          width: "calc(50% - 2px)",
          borderRadius: 1.25,
          bgcolor: value ? "rgba(59,130,246,0.22)" : "rgba(255,255,255,0.08)",
          boxShadow: value ? "0 0 0 1px rgba(59,130,246,0.5)" : "none",
          transform: `translateX(${value ? "100%" : "0%"})`,
          transition: "transform 300ms cubic-bezier(0.23,1,0.32,1), background-color 200ms, box-shadow 200ms",
        }}
      />
      {labels.map((label, index) => (
        <Box
          key={label}
          component="button"
          type="button"
          disabled={disabled}
          aria-pressed={Boolean(value) === Boolean(index)}
          onClick={() => onChange(index === 1)}
          sx={{
            position: "relative",
            zIndex: 1,
            height: 22,
            border: "none",
            bgcolor: "transparent",
            cursor: disabled ? "default" : "pointer",
            fontFamily: "inherit",
            fontSize: 11.5,
            fontWeight: 500,
            color:
              Boolean(value) === Boolean(index) ? (index === 1 ? "primary.light" : "text.primary") : "text.secondary",
            transition: "color 200ms",
          }}
        >
          {label}
        </Box>
      ))}
    </Box>
  );
}

/** Compact select — the pattern the reference card uses for longer lists. */
export function SelectField({ value, choices, onChange, format = (v) => v, disabled, width = 132 }) {
  const [anchor, setAnchor] = useState(null);

  return (
    <>
      <Box
        component="button"
        type="button"
        disabled={disabled}
        aria-expanded={Boolean(anchor)}
        onClick={(e) => setAnchor(e.currentTarget)}
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 0.5,
          width,
          height: 28,
          pl: 1.25,
          pr: 0.5,
          borderRadius: 1.5,
          border: "none",
          bgcolor: "rgba(255,255,255,0.05)",
          boxShadow: anchor ? "0 0 0 1px #3B82F6" : "none",
          cursor: disabled ? "default" : "pointer",
          opacity: disabled ? 0.45 : 1,
          fontFamily: "inherit",
          transition: "box-shadow 200ms",
          flexShrink: 0,
        }}
      >
        <Typography variant="caption" sx={{ color: "text.primary", fontSize: 12 }} noWrap>
          {format(value)}
        </Typography>
        <KeyboardArrowDownIcon
          sx={{
            fontSize: 15,
            color: "text.secondary",
            transform: anchor ? "rotate(180deg)" : "none",
            transition: "transform 200ms",
          }}
        />
      </Box>

      <Menu
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        slotProps={{
          paper: {
            sx: {
              bgcolor: "background.paper",
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 2,
              backgroundImage: "none",
              mt: 0.5,
              minWidth: width,
            },
          },
          list: { sx: { py: 0.5 } },
        }}
      >
        {choices.map((choice) => (
          <MenuItem
            key={choice}
            selected={choice === value}
            onClick={() => {
              onChange(choice);
              setAnchor(null);
            }}
            sx={{
              fontSize: 12.5,
              mx: 0.5,
              borderRadius: 1.25,
              minHeight: 30,
              "&.Mui-selected": { bgcolor: "rgba(59,130,246,0.16)", color: "primary.light" },
              "&.Mui-selected:hover": { bgcolor: "rgba(59,130,246,0.22)" },
            }}
          >
            {format(choice)}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
