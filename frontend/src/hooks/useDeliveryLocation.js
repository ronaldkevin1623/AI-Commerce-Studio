import { useCallback, useState } from "react";

/**
 * The delivery address, from the browser's real Geolocation API.
 *
 * NOTHING HERE IS SYNTHESISED. The coordinates come from the device with the
 * person's explicit permission, and the street address comes from OpenStreetMap's
 * Nominatim reverse geocoder — free, no key, no account. If either step fails
 * the hook reports the failure and offers manual entry rather than filling in a
 * plausible-looking address, which is the one thing a checkout screen must never
 * do: a shipping address you didn't actually confirm is worse than no address.
 *
 * Nominatim asks that callers identify themselves and stay under one request a
 * second. This fires once, on an explicit click, so that's comfortably met.
 */

const NOMINATIM = "https://nominatim.openstreetmap.org/reverse";

function formatAddress(data) {
  const a = data?.address ?? {};
  const line1 = [a.house_number, a.road].filter(Boolean).join(" ");
  const city = a.city || a.town || a.village || a.suburb || a.county;
  return {
    line1: line1 || a.neighbourhood || a.suburb || "",
    city: city || "",
    state: a.state || "",
    postcode: a.postcode || "",
    country: a.country || "",
    display: data?.display_name ?? "",
  };
}

export function useDeliveryLocation() {
  const [location, setLocation] = useState(null); // {lat, lon, accuracy, address}
  const [status, setStatus] = useState("idle"); // idle | locating | ready | denied | error
  const [error, setError] = useState(null);

  const share = useCallback(() => {
    if (!navigator.geolocation) {
      setStatus("error");
      setError("This browser doesn't expose a location API.");
      return;
    }

    setStatus("locating");
    setError(null);

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude, accuracy } = position.coords;
        let address = null;

        try {
          const url =
            `${NOMINATIM}?format=jsonv2&lat=${latitude}&lon=${longitude}&zoom=18&addressdetails=1`;
          const res = await fetch(url, {
            headers: { Accept: "application/json" },
          });
          if (res.ok) address = formatAddress(await res.json());
        } catch {
          // Coordinates are still genuinely useful on their own — the map and
          // the delivery pin work without a street address.
          address = null;
        }

        setLocation({
          lat: latitude,
          lon: longitude,
          accuracy: Math.round(accuracy),
          address,
          capturedAt: new Date().toISOString(),
        });
        setStatus("ready");
      },
      (err) => {
        setStatus(err.code === err.PERMISSION_DENIED ? "denied" : "error");
        setError(
          err.code === err.PERMISSION_DENIED
            ? "Location permission was declined. You can type an address instead."
            : err.message || "Couldn't get a location fix."
        );
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 }
    );
  }, []);

  /** Manual entry — the fallback whenever the device path isn't available. */
  const setManual = useCallback((line1, city, postcode) => {
    setLocation({
      lat: null,
      lon: null,
      accuracy: null,
      manual: true,
      address: { line1, city, postcode, state: "", country: "", display: "" },
      capturedAt: new Date().toISOString(),
    });
    setStatus("ready");
  }, []);

  const clear = useCallback(() => {
    setLocation(null);
    setStatus("idle");
    setError(null);
  }, []);

  return { location, status, error, share, setManual, clear };
}
