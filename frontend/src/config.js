/**
 * Where the backend lives.
 *
 * These were hardcoded as literal "http://localhost:8000" in eight separate
 * files, which meant moving the API — even temporarily, to get around a port
 * Windows had wedged — was an eight-file edit. One place, overridable from
 * the environment, costs nothing and removes that.
 */
export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export const WS_URL =
  import.meta.env.VITE_WS_URL ?? API_BASE.replace(/^http/, "ws") + "/ws/agent";

export const RAZORPAY_KEY_ID = import.meta.env.VITE_RAZORPAY_KEY_ID;
