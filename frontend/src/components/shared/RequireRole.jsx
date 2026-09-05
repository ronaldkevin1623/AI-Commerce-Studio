import { useEffect } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { ROLES, ROUTE_ROLES, useRole } from "../../context/RoleContext";

/**
 * Keeps a party out of the other party's tools.
 *
 * Two distinct cases, and they deserve different answers:
 *
 *   No role chosen yet — someone deep-linked or reloaded with the choice
 *   cleared. The URL already says which side they want, so take it: a link
 *   to /merchant/growth is a request to be the merchant, and answering it
 *   with the landing page makes a working deep link look like a broken one.
 *   The role is then remembered, so a reload or a later /orders link
 *   behaves exactly as if they had picked it on the way in.
 *
 *   This is not a hole in a boundary, because there is no boundary here to
 *   open. The switcher in the top bar changes party in one click for
 *   anybody; the role decides WHICH TOOLS ARE ON SCREEN, not what a person
 *   is allowed to see. Adopting it from the URL grants nothing that a click
 *   would not. Authorisation over data lives in the API, not in this
 *   component. A URL with no role at all still goes to the landing page,
 *   because then nothing has been asked for.
 *
 *   Wrong role — they were a customer and switched to merchant while sitting
 *   on /orders. Bouncing to the landing page here would be punitive and
 *   would lose the switch, so they land on the new role's home instead. The
 *   switch is the thing they asked for; the page was incidental.
 */
export default function RequireRole({ children }) {
  const { role, setRole } = useRole();
  const location = useLocation();

  // Prefix match, so /orders/cp-abc123 is gated exactly like /orders. An
  // exact lookup left every order-tracking page open to the merchant, which
  // is the one place a customer's individual purchases are on screen.
  const required = Object.entries(ROUTE_ROLES).find(
    ([path]) => location.pathname === path || location.pathname.startsWith(`${path}/`)
  )?.[1];
  // Before any early return: hooks cannot be conditional. Adopting the
  // role is a state change, so it belongs in an effect rather than in the
  // render pass that noticed it was needed.
  useEffect(() => {
    if (!role && required) setRole(required);
  }, [role, required, setRole]);

  if (!required) return children;

  // One frame with nothing on screen while the effect above lands, rather
  // than rendering the page with a null role — the children read the role
  // to decide what they are showing, and a merchant page that renders once
  // as nobody is how a dashboard flashes empty before it fills.
  if (!role) return null;

  if (role !== required) return <Navigate to={ROLES[role].home} replace />;

  return children;
}
