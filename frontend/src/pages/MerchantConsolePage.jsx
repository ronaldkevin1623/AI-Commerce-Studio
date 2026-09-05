import { useCallback, useEffect, useRef, useState } from "react";
import {
  Box, Button, Chip, CircularProgress, IconButton, InputBase, Stack,
  Tooltip, Typography,
} from "@mui/material";
import { Link } from "react-router-dom";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import ImageOutlinedIcon from "@mui/icons-material/ImageOutlined";
import CloseIcon from "@mui/icons-material/Close";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlineOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";

import { API_BASE } from "../config";
import { useVoice } from "../hooks/useVoice";
import { MicButton, SpeakToggle } from "../components/shared/VoiceControls";
import { compress } from "../components/merchant/MediaUpload";
import TypedPlaceholder from "../components/shared/TypedPlaceholder";

// Real things this agent can do — the reports it routes to and the actions
// it can perform. A placeholder that suggested something it cannot answer
// would be teaching the merchant to distrust it on their first message.
const MERCHANT_PROMPTS = [
  "add a product from a photo",
  "compare this month to last month",
  "find me an opportunity to increase revenue",
  "show me what is going wrong",
  "tell me which products are selling",
  "give me a detailed report on revenue growth",
];

/**
 * THE MERCHANT COMMAND CENTRE.
 *
 * The customer side of this app takes a sentence and turns it into a
 * transaction. This takes a sentence from the shop owner and turns it into
 * an analysis — the same growth agents, relationship graph and attribution
 * report that live on their own pages, run against a question and reported
 * back as one answer.
 *
 * That symmetry is the point worth making: both sides of the counter get an
 * agent, and both agents are bounded by the same kind of gate.
 *
 * EVERY ANSWER HAS THREE PARTS, AND THE THIRD IS THE UNUSUAL ONE
 *
 *     findings   what is true, with the evidence and how much of it there is
 *     actions    what could be done, priced, with the gate's verdict already on it
 *     limits     what this could NOT determine, and why
 *
 * Most revenue reports stop after the first two. A recommendation whose
 * weaknesses are invisible is not advice, it is a pitch — and on a shop this
 * size the weaknesses are the most important thing on the screen.
 */

const CARD = {
  border: "1px solid",
  borderColor: "divider",
  borderRadius: 2.5,
  bgcolor: "background.paper",
  p: 2,
};

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const VERDICT = {
  allowed: { colour: "#4ADE80", label: "Within bounds", Icon: CheckCircleOutlineIcon },
  escalated: { colour: "#FBBF24", label: "Needs you", Icon: ErrorOutlineIcon },
  blocked: { colour: "#F87171", label: "Blocked", Icon: LockOutlinedIcon },
};

const STRENGTH = {
  observed: { colour: "#4ADE80", label: "observed" },
  thin: { colour: "#FBBF24", label: "thin evidence" },
  gate: { colour: "#7DD3FC", label: "the gate" },
};

function Finding({ finding }) {
  const tone = STRENGTH[finding.strength] ?? STRENGTH.observed;
  return (
    <Box sx={{ pl: 1.75, borderLeft: "2px solid", borderColor: tone.colour, py: 0.25 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", flexWrap: "wrap" }}>
        <Typography variant="body2" sx={{ fontSize: 13.5, fontWeight: 600 }}>
          {finding.headline}
        </Typography>
        <Typography variant="caption"
                    sx={{ fontSize: 10, color: tone.colour, textTransform: "uppercase",
                          letterSpacing: 0.5, fontWeight: 700 }}>
          {tone.label}
        </Typography>
      </Stack>
      <Typography variant="body2"
                  sx={{ fontSize: 13, color: "text.secondary", lineHeight: 1.7, mt: 0.5 }}>
        {finding.detail}
      </Typography>
      {finding.evidence && (
        <Typography variant="caption"
                    sx={{ display: "block", color: "text.disabled", mt: 0.5, fontSize: 11 }}>
          Evidence: {finding.evidence}
        </Typography>
      )}
    </Box>
  );
}

function Action({ action }) {
  const verdict = VERDICT[action.verdict] ?? VERDICT.blocked;
  return (
    <Box sx={{ ...CARD, p: 1.75, bgcolor: "rgba(255,255,255,0.018)" }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start", mb: 0.75 }}>
        <Typography variant="body2"
                    sx={{ fontSize: 13, fontWeight: 600, flex: 1, minWidth: 0 }}>
          {action.headline}
        </Typography>
        <Stack direction="row" spacing={0.5}
               sx={{ alignItems: "center", flexShrink: 0, color: verdict.colour }}>
          <verdict.Icon sx={{ fontSize: 14 }} />
          <Typography variant="caption" sx={{ fontSize: 10.5, fontWeight: 700 }}>
            {verdict.label}
          </Typography>
        </Stack>
      </Stack>

      <Stack direction="row" spacing={0.75} sx={{ mb: 1, flexWrap: "wrap", gap: 0.75 }}>
        <Chip size="small" label={action.agent}
              sx={{ height: 19, fontSize: 10, bgcolor: "rgba(255,255,255,0.07)" }} />
        <Chip
          size="small"
          label={action.cost_paise ? `Costs ${inr(action.cost_paise)} of margin` : "Costs nothing"}
          sx={{ height: 19, fontSize: 10,
                bgcolor: action.cost_paise ? "rgba(251,191,36,0.14)" : "rgba(255,255,255,0.07)",
                color: action.cost_paise ? "#FBBF24" : "text.secondary" }}
        />
        <Chip
          size="small"
          label={`${action.sample_size} observation${action.sample_size === 1 ? "" : "s"}`}
          sx={{ height: 19, fontSize: 10, bgcolor: "rgba(255,255,255,0.07)" }}
        />
      </Stack>

      <Typography variant="body2"
                  sx={{ fontSize: 12.5, color: "text.secondary", lineHeight: 1.65 }}>
        {action.detail}
      </Typography>

      {/* The gate's own words, not a paraphrase. Whatever this screen says
          about an action, the sentence that decided it is the one the audit
          trail will show. */}
      <Typography variant="caption"
                  sx={{ display: "block", mt: 1, color: verdict.colour, lineHeight: 1.6,
                        fontSize: 11 }}>
        Gate: {action.verdict_reason}
      </Typography>
    </Box>
  );
}

/**
 * A section of a structured report.
 *
 * Two shapes, because two shapes is what the reports actually produce and a
 * generic renderer that handles nine would mostly be handling none of them
 * well. `metrics` is a headline row with changes; `table` is everything else.
 */
function Section({ section }) {
  return (
    <Box>
      <Typography variant="body2" sx={{ fontWeight: 700, fontSize: 13, mb: 0.5 }}>
        {section.title}
      </Typography>
      {section.note && (
        <Typography variant="caption"
                    sx={{ display: "block", color: "text.disabled", mb: 1.25,
                          lineHeight: 1.65, fontSize: 11 }}>
          {section.note}
        </Typography>
      )}

      {section.kind === "metrics" && (
        <Box sx={{ display: "grid", gap: 1.5,
                   gridTemplateColumns: { xs: "1fr 1fr", sm: "repeat(4, 1fr)" } }}>
          {section.rows.map((row) => (
            <Box key={row.label}
                 sx={{ px: 1.5, py: 1.25, borderRadius: 1.5, border: "1px solid",
                       borderColor: "divider", bgcolor: "rgba(255,255,255,0.02)" }}>
              <Typography variant="caption"
                          sx={{ color: "text.secondary", display: "block", fontSize: 10.5 }}>
                {row.label}
              </Typography>
              <Typography sx={{ fontSize: 16, fontWeight: 700, mt: 0.25,
                                fontVariantNumeric: "tabular-nums" }}>
                {row.value}
              </Typography>
              <Typography variant="caption"
                          sx={{ fontSize: 10.5,
                                color: row.delta?.startsWith("+") ? "#4ADE80"
                                  : row.delta?.startsWith("-") ? "#F87171"
                                  : "text.disabled" }}>
                {row.delta}
              </Typography>
              {row.note && (
                <Typography variant="caption"
                            sx={{ display: "block", color: "text.disabled",
                                  fontSize: 10, mt: 0.25, lineHeight: 1.5 }}>
                  {row.note}
                </Typography>
              )}
            </Box>
          ))}
        </Box>
      )}

      {section.kind === "table" && (
        <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1.5,
                   overflowX: "auto" }}>
          <Box component="table"
               sx={{ width: "100%", borderCollapse: "collapse", minWidth: 380 }}>
            <Box component="thead">
              <Box component="tr">
                {section.columns.map((column, i) => (
                  <Box component="th" key={column}
                       sx={{ textAlign: i === 0 ? "left" : "right",
                             px: 1.5, py: 1, fontSize: 10.5, fontWeight: 700,
                             letterSpacing: 0.4, color: "text.disabled",
                             textTransform: "uppercase",
                             borderBottom: "1px solid", borderColor: "divider" }}>
                    {column}
                  </Box>
                ))}
              </Box>
            </Box>
            <Box component="tbody">
              {section.rows.map((row, r) => (
                <Box component="tr" key={r}>
                  {row.map((cell, c) => (
                    <Box component="td" key={c}
                         sx={{ textAlign: c === 0 ? "left" : "right",
                               px: 1.5, py: 1, fontSize: 12,
                               color: c === 0 ? "text.primary" : "text.secondary",
                               fontVariantNumeric: c === 0 ? undefined : "tabular-nums",
                               borderTop: r === 0 ? "none" : "1px solid",
                               borderColor: "rgba(255,255,255,0.05)" }}>
                      {cell}
                    </Box>
                  ))}
                </Box>
              ))}
            </Box>
          </Box>
        </Box>
      )}
    </Box>
  );
}

function Answer({ answer }) {
  return (
    <Box sx={{ ...CARD, p: 2.5 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.5 }}>
        <AutoAwesomeIcon sx={{ fontSize: 16, color: "#7DD3FC" }} />
        <Typography variant="caption"
                    sx={{ fontSize: 10.5, letterSpacing: 0.6, fontWeight: 700,
                          color: "text.secondary", textTransform: "uppercase" }}>
          Growth agent
        </Typography>
        <Box sx={{ flex: 1 }} />
        {answer.window && (
          <Typography variant="caption" sx={{ color: "text.disabled", fontSize: 10.5 }}>
            {answer.window.label} · {answer.window.from} to {answer.window.to}
          </Typography>
        )}
      </Stack>

      <Typography variant="body1"
                  sx={{ fontSize: 15, lineHeight: 1.75, mb: answer.findings?.length ? 2.5 : 0 }}>
        {answer.summary}
      </Typography>

      {answer.sections?.length > 0 && (
        <Stack spacing={2.5} sx={{ mb: 2.5 }}>
          {answer.sections.map((section, i) => <Section key={i} section={section} />)}
        </Stack>
      )}

      {answer.findings?.length > 0 && (
        <Stack spacing={2} sx={{ mb: 2.5 }}>
          {answer.findings.map((finding, i) => <Finding key={i} finding={finding} />)}
        </Stack>
      )}

      {answer.actions?.length > 0 && (
        <>
          <Typography variant="caption"
                      sx={{ display: "block", mb: 1.25, fontSize: 10.5, fontWeight: 700,
                            letterSpacing: 0.6, color: "text.disabled",
                            textTransform: "uppercase" }}>
            What I would do — {answer.actions.length} action
            {answer.actions.length === 1 ? "" : "s"}, none of them applied
          </Typography>
          <Stack spacing={1.25} sx={{ mb: 2.5 }}>
            {answer.actions.map((action, i) => <Action key={i} action={action} />)}
          </Stack>
        </>
      )}

      {answer.limits?.length > 0 && (
        <Box sx={{ p: 1.75, borderRadius: 2, bgcolor: "rgba(255,255,255,0.025)",
                   border: "1px solid", borderColor: "divider" }}>
          <Typography variant="caption"
                      sx={{ display: "block", mb: 0.75, fontSize: 10.5, fontWeight: 700,
                            letterSpacing: 0.6, color: "text.disabled",
                            textTransform: "uppercase" }}>
            What I could not determine
          </Typography>
          <Stack spacing={0.75}>
            {answer.limits.map((limit, i) => (
              <Typography key={i} variant="caption"
                          sx={{ color: "text.secondary", lineHeight: 1.7, fontSize: 11.5 }}>
                {limit}
              </Typography>
            ))}
          </Stack>
        </Box>
      )}

      {answer.suggestions?.length > 0 && answer.intent === "unknown" && (
        <Stack spacing={0.5} sx={{ mt: 1.5 }}>
          {answer.suggestions.map((s) => (
            <Typography key={s} variant="caption"
                        sx={{ color: "text.secondary", fontSize: 12 }}>
              · {s}
            </Typography>
          ))}
        </Stack>
      )}

      {answer.links?.length > 0 && (
        <Stack direction="row" spacing={1} sx={{ mt: 2, flexWrap: "wrap", gap: 1 }}>
          {answer.links.map((link) => (
            <Button
              key={link.to}
              size="small"
              variant="outlined"
              component={Link}
              to={link.to}
              endIcon={<ArrowForwardIcon sx={{ fontSize: 14 }} />}
              sx={{ textTransform: "none", fontSize: 12, borderColor: "divider" }}
            >
              {link.label}
            </Button>
          ))}
        </Stack>
      )}
    </Box>
  );
}

export default function MerchantConsolePage() {
  const [text, setText] = useState("");
  const [turns, setTurns] = useState([]);
  const [busy, setBusy] = useState(false);

  // ── Voice ─────────────────────────────────────────────────────────────
  // Dictation writes into the same `text` state the keyboard does, so the
  // question takes the identical path to the agent either way — there is no
  // second, voice-shaped code path that could behave differently.
  const [readAloud, setReadAloud] = useState(false);
  const voice = useVoice({
    onTranscript: (heard) => setText(heard),
  });
  // Destructured because `voice` is a new object every render while `speak`
  // is a stable useCallback — depending on the object would rebuild `ask`
  // on every keystroke, depending on nothing at all left it stale.
  const { speak } = voice;

  // A photo waiting to be sent with the next message, and an action the
  // agent is still collecting fields for. `pending` comes straight back
  // from the reply — the half-built product lives in this tab and nowhere
  // else, so closing it abandons the action rather than leaving something
  // half-made on the server.
  const [photo, setPhoto] = useState(null);
  const [pending, setPending] = useState(null);
  const [attachError, setAttachError] = useState(null);
  const bottom = useRef(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy]);

  const ask = useCallback(async (question) => {
    const asked = (question ?? "").trim();
    if (!asked || busy) return;
    setText("");
    setBusy(true);
    setTurns((prev) => [...prev, { question: asked }]);
    try {
      const res = await fetch(`${API_BASE}/merchant/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: asked, image: photo, pending }),
      });
      if (!res.ok) throw new Error(`Store returned ${res.status}`);
      const answer = await res.json();
      // The SUMMARY only. Reading a whole report aloud — every table row,
      // every caveat — is unusable, and truncating a financial figure mid
      // sentence is worse than not speaking it at all.
      if (readAloud && answer?.summary) speak(answer.summary);
      // The agent says whether it still needs something. Null clears it,
      // so a finished action cannot leak into the next question.
      setPending(answer?.pending ?? null);
      setPhoto(null);
      setTurns((prev) => {
        const next = [...prev];
        next[next.length - 1] = { question: asked, answer };
        return next;
      });
    } catch (err) {
      setTurns((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          question: asked,
          answer: {
            intent: "error",
            summary: `I could not reach the shop's records: ${err.message ?? err}`,
            findings: [], actions: [], limits: [], links: [],
          },
        };
        return next;
      });
    } finally {
      setBusy(false);
    }
    // `readAloud` and `speak` belong here. Without them `ask` kept the
    // values from the render where `busy` last changed — readAloud was
    // false at mount, toggling it never changed `busy`, so the answer was
    // never spoken and the toggle looked dead.
  }, [busy, readAloud, speak, photo, pending]);

  const empty = turns.length === 0;

  return (
    <Box sx={{ px: 3, py: 4, maxWidth: 940, mx: "auto" }}>
      {empty && (
        <Box sx={{ textAlign: "center", mb: 4 }}>
          <Stack direction="row" spacing={1.25}
                 sx={{ alignItems: "center", justifyContent: "center", mb: 1.5 }}>
            <AutoAwesomeIcon sx={{ fontSize: 26, color: "#7DD3FC" }} />
            <Typography sx={{ fontSize: 30, fontWeight: 700, letterSpacing: "-0.02em" }}>
              Welcome back — what should I look into?
            </Typography>
          </Stack>
          <Typography variant="body2"
                      sx={{ color: "text.secondary", maxWidth: 620, mx: "auto",
                            lineHeight: 1.75 }}>
            Ask about revenue, performance, products, customers or what is going wrong.
            I answer from this shop's own orders, checkouts and decision log — every
            figure is computed, and I will tell you what I could not work out.
          </Typography>
        </Box>
      )}

      {/* ── the prompt ───────────────────────────────────────────────── */}
      <Box
        component="form"
        onSubmit={(e) => { e.preventDefault(); ask(text); }}
        sx={{ ...CARD, p: 1.5, mb: 2.5, position: "sticky", top: 0, zIndex: 2 }}
      >
        {(photo || pending || attachError) && (
          <Stack
            direction="row"
            spacing={1}
            sx={{ alignItems: "center", px: 1, pb: 1, flexWrap: "wrap" }}
          >
            {photo && (
              // THE PICTURE ITSELF, SMALL.
              //
              // "Photo attached" is a claim the merchant has to take on
              // trust; a thumbnail is the thing they can check. It matters
              // most where a paste went wrong — the wrong image, or a
              // screenshot of the wrong window, is obvious at 32px and
              // invisible in a text chip.
              <Box
                sx={{
                  display: "inline-flex", alignItems: "center", gap: 0.75,
                  pl: 0.5, pr: 0.75, py: 0.5, borderRadius: 1.5,
                  border: "1px solid", borderColor: "divider",
                  bgcolor: "rgba(255,255,255,0.03)",
                }}
              >
                <Box
                  component="img"
                  src={photo}
                  alt="Attached product photo"
                  sx={{
                    width: 32, height: 32, borderRadius: 1,
                    objectFit: "cover", flexShrink: 0,
                    // The shop's own products sit on light backgrounds; a
                    // dark chrome behind a white-background photo makes the
                    // edges read as ragged without it.
                    bgcolor: "rgba(255,255,255,0.06)",
                  }}
                />
                <Typography variant="caption" sx={{ fontSize: 11, color: "text.secondary" }}>
                  attached
                </Typography>
                <IconButton
                  size="small"
                  onClick={() => setPhoto(null)}
                  aria-label="Remove the attached photo"
                  sx={{ width: 20, height: 20, color: "text.disabled" }}
                >
                  <CloseIcon sx={{ fontSize: 13 }} />
                </IconButton>
              </Box>
            )}
            {pending && (
              <Typography variant="caption" sx={{ color: "#FBBF24", fontSize: 11.5 }}>
                Still collecting: {String(pending.action).replace(/_/g, " ")}.
                Nothing has changed in your store yet.
              </Typography>
            )}
            {pending && (
              <Chip
                size="small"
                variant="outlined"
                label="Cancel"
                onClick={() => setPending(null)}
                sx={{ fontSize: 11, height: 24 }}
              />
            )}
            {attachError && (
              <Typography variant="caption" sx={{ color: "error.main", fontSize: 11.5 }}>
                {attachError}
              </Typography>
            )}
          </Stack>
        )}

        <Stack direction="row" spacing={1.5} sx={{ alignItems: "flex-end" }}>
          <Box sx={{ flex: 1, position: "relative", minWidth: 0 }}>
            {/* Behind the input, and only while it is empty and idle. */}
            <TypedPlaceholder
              prefix="Ask the agent to "
              phrases={MERCHANT_PROMPTS}
              active={!text && !busy && !voice.listening}
              sx={{
                position: "absolute",
                left: 8,
                top: 4,
                right: 8,
                fontSize: 14.5,
                lineHeight: 1.5,
              }}
            />
          <InputBase
            value={text}
            onChange={(e) => setText(e.target.value)}
            // Kept, and deliberately plain: this is what a screen reader
            // announces. The typed version above is aria-hidden decoration.
            placeholder={text ? "" : " "}
            multiline
            maxRows={4}
            disabled={busy}
            // ENTER SENDS. SHIFT+ENTER KEEPS THE NEWLINE.
            //
            // `multiline` makes this a <textarea>, and a textarea does not
            // submit its form on Enter — it inserts a line break. So the
            // arrow worked and the key everyone actually presses did
            // nothing but grow the box. The form's onSubmit is left alone
            // and still handles the button; this only adds the keyboard.
            //
            // `e.target.value` rather than `text`: typing quickly or
            // pasting and hitting Enter in the same tick means React has
            // not re-rendered, so the closed-over state is still the
            // previous value. Reading the live DOM value sends what is on
            // screen. Same reason the buyer console's PromptBar does it.
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                ask(e.target.value);
              }
            }}
            // PASTE A PHOTO STRAIGHT IN.
            //
            // A screenshot or a copied product image is how somebody
            // actually has a picture to hand — reaching for a file picker
            // means saving it somewhere first. The buyer console has done
            // this all along; the merchant box was the odd one out.
            //
            // `preventDefault` only when an image is actually found, so
            // pasting ordinary text still behaves like pasting text.
            onPaste={async (e) => {
              const file = [...(e.clipboardData?.items ?? [])]
                .find((i) => i.type.startsWith("image/"))
                ?.getAsFile();
              if (!file) return;
              e.preventDefault();
              setAttachError(null);
              try {
                setPhoto(await compress(file));
              } catch (err) {
                setAttachError(err?.message || "That image could not be read.");
              }
            }}
            sx={{ width: "100%", fontSize: 14.5, px: 1, py: 0.5,
                  position: "relative", zIndex: 1,
                  "& textarea::placeholder": { opacity: 0 } }}
          />
          </Box>
          {/* Attach a photo. Staged, not uploaded: it travels with the next
              message so the merchant can say what the thing is in the same
              breath. */}
          <Tooltip title="Attach a product photo" placement="top">
            <IconButton
              component="label"
              disabled={busy}
              aria-label="Attach a product photo"
              sx={{
                width: 40, height: 40, borderRadius: 2,
                color: photo ? "#4ADE80" : "text.secondary",
                bgcolor: photo ? "rgba(74,222,128,0.12)" : "transparent",
                "&:hover": { bgcolor: "rgba(255,255,255,0.06)" },
              }}
            >
              <ImageOutlinedIcon sx={{ fontSize: 19 }} />
              <input
                type="file"
                accept="image/*"
                hidden
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  setAttachError(null);
                  try {
                    setPhoto(await compress(file));
                  } catch (err) {
                    // Say so rather than staging nothing and looking ready.
                    setAttachError(err?.message || "That image could not be read.");
                  }
                }}
              />
            </IconButton>
          </Tooltip>

          {voice.canDictate && (
            <MicButton
              listening={voice.listening}
              onStart={voice.startDictation}
              onStop={voice.stopDictation}
              disabled={busy}
              size={40}
            />
          )}
          {voice.canSpeak && (
            <SpeakToggle
              enabled={readAloud}
              speaking={voice.speaking}
              onToggle={() => {
                if (readAloud) voice.stopSpeaking();
                setReadAloud((on) => !on);
              }}
              size={40}
            />
          )}
          <Button
            type="submit"
            disabled={busy || !text.trim()}
            sx={{ minWidth: 40, width: 40, height: 40, borderRadius: "50%", p: 0,
                  bgcolor: text.trim() ? "primary.main" : "rgba(255,255,255,0.07)",
                  color: text.trim() ? "#0B0F17" : "text.disabled",
                  "&:hover": { bgcolor: text.trim() ? "primary.dark" : "rgba(255,255,255,0.1)" } }}
          >
            {busy ? <CircularProgress size={16} /> : <ArrowUpwardIcon sx={{ fontSize: 19 }} />}
          </Button>
        </Stack>
      </Box>

      {/* ── the conversation ─────────────────────────────────────────── */}
      <Stack spacing={3}>
        {turns.map((turn, i) => (
          <Box key={i}>
            <Typography
              sx={{ fontSize: 17, fontWeight: 600, mb: 1.5, lineHeight: 1.5 }}
            >
              {turn.question}
            </Typography>
            {turn.answer
              ? <Answer answer={turn.answer} />
              : (
                <Stack direction="row" spacing={1.25}
                       sx={{ alignItems: "center", px: 1, py: 2 }}>
                  <CircularProgress size={15} />
                  <Typography variant="body2" sx={{ color: "text.secondary", fontSize: 13 }}>
                    Reading orders, checkouts and the decision log…
                  </Typography>
                </Stack>
              )}
          </Box>
        ))}
        <Box ref={bottom} />
      </Stack>
    </Box>
  );
}
