import { Box, Typography } from "@mui/material";

export default function ProductCard({ product }) {
  if (!product) {
    return (
      <Box sx={{ bgcolor: "background.paper", border: "1px solid", borderColor: "divider", borderRadius: 2, p: 2 }}>
        <Typography variant="caption" color="text.secondary">No match yet</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ bgcolor: "background.paper", border: "1px solid", borderColor: "divider", borderRadius: 2, p: 2 }}>
      <Typography variant="body2" fontWeight={600}>{product.name}</Typography>
      <Typography variant="h6" fontWeight={700} sx={{ mt: 0.5 }}>
        ₹{(product.price_paise / 100).toLocaleString("en-IN")}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {product.delivery_days === 1 ? "Arrives tomorrow" : `Arrives in ${product.delivery_days} days`}
        {" · "}{product.rating}★
      </Typography>
    </Box>
  );
}