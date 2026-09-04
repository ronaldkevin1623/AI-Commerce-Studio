import { useEffect, useState } from "react";
import { Box, Stack, Typography } from "@mui/material";
import PolicyOutlinedIcon from "@mui/icons-material/PolicyOutlined";

import { API_BASE } from "../../config";

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

/**
 * THE BOUND, SHOWN BEFORE THE MONEY MOVES.
 *
 * The gate has always been able to refuse a purchase and explain why. It
 * did that AFTERWARDS — you committed, and then found out. This puts the
 * limit and the amount side by side on the checkout itself, so the one
 * number that decides whether a person has to intervene is visible while
 * there is still a decision to make.
 *
 * The awkward part, and the reason for the last line: this is ONE of the
 * gate's six checks. Stock, trust, duplicates, velocity and the payee
 * allowlist are all still ahead. A green tick that quietly implied "this
 * will go through" would be a worse lie than showing nothing, because it
 * would be believed — so the component says which check it ran and which it
 * did not, in the same breath as the tick.
 */
export default function PolicyCheck({ amountPaise }) {
  const [check, setCheck] = useState(null);

  useEffect(() => {
    if (!amountPaise) return undefined;
    let live = true;
    (async () => {
      try {
        const res = await fetch(
          `${API_BASE}/transaction-policy/check?amount_paise=${amountPaise}`);
        if (!res.ok) return;
        const data = await res.json();
        if (live) setCheck(data);
      } catch {
        // A checkout that cannot reach the policy endpoint should still be
        // usable — the gate runs server-side regardless of what this shows.
      }
    })();
    return () => { live = false; };
  }, [amountPaise]);

  if (!check) return null;

  const ok = check.within_policy;
  const colour = ok ? "#4ADE80" : "#FBBF24";

  return (
    <Box
      sx={{
        px: 1.5, py: 1.25, mb: 1.5, borderRadius: 1.5,
        border: "1px solid", borderColor: ok ? "rgba(74,222,128,0.25)" : "rgba(251,191,36,0.3)",
        bgcolor: ok ? "rgba(74,222,128,0.05)" : "rgba(251,191,36,0.07)",
      }}
    >
      <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", mb: 0.75 }}>
        <PolicyOutlinedIcon sx={{ fontSize: 14, color: colour }} />
        <Typography variant="caption" sx={{ fontWeight: 700, color: colour, fontSize: 11 }}>
          TRANSACTION POLICY
        </Typography>
      </Stack>

      <Stack direction="row" sx={{ justifyContent: "space-between" }}>
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          Maximum without approval
        </Typography>
        <Typography variant="caption" sx={{ fontVariantNumeric: "tabular-nums" }}>
          {inr(check.limit_paise)}
        </Typography>
      </Stack>
      <Stack direction="row" sx={{ justifyContent: "space-between" }}>
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          Requested
        </Typography>
        <Typography variant="caption" sx={{ fontVariantNumeric: "tabular-nums", color: colour,
                                            fontWeight: 600 }}>
          {inr(check.amount_paise)} {ok ? "✓" : "⚠"}
        </Typography>
      </Stack>

      <Typography variant="caption"
                  sx={{ color: "text.secondary", display: "block", mt: 0.75, lineHeight: 1.55,
                        fontSize: 10.5 }}>
        {ok
          ? `${inr(check.headroom_paise)} under the bound, so this needs no sign-off.`
          : "Over the bound — this will be held for a person to approve rather than charged."}
        {" "}This is the spending bound only; {check.not_checked.join(", ")} are
        checked by the gate at the moment of purchase.
      </Typography>
    </Box>
  );
}
