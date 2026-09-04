import { useEffect, useMemo, useState } from "react";
import {
  Box, Button, Checkbox, InputBase, MenuItem, Popover, Select, Stack, Typography,
} from "@mui/material";
import CalendarTodayOutlinedIcon from "@mui/icons-material/CalendarTodayOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";

/**
 * THE DATE RANGE, PICKED OFF A CALENDAR.
 *
 * This replaced a three-option dropdown. The reason it is worth the code is
 * that the dropdown could only express windows ending now, and half the
 * questions a merchant asks about a shop are about a window that ended
 * earlier — "how did the week of the launch go" is not answerable with
 * "last 7 days" on any day but one.
 *
 * TWO KINDS OF WINDOW, AND THEY ARE NOT INTERCHANGEABLE
 *
 * A ROLLING window ("last 30 days") moves with the clock and is what you
 * want for a health check. A FIXED window picked off the calendar must not
 * move: a range ending last Tuesday still ends last Tuesday when the page is
 * reloaded on Thursday. The control emits both shapes and the backend
 * honours the distinction rather than quietly converting one into the other.
 *
 * NOTHING APPLIES UNTIL APPLY
 *
 * Every edit in here is draft state. Clicking a preset, dragging out a
 * range, changing the unit — none of it refetches. Cancel discards. The
 * alternative, where each click fires a request, means a two-click range
 * selection always issues one query nobody asked for, against a range that
 * was only ever half-specified.
 *
 * WHAT IS DELIBERATELY NOT IN THE PRESET LIST
 *
 * The reference offers Black Friday, Cyber Monday and Quarters. Those are
 * useful on a shop with years of trading behind it. On this one every one of
 * them resolves to a window with nothing in it, and a menu of presets that
 * all return "no data" teaches a merchant that the control is broken.
 */

const MS_DAY = 86400000;
const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"];
const SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
               "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const addMonths = (d, n) => new Date(d.getFullYear(), d.getMonth() + n, 1);
const sameDay = (a, b) =>
  a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()
  && a.getDate() === b.getDate();

/** `YYYY-MM-DD` in LOCAL time — toISOString would shift the day in IST. */
const iso = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const daysBetween = (a, b) => Math.round((startOfDay(b) - startOfDay(a)) / MS_DAY) + 1;

function rangeLabel(start, end) {
  if (!start || !end) return "Select a range";
  const sameYear = start.getFullYear() === end.getFullYear();
  const left = `${SHORT[start.getMonth()]} ${start.getDate()}`;
  const right = `${SHORT[end.getMonth()]} ${end.getDate()}`;
  if (sameDay(start, end)) return `${left}, ${start.getFullYear()}`;
  return sameYear
    ? `${left}–${right}, ${end.getFullYear()}`
    : `${left}, ${start.getFullYear()}–${right}, ${end.getFullYear()}`;
}

const UNITS = [
  { value: "days", label: "Days", days: 1 },
  { value: "weeks", label: "Weeks", days: 7 },
  { value: "months", label: "Months", days: 30 },
];

function Month({ month, start, end, hover, onPick, onHover, today }) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const lead = first.getDay();
  const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  // While only one end is fixed, the hovered day stands in for the other, so
  // the range you are about to commit to is visible before you commit to it.
  const provisional = end ?? hover;
  const lo = start && provisional && provisional < start ? provisional : start;
  const hi = start && provisional && provisional < start ? start : provisional;

  const cells = [];
  for (let i = 0; i < lead; i += 1) cells.push(null);
  for (let d = 1; d <= count; d += 1) {
    cells.push(new Date(month.getFullYear(), month.getMonth(), d));
  }

  return (
    <Box sx={{ width: 232 }}>
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", mb: 0.5 }}>
        {WEEKDAYS.map((w) => (
          <Typography
            key={w}
            variant="caption"
            sx={{ textAlign: "center", fontSize: 10.5, color: "text.disabled", py: 0.5 }}
          >
            {w}
          </Typography>
        ))}
      </Box>
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)" }}>
        {cells.map((day, i) => {
          if (!day) return <Box key={`pad-${i}`} sx={{ height: 30 }} />;
          // Nothing has happened in the future, so it cannot be selected —
          // a range ending next month would return an empty report and look
          // like a bug in the data rather than a bug in the request.
          const future = day > today;
          const isStart = sameDay(day, lo);
          const isEnd = sameDay(day, hi);
          const inRange = lo && hi && day > lo && day < hi;
          const edge = isStart || isEnd;

          return (
            <Box
              key={iso(day)}
              component="button"
              type="button"
              disabled={future}
              onClick={() => onPick(day)}
              onMouseEnter={() => onHover(day)}
              sx={{
                height: 30, border: "none", p: 0,
                cursor: future ? "default" : "pointer",
                fontSize: 12,
                fontVariantNumeric: "tabular-nums",
                fontWeight: edge ? 700 : 500,
                color: future ? "text.disabled"
                  : edge ? "#0B0F17"
                  : inRange ? "text.primary" : "text.secondary",
                bgcolor: edge ? "#E6E9EF"
                  : inRange ? "rgba(255,255,255,0.07)" : "transparent",
                // Square ends on the inside of the range, rounded on the
                // outside, so a selection reads as one bar rather than a
                // row of separate chips.
                borderTopLeftRadius: isStart || !inRange ? 6 : 0,
                borderBottomLeftRadius: isStart || !inRange ? 6 : 0,
                borderTopRightRadius: isEnd || !inRange ? 6 : 0,
                borderBottomRightRadius: isEnd || !inRange ? 6 : 0,
                "&:hover": future ? {} : {
                  bgcolor: edge ? "#E6E9EF" : "rgba(255,255,255,0.12)",
                },
              }}
            >
              {day.getDate()}
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}

export default function DateRangePicker({ value, onChange }) {
  const [anchor, setAnchor] = useState(null);
  const today = useMemo(() => startOfDay(new Date()), []);

  // Draft state. Seeded from the committed value each time the popover
  // opens, so cancelling genuinely discards rather than half-applying.
  const [mode, setMode] = useState(value?.mode ?? "last");
  const [count, setCount] = useState(value?.count ?? 30);
  const [unit, setUnit] = useState(value?.unit ?? "days");
  const [includeToday, setIncludeToday] = useState(value?.includeToday ?? true);
  const [start, setStart] = useState(value?.start ?? addDays(today, -29));
  const [end, setEnd] = useState(value?.end ?? today);
  const [picking, setPicking] = useState(false);
  const [hover, setHover] = useState(null);
  const [rightMonth, setRightMonth] = useState(() => addMonths(today, 0));

  const open = Boolean(anchor);

  useEffect(() => {
    if (!open) return;
    setMode(value?.mode ?? "last");
    setCount(value?.count ?? 30);
    setUnit(value?.unit ?? "days");
    setIncludeToday(value?.includeToday ?? true);
    setStart(value?.start ?? addDays(today, -29));
    setEnd(value?.end ?? today);
    setPicking(false);
    setHover(null);
    setRightMonth(addMonths(value?.end ?? today, 0));
  }, [open]);   // eslint-disable-line react-hooks/exhaustive-deps

  // The "Last N units" editor drives the calendar rather than sitting beside
  // it, so the two halves of the popover can never disagree about what is
  // selected.
  useEffect(() => {
    if (mode !== "last") return;
    const span = (UNITS.find((u) => u.value === unit)?.days ?? 1) * Math.max(1, count);
    const last = includeToday ? today : addDays(today, -1);
    setEnd(last);
    setStart(addDays(last, -(span - 1)));
  }, [mode, count, unit, includeToday, today]);

  const applyPreset = (next) => {
    setMode(next);
    if (next === "today") { setStart(today); setEnd(today); }
    if (next === "yesterday") {
      const y = addDays(today, -1);
      setStart(y); setEnd(y);
    }
    if (next === "month") { setStart(new Date(today.getFullYear(), today.getMonth(), 1)); setEnd(today); }
    if (next === "year") { setStart(new Date(today.getFullYear(), 0, 1)); setEnd(today); }
    setPicking(false);
  };

  const pickDay = (day) => {
    // Any click on the calendar is a custom range by definition — leaving
    // the mode on "Last 30 days" while the dates say otherwise is the bug
    // this line exists to prevent.
    setMode("custom");
    if (!picking) {
      setStart(day);
      setEnd(null);
      setPicking(true);
      return;
    }
    if (day < start) {
      setEnd(start);
      setStart(day);
    } else {
      setEnd(day);
    }
    setPicking(false);
  };

  const label = (() => {
    if (!value) return "Last 30 days";
    if (value.mode === "today") return "Today";
    if (value.mode === "yesterday") return "Yesterday";
    if (value.mode === "month") return "Month to date";
    if (value.mode === "year") return "Year to date";
    if (value.mode === "last") {
      const u = UNITS.find((x) => x.value === value.unit)?.label.toLowerCase() ?? "days";
      return `Last ${value.count} ${value.count === 1 ? u.replace(/s$/, "") : u}`;
    }
    return rangeLabel(value.start, value.end);
  })();

  const commit = () => {
    if (!start || !end) return;
    onChange({
      mode, count, unit, includeToday, start, end,
      // Both shapes travel together: a rolling window keeps its day count so
      // it can stay rolling, a fixed one carries the dates it was pinned to.
      days: daysBetween(start, end),
      startISO: iso(start),
      endISO: iso(end),
      rolling: mode === "last" && includeToday,
    });
    setAnchor(null);
  };

  const PRESETS = [
    { key: "today", label: "Today" },
    { key: "yesterday", label: "Yesterday" },
    { divider: true },
    { key: "last", label: "Last" },
    { key: "month", label: "Month to date" },
    { key: "year", label: "Year to date" },
    { divider: true },
    { key: "custom", label: "Custom range" },
  ];

  return (
    <>
      <Button
        size="small"
        variant="outlined"
        onClick={(e) => setAnchor(e.currentTarget)}
        startIcon={<CalendarTodayOutlinedIcon sx={{ fontSize: 14 }} />}
        endIcon={open ? <ExpandLessIcon sx={{ fontSize: 16 }} /> : <ExpandMoreIcon sx={{ fontSize: 16 }} />}
        sx={{
          textTransform: "none", fontSize: 12.5, fontWeight: 500,
          borderColor: "divider", color: "text.primary",
          "&:hover": { borderColor: "rgba(255,255,255,0.24)" },
        }}
      >
        {label}
      </Button>

      <Popover
        open={open}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{
          paper: {
            sx: {
              mt: 1, borderRadius: 2.5, border: "1px solid",
              borderColor: "divider", bgcolor: "background.paper",
              backgroundImage: "none",
            },
          },
        }}
      >
        <Stack direction="row" sx={{ alignItems: "stretch" }}>
          {/* ── presets ─────────────────────────────────────────────── */}
          <Stack
            spacing={0.25}
            sx={{ width: 168, p: 1, borderRight: "1px solid", borderColor: "divider" }}
          >
            {PRESETS.map((preset, i) =>
              preset.divider ? (
                <Box key={`d-${i}`} sx={{ my: 0.75, borderTop: "1px solid", borderColor: "divider" }} />
              ) : (
                <Box
                  key={preset.key}
                  component="button"
                  type="button"
                  onClick={() => applyPreset(preset.key)}
                  sx={{
                    textAlign: "left", border: "none", cursor: "pointer",
                    px: 1.25, py: 0.85, borderRadius: 1.5, fontSize: 13,
                    fontWeight: mode === preset.key ? 600 : 500,
                    color: mode === preset.key ? "text.primary" : "text.secondary",
                    bgcolor: mode === preset.key ? "rgba(255,255,255,0.08)" : "transparent",
                    "&:hover": { bgcolor: "rgba(255,255,255,0.05)", color: "text.primary" },
                  }}
                >
                  {preset.label}
                </Box>
              ))}
          </Stack>

          {/* ── the range itself ────────────────────────────────────── */}
          <Box sx={{ p: 2 }}>
            {mode === "last" && (
              <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", mb: 2 }}>
                <Typography variant="body2" sx={{ fontSize: 13, color: "text.secondary" }}>
                  Last
                </Typography>
                <InputBase
                  value={count}
                  onChange={(e) => {
                    const n = parseInt(e.target.value.replace(/\D/g, ""), 10);
                    setCount(Number.isFinite(n) ? Math.min(n, 365) : "");
                  }}
                  onBlur={() => { if (!count) setCount(1); }}
                  sx={{
                    width: 68, px: 1.25, height: 34, fontSize: 13,
                    border: "1px solid", borderColor: "divider", borderRadius: 1.5,
                  }}
                />
                <Select
                  size="small"
                  value={unit}
                  onChange={(e) => setUnit(e.target.value)}
                  sx={{ width: 120, height: 34, fontSize: 13 }}
                >
                  {UNITS.map((u) => (
                    <MenuItem key={u.value} value={u.value} sx={{ fontSize: 13 }}>
                      {u.label}
                    </MenuItem>
                  ))}
                </Select>
                <Stack direction="row" spacing={0.25} sx={{ alignItems: "center" }}>
                  <Checkbox
                    size="small"
                    checked={includeToday}
                    onChange={(e) => setIncludeToday(e.target.checked)}
                  />
                  <Typography variant="body2" sx={{ fontSize: 13, color: "text.secondary" }}>
                    Include today
                  </Typography>
                </Stack>
              </Stack>
            )}

            <Stack direction="row" spacing={3} onMouseLeave={() => setHover(null)}>
              {[addMonths(rightMonth, -1), rightMonth].map((month, i) => (
                <Box key={i}>
                  <Stack
                    direction="row"
                    sx={{ alignItems: "center", justifyContent: "space-between", mb: 1, height: 28 }}
                  >
                    {i === 0 ? (
                      <Box
                        component="button" type="button"
                        onClick={() => setRightMonth((m) => addMonths(m, -1))}
                        sx={{ border: "none", bgcolor: "transparent", cursor: "pointer",
                              color: "text.secondary", display: "flex", p: 0.25, borderRadius: 1,
                              "&:hover": { bgcolor: "rgba(255,255,255,0.06)" } }}
                      >
                        <ChevronLeftIcon sx={{ fontSize: 18 }} />
                      </Box>
                    ) : <Box sx={{ width: 22 }} />}

                    <Typography variant="body2" sx={{ fontSize: 13, fontWeight: 600 }}>
                      {MONTHS[month.getMonth()]} {month.getFullYear()}
                    </Typography>

                    {i === 1 ? (
                      <Box
                        component="button" type="button"
                        // Cannot page into a month that has not happened.
                        disabled={addMonths(rightMonth, 1) > addMonths(today, 0)}
                        onClick={() => setRightMonth((m) => addMonths(m, 1))}
                        sx={{ border: "none", bgcolor: "transparent",
                              cursor: addMonths(rightMonth, 1) > addMonths(today, 0) ? "default" : "pointer",
                              color: addMonths(rightMonth, 1) > addMonths(today, 0)
                                ? "text.disabled" : "text.secondary",
                              display: "flex", p: 0.25, borderRadius: 1,
                              "&:hover": { bgcolor: "rgba(255,255,255,0.06)" } }}
                      >
                        <ChevronRightIcon sx={{ fontSize: 18 }} />
                      </Box>
                    ) : <Box sx={{ width: 22 }} />}
                  </Stack>

                  <Month
                    month={month}
                    start={start}
                    end={end}
                    hover={picking ? hover : null}
                    today={today}
                    onPick={pickDay}
                    onHover={setHover}
                  />
                </Box>
              ))}
            </Stack>
          </Box>
        </Stack>

        <Stack
          direction="row"
          sx={{
            alignItems: "center", justifyContent: "space-between",
            px: 2, py: 1.5, borderTop: "1px solid", borderColor: "divider", gap: 2,
          }}
        >
          <Typography variant="body2" sx={{ fontSize: 12.5, color: "text.secondary" }}>
            {picking
              ? "Pick the end of the range"
              : `${rangeLabel(start, end)}${start && end ? ` · ${daysBetween(start, end)} days` : ""}`}
          </Typography>
          <Stack direction="row" spacing={1}>
            <Button size="small" variant="outlined" onClick={() => setAnchor(null)}
                    sx={{ textTransform: "none", borderColor: "divider", color: "text.secondary" }}>
              Cancel
            </Button>
            <Button size="small" variant="contained" onClick={commit}
                    disabled={!start || !end}
                    sx={{ textTransform: "none", boxShadow: "none" }}>
              Apply
            </Button>
          </Stack>
        </Stack>
      </Popover>
    </>
  );
}
