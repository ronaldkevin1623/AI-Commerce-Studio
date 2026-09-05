import { useCallback, useEffect, useState } from "react";
import {
  Box, Button, IconButton, InputBase, MenuItem, Select, Stack, Typography,
  CircularProgress, Collapse, Dialog, DialogTitle, DialogContent,
  DialogContentText, DialogActions,
} from "@mui/material";
import { Link, useNavigate } from "react-router-dom";
import AddIcon from "@mui/icons-material/Add";
import LocalOfferOutlinedIcon from "@mui/icons-material/LocalOfferOutlined";
import ImageOutlinedIcon from "@mui/icons-material/ImageOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlineOutlined";

import { API_BASE } from "../config";
import PromotionsPanel from "../components/merchant/PromotionsPanel";
import ProductDetails from "../components/merchant/ProductDetails";
import { motion, useReducedMotion } from "motion/react";

const inr = (paise) =>
  `₹${((paise ?? 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

/**
 * The store's own stock list.
 *
 * This reads /merchant/products rather than /merchant/catalog on purpose:
 * the catalogue endpoint answers buying agents and only ever shows what is
 * genuinely for sale, while the shop owner needs to see drafts too. Same
 * collection, two audiences, and conflating them would either hide the
 * operator's unpublished work or let agents buy it.
 */
export default function MerchantProductsPage() {
  const navigate = useNavigate();
  const stillness = useReducedMotion();
  const [state, setState] = useState({ status: "loading", products: [], error: null });
  // One open row at a time. Several expanded panels turn a stock list into
  // a wall of forms, and the merchant loses the comparison the list exists
  // to give them.
  const [openId, setOpenId] = useState(null);
  // Which row is mid-flight, and what went wrong on it. Keyed by product so
  // one failing row cannot blank the whole list.
  const [flipping, setFlipping] = useState(null);
  const [flipError, setFlipError] = useState({});
  // What the last removal also retired, so the merchant is told rather than
  // discovering later that a promotion quietly stopped.
  const [removedNote, setRemovedNote] = useState(null);
  // Which row is asking. Inline rather than a dialog, for the same reason
  // the panel does it that way: a modal is dismissed by reflex, a row that
  // changes shape has to be read.
  // The product itself, not an id: the dialog names what it is about to
  // remove, and a dialog that says "are you sure?" without saying what is
  // the reason people click through them without reading.
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleteError, setDeleteError] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const removeProduct = useCallback(async (product) => {
    setDeleting(true);
    setDeleteError(null);
    try {
      const res = await fetch(`${API_BASE}/merchant/products/${product.id}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `Store returned ${res.status}`);
      setPendingDelete(null);
      setOpenId((id) => (id === product.id ? null : id));
      setState((prev) => ({
        ...prev,
        products: prev.products.filter((p) => p.id !== product.id),
      }));
      const retired = data.retired ?? [];
      setRemovedNote(
        `Removed ${product.name}.`
        + (retired.length ? ` Also retired: ${retired.join(", ")}.` : "")
      );
    } catch (err) {
      // The dialog stays open holding the refusal. Closing it and putting
      // the reason somewhere else would make the merchant hunt for why
      // nothing happened — and the reason is the useful part.
      setDeleteError(String(err.message ?? err));
    } finally {
      setDeleting(false);
    }
  }, []);

  // PUBLISHING FROM THE LIST, WITHOUT OPENING ANYTHING.
  //
  // The details panel can already do this, but pulling a product off sale
  // is the one edit a merchant makes in a hurry — a mispriced item is live
  // and buyable while they hunt for the right row. It writes through the
  // same PATCH, so it is the same validation and the same audit entry as
  // every other route to the change.
  const patchProduct = useCallback(async (product, patch) => {
    setFlipping(product.id);
    setFlipError((e) => ({ ...e, [product.id]: null }));
    try {
      const res = await fetch(`${API_BASE}/merchant/products/${product.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `Store returned ${res.status}`);
      setState((prev) => ({
        ...prev,
        products: prev.products.map((p) =>
          p.id === data.id ? { ...p, ...data } : p),
      }));
    } catch (err) {
      // The row keeps its old status, because that is still what is stored.
      setFlipError((e) => ({ ...e, [product.id]: String(err.message ?? err) }));
    } finally {
      setFlipping(null);
    }
  }, []);

  const load = useCallback(async () => {
    setState((s) => ({ ...s, status: "loading" }));
    try {
      const res = await fetch(`${API_BASE}/merchant/products`);
      if (!res.ok) throw new Error(`Store returned ${res.status}`);
      const data = await res.json();
      setState({ status: "ready", products: data.products ?? [], error: null });
    } catch (err) {
      setState({ status: "error", products: [], error: String(err.message ?? err) });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const { status, products, error } = state;

  return (
    <Box sx={{ p: 3, maxWidth: 1180, mx: "auto" }}>
      <Stack
        direction="row"
        sx={{ alignItems: "center", justifyContent: "space-between", mb: 2.5, gap: 2 }}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <LocalOfferOutlinedIcon sx={{ fontSize: 18, color: "text.secondary" }} />
          <Typography variant="h6" sx={{ fontSize: 19, fontWeight: 600 }}>
            Products
          </Typography>
        </Stack>

        {products.length > 0 && (
          <Button
            variant="contained"
            size="small"
            startIcon={<AddIcon sx={{ fontSize: 16 }} />}
            component={Link}
            to="/merchant/products/new"
          >
            Add product
          </Button>
        )}
      </Stack>

      {status === "loading" && (
        <Stack sx={{ alignItems: "center", py: 8 }}>
          <CircularProgress size={22} />
        </Stack>
      )}

      {status === "error" && (
        <Box
          sx={{
            p: 2,
            borderRadius: 2,
            border: "1px solid",
            borderColor: "error.main",
            bgcolor: "rgba(239,68,68,0.08)",
          }}
        >
          <Typography variant="body2" sx={{ color: "error.main", fontWeight: 600 }}>
            Couldn't read the catalogue
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            {error} — is the backend running on {API_BASE}?
          </Typography>
        </Box>
      )}

      {status === "ready" && products.length === 0 && (
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2.5,
            bgcolor: "background.paper",
            px: 4,
            py: 6,
            textAlign: "center",
          }}
        >
          <Typography sx={{ fontWeight: 600, fontSize: 17, mb: 0.75 }}>
            Add your products
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary", mb: 2.5 }}>
            Start by stocking the store with something an agent can find and buy.
          </Typography>
          <Button
            variant="contained"
            startIcon={<AddIcon sx={{ fontSize: 16 }} />}
            onClick={() => navigate("/merchant/products/new")}
          >
            Add product
          </Button>
        </Box>
      )}

      {removedNote && (
        <Typography
          variant="body2"
          sx={{ color: "text.secondary", mb: 2, lineHeight: 1.7 }}
        >
          {removedNote} Past orders keep their own copy of the line, so
          nothing already sold or reported has changed.
        </Typography>
      )}

      {status === "ready" && products.length > 0 && (
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2.5,
            bgcolor: "background.paper",
            overflow: "hidden",
          }}
        >
          <Stack
            direction="row"
            sx={{
              px: 2, py: 1.25, gap: 2,
              borderBottom: "1px solid", borderColor: "divider",
              color: "text.secondary",
            }}
          >
            <Typography variant="caption" sx={{ flex: 1, fontWeight: 700, fontSize: 11, letterSpacing: "0.06em", color: "text.secondary" }}>
              PRODUCT
            </Typography>
            <Typography variant="caption" sx={{ width: 120, fontWeight: 700, fontSize: 11, letterSpacing: "0.06em", color: "text.secondary" }}>
              STATUS
            </Typography>
            <Typography variant="caption" sx={{ width: 120, fontWeight: 700, fontSize: 11, letterSpacing: "0.06em", color: "text.secondary", textAlign: "right" }}>
              STOCK
            </Typography>
            <Typography variant="caption" sx={{ width: 140, fontWeight: 700, fontSize: 11, letterSpacing: "0.06em", color: "text.secondary", textAlign: "right" }}>
              PRICE
            </Typography>
            {/* Matches the remove + chevron controls so the columns above
                and below stay in line. */}
            <Box sx={{ width: 80, flexShrink: 0 }} />
          </Stack>

          {/* NO ENTRANCE ANIMATION HERE, DELIBERATELY.
              An entrance hides its content until it runs, and this is an
              operational table rather than a landing page — the merchant
              opens it to read stock, and anything that stalls the main
              thread would leave them looking at an empty catalogue and
              reaching for refresh. The one guard `mount` mode has is for a
              missing IntersectionObserver, not for a frame that never
              arrives, so the risk is real and the payoff is a flourish on
              a screen someone sees fifty times a day.

              The hover below stays: it responds to the operator, and it
              cannot hide anything. */}
          {products.map((product, index) => {
            const draft = (product.status ?? "active") !== "active";
            return (
              <Box
                key={product.id}
                component={motion.div}
                // The row lifts its GROUND, not itself: a table row that
                // moves under the pointer takes the column you are reading
                // with it. Nothing is hidden at rest, so a hover that never
                // runs costs the reader nothing.
                whileHover={stillness ? undefined : {
                  backgroundColor: "rgba(255,255,255,0.035)",
                }}
                transition={{ duration: 0.18 }}
                sx={{
                  borderTop: index === 0 ? "none" : "1px solid",
                  borderColor: "divider",
                  cursor: "default",
                }}
              >
              <Stack
                direction="row"
                sx={{
                  px: 2.5, py: 2, gap: 2, alignItems: "center",
                }}
              >
                <Stack direction="row" spacing={1.5} sx={{ flex: 1, minWidth: 0, alignItems: "center" }}>
                  <Box
                    sx={{
                      width: 46, height: 46, borderRadius: 2, flexShrink: 0,
                      border: "1px solid", borderColor: "divider",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      overflow: "hidden", bgcolor: "rgba(255,255,255,0.04)",
                    }}
                  >
                    {product.image ? (
                      <Box
                        component="img"
                        src={product.image}
                        alt=""
                        sx={{ width: "100%", height: "100%", objectFit: "cover" }}
                      />
                    ) : (
                      <ImageOutlinedIcon sx={{ fontSize: 20, color: "text.disabled" }} />
                    )}
                  </Box>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="body2" noWrap sx={{ fontWeight: 600, fontSize: 14.5, letterSpacing: "-0.005em" }}>
                      {product.name}
                    </Typography>
                    <Typography variant="caption" noWrap sx={{ color: "text.secondary", fontSize: 12.5, mt: 0.2, display: "block" }}>
                      {product.category ?? "Uncategorised"}
                    </Typography>
                  </Box>
                </Stack>

                <Box sx={{ width: 120 }}>
                  <Select
                    value={draft ? "draft" : "active"}
                    onChange={(e) => patchProduct(product, { status: e.target.value })}
                    disabled={flipping === product.id}
                    variant="standard"
                    disableUnderline
                    aria-label={`Status of ${product.name}`}
                    sx={{
                      fontSize: 11.5, fontWeight: 700, borderRadius: 1,
                      px: 1.1, py: 0.2,
                      color: draft ? "warning.main" : "success.main",
                      bgcolor: draft ? "rgba(245,158,11,0.12)" : "rgba(34,197,94,0.12)",
                      "& .MuiSelect-select": { py: 0.2, pr: "20px !important" },
                      "& .MuiSelect-icon": {
                        color: draft ? "warning.main" : "success.main",
                        fontSize: 16, right: 2,
                      },
                    }}
                  >
                    <MenuItem value="draft" sx={{ fontSize: 12.5 }}>Draft</MenuItem>
                    <MenuItem value="active" sx={{ fontSize: 12.5 }}>Active</MenuItem>
                  </Select>
                </Box>

                {/* STOCK IS EDITED WHERE IT IS READ.
                    Counting stock is the edit a shop makes most often and
                    the one least worth a form: the merchant is looking at
                    the number when they discover it is wrong. Saved on
                    blur or Enter rather than per keystroke, so typing "12"
                    is one write and not a write for "1" then another for
                    "12" — each of which would be a real audit entry. */}
                <Box sx={{ width: 120, display: "flex", justifyContent: "flex-end" }}>
                  <InputBase
                    defaultValue={product.stock ?? 0}
                    key={`${product.id}-${product.stock}`}
                    disabled={flipping === product.id}
                    inputProps={{
                      "aria-label": `Stock for ${product.name}`,
                      inputMode: "numeric",
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") e.target.blur();
                      // Escape abandons the edit and puts the stored value
                      // back, so a half-typed number is never a save.
                      if (e.key === "Escape") {
                        e.target.value = String(product.stock ?? 0);
                        e.target.blur();
                      }
                    }}
                    onBlur={(e) => {
                      const next = e.target.value.trim();
                      if (next === "" || !/^\d+$/.test(next)) {
                        e.target.value = String(product.stock ?? 0);
                        return;
                      }
                      if (Number(next) === (product.stock ?? 0)) return;
                      patchProduct(product, { stock: Number(next) });
                    }}
                    sx={{
                      width: 62,
                      "& input": {
                        textAlign: "right", fontSize: 14.5, fontWeight: 500,
                        fontVariantNumeric: "tabular-nums",
                        color: (product.stock ?? 0) > 0 ? "text.primary" : "error.main",
                        px: 0.75, py: 0.25, borderRadius: 1,
                        border: "1px solid transparent",
                        transition: "border-color 150ms, background-color 150ms",
                        "&:hover": { borderColor: "divider" },
                        "&:focus": {
                          borderColor: "rgba(255,255,255,0.22)",
                          bgcolor: "rgba(255,255,255,0.04)",
                        },
                      },
                    }}
                  />
                </Box>

                <Typography
                  variant="body2"
                  sx={{ width: 140, textAlign: "right", fontWeight: 600, fontSize: 14.5, fontVariantNumeric: "tabular-nums" }}
                >
                  {inr(product.price_paise)}
                </Typography>

                <IconButton
                  onClick={() => {
                    setPendingDelete(product);
                    setDeleteError(null);
                    setRemovedNote(null);
                  }}
                  aria-label={`Remove ${product.name}`}
                  sx={{
                    width: 32, height: 32, ml: 1, flexShrink: 0,
                    color: "text.disabled",
                    "&:hover": { color: "error.main" },
                  }}
                >
                  <DeleteOutlineIcon sx={{ fontSize: 18 }} />
                </IconButton>

                <IconButton
                  onClick={() => setOpenId((id) => (id === product.id ? null : product.id))}
                  aria-label={openId === product.id
                    ? `Hide details for ${product.name}`
                    : `Show details for ${product.name}`}
                  aria-expanded={openId === product.id}
                  sx={{
                    width: 32, height: 32, ml: 1, flexShrink: 0,
                    color: "text.secondary",
                    transform: openId === product.id ? "rotate(180deg)" : "none",
                    transition: "transform 180ms",
                  }}
                >
                  <ExpandMoreIcon sx={{ fontSize: 20 }} />
                </IconButton>
              </Stack>

              {/* A refusal is a sentence, not a cell. In the 120px status
                  column it wrapped into an unreadable vertical stripe; the
                  reason a deletion was refused is the most useful thing on
                  the row and has to be legible. */}
              {flipError[product.id] && (
                <Typography
                  variant="caption"
                  sx={{ display: "block", color: "error.main", fontSize: 11.5,
                        lineHeight: 1.6, px: 2.5, pb: 1.5 }}
                >
                  {flipError[product.id]}
                </Typography>
              )}

              <Collapse in={openId === product.id} unmountOnExit>
                <ProductDetails
                  product={product}
                  onRequestRemove={(p) => {
                    setPendingDelete(p);
                    setDeleteError(null);
                    setRemovedNote(null);
                  }}
                  onSaved={(updated) => {
                    // Replace the row in place rather than refetching the
                    // list: the merchant is looking at this row, and a
                    // reload would collapse it and lose their place.
                    setState((prev) => ({
                      ...prev,
                      products: prev.products.map((p) =>
                        p.id === updated.id ? { ...p, ...updated } : p),
                    }));
                  }}
                />
              </Collapse>
              </Box>
            );
          })}
        </Box>
      )}

      {status === "ready" && products.length > 0 && (
        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 1.5 }}>
          Drafts are stored but kept out of the UCP catalogue, so a buying agent can
          neither discover nor check one out until it is published.
        </Typography>
      )}

      {status === "ready" && <PromotionsPanel products={products} />}

      <Dialog
        open={Boolean(pendingDelete)}
        onClose={() => (deleting ? null : setPendingDelete(null))}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle sx={{ fontSize: 17, fontWeight: 600 }}>
          Remove {pendingDelete?.name}?
        </DialogTitle>
        <DialogContent>
          {/* What is about to go, so the decision is about this product and
              not about a generic warning. */}
          <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", mb: 2 }}>
            <Box
              sx={{
                width: 52, height: 52, borderRadius: 1.5, flexShrink: 0,
                border: "1px solid", borderColor: "divider", overflow: "hidden",
                bgcolor: "rgba(255,255,255,0.05)",
              }}
            >
              {pendingDelete?.image && (
                <Box component="img" src={pendingDelete.image} alt=""
                     sx={{ width: "100%", height: "100%", objectFit: "cover" }} />
              )}
            </Box>
            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {inr(pendingDelete?.price_paise)} · stock {pendingDelete?.stock ?? 0}
              </Typography>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                {(pendingDelete?.status ?? "active") === "active"
                  ? "Active — currently in the agent catalogue"
                  : "Draft — not in the agent catalogue"}
              </Typography>
            </Box>
          </Stack>

          <DialogContentText sx={{ fontSize: 13.5, lineHeight: 1.7 }}>
            Past orders keep their own copy of the line, so nothing already
            sold or reported changes. Any promotion or growth offer pointing
            at this product is retired with it.
          </DialogContentText>

          {deleteError && (
            <Typography
              variant="body2"
              sx={{ color: "error.main", mt: 2, fontSize: 13, lineHeight: 1.6 }}
            >
              {deleteError}
            </Typography>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button
            onClick={() => setPendingDelete(null)}
            disabled={deleting}
            sx={{ textTransform: "none", color: "text.secondary" }}
          >
            Cancel
          </Button>
          <Button
            onClick={() => removeProduct(pendingDelete)}
            disabled={deleting || Boolean(deleteError)}
            sx={{ textTransform: "none", color: "error.main" }}
          >
            {deleting ? <CircularProgress size={16} /> : "Remove product"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
