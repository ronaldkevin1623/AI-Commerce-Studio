import { useEffect, useState } from "react";
import { Box, Chip, Stack, Typography } from "@mui/material";

import PageBanner from "../components/shared/PageBanner";
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

            <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mt: 1.75 }}>
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

          <Card title="Why they never arrive here">
            <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.8 }}>
              Card numbers, netbanking logins and UPI PINs are typed into Razorpay
              Checkout, which runs in an iframe served from Razorpay's own domain.
              Browsers forbid this page from reading inside it, so those values are
              never in this application's memory, never travel to its server, and
              cannot be written to its database.
            </Typography>
            <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.8, mt: 1.5 }}>
              What comes back across that boundary is the whole of what the payment
              endpoint will accept:
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mt: 1.25 }}>
              {data.accepted_by_verify_payment.map((f) => (
                <Chip key={f} size="small" label={f}
                      sx={{ fontFamily: "monospace", fontSize: 11 }} />
              ))}
            </Stack>
            <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.8, mt: 1.5 }}>
              The key this page holds is the publishable one —{" "}
              <Box component="span" sx={{ fontFamily: "monospace" }}>
                {data.razorpay_key_in_browser}
              </Box>
              . It can only start a payment. The secret that can move money stays on
              the server and is never sent to a browser.
            </Typography>
          </Card>

          <Card title="What is kept about you">
            <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.8, mb: 1.5 }}>
              Not nothing — that would be the easy claim. This is the list:
            </Typography>
            {data.personal_data_held.map((p) => (
              <Box key={p.field} sx={{ display: "flex", gap: 1.5, mb: 1 }}>
                <Typography
                  variant="body2"
                  sx={{ fontFamily: "monospace", minWidth: 120, color: "text.primary" }}
                >
                  {p.field}
                </Typography>
                <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.7 }}>
                  {p.why}
                </Typography>
              </Box>
            ))}
          </Card>

          <Card title="Every field stored on a paid order">
            <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.8, mb: 1.5 }}>
              Taken from a real order that was paid for. These are all of them —
              the payment is represented by identifiers that mean nothing without
              Razorpay.
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={0.75}>
              {data.order_fields.map((f) => (
                <Chip
                  key={f}
                  size="small"
                  label={f}
                  variant="outlined"
                  sx={{
                    fontFamily: "monospace",
                    fontSize: 11,
                    borderColor: f.includes("razorpay") ? "info.dark" : "divider",
                  }}
                />
              ))}
            </Stack>
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
