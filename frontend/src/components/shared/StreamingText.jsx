import { useEffect, useState } from "react";
import { Typography } from "@mui/material";

const WORD_MS = 45;

/**
 * Reveals text word-by-word rather than all at once — adapted from
 * the reference's streaming-text pattern, stripped of citation/source
 * chips since this project has nothing equivalent to attribute here.
 * Calls onDone once fully revealed, useful for sequencing follow-up UI.
 */
export default function StreamingText({ text, sx, onDone }) {
  const words = text.split(" ");
  const [count, setCount] = useState(0);
  const done = count >= words.length;

  useEffect(() => {
    setCount(0);
  }, [text]);

  useEffect(() => {
    if (done) {
      onDone?.();
      return;
    }
    const t = setTimeout(() => setCount((c) => c + 1), WORD_MS);
    return () => clearTimeout(t);
  }, [count, done, onDone]);

  return (
    <Typography component="span" sx={sx}>
      {words.slice(0, count).join(" ")}
      {!done && (
        <Typography
          component="span"
          sx={{
            display: "inline-block",
            width: "2px",
            height: "0.9em",
            ml: "2px",
            bgcolor: "currentColor",
            verticalAlign: "text-bottom",
            animation: "commerce-studio-cursor-blink 0.9s step-start infinite",
          }}
        />
      )}

      <style>{`
        @keyframes commerce-studio-cursor-blink { 50% { opacity: 0; } }
      `}</style>
    </Typography>
  );
}