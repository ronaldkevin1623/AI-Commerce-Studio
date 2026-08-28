import { createContext, useCallback, useContext, useMemo, useState } from "react";

/**
 * The cart.
 *
 * In-memory for the session, deliberately: a cart that survived a refresh
 * would need to re-price every line against live eBay listings before it
 * could be trusted, and a stale price is exactly what the mandate chain
 * exists to catch. Until that re-pricing exists, a short-lived cart is the
 * honest version.
 */
const CartContext = createContext(null);

export function CartProvider({ children }) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [lastAdded, setLastAdded] = useState(null);

  /**
   * Adding does NOT open the cart.
   *
   * It used to, and that made a second item impossible to add: the cart is a
   * modal drawer, so its backdrop swallowed every click on the product row
   * behind it. You had to close the cart before each addition, which nobody
   * would guess. Now the badge counts up and a toast confirms, and the cart
   * opens only when you ask for it.
   */
  const add = useCallback((product, quantity = 1) => {
    setItems((prev) => {
      const existing = prev.find((i) => String(i.id) === String(product.id));
      if (existing) {
        return prev.map((i) =>
          String(i.id) === String(product.id)
            ? { ...i, quantity: i.quantity + quantity }
            : i
        );
      }
      return [...prev, { ...product, quantity }];
    });
    setLastAdded({ name: product.name, at: Date.now() });
  }, []);

  const remove = useCallback((id) => {
    setItems((prev) => prev.filter((i) => String(i.id) !== String(id)));
  }, []);

  const setQuantity = useCallback((id, quantity) => {
    setItems((prev) =>
      quantity <= 0
        ? prev.filter((i) => String(i.id) !== String(id))
        : prev.map((i) => (String(i.id) === String(id) ? { ...i, quantity } : i))
    );
  }, []);

  const clear = useCallback(() => setItems([]), []);

  const totals = useMemo(() => {
    const subtotal = items.reduce(
      (sum, i) => sum + (i.price_paise ?? 0) * (i.quantity ?? 1),
      0
    );
    const shipping = items.reduce(
      (sum, i) => sum + (i.shipping_cost_paise ?? 0),
      0
    );
    const count = items.reduce((sum, i) => sum + (i.quantity ?? 1), 0);
    return { subtotal_paise: subtotal, shipping_paise: shipping, count };
  }, [items]);

  const has = useCallback(
    (id) => items.some((i) => String(i.id) === String(id)),
    [items]
  );

  return (
    <CartContext.Provider
      value={{
        items, totals, open, setOpen, add, remove, setQuantity, clear, has,
        lastAdded, dismissAdded: () => setLastAdded(null),
      }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used inside CartProvider");
  return ctx;
}
