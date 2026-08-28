import { createContext, useContext } from "react";
import { useAgentSettings } from "../hooks/useAgentSettings";

/**
 * One settings instance for the whole app.
 *
 * The role preset buttons, the tune card inside a node, and the "tuned"
 * dots on the canvas all read and write the same values, so they have to
 * share state — applying the Seller preset above the canvas has to light
 * the dots below it in the same render. Holding this per-component would
 * also mean one /agent-settings fetch per conversation turn.
 */
const HiveSettingsContext = createContext(null);

export function HiveSettingsProvider({ children }) {
  const settings = useAgentSettings();
  return (
    <HiveSettingsContext.Provider value={settings}>{children}</HiveSettingsContext.Provider>
  );
}

export function useHiveSettings() {
  const ctx = useContext(HiveSettingsContext);
  if (!ctx) throw new Error("useHiveSettings must be used inside HiveSettingsProvider");
  return ctx;
}
