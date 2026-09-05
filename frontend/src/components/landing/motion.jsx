import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Box } from "@mui/material";
import { motion, useInView, useReducedMotion } from "motion/react";

/**
 * THE MOTION PRIMITIVES THE LANDING PAGE IS BUILT FROM.
 *
 * Three rules, and they are the difference between motion that reads as
 * craft and motion that reads as a template:
 *
 * NOTHING MOVES WITHOUT A REASON. Entrances orient you as you scroll and
 * connectors show direction of flow. Anything that would move for its own
 * sake has been left out, because a page where everything animates has no
 * way left to draw attention to the thing that matters.
 *
 * SPRINGS, NOT DURATIONS, wherever something is responding to you. A hover
 * that eases over 200ms feels like a video; a hover that springs feels like
 * an object. Entrances keep easing, because they are choreography rather
 * than response.
 *
 * IT MUST BE COMPLETE WITHOUT ANY OF IT. `prefers-reduced-motion` does not
 * degrade this page — it removes the animation and leaves the finished
 * layout. And where the browser cannot support the trigger at all, the
 * content renders revealed rather than hidden: an entrance that never runs
 * must not be able to hide a section permanently, which is the one failure
 * mode of scroll animation that actually costs anything.
 */

export const SPRING = { type: "spring", stiffness: 260, damping: 28, mass: 0.9 };
export const SOFT = { type: "spring", stiffness: 140, damping: 24 };
export const EASE = [0.16, 1, 0.3, 1];

const StaggerContext = createContext(0);

/**
 * Can this browser tell us when something scrolls into view?
 *
 * Everywhere real, yes. Where it cannot, every entrance below resolves to
 * "already shown" and the page renders complete — the same state a reader
 * with reduced motion gets.
 */
const CAN_OBSERVE =
  typeof window !== "undefined" && typeof IntersectionObserver !== "undefined";

/** Shared viewport options, so every entrance triggers on the same terms. */
const VIEWPORT = { once: true, amount: 0.15 };

/**
 * Should this render finished, with no animation at all?
 *
 * One answer for the whole page: the reader asked for reduced motion, or the
 * browser cannot tell us when something scrolls into view. The second half
 * matters most for the masked text — a line parked at y:108% behind a clip
 * is not merely un-animated, it is invisible, so an entrance that cannot
 * fire has to resolve to "already arrived" rather than "not yet".
 */
export function useFlat() {
  return useReducedMotion() || !CAN_OBSERVE;
}

/**
 * Scroll-triggered entrance.
 *
 * Once only: a section that re-animates on the way back up turns scrolling
 * into a slideshow, and the second viewing is never the one you wanted to
 * choreograph.
 */
export function Reveal({ children, delay = 0, y = 18, ...rest }) {
  const flat = useReducedMotion() || !CAN_OBSERVE;
  const inherited = useContext(StaggerContext);
  return (
    <motion.div
      initial={flat ? false : { opacity: 0, y }}
      whileInView={flat ? undefined : { opacity: 1, y: 0 }}
      viewport={VIEWPORT}
      transition={{ duration: 0.7, ease: EASE, delay: delay + inherited }}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

/**
 * Children arrive in sequence.
 *
 * Takes `sx` and renders as a real MUI Box so it can BE the grid or stack it
 * is orchestrating. That is not a convenience — it is one observer for a
 * whole group instead of one per cell, which is both cheaper and the
 * arrangement in which the items cannot desynchronise from each other.
 */
export function Stagger({ children, step = 0.07, start = 0, sx, mount = false, ...rest }) {
  const flat = useReducedMotion() || !CAN_OBSERVE;
  // `mount` for anything above the fold, which is already on screen when the
  // page loads and therefore never scrolls into view.
  const trigger = mount
    ? { animate: "shown" }
    : { whileInView: "shown", viewport: VIEWPORT };
  return (
    <Box
      component={motion.div}
      sx={sx}
      initial={flat ? false : "hidden"}
      {...(flat ? {} : trigger)}
      variants={{
        hidden: {},
        shown: { transition: { staggerChildren: step, delayChildren: start } },
      }}
      {...rest}
    >
      {children}
    </Box>
  );
}

export function Item({ children, y = 16, sx, ...rest }) {
  const flat = useReducedMotion() || !CAN_OBSERVE;
  return (
    <Box
      component={motion.div}
      sx={sx}
      variants={flat ? undefined : {
        hidden: { opacity: 0, y },
        shown: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE } },
      }}
      {...rest}
    >
      {children}
    </Box>
  );
}

/** A surface that lifts under the pointer. Spring, because it is a response. */
export function Lift({ children, lift = -3, ...rest }) {
  const flat = useReducedMotion();
  return (
    <motion.div
      whileHover={flat ? undefined : { y: lift }}
      transition={SPRING}
      style={{ height: "100%" }}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

/**
 * A number that counts up the first time it is seen.
 *
 * Only where the figure is genuinely a quantity that grew. A value the page
 * does not have yet renders as an em dash and never animates — counting to
 * a number nobody has fetched is how a placeholder becomes a claim. And the
 * resting state is the FINAL value rather than zero, so if the count never
 * runs the figure on screen is still the right one.
 */
export function Counter({ value, format = (n) => String(Math.round(n)), duration = 1.1 }) {
  const flat = useReducedMotion() || !CAN_OBSERVE;
  const ref = useRef(null);
  const seen = useInView(ref, { once: true, amount: 0.2 });
  const [shown, setShown] = useState(value ?? 0);

  useEffect(() => {
    if (value === null || value === undefined) return undefined;
    if (flat || !seen) {
      setShown(value);
      return undefined;
    }
    let raf;
    const started = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - started) / (duration * 1000));
      // The same shape as the entrances, so a number and the card holding
      // it settle together rather than one chasing the other.
      setShown(value * (1 - Math.pow(1 - t, 3)));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [seen, value, duration, flat]);

  return (
    <span ref={ref}>
      {value === null || value === undefined ? "—" : format(shown)}
    </span>
  );
}

export { motion, useReducedMotion };
