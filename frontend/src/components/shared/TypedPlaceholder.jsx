import { useEffect, useRef, useState } from "react";
import { Box } from "@mui/material";
import { useReducedMotion } from "motion/react";

/**
 * A PLACEHOLDER THAT TYPES ITSELF.
 *
 * A fixed prefix, then a suffix that types out, holds, deletes itself and
 * gives way to the next. It is there to answer "what can I even ask this
 * thing" without a wall of example text, which is the actual problem with
 * an empty chat box.
 *
 * IT IS A PLACEHOLDER, NOT CONTENT.
 *
 * Three consequences, and they are the whole of the design:
 *
 *   It stops the moment anyone types. Animation behind live text competes
 *   with the person's own words for attention, and the box they are typing
 *   into should be the stillest thing on screen.
 *
 *   It is `aria-hidden` and the real input keeps its own static
 *   `placeholder`. A screen reader that announced this would read a
 *   half-typed word, then the same word again a letter later. Assistive
 *   technology gets the plain version; the animation is decoration on top.
 *
 *   `prefers-reduced-motion` gets the first suffix, complete and still.
 *   Not an empty box — the point is to show what you can ask, and that
 *   survives without the typing.
 */
export default function TypedPlaceholder({
  prefix = "",
  phrases = [],
  active = true,
  typeMs = 45,
  deleteMs = 22,
  holdMs = 1600,
  sx,
}) {
  const still = useReducedMotion();
  const [shown, setShown] = useState(still ? (phrases[0] ?? "") : "");
  const timer = useRef(null);

  useEffect(() => {
    if (!active || still || phrases.length === 0) return undefined;

    let phrase = 0;
    let cut = 0;
    let deleting = false;
    let stopped = false;

    const tick = () => {
      if (stopped) return;
      const target = phrases[phrase % phrases.length];

      if (!deleting) {
        cut += 1;
        setShown(target.slice(0, cut));
        if (cut >= target.length) {
          deleting = true;
          timer.current = setTimeout(tick, holdMs);
          return;
        }
        timer.current = setTimeout(tick, typeMs);
        return;
      }

      cut -= 1;
      setShown(target.slice(0, Math.max(0, cut)));
      if (cut <= 0) {
        deleting = false;
        phrase += 1;
        // A beat before the next one starts, or the loop reads as a
        // stutter rather than a list of things you could ask.
        timer.current = setTimeout(tick, 320);
        return;
      }
      timer.current = setTimeout(tick, deleteMs);
    };

    timer.current = setTimeout(tick, 420);
    return () => {
      stopped = true;
      clearTimeout(timer.current);
    };
  }, [active, still, phrases, typeMs, deleteMs, holdMs]);

  if (!active && !still) return null;

  return (
    <Box
      aria-hidden
      sx={{
        pointerEvents: "none",
        color: "text.disabled",
        whiteSpace: "pre",
        overflow: "hidden",
        textOverflow: "ellipsis",
        ...sx,
      }}
    >
      {prefix}
      {shown}
      {!still && (
        <Box
          component="span"
          sx={{
            display: "inline-block",
            width: "1px",
            height: "1em",
            verticalAlign: "text-bottom",
            bgcolor: "text.disabled",
            ml: "1px",
            animation: "caretBlink 1s step-end infinite",
            "@keyframes caretBlink": {
              "0%, 100%": { opacity: 1 },
              "50%": { opacity: 0 },
            },
          }}
        />
      )}
    </Box>
  );
}
