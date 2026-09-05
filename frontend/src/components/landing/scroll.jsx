import { useLayoutEffect, useRef, useState } from "react";
import { Box } from "@mui/material";
import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "motion/react";

import { EASE, useFlat } from "./motion";

/** `h1`/`h2`/... as a motion component, so a heading can drive its own lines. */
const motionTag = (tag) => motion[tag] || motion.h2;

/**
 * SCROLL-LINKED MOTION.
 *
 * The entrances elsewhere on this page are one-shot: a thing fades up as it
 * arrives and then it is done. That is the right treatment for a card, and
 * it is almost invisible on a hero — the reader is looking at the hero
 * before any of it has had a chance to happen.
 *
 * These two are different in kind. They are tied to scroll POSITION rather
 * than triggered by it, so the page responds continuously while you move
 * and stops the moment you do. That is what makes a page feel like a
 * surface rather than a slideshow, and it is the only motion here you can
 * actually steer.
 *
 * WHY THE CONTAINER HAS TO BE FOUND
 *
 * This app scrolls inside a pane, not the window. `useScroll` watching the
 * window would sit at progress 0 forever and nothing would move at all —
 * so the nearest genuinely scrollable ancestor is resolved on mount and
 * handed over. `overflowX: hidden` computes `overflowY` to `auto` on the
 * same element, so a candidate also has to have somewhere to scroll to
 * before it counts.
 */
function useScrollContainer() {
  const anchor = useRef(null);
  const container = useRef(null);
  const [, setResolved] = useState(0);

  useLayoutEffect(() => {
    let node = anchor.current?.parentElement;
    while (node && node !== document.body) {
      const overflow = getComputedStyle(node).overflowY;
      const scrolls = node.scrollHeight > node.clientHeight + 1;
      if ((overflow === "auto" || overflow === "scroll") && scrolls) {
        container.current = node;
        setResolved((n) => n + 1);
        return;
      }
      node = node.parentElement;
    }
    container.current = null;
    setResolved((n) => n + 1);
  }, []);

  return [anchor, container];
}

/**
 * THE HERO, PUSHED BACK AS YOU LEAVE IT.
 *
 * Scale and fade tied to how far the hero has travelled up the screen. It
 * reads as depth: the diagram recedes rather than scrolling away flat, and
 * the section arriving underneath feels like it is coming forward.
 *
 * Scaling DOWN on exit rather than up, which is the opposite of the usual
 * "zoom on scroll" treatment and the reason this one does not feel like a
 * screensaver — something growing as it leaves fights the direction you are
 * moving, and every reader feels that even if they cannot name it.
 *
 * The spring on progress is what stops it feeling mechanically welded to
 * the wheel. Without it, a trackpad flick makes the whole hero twitch.
 */
export function ScrollZoom({ children, from = 1, to = 0.94, fade = 0.35, sx }) {
  const flat = useReducedMotion();
  const [anchor, container] = useScrollContainer();

  const { scrollYProgress } = useScroll({
    target: anchor,
    container,
    // From the moment the block sits at the top of the pane, to the moment
    // its bottom edge has left it.
    offset: ["start start", "end start"],
  });

  const eased = useSpring(scrollYProgress, {
    stiffness: 140, damping: 30, restDelta: 0.001,
  });

  const scale = useTransform(eased, [0, 1], [from, to]);
  const opacity = useTransform(eased, [0, 1], [1, fade]);
  const y = useTransform(eased, [0, 1], [0, -28]);

  return (
    <Box
      component={motion.div}
      ref={anchor}
      sx={sx}
      style={flat ? undefined : { scale, opacity, y, transformOrigin: "50% 0%" }}
    >
      {children}
    </Box>
  );
}

/**
 * A HEADLINE THAT ARRIVES A LINE AT A TIME.
 *
 * Each line rises out of the one below it, clipped so it appears from behind
 * a hard edge rather than fading in place. The clip is what makes this read
 * as typesetting rather than as a fade — text that fades looks like it is
 * loading, text that slides out from a mask looks like it was placed.
 *
 * The lines are given, not measured. Splitting rendered text by where the
 * browser happens to wrap means the break moves with the viewport and a
 * line can be masked mid-word; an author choosing the breaks gets a
 * headline that reads correctly at every width, which is the entire reason
 * to set a headline in lines in the first place.
 */
export function ScrollLines({
  lines, component = "h2", sx, lineSx, stagger = 0.09, y = "108%",
  mount = false, delay = 0,
}) {
  // `lineSx` may be a function of the line index. It has to be: a line is the
  // only child of its own clip wrapper, so a selector like `&:last-of-type`
  // matches EVERY line rather than the last one — which is how a gradient
  // meant for the closing line ended up painting `-webkit-text-fill-color:
  // transparent` onto a line with no gradient behind it, rendering it
  // invisible. An index is unambiguous; a positional selector here is not.
  const styleFor = (i) =>
    (typeof lineSx === "function" ? lineSx(i, lines.length) : lineSx) || null;

  // Reduced motion always wins. A missing observer only matters for the
  // scroll-triggered case: a masked line parked at y:108% behind a clip is
  // invisible rather than merely static, so an entrance that can never fire
  // must resolve to "already arrived".
  const reduced = useReducedMotion();
  const needsObserver = useFlat();
  const flat = reduced || (!mount && needsObserver);

  // Above the fold there is nothing to scroll into view, so the hero plays on
  // mount instead. Without this the first thing a reader sees is the only
  // thing that never moves.
  const trigger = mount
    ? { animate: "shown" }
    : { whileInView: "shown", viewport: { once: true, amount: 0.4 } };

  return (
    // THE OBSERVER GOES HERE, ON THE HEADING — never on the lines.
    //
    // IntersectionObserver intersects an element's rect with the clip rect of
    // every ancestor before reporting a ratio. A line translated to y:108%
    // inside `clip-path: inset(...)` is therefore reported at ratio 0, so a
    // `whileInView` sitting on the line itself can never reach its threshold:
    // it stays hidden because it is hidden. That deadlock is why section
    // headlines rendered as blank space holding their own height while the
    // eyebrow and the lede around them appeared normally.
    //
    // The heading is not transformed and not clipped, so it is observable.
    // It drives the lines through variants, which also means one observer per
    // headline instead of one per line, and lines that cannot desynchronise.
    <Box
      component={motionTag(component)}
      sx={{ m: 0, ...sx }}
      initial={flat ? false : "hidden"}
      {...(flat ? {} : trigger)}
      variants={{
        hidden: {},
        shown: { transition: { staggerChildren: stagger, delayChildren: delay } },
      }}
    >
      {lines.map((line, i) => (
        <Box
          key={line}
          // The mask. `clip-path` rather than `overflow: hidden` so a
          // descender is never shaved off the line above it.
          sx={{
            display: "block",
            clipPath: flat ? "none" : "inset(-18% 0% -12% 0%)",
          }}
        >
          <Box
            component={motion.span}
            sx={{ display: "block" }}
            variants={flat ? undefined : {
              hidden: { y, opacity: 0 },
              shown: { y: "0%", opacity: 1,
                       transition: { duration: 0.85, ease: EASE } },
            }}
          >
            {/* Appearance goes on a STATIC inner span, never on the animating
                one. `background-clip: text` painted onto an element that is
                being transformed inside a clip-path gets composited onto its
                own layer, and Chrome drops the clipped background when it
                does — the glyphs come out fully transparent and the headline
                silently disappears. Separating movement from paint means the
                text cannot be lost to a compositing decision. */}
            <Box component="span" sx={{ display: "block", ...styleFor(i) }}>
              {line}
            </Box>
          </Box>
        </Box>
      ))}
    </Box>
  );
}
