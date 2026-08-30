import { createContext, useCallback, useContext, useMemo, useState } from "react";

/**
 * WHICH SIDE OF THE COUNTER YOU ARE STANDING ON.
 *
 * This is deliberately not a "view mode" or a preference. In agentic commerce
 * the buyer and the merchant are counterparties in a protocol — AI Commerce Studio
 * discovers the demo store over UCP and is refused by it when it misbehaves.
 * Nothing in the real ecosystem models this as a switch: a merchant works in
 * Shopify Admin or the Stripe Dashboard, and the buyer is ChatGPT or Gemini.
 * They are different parties, not two skins on one screen.
 *
 * So this picks a party, and the app then shows that party's tools. The
 * switcher exists because one person is demonstrating both halves — the same
 * reason Airbnb lets a host switch to travelling — and it lives in the top
 * bar rather than only on the landing page, because being able to see the
 * other side in one click matters more than making the choice feel weighty.
 *
 * The role changes what the DATA MEANS, not just which links render. A
 * customer sees their own runs and their own orders; a merchant sees inbound
 * agent traffic against their store. Same Firestore rows, opposite ends of
 * the transaction. A role that only filtered a menu would be decoration.
 */

const STORAGE_KEY = "commerce-studio.role";

export const ROLES = {
  customer: {
    id: "customer",
    label: "Customer",
    // What this party does, in their own words — used on the landing cards.
    tagline: "Shop with the agent",
    blurb:
      "Give it a budget and a constraint. It has to get past the gate "
      + "before it can spend.",
    home: "/console",
  },
  merchant: {
    id: "merchant",
    label: "Merchant",
    tagline: "Sell to agents",
    blurb:
      "Publish a storefront agents can discover and pay. Watch what they "
      + "ask for — and what you refuse.",
    home: "/merchant",
  },
};

/** Routes only one party may open. Anything absent here is shared. */
export const ROUTE_ROLES = {
  "/hive": "customer",
  "/approvals": "customer",
  "/orders": "customer",
  "/merchant": "merchant",
};

function readStoredRole() {
  // Private windows, cleared site data and thumbnail capture can all make
  // this throw or come back empty, so an unreadable store just means the
  // landing page asks again.
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored && ROLES[stored] ? stored : null;
  } catch {
    return null;
  }
}

const RoleContext = createContext(null);

export function RoleProvider({ children }) {
  const [role, setRoleState] = useState(readStoredRole);

  const setRole = useCallback((next) => {
    if (!ROLES[next]) return;
    setRoleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // A role that cannot be remembered still works for this session.
    }
  }, []);

  const clearRole = useCallback(() => {
    setRoleState(null);
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* nothing to clean up */
    }
  }, []);

  const value = useMemo(
    () => ({
      role,
      profile: role ? ROLES[role] : null,
      setRole,
      clearRole,
      canOpen: (path) => !ROUTE_ROLES[path] || ROUTE_ROLES[path] === role,
    }),
    [role, setRole, clearRole]
  );

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRole() {
  const context = useContext(RoleContext);
  if (!context) throw new Error("useRole must be used inside a RoleProvider");
  return context;
}
