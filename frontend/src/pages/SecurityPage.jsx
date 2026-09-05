import { useEffect, useState } from "react";
import { Box, Chip, Stack, Typography } from "@mui/material";

import PageBanner from "../components/shared/PageBanner";
import ForgetSearches from "../components/shared/ForgetSearches";
import LoadingState from "../components/shared/LoadingState";
import { API_BASE } from "../config";

/**
 * What this system holds about you — re-checked on every load.
 *
 * The usual version of this page is a promise written once. This one calls an
 * endpoint that walks the live database and reports what it found, so the
 * claim can fail. If a card number ever reached storage, the panel below
 * turns into a finding rather than continuing to say everything is fine.
 *
 * It also names the personal data that *is* held. "We store nothing about
 * you" would be the comfortable version and it would be untrue: there is a
 * name and an email address in there.
 */

function Card({ title, children, tone }) {
  return (
    <Box
      sx={{
        p: 2.5,
        borderRadius: 2.5,
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
        borderTop: "2px solid",
        borderTopColor: tone ?? "divider",
      }}
    >
      <Typography
        variant="overline"
        sx={{ letterSpacing: 1, color: "text.secondary", display: "block", mb: 1.25 }}
      >
        {title}
      </Typography>
      {children}
    </Box>
  );
}

export default function SecurityPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/security/data-audit`)
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <Box sx={{ p: 4 }}>
        <Typography variant="body2" color="warning.main">
          The audit could not be run: {error}
        </Typography>
      </Box>
    );
  }
  if (!data) return <LoadingState label="Walking the database…" />;

  const clean = data.clean;

  return (
    <Box>
      <PageBanner
        title="Your banking details"
        subtitle="Where they go, and what this system keeps"
      />

      <Box sx={{ maxWidth: 980, mx: "auto", px: 3, py: 4 }}>
        <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.8, mb: 3.5 }}>
          An agent that spends your money should be able to answer what it knows
          about you. This page does not assert an answer — it runs the check when
          you open it and prints what it found.
        </Typography>

        <Stack spacing={2.5}>
          <Card
            title="The check, run just now"
            tone={clean ? "success.main" : "error.main"}
          >
            <Typography sx={{ fontSize: 26, fontWeight: 700, letterSpacing: "-0.015em" }}>
              {clean ? "Nothing sensitive found" : `${data.findings.length} findings`}
            </Typography>
            <Typography variant="body2" sx={{ color: "text.secondary", mt: 0.75, lineHeight: 1.7 }}>
              {data.scanned_documents.toLocaleString()} documents across{" "}
              {data.collections.length} collections were searched for{" "}
              {data.checked_for.length} kinds of sensitive data.
            </Typography>

            <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 0.75, mt: 1.75 }}>
              {data.checked_for.map((k) => (
                <Chip
                  key={k}
                  size="small"
                  label={k}
                  variant="outlined"
                  sx={{ fontSize: 11, borderColor: "divider" }}
                />
              ))}
            </Stack>

            {!clean && (
              <Box sx={{ mt: 2 }}>
                {data.findings.slice(0, 10).map((f, i) => (
                  <Typography key={i} variant="body2" sx={{ color: "error.main" }}>
                    {f.kind} in {f.collection}/{f.document}
                  </Typography>
                ))}
              </Box>
            )}
          </Card>

          {/* The page audits what is stored; this is the part that lets
              someone do something about it. Placed before the inventory
              because a control that acts is more use than a list that
              only informs. */}
          {/* THE ONE THING HERE THAT LEAVES THE MACHINE.
              The database scan above can only ever report what was written
              down. Voice is different: the audio never reaches the database,
              so no scan would ever surface it, and a page that reported
              "nothing sensitive found" while a microphone streamed a shop
              owner's voice to a third party would be true and misleading at
              once. It is stated here because it cannot be discovered. */}
          <Card title="If you use the microphone">
            <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.8 }}>
              The voice buttons in the two chats use what the browser already
              has, and the two halves behave differently:
            </Typography>
            <Box sx={{ display: "flex", gap: 1.5, mt: 1.5 }}>
              <Typography
                variant="body2"
                sx={{ fontFamily: "monospace", minWidth: 118, color: "text.primary" }}
              >
                speaking
              </Typography>
              <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.7 }}>
                Reading an answer aloud happens on this device. No audio and
                no text leave it.
              </Typography>
            </Box>
            <Box sx={{ display: "flex", gap: 1.5, mt: 1 }}>
              <Typography
                variant="body2"
                sx={{ fontFamily: "monospace", minWidth: 118, color: "#F59E0B" }}
              >
                dictation
              </Typography>
              <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.7 }}>
                Chrome and Edge transcribe speech by sending the recorded
                audio to Google. That is the browser&rsquo;s implementation, not
                a service this project added, and it is the only point at
                which anything you say leaves your machine. Nothing is
                recorded here: what comes back is text, it lands in the
                message box for you to read, and only what you send is
                stored. Type instead and the microphone is never opened.
              </Typography>
            </Box>
          </Card>

          <Card title="Searches this agent remembers">
            <ForgetSearches />
          </Card>
        </Stack>

        <Typography
          variant="caption"
          sx={{ color: "text.disabled", display: "block", mt: 3, lineHeight: 1.7 }}
        >
          {data.disclosure}
        </Typography>
      </Box>
    </Box>
  );
}
