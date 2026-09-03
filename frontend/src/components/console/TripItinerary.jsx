import { Box, Stack, Typography, Button, Chip, Divider } from "@mui/material";
import FlightIcon from "@mui/icons-material/FlightTakeoffOutlined";
import HotelIcon from "@mui/icons-material/HotelOutlined";
import RestaurantIcon from "@mui/icons-material/RestaurantOutlined";
import WarningIcon from "@mui/icons-material/WarningAmberOutlined";

/**
 * One assembled itinerary.
 *
 * This is deliberately not the product card grid with different icons. A
 * product result is a list you choose from; an itinerary is a single
 * answer whose parts depend on each other, and showing it as a ranked list
 * would misrepresent what the agent did. So: legs in order, one total, and
 * the compromises stated rather than hidden.
 */

const LEG_ICON = {
  flight: <FlightIcon sx={{ fontSize: 18 }} />,
  hotel: <HotelIcon sx={{ fontSize: 18 }} />,
  meal: <RestaurantIcon sx={{ fontSize: 18 }} />,
};

const rupees = (paise) => `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

export default function TripItinerary({ plan, onBook, booking }) {
  if (!plan) return null;

  // The route answered with a question instead of an itinerary.
  if (!plan.ok) {
    return (
      <Box sx={{ p: 2, borderRadius: 2, border: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
        <Typography variant="body2" sx={{ mb: 1 }}>
          {plan.detail}
        </Typography>
        {plan.needs?.length > 0 && (
          <Typography variant="caption" color="text.secondary">
            Still needed: {plan.needs.map((n) => n.prompt).join("  ")}
          </Typography>
        )}
      </Box>
    );
  }

  const payable = plan.payable_leg;

  return (
    <Box sx={{ borderRadius: 2, border: "1px solid", borderColor: "divider", bgcolor: "background.paper", overflow: "hidden" }}>
      <Box sx={{ p: 2, pb: 1.5 }}>
        <Typography variant="body2" sx={{ mb: 1.5, lineHeight: 1.6 }}>
          {plan.narrative}
        </Typography>

        <Stack spacing={0.25}>
          {plan.legs.map((leg, i) => (
            <Stack
              key={`${leg.record_id}-${i}`}
              direction="row"
              spacing={1.25}
              sx={{ alignItems: "center", py: 0.75, borderTop: i ? "1px solid" : "none", borderColor: "divider" }}
            >
              <Box sx={{ color: "text.secondary", display: "flex" }}>{LEG_ICON[leg.leg]}</Box>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" noWrap sx={{ fontWeight: 500 }}>
                  {leg.name}
                </Typography>
                <Typography variant="caption" color="text.secondary" noWrap sx={{ display: "block" }}>
                  {leg.role}
                  {leg.rating ? ` · ${leg.rating}★${leg.reviews || leg.votes ? ` (${leg.reviews || leg.votes} reviews)` : ""}` : ""}
                  {leg.distance_km != null ? ` · ${leg.distance_km} km from the hotel` : ""}
                  {/* Not asserted as open — said to be unknown. */}
                  {leg.leg === "meal" && leg.hours_known === false ? " · opening hours unknown" : ""}
                </Typography>
              </Box>
              <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>
                {rupees(leg.price_paise)}
              </Typography>
            </Stack>
          ))}
        </Stack>

        <Divider sx={{ my: 1.25 }} />
        <Stack direction="row" sx={{ alignItems: "baseline" }}>
          <Typography variant="body2" sx={{ flex: 1, fontWeight: 600 }}>
            Total
          </Typography>
          <Typography variant="body2" sx={{ fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
            {rupees(plan.total_paise)}
          </Typography>
        </Stack>
      </Box>

      {plan.warnings?.length > 0 && (
        <Box sx={{ px: 2, py: 1.25, bgcolor: "rgba(255,183,77,0.08)", borderTop: "1px solid", borderColor: "divider" }}>
          {plan.warnings.map((w) => (
            <Stack key={w} direction="row" spacing={1} sx={{ alignItems: "flex-start", mb: 0.5 }}>
              <WarningIcon sx={{ fontSize: 14, color: "warning.main", mt: "2px", flexShrink: 0 }} />
              <Typography variant="caption" sx={{ color: "warning.main", lineHeight: 1.5 }}>
                {w}
              </Typography>
            </Stack>
          ))}
        </Box>
      )}

      {/* What the agent actually did, in the order it did it. Same shape as
          the product pipeline's trace, because it is the same claim: this
          is the funnel, not a summary of it. */}
      {plan.steps?.length > 0 && (
        <Box sx={{ px: 2, py: 1.25, borderTop: "1px solid", borderColor: "divider" }}>
          {plan.steps.map((s) => (
            <Typography key={s.step} variant="caption" color="text.secondary" sx={{ display: "block", lineHeight: 1.7 }}>
              <strong>{s.step}</strong> — considered {s.considered.toLocaleString("en-IN")}, chose {s.chose} ({s.detail})
            </Typography>
          ))}
        </Box>
      )}

      {/* The disclosure the user asked for, on the card itself rather than
          in a docs file: a real capture against a stand-in merchant is not
          a booking, and nobody should have to infer that. */}
      <Box sx={{ px: 2, py: 1.5, borderTop: "1px solid", borderColor: "divider", bgcolor: "action.hover" }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", gap: 1 }}>
          <Chip size="small" label="Dataset snapshot — not live availability" sx={{ height: 20, fontSize: 10.5 }} />
          {payable && <Chip size="small" label="1 of 4 legs payable" sx={{ height: 20, fontSize: 10.5 }} />}
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1, lineHeight: 1.6 }}>
          {plan.disclosure}
        </Typography>

        {payable && (
          <Box sx={{ mt: 1.5 }}>
            <Typography variant="caption" sx={{ display: "block", color: "warning.main", lineHeight: 1.6, mb: 1 }}>
              {payable.disclosure}
            </Typography>
            <Button
              size="small"
              variant="outlined"
              disabled={booking}
              onClick={() => onBook?.(payable)}
              sx={{ textTransform: "none" }}
            >
              {booking
                ? "Creating order…"
                : `Pay ${rupees(payable.price_paise)} for the stay (stand-in merchant)`}
            </Button>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75, lineHeight: 1.5 }}>
              Charged from {payable.name}'s own dataset row ({payable.record_id}) —
              {" "}{rupees(payable.nightly_paise)} + {rupees(payable.nightly_tax_paise)} tax × {payable.nights}{" "}
              night{payable.nights > 1 ? "s" : ""}. The record id travels with the Razorpay
              order, so the capture is traceable to this specific hotel.
            </Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}
