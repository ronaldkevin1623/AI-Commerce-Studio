import { Box, Typography } from "@mui/material";

import HiveCanvas from "../components/hive/HiveCanvas";
import { SPECIALISTS } from "../components/hive/topology";

/**
 * The seller's half of the machine.
 *
 * Same canvas, different half. A merchant has no use for the buyer's intent
 * parser or its risk gate — those decide what the shopper's agent does —
 * and showing them here would pad the page with machinery the seller does
 * not own. What is left is what a seller actually runs: the shop agents can
 * discover, the catalogue they read, the checkout that prices from the
 * shop's own record, the settlement that refuses an unverified payment, and
 * the growth agents that read what all of it produced.
 */
export default function MerchantHivePage() {
  const live = SPECIALISTS.filter(
    (s) => s.cluster === "storefront" && s.state === "live").length;

  return (
    <Box sx={{ p: 3, maxWidth: 1180, mx: "auto" }}>
      <Typography variant="h6" sx={{ fontSize: 19, fontWeight: 600 }}>
        How your shop works
      </Typography>
      <Typography
        variant="body2"
        sx={{ color: "text.secondary", maxWidth: "70ch", lineHeight: 1.75, mt: 0.75, mb: 2.5 }}
      >
        Every part of the selling side, and what it touches. The {live} shop
        nodes all run today — an agent can discover this store, read its
        catalogue, open a checkout and be refused if it cannot prove it paid.
        Click any node to read what it does; the growth nodes below it are
        marked for what they are, and two of them are not built yet.
      </Typography>

      <HiveCanvas mode="map" clusters={["storefront", "growth"]} />
    </Box>
  );
}
