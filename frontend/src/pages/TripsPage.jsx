import { useEffect, useState } from "react";
import { Box, Stack, Typography, Chip } from "@mui/material";
import { Link } from "react-router-dom";
import FlightTakeoffIcon from "@mui/icons-material/FlightTakeoffOutlined";

import { API_BASE } from "../config";
import PageBanner from "../components/shared/PageBanner";
import LoadingState from "../components/shared/LoadingState";

/**
 * Trips that reached payment.
 *
 * There is no seeded content here and no sample card. If nothing has been
 * booked the page says nothing has been booked — a grid of plausible
 * destinations would be the single most convincing thing on the screen and
 * the least true.
 *
 * ON THE ARTWORK: the reference for this layout uses destination
 * photography. There is no photo of any of these cities in the project and
 * nothing that could fetch one, so each card carries a generated mark built
 * from the city name instead. It is obviously a graphic rather than a
 * picture, which is the point — a stock photo of Mumbai would imply the
 * itinerary knows what the hotel looks like.
 */

const rupees = (paise) =>
  `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

// Deterministic, so a city keeps its colour between visits.
function hueFor(text) {
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) % 360;
  return hash;
}

const STATUS = {
  booked: { label: "Stay paid", color: "success" },
  payment_pending: { label: "Payment not completed", color: "warning" },
};

function TripCard({ trip }) {
  const need = trip.need || {};
  const city = need.to_city || "—";
  const hue = hueFor(city);
  const status = STATUS[trip.status] ?? { label: trip.status, color: "default" };
  const legs = trip.itinerary?.legs || [];

  return (
    <Box
      component={Link}
      to={`/trips/${trip.trip_id}`}
      sx={{
        textDecoration: "none",
        color: "text.primary",
        display: "block",
        width: 260,
        borderRadius: 2,
        overflow: "hidden",
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
        transition: "border-color 160ms, transform 160ms",
        "&:hover": { borderColor: "rgba(255,255,255,0.28)", transform: "translateY(-2px)" },
      }}
    >
      <Box
        sx={{
          height: 116,
          position: "relative",
          background: `linear-gradient(135deg,
            hsl(${hue} 42% 26%) 0%,
            hsl(${(hue + 40) % 360} 38% 16%) 100%)`,
          display: "flex",
          alignItems: "flex-end",
          p: 1.5,
        }}
      >
        <Typography
          sx={{
            fontSize: 26,
            fontWeight: 700,
            color: "rgba(255,255,255,0.92)",
            letterSpacing: -0.5,
            lineHeight: 1,
          }}
        >
          {city}
        </Typography>
      </Box>

      <Box sx={{ p: 1.5 }}>
        <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", mb: 0.5 }}>
          <FlightTakeoffIcon sx={{ fontSize: 15, color: "text.secondary" }} />
          <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13 }}>
            {need.from_city || "—"} → {city}
          </Typography>
        </Stack>
        <Typography variant="caption" sx={{ display: "block", color: "text.secondary" }}>
          {need.nights} night{need.nights === 1 ? "" : "s"} · {legs.length} legs · {rupees(trip.amount_paise)} stay
        </Typography>
        <Chip
          size="small"
          label={status.label}
          color={status.color}
          variant="outlined"
          sx={{ mt: 1, height: 20, fontSize: 10.5 }}
        />
      </Box>
    </Box>
  );
}

export default function TripsPage() {
  const [trips, setTrips] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/trips`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => alive && setTrips(d.trips || []))
      .catch(() => alive && setError("The trip records could not be read."));
    return () => { alive = false; };
  }, []);

  return (
    <Box sx={{ p: 3, overflowY: "auto", height: "100%" }}>
      <PageBanner
        title="Trips"
        subtitle="Itineraries that reached payment. A trip appears here once its stay has an order against it."
      />

      {error && (
        <Typography variant="body2" color="error" sx={{ mt: 2 }}>
          {error}
        </Typography>
      )}

      {!trips && !error && <LoadingState label="Reading trips" />}

      {trips?.length === 0 && (
        <Box sx={{ mt: 3, p: 2.5, borderRadius: 2, border: "1px dashed", borderColor: "divider" }}>
          <Typography variant="body2" sx={{ mb: 0.5 }}>
            No trips booked yet.
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.6 }}>
            Type <strong>/trip</strong> in the console to assemble one. It appears here
            once you start paying for the stay. Nothing is shown here that was not
            actually planned and priced.
          </Typography>
        </Box>
      )}

      {trips?.length > 0 && (
        <Stack direction="row" spacing={2} sx={{ mt: 3, flexWrap: "wrap", gap: 2 }}>
          {trips.map((trip) => (
            <TripCard key={trip.trip_id} trip={trip} />
          ))}
        </Stack>
      )}
    </Box>
  );
}
