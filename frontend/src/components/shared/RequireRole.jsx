import { Navigate, useLocation } from "react-router-dom";

import { ROLES, ROUTE_ROLES, useRole } from "../../context/RoleContext";

/**
 * Keeps a party out of the other party's tools.
 *
 * Two distinct cases, and they deserve different answers:
 *
 *   No role chosen yet — someone deep-linked or reloaded with the choice
 *   cleared. Send them to the landing page to pick a side.
 *
 *   Wrong role — they were a customer and switched to merchant while sitting
 *   on /orders. Bouncing to the landing page here would be punitive and
 *   would lose the switch, so they land on the new role's home instead. The
 *   switch is the thing they asked for; the page was incidental.
 */
export default function RequireRole({ children }) {
  const { role } = useRole();
  const location = useLocation();

  // Prefix match, so /orders/cp-abc123 is gated exactly like /orders. An
  // exact lookup left every order-tracking page open to the merchant, which
  // is the one place a customer's individual purchases are on screen.
  const required = Object.entries(ROUTE_ROLES).find(
    ([path]) => location.pathname === path || location.pathname.startsWith(`${path}/`)
  )?.[1];
  if (!required) return children;

  if (!role) return <Navigate to="/" replace />;
  if (role !== required) return <Navigate to={ROLES[role].home} replace />;

  return children;
}
