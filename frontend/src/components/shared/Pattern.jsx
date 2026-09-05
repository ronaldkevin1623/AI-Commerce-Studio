import { motion, useReducedMotion } from "motion/react";

import "../../styles/pattern.css";

/**
 * The background the app sits on.
 *
 * The geometry is in pattern.css; what lives here is the only part that
 * moves — two large, very faint washes drifting across the field. Everything
 * else is static, because a background that animates more than this stops
 * being a background.
 *
 * WHY IT MOVES AT ALL
 *
 * An agent console is a screen people sit in front of while something is
 * thinking. A field with a slow current under it reads as a system that is
 * awake; a perfectly still one reads as a screenshot. That is the whole
 * argument, and it only holds while the motion stays below the threshold of
 * attention — which is why these take the better part of a minute to travel
 * a few percent of the viewport, and why nothing else here moves at all.
 *
 * TRANSFORM ONLY
 *
 * The two animated properties are `x` and `y`, so each layer composites on
 * the GPU and never triggers layout or paint. This sits behind every page in
 * the app, including one running a live WebSocket and a chat, so it has to
 * cost approximately nothing.
 */

// Slow, and deliberately not the same slow. Two loops of equal length drift
// in lockstep and the pair reads as one object sliding about; primes keep
// them out of phase for long enough that the field never repeats visibly.
const PRIMARY = { x: [0, "5%", "-3%", 0], y: [0, "-4%", "3%", 0], seconds: 47 };
const ACCENT = { x: [0, "-4%", "4%", 0], y: [0, "3%", "-3%", 0], seconds: 61 };

export default function Pattern() {
  // Respected rather than merely allowed for: somebody who has asked their
  // system for less motion is asking about this too, and a background is the
  // easiest thing in the app to hold still. The layers stay exactly where
  // they are, so the composition is unchanged — it simply stops drifting.
  const still = useReducedMotion();

  const drift = ({ x, y, seconds }) =>
    still
      ? {}
      : {
          animate: { x, y },
          transition: {
            duration: seconds,
            repeat: Infinity,
            ease: "easeInOut",
            // The keyframes end where they began, so the loop closes on
            // itself and there is no jump at the seam.
            times: [0, 0.33, 0.66, 1],
          },
        };

  return (
    <div className="pattern-backdrop" aria-hidden="true">
      <div className="pattern-base" />
      <motion.div
        className="pattern-glow pattern-glow--primary"
        {...drift(PRIMARY)}
      />
      <motion.div
        className="pattern-glow pattern-glow--accent"
        {...drift(ACCENT)}
      />
      <div className="pattern-grid" />
      <div className="pattern-vignette" />
    </div>
  );
}
