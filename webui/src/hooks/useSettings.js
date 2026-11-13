// Réglages de Rosalie : l'état du serveur + un brouillon des modifications pas encore enregistrées.
// draft : clé -> nouvelle valeur (null = revenir à la valeur par défaut).
import { useCallback, useEffect, useMemo, useState } from "react";
import { getSettings, saveSettings } from "../api/settings.js";

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

export function slugify(text) {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

/** user : le compte connecté (les sections dépendent de ses permissions). */
export default function useSettings(user) {
  const [state, setState] = useState(null);
  const [draft, setDraft] = useState(new Map());
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setState(await getSettings());
    } catch (failure) {
      setError(failure.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const fields = useMemo(() => new Map((state?.fields ?? []).map((f) => [f.key, f])), [state]);

  /** Valeur affichée : brouillon, sinon valeur enregistrée (les secrets ne sont jamais renvoyés). */
  const valueOf = useCallback(
    (field) => {
      if (draft.has(field.key)) return draft.get(field.key) ?? field.default;
      return field.secret ? "" : field.value;
    },
    [draft],
  );

  const change = useCallback((field, value) => {
    setDraft((current) => {
      const next = new Map(current);
      if (!field.secret && value !== null && same(value, field.value)) next.delete(field.key);
      else next.set(field.key, value);
      return next;
    });
  }, []);

  const forget = useCallback((key) => {
    setDraft((current) => {
      const next = new Map(current);
      next.delete(key);
      return next;
    });
  }, []);

  /** Enregistre le brouillon ; renvoie les clés modifiées. */
  const save = useCallback(async () => {
    setSaving(true);
    try {
      const result = await saveSettings(Object.fromEntries(draft));
      setState(result.state);
      setDraft(new Map());
      return result.changed;
    } finally {
      setSaving(false);
    }
  }, [draft]);

  const sections = useMemo(() => {
    const labels = [];
    if (user.permissions.includes("settings")) labels.push(...(state?.groups ?? []));
    if (user.permissions.includes("personas")) labels.push("Personas");
    return labels.map((label) => ({ label, slug: slugify(label) }));
  }, [state, user]);

  return {
    state, setState, error, fields, sections, draft, valueOf, change, forget, saving, save, reload: load,
    discard: () => setDraft(new Map()),
  };
}
