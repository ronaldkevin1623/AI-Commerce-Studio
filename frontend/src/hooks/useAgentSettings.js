import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { API_BASE } from "../config";

/**
 * The hive's control surface, backed by the real /agent-settings API.
 *
 * The spec is fetched rather than hardcoded, so a parameter the backend
 * doesn't actually consume can never appear as a dial in the UI. Edits are
 * held locally until committed, then PATCHed — because a scrub that fired a
 * request per pixel would flood the audit trail with meaningless rows.
 */
export function useAgentSettings() {
  const [spec, setSpec] = useState(null);
  const [values, setValues] = useState(null);
  const [defaults, setDefaults] = useState(null);
  const [noTunables, setNoTunables] = useState({});
  const [presets, setPresets] = useState({});
  const [presetScope, setPresetScope] = useState([]);
  const [activePreset, setActivePreset] = useState(null);
  const [draft, setDraft] = useState({});
  const [status, setStatus] = useState("loading"); // loading | ready | saving | error
  const [lastChanged, setLastChanged] = useState([]);

  // Set on the way in as well as the way out: StrictMode mounts, unmounts
  // and remounts in development, and a flag only ever cleared would leave
  // every later setState silently dropped.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/agent-settings`);
      if (!res.ok) throw new Error("bad status");
      const data = await res.json();
      if (!mounted.current) return;
      setSpec(data.spec);
      setValues(data.values);
      setDefaults(data.defaults);
      setNoTunables(data.no_tunables ?? {});
      setPresets(data.presets ?? {});
      setPresetScope(data.preset_scope ?? []);
      setActivePreset(data.active_preset ?? null);
      setStatus("ready");
    } catch {
      if (mounted.current) setStatus("error");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  /** Effective value: the uncommitted draft if there is one, else the server's. */
  const valueOf = useCallback(
    (node, key) => draft[node]?.[key] ?? values?.[node]?.[key],
    [draft, values]
  );

  const setLocal = useCallback((node, key, value) => {
    setDraft((prev) => ({ ...prev, [node]: { ...prev[node], [key]: value } }));
  }, []);

  const discard = useCallback((node) => {
    setDraft((prev) => {
      if (!prev[node]) return prev;
      const next = { ...prev };
      delete next[node];
      return next;
    });
  }, []);

  const commit = useCallback(
    async (node) => {
      const patch = node ? { [node]: draft[node] } : draft;
      if (!patch || !Object.keys(patch).length) return [];
      const scoped = node && !draft[node] ? null : patch;
      if (!scoped) return [];

      setStatus("saving");
      try {
        const res = await fetch(`${API_BASE}/agent-settings`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ changes: scoped }),
        });
        if (!res.ok) throw new Error("bad status");
        const data = await res.json();
        if (!mounted.current) return [];
        setValues(data.values);
        setLastChanged(data.changed);
        setActivePreset(data.active_preset ?? null);
        if (node) discard(node);
        else setDraft({});
        setStatus("ready");
        return data.changed;
      } catch {
        if (mounted.current) setStatus("error");
        return [];
      }
    },
    [draft, discard]
  );

  const resetNode = useCallback(
    async (node) => {
      setStatus("saving");
      try {
        const res = await fetch(`${API_BASE}/agent-settings/reset`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ node }),
        });
        if (!res.ok) throw new Error("bad status");
        const data = await res.json();
        if (!mounted.current) return;
        setValues(data.values);
        setLastChanged(data.changed);
        setActivePreset(data.active_preset ?? null);
        discard(node);
        setStatus("ready");
      } catch {
        if (mounted.current) setStatus("error");
      }
    },
    [discard]
  );

  /**
   * What a preset would change, without changing anything — so the button
   * can show its work before it acts. Only keys the preset actually names
   * are compared, and anything already matching is left out.
   */
  const previewPreset = useCallback(
    (name) => {
      const preset = presets[name];
      if (!preset || !values || !spec) return [];
      const diff = [];
      for (const [node, params] of Object.entries(preset.values)) {
        for (const [key, next] of Object.entries(params)) {
          const current = values[node]?.[key];
          if (current === next) continue;
          diff.push({
            node,
            key,
            label: spec[node]?.[key]?.label ?? key,
            from: current,
            to: next,
            suffix: spec[node]?.[key]?.suffix,
            prefix: spec[node]?.[key]?.prefix,
          });
        }
      }
      return diff;
    },
    [presets, values, spec]
  );

  const applyPreset = useCallback(async (name) => {
    setStatus("saving");
    try {
      const res = await fetch(`${API_BASE}/agent-settings/preset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) throw new Error("bad status");
      const data = await res.json();
      if (!mounted.current) return [];
      setValues(data.values);
      setLastChanged(data.changed);
      setActivePreset(data.active_preset ?? null);
      setDraft({});
      setStatus("ready");
      return data.changed;
    } catch {
      if (mounted.current) setStatus("error");
      return [];
    }
  }, []);

  /** Nodes whose committed values differ from the shipped defaults. */
  const editedNodes = useMemo(() => {
    if (!values || !defaults) return new Set();
    const set = new Set();
    for (const [node, params] of Object.entries(values)) {
      for (const [key, value] of Object.entries(params)) {
        if (defaults[node]?.[key] !== value) set.add(node);
      }
    }
    return set;
  }, [values, defaults]);

  const dirtyNodes = useMemo(() => {
    const set = new Set();
    for (const [node, params] of Object.entries(draft)) {
      for (const [key, value] of Object.entries(params ?? {})) {
        if (values?.[node]?.[key] !== value) set.add(node);
      }
    }
    return set;
  }, [draft, values]);

  return {
    spec,
    values,
    defaults,
    noTunables,
    presets,
    presetScope,
    activePreset,
    previewPreset,
    applyPreset,
    status,
    lastChanged,
    valueOf,
    setLocal,
    commit,
    discard,
    resetNode,
    editedNodes,
    dirtyNodes,
    reload: load,
  };
}
