import { useEffect, useState } from "react";
import { Box, Stack, Typography, Chip, Divider } from "@mui/material";
import { Link, useParams } from "react-router-dom";
import ArrowBackIcon from "@mui/icons-material/ArrowBackOutlined";
import FlightIcon from "@mui/icons-material/FlightTakeoffOutlined";
import HotelIcon from "@mui/icons-material/HotelOutlined";
import RestaurantIcon from "@mui/icons-material/RestaurantOutlined";
import WarningIcon from "@mui/icons-material/WarningAmberOutlined";

import { API_BASE } from "../config";
import LoadingState from "../components/shared/LoadingState";

/**
 * One booked trip, as it was actually assembled.
 *
 * The itinerary rendered here is the one the SERVER built and stored at
 * booking time, not a description the page was handed. That is why it can
 * be shown as a record rather than a preview.
 *
 * WHAT THIS PAGE DOES NOT HAVE, deliberately: no weather, no live traffic,
 * no currency converter, no translator. Every one of those needs a live
 * feed this build does not have, and inventing them would put four
 * confident, wrong panels next to five real ones.
 */

const LEG_ICON = {
  flight: <FlightIcon sx={{ fontSize: 18 }} />,
  hotel: <HotelIcon sx={{ fontSize: 18 }} />,
  meal: <RestaurantIcon sx={{ fontSize: 18 }} />,
};

const rupees = (paise) =>
  `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

function hueFor(text) {
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) % 360;
  return hash;
}

function Row({ k, v }) {
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: "baseline" }}>
      <Typography variant="caption" color="text.secondary" sx={{ width: 110, flexShrink: 0 }}>
        {k}
      </Typography>
      <Typography variant="caption" sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>
        {v}
      </Typography>
    </Stack>
  );
}

export default function TripDetailPage() {
  const { tripId } = useParams();
  const [trip, setTrip] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/trips/${tripId}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => alive && setTrip(d))
      .catch(() => alive && setError("That trip could not be read."));
    return () => { alive = false; };
  }, [tripId]);

  if (error) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="body2" color="error">{error}</Typography>
      </Box>
    );
  }
  if (!trip) return <Box sx={{ p: 3 }}><LoadingState label="Reading the itinerary" /></Box>;

  const need = trip.need || {};
  const plan = trip.itinerary || {};
  const legs = plan.legs || [];
  const city = need.to_city || "—";
  const hue = hueFor(city);
  const booked = trip.status === "booked";

  return (
    <Box sx={{ p: 3, overflowY: "auto", height: "100%" }}>
      <Box
        component={Link}
        to="/trips"
        sx={{
          display: "inline-flex", alignItems: "center", gap: 0.5, mb: 2,
          color: "text.secondary", textDecoration: "none", fontSize: 13,
          "&:hover": { color: "text.primary" },
        }}
      >
        <ArrowBackIcon sx={{ fontSize: 16 }} /> All trips
      </Box>

      <Box sx={{ maxWidth: 860 }}>
        <Box sx={{ borderRadius: 2, overflow: "hidden", border: "1px solid", borderColor: "divider", mb: 2.5 }}>
          <Box
            sx={{
              p: 2.5,
              background: `linear-gradient(135deg, hsl(${hue} 42% 26%) 0%, hsl(${(hue + 40) % 360} 38% 16%) 100%)`,
            }}
          >
            <Typography
              sx={{ fontSize: 30, fontWeight: 700, color: "rgba(255,255,255,0.94)", letterSpacing: -0.6, lineHeight: 1.1 }}
            >
              {need.from_city} → {city}
            </Typography>
            <Typography variant="body2" sx={{ color: "rgba(255,255,255,0.78)", mt: 0.5 }}>
              {need.nights} night{need.nights === 1 ? "" : "s"}
              {plan.date_note ? ` · ${plan.date_note}` : ""}
            </Typography>
            <Stack direction="row" spacing={1} sx={{ mt: 1.5, flexWrap: "wrap", gap: 1 }}>
              <Chip
                size="small"
                label={booked ? "Stay paid" : "Payment not completed"}
                color={booked ? "success" : "warning"}
                sx={{ height: 22, fontSize: 11 }}
              />
              <Chip size="small" label={`Total ${rupees(plan.total_paise || 0)}`} sx={{ height: 22, fontSize: 11 }} />
              <Chip size="small" label={`Stay ${rupees(trip.amount_paise || 0)}`} sx={{ height: 22, fontSize: 11 }} />
            </Stack>
          </Box>
        </Box>

        {plan.narrative && (
          <Typography variant="body2" sx={{ mb: 2, lineHeight: 1.7 }}>
            {plan.narrative}
          </Typography>
        )}

        {/* The itinerary itself, in the order the days run. */}
        <Box sx={{ borderRadius: 2, border: "1px solid", borderColor: "divider", bgcolor: "background.paper", p: 2 }}>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mb: 1.5, letterSpacing: 0.3, fontWeight: 600 }}
          >
            ITINERARY
          </Typography>
          {legs.map((leg, i) => (
            <Stack
              key={`${leg.record_id}-${i}`}
              direction="row"
              spacing={1.5}
              sx={{ alignItems: "flex-start", py: 1.25, borderTop: i ? "1px solid" : "none", borderColor: "divider" }}
            >
              <Box sx={{ color: "text.secondary", display: "flex", mt: "2px" }}>{LEG_ICON[leg.leg]}</Box>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{leg.name}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                  {leg.role}
                  {leg.rating ? ` · ${leg.rating}★${leg.reviews || leg.votes ? ` (${leg.reviews || leg.votes} reviews)` : ""}` : ""}
                  {leg.locality ? ` · ${leg.locality}` : ""}
                  {leg.distance_km != null ? ` · ${leg.distance_km} km from the hotel` : ""}
                  {leg.leg === "meal" && leg.hours_known === false ? " · opening hours unknown" : ""}
                </Typography>
              </Box>
              <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>
                {rupees(leg.price_paise)}
              </Typography>
            </Stack>
          ))}
          <Divider sx={{ my: 1.25 }} />
          <Stack direction="row" sx={{ alignItems: "baseline" }}>
            <Typography variant="body2" sx={{ flex: 1, fontWeight: 700 }}>Total</Typography>
            <Typography variant="body2" sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
              {rupees(plan.total_paise || 0)}
            </Typography>
          </Stack>
        </Box>

        {plan.warnings?.length > 0 && (
          <Box
            sx={{ mt: 2, p: 1.75, borderRadius: 2, bgcolor: "rgba(210,153,34,0.08)", border: "1px solid", borderColor: "divider" }}
          >
            {plan.warnings.map((w) => (
              <Stack key={w} direction="row" spacing={1} sx={{ alignItems: "flex-start", mb: 0.5 }}>
                <WarningIcon sx={{ fontSize: 14, color: "warning.main", mt: "2px", flexShrink: 0 }} />
                <Typography variant="caption" sx={{ color: "warning.main", lineHeight: 1.6 }}>{w}</Typography>
              </Stack>
            ))}
          </Box>
        )}

        {/* The payment record, and what it does and does not mean. */}
        <Box sx={{ mt: 2, p: 2, borderRadius: 2, border: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mb: 1, letterSpacing: 0.3, fontWeight: 600 }}
          >
            PAYMENT RECORD
          </Typography>
          <Stack spacing={0.5}>
            <Row k="Razorpay order" v={trip.razorpay_order_id} />
            {trip.razorpay_payment_id && <Row k="Capture" v={trip.razorpay_payment_id} />}
            {plan.payable_leg?.record_id && <Row k="Hotel record" v={plan.payable_leg.record_id} />}
            <Row k="Amount" v={rupees(trip.amount_paise || 0)} />
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5, lineHeight: 1.6 }}>
            {booked
              ? "Real payment captured for a demo-merchant stand-in. This is not a hotel booking: no room is held and no hotel is contacted. Production would require direct hotel-supplier integration."
              : "An order exists for the stay but no capture has been recorded against it. Nothing has been paid."}
            {" "}The flight and the meals are not payable at all — the datasets behind them
            carry no booking rail, and none is implied here.
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}
