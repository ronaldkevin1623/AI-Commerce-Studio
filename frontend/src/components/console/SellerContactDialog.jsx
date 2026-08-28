import { useCallback, useState } from "react";
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyIcon from "@mui/icons-material/ContentCopyOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import { API_BASE } from "../../config";

const GOALS = [
  { id: "condition", label: "Ask about condition" },
  { id: "authenticity", label: "Ask for proof it's genuine" },
  { id: "price", label: "Ask for a better price" },
  { id: "shipping", label: "Ask about shipping" },
];

const inr = (paise) => `₹${Math.round((paise ?? 0) / 100).toLocaleString("en-IN")}`;

/**
 * The Negotiator agent's surface.
 *
 * The disclosure at the bottom is not boilerplate — AI Commerce Studio genuinely
 * cannot send this message, and the dialog is built around that: there is
 * no send button to mistake for one, only copy and a link to the real
 * listing. The "based on" block shows the exact facts the model was given,
 * so the draft can be checked rather than trusted.
 */
export default function SellerContactDialog({ open, product, customerId, onClose }) {
  const [goal, setGoal] = useState("condition");
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | drafting | error
  const [copied, setCopied] = useState(false);

  const draft = useCallback(async () => {
    setStatus("drafting");
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/contact-seller`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product, goal, customer_id: customerId ?? null }),
      });
      if (!res.ok) {
        setStatus("error");
        return;
      }
      setResult(await res.json());
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  }, [product, goal, customerId]);

  const copy = async () => {
    if (!result?.draft) return;
    try {
      await navigator.clipboard.writeText(result.draft);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  const handleClose = () => {
    setResult(null);
    setStatus("idle");
    onClose();
  };

  if (!product) return null;
  const grounding = result?.grounding;

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
      slotProps={{
        paper: {
          sx: {
            bgcolor: "background.paper",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2.5,
            backgroundImage: "none",
          },
        },
      }}
    >
      <DialogTitle sx={{ pb: 1 }}>
        <Stack direction="row" sx={{ alignItems: "flex-start", justifyContent: "space-between", gap: 2 }}>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1 }}>
              Negotiator
            </Typography>
            <Typography variant="body2" fontWeight={600} noWrap>
              {product.name}
            </Typography>
          </Box>
          <Button
            size="small"
            onClick={handleClose}
            sx={{ minWidth: 0, color: "text.secondary", boxShadow: "none", "&:hover": { boxShadow: "none" } }}
          >
            <CloseIcon sx={{ fontSize: 18 }} />
          </Button>
        </Stack>
      </DialogTitle>

      <DialogContent>
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1, display: "block", mb: 1 }}>
          What do you want to ask?
        </Typography>
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", mb: 2.5 }}>
          {GOALS.map((g) => (
            <Chip
              key={g.id}
              label={g.label}
              onClick={() => setGoal(g.id)}
              sx={{
                cursor: "pointer",
                bgcolor: goal === g.id ? "rgba(59,130,246,0.16)" : "rgba(255,255,255,0.05)",
                color: goal === g.id ? "primary.light" : "text.secondary",
                border: "1px solid",
                borderColor: goal === g.id ? "primary.main" : "transparent",
              }}
            />
          ))}
        </Stack>

        <Button
          variant="contained"
          onClick={draft}
          disabled={status === "drafting"}
          sx={{ boxShadow: "none", "&:hover": { boxShadow: "none" }, mb: 2 }}
        >
          {status === "drafting" ? "Drafting locally…" : result ? "Draft again" : "Draft message"}
        </Button>

        {status === "error" && (
          <Typography variant="body2" sx={{ color: "error.main", mb: 2 }}>
            Couldn't reach the Negotiator. Check that the backend and Ollama are both running.
          </Typography>
        )}

        {result && (
          <>
            {/* The exact facts the model was handed — shown so the draft
                can be verified instead of taken on faith. */}
            {grounding && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1, display: "block", mb: 0.75 }}>
                  Based only on
                </Typography>
                <Stack spacing={0.35}>
                  <Fact label="Asking price" value={inr(product.price_paise)} />
                  <Fact label="Condition" value={grounding.condition} />
                  <Fact
                    label="Seller feedback"
                    value={grounding.seller_feedback != null ? `${grounding.seller_feedback}%` : "not reported"}
                  />
                  <Fact
                    label="Trust flags"
                    value={grounding.trust_flags?.length ? grounding.trust_flags.join("; ") : "none"}
                  />
                </Stack>
              </Box>
            )}

            <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1, display: "block", mb: 0.75 }}>
              Draft
            </Typography>
            <Box
              sx={{
                bgcolor: "rgba(255,255,255,0.03)",
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 2,
                p: 1.75,
                mb: 2,
              }}
            >
              <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: 12.5, whiteSpace: "pre-wrap", color: "text.primary" }}>
                {result.draft}
              </Typography>
            </Box>

            <Stack direction="row" spacing={1} sx={{ mb: 2.5, flexWrap: "wrap" }} useFlexGap>
              <Button
                size="small"
                variant="outlined"
                startIcon={<ContentCopyIcon sx={{ fontSize: 16 }} />}
                onClick={copy}
                sx={{ boxShadow: "none", "&:hover": { boxShadow: "none" } }}
              >
                {copied ? "Copied" : "Copy message"}
              </Button>
              {result.listing_url && (
                <Button
                  size="small"
                  variant="outlined"
                  component="a"
                  href={result.listing_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  endIcon={<OpenInNewIcon sx={{ fontSize: 16 }} />}
                  sx={{ boxShadow: "none", "&:hover": { boxShadow: "none" } }}
                >
                  Open the listing
                </Button>
              )}
            </Stack>

            <Box
              sx={{
                display: "flex",
                gap: 1.25,
                alignItems: "flex-start",
                bgcolor: "rgba(245,158,11,0.08)",
                border: "1px solid",
                borderColor: "rgba(245,158,11,0.25)",
                borderRadius: 2,
                p: 1.5,
              }}
            >
              <InfoOutlinedIcon sx={{ fontSize: 17, color: "warning.main", mt: "1px", flexShrink: 0 }} />
              <Typography variant="caption" color="text.secondary">
                AI Commerce Studio can't send this for you. eBay's Browse API is read-only, and messaging a
                seller needs the Sell API plus sign-in to your own eBay account. The draft is real;
                sending it is your step. The draft was logged to the audit trail.
              </Typography>
            </Box>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Fact({ label, value }) {
  return (
    <Box sx={{ display: "flex", gap: 1.5, alignItems: "baseline" }}>
      <Typography variant="caption" sx={{ color: "text.secondary", width: 108, flexShrink: 0 }}>
        {label}
      </Typography>
      <Typography variant="caption" sx={{ color: "text.primary", minWidth: 0 }}>
        {value}
      </Typography>
    </Box>
  );
}
