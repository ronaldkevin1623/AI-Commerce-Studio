import { useEffect, useState } from "react";
import { Box, CircularProgress, Stack, Typography } from "@mui/material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlineOutlined";
import BlockIcon from "@mui/icons-material/BlockOutlined";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutlineOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutlineOutlined";

import { API_BASE } from "../../config";

/**
 * WHICH RAILS CAN ACTUALLY TAKE MONEY, AND HOW WE KNOW.
 *
 * This is the honest answer to "try every payment method". An agent that
 * retries a dead rail is not persistent, it is stuck — and on a real card,
 * three attempts is three attempts on somebody's account. So the rails are
 * enumerated with a verdict each, and every verdict is backed by what this
 * Razorpay account has actually done rather than by a config file.
 *
 * The row that matters is the one carrying "needs a person". Netbanking
 * works here and still puts a human on the bank's own page, so no rail on
 * this account completes unattended. Saying that plainly is the difference
 * between a capability and a claim.
 */
const VERDICT = {
  works: { colour: "#4ADE80", Icon: CheckCircleOutlineIcon, label: "Works" },
  rejected: { colour: "#F87171", Icon: BlockIcon, label: "Rejected" },
  untried: { colour: "#6B7280", Icon: RemoveCircleOutlineIcon, label: "Untried" },
};

export default function PaymentRails({ card, refreshKey }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/payment-rails`);
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        const json = await res.json();
        if (live) { setData(json); setError(null); }
      } catch (err) {
        if (live) setError(String(err.message ?? err));
      }
    })();
    return () => { live = false; };
  }, [refreshKey]);

  return (
    <Box sx={card}>
      <Stack direction="row"
             sx={{ alignItems: "baseline", justifyContent: "space-between", mb: 1.5, gap: 2 }}>
        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13.5 }}>
          Payment rails on this account
        </Typography>
        {data?.payments_read != null && (
          <Typography variant="caption" sx={{ color: "text.disabled", fontSize: 11 }}>
            from {data.payments_read} real payments
          </Typography>
        )}
      </Stack>

      {!data && !error && (
        <Stack direction="row" spacing={1.25} sx={{ alignItems: "center", py: 2 }}>
          <CircularProgress size={14} />
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            Reading this account's payment history…
          </Typography>
        </Stack>
      )}

      {error && (
        <Typography variant="caption" sx={{ color: "warning.main", lineHeight: 1.7 }}>
          Razorpay could not be reached, so no rail can be verified from
          history right now: {error}
        </Typography>
      )}

      {data?.rails?.length > 0 && (
        <Stack spacing={0}>
          {data.rails.map((rail, i) => {
            const tone = VERDICT[rail.verdict] ?? VERDICT.untried;
            return (
              <Stack
                key={rail.key}
                direction="row"
                spacing={1.5}
                sx={{
                  alignItems: "flex-start", py: 1.25,
                  borderTop: i === 0 ? "none" : "1px solid",
                  borderColor: "divider",
                }}
              >
                <tone.Icon sx={{ fontSize: 17, color: tone.colour, mt: "1px", flexShrink: 0 }} />
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", flexWrap: "wrap" }}>
                    <Typography variant="body2" sx={{ fontSize: 13, fontWeight: 600 }}>
                      {rail.label}
                    </Typography>
                    <Typography sx={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.4,
                                      color: tone.colour, textTransform: "uppercase" }}>
                      {tone.label}
                    </Typography>
                    {rail.verdict === "works" && rail.needs_a_person && (
                      <Stack direction="row" spacing={0.4} sx={{ alignItems: "center" }}>
                        <PersonOutlineIcon sx={{ fontSize: 12, color: "#FBBF24" }} />
                        <Typography sx={{ fontSize: 10, color: "#FBBF24", fontWeight: 600 }}>
                          needs a person
                        </Typography>
                      </Stack>
                    )}
                  </Stack>
                  <Typography variant="caption"
                              sx={{ color: "text.secondary", display: "block", mt: 0.25,
                                    lineHeight: 1.6 }}>
                    {rail.headline}
                    {rail.error && ` — “${rail.error}”`}
                  </Typography>
                </Box>
              </Stack>
            );
          })}
        </Stack>
      )}

      {data?.note && (
        <Typography variant="caption"
                    sx={{ display: "block", mt: 1.75, pt: 1.5, borderTop: "1px solid",
                          borderColor: "divider", color: "text.secondary",
                          lineHeight: 1.7, fontSize: 11.5 }}>
          {data.note}
        </Typography>
      )}
      {data?.disclosure && (
        <Typography variant="caption"
                    sx={{ display: "block", mt: 0.75, color: "text.disabled",
                          lineHeight: 1.65, fontSize: 10.5 }}>
          {data.disclosure}
        </Typography>
      )}
    </Box>
  );
}
