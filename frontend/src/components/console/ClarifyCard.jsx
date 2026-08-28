import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Box, Button, Stack, Typography } from "@mui/material";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import CheckIcon from "@mui/icons-material/Check";

/**
 * One question at a time, before any money moves.
 *
 * The stack slides vertically as you move between questions and the card's
 * height animates to fit, so the card never jumps to the tallest question's
 * size. Single-choice answers auto-advance; multi-select waits for Continue.
 *
 * The questions and every option come from the backend, derived from the
 * listings actually retrieved — this component renders what it is given and
 * invents nothing. If the result set had one condition and no repeated
 * brand, only the quantity question arrives, and that is what shows.
 *
 * Skipping is a first-class answer: the run continues with the results
 * unnarrowed rather than stalling on a question nobody wanted.
 */

const SLIDE = "360ms cubic-bezier(0.22, 1, 0.36, 1)";
const ROLL_MS = 380;

/** Odometer digits — only the characters that change roll. */
function RollingDigits({ value }) {
  const previous = useRef(value);
  const [older, setOlder] = useState(value);
  const [rolling, setRolling] = useState(false);
  const [shifted, setShifted] = useState(false);

  useEffect(() => {
    if (previous.current === value) return;
    const from = previous.current;
    previous.current = value;
    setOlder(from);
    setRolling(true);
    setShifted(false);

    let second = 0;
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => setShifted(true));
    });
    const done = setTimeout(() => {
      setRolling(false);
      setOlder(value);
      setShifted(false);
    }, ROLL_MS);

    return () => {
      cancelAnimationFrame(first);
      cancelAnimationFrame(second);
      clearTimeout(done);
    };
  }, [value]);

  const chars = rolling ? value : older;

  return (
    <>
      {Array.from({ length: chars.length }, (_, i) => {
        const before = older[i] ?? "";
        const after = chars[i] ?? "";
        if (!rolling || before === after) return <span key={`${i}-${after}`}>{after}</span>;
        return (
          <Box
            key={`${i}-${before}-${after}`}
            component="span"
            sx={{
              display: "inline-block", position: "relative", overflow: "hidden",
              height: "1em", lineHeight: "1em", verticalAlign: "-0.05em",
            }}
          >
            <Box
              component="span"
              sx={{
                display: "flex", flexDirection: "column",
                transition: "transform 350ms cubic-bezier(0.4,0,0.2,1)",
                transform: `translateY(${shifted ? "-1em" : "0"})`,
              }}
            >
              <span style={{ height: "1em", lineHeight: "1em" }}>{before}</span>
              <span style={{ height: "1em", lineHeight: "1em" }}>{after}</span>
            </Box>
          </Box>
        );
      })}
    </>
  );
}

export default function ClarifyCard({ questions = [], candidateCount, onSubmit, onSkip }) {
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [typed, setTyped] = useState({});

  const advanceTimer = useRef(null);
  const questionRefs = useRef([]);
  const measured = useRef(false);
  const [viewportHeight, setViewportHeight] = useState(undefined);
  const [trackY, setTrackY] = useState(0);
  const [animate, setAnimate] = useState(false);
  const [ready, setReady] = useState(false);

  const last = index === questions.length - 1;
  const current = questions[index];
  const picked = answers[current?.id] ?? [];
  // A typed answer counts. An open question with nothing in it is also a
  // valid answer — "no preference" — so Continue stays live for those.
  const hasAnswer = current?.type === "text" ? true : picked.length > 0;

  const sync = (withAnimation) => {
    const node = questionRefs.current[index];
    if (!node) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    setViewportHeight(node.offsetHeight);
    setTrackY(node.offsetTop);
    setAnimate(withAnimation && !reduce);
  };

  useLayoutEffect(() => {
    const withAnimation = measured.current;
    measured.current = true;
    sync(withAnimation);
    setReady(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, answers]);

  useEffect(() => () => clearTimeout(advanceTimer.current), []);

  const goTo = (next) => {
    clearTimeout(advanceTimer.current);
    setIndex(Math.min(Math.max(next, 0), questions.length - 1));
  };

  // Answering unmounts this card — the run resumes and the transcript takes
  // over — so there is no "sent" state to render here.
  const send = (payload) => {
    clearTimeout(advanceTimer.current);
    onSubmit?.(payload ?? answers);
  };

  const advance = () => (last ? send() : goTo(index + 1));

  const toggle = (option) => {
    const question = questions[index];
    let nextAnswers;
    setTyped((state) => ({ ...state, [question.id]: "" }));
    setAnswers((state) => {
      const chosen = state[question.id] ?? [];
      const next =
        question.type === "radio"
          ? [option.value]
          : chosen.includes(option.value)
            ? chosen.filter((v) => v !== option.value)
            : [...chosen, option.value];
      nextAnswers = { ...state, [question.id]: next };
      return nextAnswers;
    });

    if (question.type === "radio") {
      clearTimeout(advanceTimer.current);
      advanceTimer.current = setTimeout(() => {
        // The last radio answer submits, and it has to carry the value the
        // click just produced — reading state here would send the previous
        // answer set, because this fires before the re-render settles.
        if (last) send(nextAnswers);
        else setIndex((i) => Math.min(questions.length - 1, i + 1));
      }, 420);
    }
  };

  if (!questions.length) return null;

  return (
    <Box
      sx={{
        maxWidth: 380, my: 1.5,
        border: "1px solid", borderColor: "divider",
        borderRadius: 2.5, bgcolor: "background.paper", overflow: "hidden",
      }}
    >
      <Box sx={{ p: 2 }}>
        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 1.25 }}>
          Before I spend anything — {candidateCount} listings found
        </Typography>

        <Box
          sx={{ overflow: "hidden", height: viewportHeight,
                transition: animate ? `height ${SLIDE}` : undefined }}
          aria-live="polite"
        >
          <Box
            sx={{
              display: "flex", flexDirection: "column", gap: "26px",
              transform: `translate3d(0, ${-trackY}px, 0)`,
              transition: animate ? `transform ${SLIDE}` : undefined,
              willChange: "transform",
            }}
          >
            {questions.map((question, qIndex) => {
              const active = qIndex === index;
              // Before the first measure only the active question mounts, so
              // the card opens at its real height instead of flashing to the
              // full stack height and shrinking.
              if (!ready && !active) return null;
              const chosen = answers[question.id] ?? [];

              return (
                <Box
                  key={question.id}
                  ref={(el) => { questionRefs.current[qIndex] = el; }}
                  aria-hidden={active ? undefined : true}
                  sx={{
                    opacity: active ? 1 : 0,
                    transition: animate ? `opacity ${SLIDE}` : undefined,
                    pointerEvents: active ? undefined : "none",
                  }}
                >
                  <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5, mb: 1.25 }}>
                    {question.question}
                  </Typography>

                  {question.type === "text" ? (
                    <Box
                      component="input"
                      type="text"
                      value={chosen[0] ?? ""}
                      placeholder={question.placeholder ?? ""}
                      tabIndex={active ? 0 : -1}
                      onChange={(e) =>
                        setAnswers((state) => ({
                          ...state,
                          [question.id]: e.target.value ? [e.target.value] : [],
                        }))
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          advance();
                        }
                      }}
                      sx={{
                        width: "100%",
                        px: 1.25,
                        py: 1,
                        fontSize: 13,
                        fontFamily: "inherit",
                        color: "text.primary",
                        bgcolor: "rgba(255,255,255,0.04)",
                        border: "1px solid",
                        borderColor: "divider",
                        borderRadius: 1.5,
                        outline: "none",
                        "&:focus": { borderColor: "rgba(255,255,255,0.28)" },
                        "&::placeholder": { color: "text.disabled" },
                      }}
                    />
                  ) : (
                  <Stack spacing={0.25}>
                    {question.options.map((option) => {
                      const on = chosen.includes(option.value);
                      return (
                        <Box
                          key={option.value}
                          component="button"
                          type="button"
                          aria-pressed={on}
                          tabIndex={active ? 0 : -1}
                          onClick={() => active && toggle(option)}
                          sx={{
                            display: "flex", alignItems: "center", gap: 1,
                            width: "100%", textAlign: "left",
                            px: 0.75, py: 0.75, borderRadius: 1.5,
                            border: "none", bgcolor: "transparent", cursor: "pointer",
                            "&:hover": { bgcolor: "rgba(255,255,255,0.05)" },
                          }}
                        >
                          <Box
                            sx={{
                              width: 16, height: 16, flexShrink: 0,
                              display: "flex", alignItems: "center", justifyContent: "center",
                              borderRadius: question.type === "radio" ? "50%" : "5px",
                              bgcolor: on ? "#ECECEE" : "transparent",
                              boxShadow: on ? "none" : "inset 0 0 0 1.5px rgba(255,255,255,0.28)",
                              transition: "background-color 180ms",
                            }}
                          >
                            {question.type === "radio" ? (
                              <Box
                                sx={{
                                  width: 6, height: 6, borderRadius: "50%", bgcolor: "#0A0A0B",
                                  transform: on ? "scale(1)" : "scale(0)",
                                  transition: "transform 180ms",
                                }}
                              />
                            ) : (
                              <CheckIcon
                                sx={{ fontSize: 11, color: on ? "#0A0A0B" : "transparent" }}
                              />
                            )}
                          </Box>

                          <Typography
                            variant="body2"
                            sx={{ fontSize: 13, flex: 1, minWidth: 0,
                                  color: on ? "text.primary" : "text.secondary" }}
                          >
                            {option.label}
                          </Typography>

                          {option.count != null && (
                            <Typography
                              variant="caption"
                              sx={{ color: "text.disabled", fontSize: 11,
                                    fontVariantNumeric: "tabular-nums" }}
                            >
                              {option.count}
                            </Typography>
                          )}
                        </Box>
                      );
                    })}
                  </Stack>
                  )}

                  {/* Pick one, or say something the list does not cover.
                      Typing clears the selection and selecting clears the
                      text, so exactly one answer leaves here. */}
                  {question.allow_text && question.type !== "text" && (
                    <Box
                      component="input"
                      type="text"
                      value={typed[question.id] ?? ""}
                      placeholder={question.placeholder ?? "or type an answer"}
                      tabIndex={active ? 0 : -1}
                      onChange={(e) => {
                        const value = e.target.value;
                        setTyped((state) => ({ ...state, [question.id]: value }));
                        setAnswers((state) => ({
                          ...state,
                          [question.id]: value ? [value] : [],
                        }));
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          advance();
                        }
                      }}
                      sx={{
                        width: "100%",
                        mt: 0.75,
                        px: 1.25,
                        py: 0.85,
                        fontSize: 13,
                        fontFamily: "inherit",
                        color: "text.primary",
                        bgcolor: "rgba(255,255,255,0.04)",
                        border: "1px solid",
                        borderColor: "divider",
                        borderRadius: 1.5,
                        outline: "none",
                        "&:focus": { borderColor: "rgba(255,255,255,0.28)" },
                        "&::placeholder": { color: "text.disabled" },
                      }}
                    />
                  )}

                  {question.note && (
                    <Typography
                      variant="caption"
                      sx={{ color: "text.disabled", display: "block", mt: 1, fontSize: 11 }}
                    >
                      {question.note}
                    </Typography>
                  )}
                </Box>
              );
            })}
          </Box>
        </Box>
      </Box>

      <Stack
        direction="row"
        sx={{
          alignItems: "center", justifyContent: "space-between",
          px: 1.5, py: 1, borderTop: "1px solid", borderColor: "divider",
        }}
      >
        <Stack direction="row" spacing={0.5} sx={{ alignItems: "center", color: "text.disabled" }}>
          <Box
            component="button"
            type="button"
            aria-label="Previous question"
            disabled={index <= 0}
            onClick={() => goTo(index - 1)}
            sx={{
              display: "flex", border: "none", bgcolor: "transparent",
              color: "inherit", cursor: "pointer", p: 0.25, borderRadius: 1,
              "&:disabled": { opacity: 0.3, cursor: "default" },
              "&:hover:not(:disabled)": { color: "text.primary" },
            }}
          >
            <KeyboardArrowUpIcon sx={{ fontSize: 15 }} />
          </Box>

          <Typography
            variant="caption"
            sx={{ fontSize: 11.5, fontWeight: 600, fontVariantNumeric: "tabular-nums", lineHeight: 1 }}
          >
            <RollingDigits value={`${index + 1} / ${questions.length}`} />
          </Typography>

          <Box
            component="button"
            type="button"
            aria-label="Next question"
            disabled={last}
            onClick={() => goTo(index + 1)}
            sx={{
              display: "flex", border: "none", bgcolor: "transparent",
              color: "inherit", cursor: "pointer", p: 0.25, borderRadius: 1,
              "&:disabled": { opacity: 0.3, cursor: "default" },
              "&:hover:not(:disabled)": { color: "text.primary" },
            }}
          >
            <KeyboardArrowDownIcon sx={{ fontSize: 15 }} />
          </Box>
        </Stack>

        <Stack direction="row" spacing={1}>
          <Button
            size="small"
            onClick={onSkip}
            sx={{ color: "text.secondary", fontSize: 12 }}
          >
            Skip
          </Button>
          <Button
            size="small"
            variant="contained"
            disabled={!hasAnswer}
            onClick={advance}
            sx={{ fontSize: 12, boxShadow: "none", "&:hover": { boxShadow: "none" } }}
          >
            {last ? "Search" : "Continue"}
          </Button>
        </Stack>
      </Stack>
    </Box>
  );
}
