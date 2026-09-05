import { Box, Button, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";

import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import ArrowOutwardIcon from "@mui/icons-material/ArrowOutward";
import StorefrontOutlinedIcon from "@mui/icons-material/StorefrontOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import TravelExploreOutlinedIcon from "@mui/icons-material/TravelExploreOutlined";
import CreditCardOutlinedIcon from "@mui/icons-material/CreditCardOutlined";
import ReceiptLongOutlinedIcon from "@mui/icons-material/ReceiptLongOutlined";
import TrendingUpOutlinedIcon from "@mui/icons-material/TrendingUpOutlined";
import PersonOutlineOutlinedIcon from "@mui/icons-material/PersonOutlineOutlined";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import ReplayOutlinedIcon from "@mui/icons-material/ReplayOutlined";
import FingerprintOutlinedIcon from "@mui/icons-material/FingerprintOutlined";
import GitHubIcon from "@mui/icons-material/GitHub";

import { ROLES, useRole } from "../context/RoleContext";
import Flow from "../components/landing/Flow";
import { BuyerChat, CommandCentre, PolicyTrace } from "../components/landing/LivePanels";
import { Item, Lift, Reveal, Stagger, motion, useReducedMotion } from "../components/landing/motion";
import { ScrollLines, ScrollZoom } from "../components/landing/scroll";

/**
 * THE LANDING PAGE.
 *
 * Its job is unchanged: this is where somebody picks a side of the counter,
 * and both primary actions still set a role and land on that role's home.
 * Everything above and below that is an argument for why the product is
 * worth entering.
 *
 * TWO THINGS THIS PAGE DOES THAT MOST DO NOT
 *
 * The dashboard preview is the dashboard. `CommandCentre` and `PolicyTrace`
 * read the same endpoints the product serves, so the figures on the
 * marketing page are the figures in the build. Where the backend is not
 * running they show em dashes and say why, because a placeholder number on a
 * landing page is indistinguishable from a claim.
 *
 * And the protocol section lists only what is actually implemented. A rail
 * this build does not genuinely speak is left off the page rather than
 * softened into a status a reader has to interpret — the honest move is to
 * not make the claim, not to qualify it. A page that overstates the thing it
 * is selling gets checked, and this one is checkable.
 */

const ACCENT = "#4F8DF7";
/**
 * The content column.
 *
 * Wide, because the things that want the room are the diagrams and the
 * grids — a six-stage flow squeezed into 1120px on a 1900px display leaves
 * the page looking like a phone screenshot with a black border. Running
 * prose does NOT get this width: every lede is capped near 65 characters
 * separately, because a measure this wide is unreadable no matter how much
 * space is going spare.
 */
const MAX = 1520;

const Section = ({ children, sx, id }) => (
  <Box component="section" id={id}
       sx={{ maxWidth: MAX, mx: "auto", px: { xs: 3, sm: 5, md: 7, lg: 9 },
             py: { xs: 8, md: 12 }, ...sx }}>
    {children}
  </Box>
);

const Eyebrow = ({ children }) => (
  <Typography sx={{
    fontSize: 11, fontWeight: 700, letterSpacing: "0.14em",
    textTransform: "uppercase", color: "#6E6E78", mb: 1.25,
  }}>
    {children}
  </Typography>
);

/**
 * Section headlines are set in LINES, and each one rises out from behind a
 * mask as it arrives. The breaks are authored rather than left to the
 * browser: a mask that cuts wherever the text happens to wrap will sooner
 * or later cut through the middle of a word.
 */
const Headline = ({ lines, sx }) => (
  <ScrollLines
    lines={lines}
    sx={{
      fontSize: { xs: 30, sm: 38, md: 46 },
      fontWeight: 600, letterSpacing: "-0.032em",
      lineHeight: 1.08, color: "#ECECEE", ...sx,
    }}
  />
);

const Lede = ({ children, sx }) => (
  <Typography sx={{
    fontSize: { xs: 15, md: 16.5 }, lineHeight: 1.7, color: "#8E8E96",
    maxWidth: 620, mt: 2, ...sx,
  }}>
    {children}
  </Typography>
);

/** A hairline that separates sections without drawing a box round them. */
const Rule = () => (
  <Box sx={{ maxWidth: MAX, mx: "auto", px: { xs: 3, sm: 5, md: 7, lg: 9 } }}>
    <Box sx={{ height: 1, background:
      "linear-gradient(90deg, transparent, rgba(255,255,255,0.10) 18%, rgba(255,255,255,0.10) 82%, transparent)" }} />
  </Box>
);

const HERO_FLOW = [
  { label: "Merchant", detail: "Catalogue and orders", icon: StorefrontOutlinedIcon },
  { label: "Commerce Studio", detail: "Growth intelligence", icon: HubOutlinedIcon },
  { label: "AI buyer", detail: "Intent and constraints", icon: SmartToyOutlinedIcon },
  { label: "Discovery", detail: "Rank, screen, refuse", icon: TravelExploreOutlinedIcon },
  { label: "Razorpay", detail: "Gated authorisation", icon: CreditCardOutlinedIcon },
  { label: "Transaction", detail: "Audited, reconciled", icon: ReceiptLongOutlinedIcon },
];

const STACK_FLOW = [
  { label: "AI buyer", detail: "Any agent client", icon: SmartToyOutlinedIcon },
  { label: "Agent protocol", detail: "UCP · ACP · AP2", icon: AccountTreeOutlinedIcon },
  { label: "Commerce Studio", detail: "Gate, policy, audit", icon: HubOutlinedIcon },
  { label: "Merchant", detail: "Catalogue and stock", icon: StorefrontOutlinedIcon },
  { label: "Razorpay", detail: "Order and capture", icon: CreditCardOutlinedIcon },
];

const CAPABILITIES = [
  {
    icon: TrendingUpOutlinedIcon,
    title: "AI-powered growth",
    line: "Discover revenue opportunities before they become obvious.",
    points: ["Upsell and cross-sell learned from real baskets",
             "Lapsed-customer detection against each customer's own rhythm",
             "Campaigns with a margin envelope and four ways to stop",
             "Attribution that counts only what it can name"],
  },
  {
    icon: AccountTreeOutlinedIcon,
    title: "Agent-readable commerce",
    line: "Make your catalogue understandable to machines.",
    points: ["Availability and inventory as separate facts",
             "Structured attributes, delivery and returns windows",
             "Merchant-declared policy marked as declared",
             "Complements carrying the basis for the claim"],
  },
  {
    icon: ShieldOutlinedIcon,
    title: "Autonomous transactions",
    line: "Let AI buyers complete purchases safely.",
    points: ["Six gate rules before any charge",
             "Signed mandate chain, verified before money moves",
             "Human approval above the bound — never self-cleared",
             "Every action written to an audit trail, refusals included"],
  },
];

const TRUST = [
  { icon: DescriptionOutlinedIcon, title: "Explainable actions",
    line: "Every decision carries the sentence that produced it, verbatim." },
  { icon: ShieldOutlinedIcon, title: "Bounded authority",
    line: "Spend ceiling, session budget, velocity, duplicates, payee allowlist." },
  { icon: PersonOutlineOutlinedIcon, title: "Human in the loop",
    line: "Above the bound it escalates, and no exposed tool clears it." },
  { icon: ReceiptLongOutlinedIcon, title: "Audit trail",
    line: "Append-only, including the actions that were refused." },
  { icon: ReplayOutlinedIcon, title: "Failure handling",
    line: "A failed payment is never retried automatically. It stops and asks." },
  { icon: FingerprintOutlinedIcon, title: "Idempotent execution",
    line: "An atomic claim, so two concurrent retries cannot both charge." },
];

const PROTOCOLS = [
  { name: "UCP", state: "Implemented",
    line: "Discovery, catalogue, checkout and settlement.", tone: "ok" },
  { name: "AP2", state: "Implemented",
    line: "ES256 mandate chain, verified before money moves.", tone: "ok" },
  { name: "ACP", state: "Implemented",
    line: "Agentic checkout on the same store, against the published spec.", tone: "ok" },
];

export default function LandingPage() {
  const navigate = useNavigate();
  const { setRole } = useRole();
  const flat = useReducedMotion();

  const enter = (id) => {
    setRole(id);
    navigate(ROLES[id].home);
  };

  return (
    <Box sx={{ position: "relative", bgcolor: "#0A0A0B", color: "#ECECEE",
               overflowX: "hidden" }}>
      {/* THE GROUND.
          Fixed rather than scrolled, and sized in viewport units so it fills
          whatever window it is given — the previous glows were pinned in
          pixels and masked to a narrow band, which is why a wide display got
          a small bright patch surrounded by pure black. Held at very low
          contrast: this is the surface the content sits on, and the moment
          you can point at it as "the background" it is too strong. */}
      <Box aria-hidden sx={{
        position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0,
        backgroundImage:
          "linear-gradient(rgba(255,255,255,0.034) 1px, transparent 1px)," +
          "linear-gradient(90deg, rgba(255,255,255,0.034) 1px, transparent 1px)",
        backgroundSize: "clamp(56px, 5vw, 88px) clamp(56px, 5vw, 88px)",
        // Wide and shallow, so the texture reaches the corners of a large
        // display instead of dying just past the headline. It still falls
        // away at the foot of the viewport — a grid that runs edge to edge
        // stops being a ground and becomes a pattern.
        maskImage: "radial-gradient(150% 125% at 50% -5%, #000 40%, transparent 96%)",
        WebkitMaskImage: "radial-gradient(150% 125% at 50% -5%, #000 40%, transparent 96%)",
      }} />
      <Box aria-hidden sx={{
        position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0,
        background:
          // A lift off pure black across the whole field, so no part of the
          // page is the same colour as the void behind the browser.
          "linear-gradient(180deg, rgba(255,255,255,0.020), rgba(255,255,255,0.006) 45%, rgba(255,255,255,0.014))," +
          "radial-gradient(95vw 62vh at 50% -12%, rgba(79,141,247,0.14), transparent 64%)," +
          "radial-gradient(70vw 55vh at 92% 18%, rgba(79,141,247,0.055), transparent 62%)," +
          "radial-gradient(75vw 60vh at 4% 78%, rgba(120,160,255,0.045), transparent 64%)",
      }} />

      {/* Everything above the ground. */}
      <Box sx={{ position: "relative", zIndex: 1 }}>
      {/* ── Hero ──────────────────────────────────────────────────────── */}
      <Box sx={{ position: "relative" }}>
        <Section sx={{ position: "relative", pt: { xs: 7, md: 10 }, pb: { xs: 7, md: 9 } }}>
          <Stagger step={0.09} mount>
            <Item>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 3 }}>
                <Box sx={{ width: 5, height: 5, borderRadius: "50%", bgcolor: ACCENT }} />
                <Typography sx={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.14em",
                                  textTransform: "uppercase", color: "#8E8E96" }}>
                  The infrastructure for agentic commerce
                </Typography>
              </Stack>
            </Item>

            {/* Set as two lines so the second can carry the gradient and
                arrive after the first, which is the whole beat of the hero. */}
            <ScrollLines
              mount
              component="h1"
              delay={0.15}
              stagger={0.12}
              lines={["Turn every merchant into", "an AI-native business."]}
              sx={{
                fontSize: { xs: 40, sm: 56, md: 68 }, fontWeight: 600,
                letterSpacing: "-0.042em", lineHeight: 1.05, maxWidth: 880,
              }}
              // By index, not by selector: every line is the only child of
              // its own wrapper, so `:last-of-type` would match both.
              lineSx={(i) => (i === 1 ? {
                background: "linear-gradient(96deg, #ECECEE 8%, #4F8DF7 118%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              } : null)}
            />

            <Item>
              <Lede sx={{ maxWidth: 660 }}>
                AI Commerce Studio connects merchants, AI buyers, product discovery,
                growth intelligence and payments into one autonomous commerce
                layer — with every financial action bounded, explainable and audited.
              </Lede>
            </Item>

            <Item>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}
                     sx={{ mt: 4, alignItems: { sm: "center" } }}>
                <Button
                  variant="contained" size="large"
                  onClick={() => enter("customer")}
                  endIcon={<ArrowForwardIcon sx={{ fontSize: 17 }} />}
                  sx={{ py: 1.35, px: 2.75, fontSize: 14.5 }}
                >
                  Explore the studio
                </Button>
                <Button
                  variant="outlined" size="large"
                  href="#architecture"
                  endIcon={<ArrowOutwardIcon sx={{ fontSize: 16 }} />}
                  sx={{ py: 1.35, px: 2.5, fontSize: 14.5 }}
                >
                  View architecture
                </Button>
              </Stack>
            </Item>
          </Stagger>

          <ScrollZoom sx={{ mt: { xs: 6, md: 8 } }}>
            <Typography sx={{ fontSize: 10.5, letterSpacing: "0.12em", fontWeight: 700,
                              textTransform: "uppercase", color: "#5A5A62", mb: 2.5 }}>
              One request, end to end
            </Typography>
            <Flow nodes={HERO_FLOW} mount />
          </ScrollZoom>
        </Section>
      </Box>

      {/* ── 2. What it does ───────────────────────────────────────────── */}
      <Section>
        <Reveal><Eyebrow>Capabilities</Eyebrow></Reveal>
        <Reveal><Headline lines={["Three surfaces,", "one system."]} /></Reveal>

        <Box sx={{ mt: 4.5, display: "grid", gap: { xs: 2.5, md: 2.5 },
                   gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" } }}>
          {CAPABILITIES.map((cap, i) => (
            <Reveal key={cap.title} delay={i * 0.08}>
              <Lift>
                <Box sx={{
                  height: "100%", p: { xs: 2.5, md: 3 }, borderRadius: 2,
                  border: "1px solid rgba(255,255,255,0.08)",
                  bgcolor: "rgba(255,255,255,0.015)",
                  transition: "border-color 240ms, background-color 240ms",
                  "&:hover": { borderColor: "rgba(255,255,255,0.16)",
                               bgcolor: "rgba(255,255,255,0.028)" },
                }}>
                  <cap.icon sx={{ fontSize: 20, color: ACCENT, mb: 2 }} />
                  <Typography sx={{ fontSize: 17, fontWeight: 600, letterSpacing: "-0.015em",
                                    mb: 1 }}>
                    {cap.title}
                  </Typography>
                  <Typography sx={{ fontSize: 13.5, lineHeight: 1.65, color: "#8E8E96", mb: 2.5 }}>
                    {cap.line}
                  </Typography>
                  <Stack spacing={1.1}>
                    {cap.points.map((point) => (
                      <Stack key={point} direction="row" spacing={1.25}
                             sx={{ alignItems: "flex-start" }}>
                        <Box sx={{ width: 3, height: 3, borderRadius: "50%", mt: "7px",
                                   flexShrink: 0, bgcolor: "rgba(255,255,255,0.32)" }} />
                        <Typography sx={{ fontSize: 12.5, lineHeight: 1.6, color: "#A8A8B0" }}>
                          {point}
                        </Typography>
                      </Stack>
                    ))}
                  </Stack>
                </Box>
              </Lift>
            </Reveal>
          ))}
        </Box>
      </Section>

      {/* ── 3. Agent control ──────────────────────────────────────────── */}
      <Section>
        <Box sx={{ display: "grid", gap: { xs: 5, md: 7 },
                   gridTemplateColumns: { xs: "1fr", md: "0.85fr 1.15fr" },
                   alignItems: "center" }}>
          <Box>
            <Reveal><Eyebrow>Control</Eyebrow></Reveal>
            <Reveal><Headline lines={["Autonomy with", "boundaries."]}
                      sx={{ fontSize: { xs: 30, sm: 36, md: 42 } }} /></Reveal>
            <Reveal delay={0.05}>
              <Lede>
                Every financial action is explainable, bounded and gated. The agent
                that proposes a purchase cannot approve it, cannot widen the bound it
                was given, and cannot edit the record of what it did.
              </Lede>
            </Reveal>
          </Box>
          <Reveal delay={0.1}>
            <PolicyTrace />
          </Reveal>
        </Box>
      </Section>

      <Rule />

      {/* ── 4. AI buyer ───────────────────────────────────────────────── */}
      <Section>
        <Box sx={{ display: "grid", gap: { xs: 5, md: 7 },
                   gridTemplateColumns: { xs: "1fr", md: "1.15fr 0.85fr" },
                   alignItems: "center" }}>
          <Reveal>
            <BuyerChat />
          </Reveal>
          <Box>
            <Reveal><Eyebrow>The buyer</Eyebrow></Reveal>
            <Reveal><Headline lines={["Shopping becomes", "a conversation."]}
                      sx={{ fontSize: { xs: 30, sm: 36, md: 42 } }} /></Reveal>
            <Reveal delay={0.05}>
              <Lede>
                Constraints in plain language — a colour, a size, a ceiling, a
                deadline. The agent screens, ranks and says what it set aside and
                why, then stops at the point a person is genuinely required.
              </Lede>
            </Reveal>
          </Box>
        </Box>
      </Section>

      <Rule />

      {/* ── 5. Merchant command centre ────────────────────────────────── */}
      <Section>
        <Reveal><Eyebrow>Merchant command centre</Eyebrow></Reveal>
        <Reveal><Headline lines={["Ask your shop", "a question."]} /></Reveal>
        <Reveal delay={0.05}>
          <Lede>
            The merchant side gets an agent too. It reads the shop&rsquo;s own orders,
            checkouts and decision log, and answers with computed figures — never
            with a sentence a language model made up.
          </Lede>
        </Reveal>

        <Reveal delay={0.1}>
          <Box sx={{ mt: 5 }}>
            <CommandCentre />
          </Box>
        </Reveal>

        <Stagger step={0.07} start={0.1}>
          <Box sx={{ mt: 2.5, display: "grid", gap: 2,
                     gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" } }}>
            {[
              "Find me an opportunity to increase revenue",
              "How is the shop doing this month?",
              "What is going wrong?",
            ].map((prompt) => (
              <Item key={prompt}>
                <Box sx={{ px: 1.75, py: 1.4, borderRadius: 1.5,
                           border: "1px solid rgba(255,255,255,0.08)",
                           bgcolor: "rgba(255,255,255,0.015)" }}>
                  <Typography sx={{ fontSize: 12.5, color: "#A8A8B0", lineHeight: 1.5 }}>
                    &ldquo;{prompt}&rdquo;
                  </Typography>
                </Box>
              </Item>
            ))}
          </Box>
        </Stagger>
      </Section>

      <Rule />

      {/* ── 6. Trust ──────────────────────────────────────────────────── */}
      <Section>
        <Reveal><Eyebrow>Trust</Eyebrow></Reveal>
        <Reveal><Headline lines={["Built for transactions,", "not just recommendations."]} /></Reveal>
        <Reveal delay={0.05}>
          <Lede>
            Recommending is cheap. Moving money is not — so the interesting part of
            this system is everything that can stop it.
          </Lede>
        </Reveal>

        {/* The stagger container IS the grid. An ordinary element between a
            variant parent and its children stops the orchestration reaching
            them — only the first cell was arriving, and the other five sat
            at opacity zero inside a visible border. */}
        <Stagger
          step={0.06}
          start={0.05}
          sx={{
            mt: 6, display: "grid", gap: 0,
            gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "repeat(3, 1fr)" },
            border: "1px solid rgba(255,255,255,0.08)", borderRadius: 2,
            overflow: "hidden",
          }}
        >
          <>
            {TRUST.map((item, i) => (
              <Item key={item.title}>
                <Box sx={{
                  height: "100%", p: { xs: 2.5, md: 3 },
                  borderRight: { md: (i + 1) % 3 === 0 ? "none" : "1px solid rgba(255,255,255,0.07)" },
                  borderBottom: i < TRUST.length - (TRUST.length % 3 || 3)
                    ? "1px solid rgba(255,255,255,0.07)" : "none",
                  transition: "background-color 240ms",
                  "&:hover": { bgcolor: "rgba(255,255,255,0.022)" },
                }}>
                  <item.icon sx={{ fontSize: 18, color: "#8E8E96", mb: 1.75 }} />
                  <Typography sx={{ fontSize: 14.5, fontWeight: 600, mb: 0.85,
                                    letterSpacing: "-0.01em" }}>
                    {item.title}
                  </Typography>
                  <Typography sx={{ fontSize: 12.5, lineHeight: 1.65, color: "#8E8E96" }}>
                    {item.line}
                  </Typography>
                </Box>
              </Item>
            ))}
          </>
        </Stagger>
      </Section>

      <Rule />

      {/* ── 7. Protocols ──────────────────────────────────────────────── */}
      <Section id="architecture">
        <Reveal><Eyebrow>Architecture</Eyebrow></Reveal>
        <Reveal><Headline lines={["The stack an agent", "talks through."]} /></Reveal>
        <Reveal delay={0.05}>
          <Lede>
            An agent that has never heard of a shop should be able to find it, read
            its catalogue and pay it. That is a protocol problem before it is a
            product one.
          </Lede>
        </Reveal>

        <Reveal delay={0.1}>
          <Box sx={{ mt: 4.5, p: { xs: 2.5, md: 4 }, borderRadius: 2.5,
                     border: "1px solid rgba(255,255,255,0.09)",
                     bgcolor: "rgba(255,255,255,0.016)" }}>
            <Flow nodes={STACK_FLOW} />
          </Box>
        </Reveal>

        <Stagger step={0.06} start={0.05}>
          <Stack sx={{ mt: 3, border: "1px solid rgba(255,255,255,0.08)",
                       borderRadius: 2, overflow: "hidden" }}>
            {PROTOCOLS.map((protocol, i) => (
              <Item key={protocol.name}>
                <Stack direction={{ xs: "column", sm: "row" }}
                       spacing={{ xs: 0.5, sm: 2 }}
                       sx={{ px: { xs: 2, md: 2.5 }, py: 1.75,
                             alignItems: { sm: "baseline" },
                             borderTop: i === 0 ? "none" : "1px solid rgba(255,255,255,0.06)" }}>
                  <Typography sx={{ fontSize: 13.5, fontWeight: 700, width: { sm: 96 },
                                    flexShrink: 0, letterSpacing: "-0.01em" }}>
                    {protocol.name}
                  </Typography>
                  <Typography sx={{
                    fontSize: 10.5, fontWeight: 700, letterSpacing: "0.06em",
                    textTransform: "uppercase", width: { sm: 128 }, flexShrink: 0,
                    color: protocol.tone === "ok" ? "#3FB950"
                      : protocol.tone === "warn" ? "#D29922" : "#6E6E78",
                  }}>
                    {protocol.state}
                  </Typography>
                  <Typography sx={{ fontSize: 12.5, lineHeight: 1.65, color: "#8E8E96" }}>
                    {protocol.line}
                  </Typography>
                </Stack>
              </Item>
            ))}
          </Stack>
        </Stagger>

        <Reveal delay={0.05}>
          <Typography sx={{ fontSize: 12, color: "#5A5A62", mt: 2.5, lineHeight: 1.7,
                            maxWidth: 660 }}>
            Implemented against the published specifications, not adapted from
            them. Every limit is declared in the thing itself — a capability
            flag, a scheme name, an error code — so a client discovers it by
            reading, not by failing.
          </Typography>
        </Reveal>
      </Section>

      {/* ── 8. Final CTA ──────────────────────────────────────────────── */}
      <Box sx={{ position: "relative", borderTop: "1px solid rgba(255,255,255,0.07)" }}>
        <Box aria-hidden sx={{
          position: "absolute", inset: 0, pointerEvents: "none",
          background: "radial-gradient(80vw 46vh at 50% 100%, rgba(79,141,247,0.13), transparent 70%)",
        }} />
        <Section sx={{ position: "relative", textAlign: "center",
                       py: { xs: 9, md: 13 } }}>
          <ScrollLines
            lines={["Commerce is", "becoming agentic."]}
            stagger={0.11}
            sx={{
              fontSize: { xs: 34, sm: 46, md: 56 }, fontWeight: 600,
              letterSpacing: "-0.038em", lineHeight: 1.05,
            }}
          />
          <Reveal delay={0.06}>
            <Lede sx={{ mx: "auto", textAlign: "center" }}>
              Give your merchants the intelligence to grow, and your customers the
              agents to buy.
            </Lede>
          </Reveal>
          <Reveal delay={0.12}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}
                   sx={{ mt: 4.5, justifyContent: "center" }}>
              <Button variant="contained" size="large"
                      onClick={() => enter("merchant")}
                      endIcon={<StorefrontOutlinedIcon sx={{ fontSize: 17 }} />}
                      sx={{ py: 1.35, px: 2.75, fontSize: 14.5 }}>
                Launch as merchant
              </Button>
              <Button variant="outlined" size="large"
                      onClick={() => enter("customer")}
                      endIcon={<PersonOutlineOutlinedIcon sx={{ fontSize: 17 }} />}
                      sx={{ py: 1.35, px: 2.5, fontSize: 14.5 }}>
                Launch as customer
              </Button>
            </Stack>
          </Reveal>
          <Reveal delay={0.16}>
            <Typography sx={{ fontSize: 12, color: "#5A5A62", mt: 3 }}>
              Razorpay test mode. Nothing here charges a real card.
            </Typography>
          </Reveal>
        </Section>
      </Box>

      {/* ── Footer ────────────────────────────────────────────────────── */}
      <Box component="footer" sx={{ borderTop: "1px solid rgba(255,255,255,0.07)" }}>
        <Box sx={{ maxWidth: MAX, mx: "auto", px: { xs: 3, sm: 5, md: 7, lg: 9 },
                   py: { xs: 5, md: 7 } }}>
          <Stack direction={{ xs: "column", md: "row" }}
                 spacing={{ xs: 4, md: 6 }}
                 sx={{ justifyContent: "space-between" }}>
            <Box sx={{ maxWidth: 300 }}>
              <Stack direction="row" spacing={1.1} sx={{ alignItems: "center", mb: 1.25 }}>
                <HubOutlinedIcon sx={{ fontSize: 17, color: ACCENT }} />
                <Typography sx={{ fontSize: 14.5, fontWeight: 650, letterSpacing: "-0.01em" }}>
                  AI Commerce Studio
                </Typography>
              </Stack>
              <Typography sx={{ fontSize: 12.5, color: "#8E8E96", lineHeight: 1.7 }}>
                AI infrastructure for agentic commerce.
              </Typography>
            </Box>

            <Stack direction="row" spacing={{ xs: 4, sm: 7 }} sx={{ flexWrap: "wrap", gap: 3 }}>
              {[
                { head: "Product", links: [
                  { label: "AI buyer", go: () => enter("customer") },
                  { label: "Merchant", go: () => enter("merchant") },
                ] },
                { head: "System", links: [
                  { label: "Architecture", href: "#architecture" },
                  { label: "Security", go: () => enter("customer") },
                ] },
              ].map((group) => (
                <Stack key={group.head} spacing={1.25}>
                  <Typography sx={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em",
                                    textTransform: "uppercase", color: "#5A5A62" }}>
                    {group.head}
                  </Typography>
                  {group.links.map((link) => (
                    <Box
                      key={link.label}
                      component={link.href ? "a" : "button"}
                      href={link.href}
                      onClick={link.go}
                      type={link.href ? undefined : "button"}
                      sx={{
                        background: "none", border: "none", p: 0, textAlign: "left",
                        cursor: "pointer", textDecoration: "none",
                        fontSize: 12.5, color: "#8E8E96", fontFamily: "inherit",
                        transition: "color 180ms",
                        "&:hover": { color: "#ECECEE" },
                      }}
                    >
                      {link.label}
                    </Box>
                  ))}
                </Stack>
              ))}
            </Stack>
          </Stack>

          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}
                 sx={{ mt: 5, pt: 3, borderTop: "1px solid rgba(255,255,255,0.06)",
                       justifyContent: "space-between", alignItems: { sm: "center" } }}>
            <Typography sx={{ fontSize: 11.5, color: "#5A5A62" }}>
              Built for the Razorpay Buildathon · Agentic commerce track
            </Typography>
            <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
              <GitHubIcon sx={{ fontSize: 14, color: "#5A5A62" }} />
              <Typography sx={{ fontSize: 11.5, color: "#5A5A62" }}>
                Source available in the repository
              </Typography>
            </Stack>
          </Stack>
        </Box>
      </Box>

      {/* A page whose motion is off should look finished, not unstarted.
          Nothing above depends on this; it is only here so the note is
          visible to whoever reads the file next. */}
      {flat && <Box aria-hidden sx={{ display: "none" }} data-motion="reduced" />}
      </Box>
    </Box>
  );
}
