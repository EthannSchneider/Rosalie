// Le bon contrôle selon le type du réglage (libs/config/schema.py).
import { useEffect, useState } from "react";
import { getModels } from "../../api/settings.js";
import { useToast } from "../../context/ToastContext.jsx";
import Button from "../ui/Button.jsx";
import Toggle from "../ui/Toggle.jsx";
import { inputClass } from "../ui/styles.js";

export const PROVIDER_LABELS = { ollama: "Ollama", openai: "OpenAI", anthropic: "Anthropic", gemini: "Gemini" };
const MODEL_EXAMPLES = { openai: "gpt-4o-mini", anthropic: "claude-sonnet-5-5", gemini: "gemini-2.5-flash" };

/** « fournisseur:nom » -> [fournisseur, nom] ; sans préfixe connu : Ollama (comme split_model côté serveur). */
export function splitModel(ref) {
  const at = ref.indexOf(":");
  const head = ref.slice(0, at);
  if (at > 0 && head in PROVIDER_LABELS) return [head, ref.slice(at + 1)];
  return ["ollama", ref];
}

export default function FieldControl({ id, field, settings }) {
  const value = settings.valueOf(field);
  const set = (next) => settings.change(field, next);

  switch (field.kind) {
    case "bool":
      return <Toggle id={id} checked={Boolean(value)} onChange={set} />;
    case "int":
    case "float":
      return <NumberInput id={id} field={field} value={value} onChange={set} />;
    case "choice":
      return (
        <div role="radiogroup" id={id} className="inline-flex flex-wrap rounded-xl border border-stone-200 bg-stone-100 p-1 dark:border-stone-700 dark:bg-stone-800">
          {field.choices.map((choice) => (
            <button
              key={choice}
              type="button"
              role="radio"
              aria-checked={choice === value}
              onClick={() => set(choice)}
              className={`rounded-lg px-3.5 py-1 ${choice === value ? "bg-white font-semibold shadow-sm dark:bg-stone-950" : "text-stone-500"}`}
            >
              {choice}
            </button>
          ))}
        </div>
      );
    case "choices":
      return (
        <div id={id} role="group" className="flex flex-wrap gap-1.5">
          {field.choices.map((choice) => {
            const on = value.includes(choice);
            return (
              <button
                key={choice}
                type="button"
                aria-pressed={on}
                onClick={() => set(field.choices.filter((c) => (c === choice ? !on : value.includes(c))))}
                className={`rounded-lg border px-3.5 py-1 ${
                  on
                    ? "border-rose-300 bg-rose-100 font-semibold text-rose-700 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-300"
                    : "border-stone-200 bg-stone-100 text-stone-500 dark:border-stone-700 dark:bg-stone-800"
                }`}
              >
                {on ? "✓ " : ""}{PROVIDER_LABELS[choice] ?? choice}
              </button>
            );
          })}
        </div>
      );
    case "secret":
      return <SecretInput id={id} field={field} settings={settings} />;
    case "ids":
    case "list":
      return (
        <ChipsInput id={id} numeric={field.kind === "ids"} value={value} onChange={set} suggest={field.key === "ollama_allowed_models"} />
      );
    case "persona":
      return (
        <select id={id} value={value} onChange={(e) => set(e.target.value)} className={inputClass}>
          {settings.state.personas.map((p) => (
            <option key={p.name} value={p.name}>{p.builtin ? `${p.name} (intégrée)` : p.name}</option>
          ))}
        </select>
      );
    case "model":
      return <ModelInput id={id} field={field} settings={settings} value={value} onChange={set} />;
    default:
      return (
        <input
          id={id}
          value={value}
          onChange={(e) => set(e.target.value)}
          placeholder={field.kind === "hours" ? "23-8" : field.default || ""}
          spellCheck={false}
          autoComplete="off"
          className={inputClass}
        />
      );
  }
}

function NumberInput({ id, field, value, onChange }) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);
  return (
    <input
      id={id}
      type="number"
      value={text}
      min={field.min ?? undefined}
      max={field.max ?? undefined}
      step={field.kind === "float" ? "0.1" : "1"}
      inputMode={field.kind === "float" ? "decimal" : "numeric"}
      onChange={(e) => {
        setText(e.target.value);
        const number = Number(e.target.value);
        if (e.target.value !== "" && !Number.isNaN(number)) onChange(number);
      }}
      className={inputClass}
    />
  );
}

function SecretInput({ id, field, settings }) {
  const pending = settings.draft.has(field.key);
  const cleared = pending && settings.draft.get(field.key) === null;
  const isSet = field.is_set && !cleared;
  return (
    <div className="flex gap-2">
      <input
        id={id}
        type="password"
        autoComplete="new-password"
        value={pending && !cleared ? settings.draft.get(field.key) : ""}
        placeholder={isSet ? "•••••••• défini" : "(vide)"}
        onChange={(e) => (e.target.value ? settings.change(field, e.target.value) : settings.forget(field.key))}
        className={inputClass}
      />
      {isSet && <Button variant="ghost" size="sm" onClick={() => settings.change(field, null)}>Effacer</Button>}
    </div>
  );
}

function ChipsInput({ id, numeric, value, onChange, suggest = false }) {
  const toast = useToast();
  const installed = useOllamaModels(suggest);
  const [text, setText] = useState("");
  const commit = () => {
    const parts = text.split(numeric ? /[\s,]+/ : /,/).map((p) => p.trim()).filter(Boolean);
    if (!parts.length) return;
    if (numeric && parts.some((p) => !/^\d+$/.test(p))) {
      toast("Un identifiant Discord ne contient que des chiffres.", "error");
      return;
    }
    onChange([...value, ...parts.filter((p) => !value.includes(p))]);
    setText("");
  };
  return (
    <div className="flex cursor-text flex-wrap gap-1.5 rounded-lg border border-stone-300 bg-white p-1.5 focus-within:border-rose-500 focus-within:ring-3 focus-within:ring-rose-500/20 dark:border-stone-700 dark:bg-stone-900">
      {value.map((item) => (
        <span key={item} className="inline-flex max-w-full items-center gap-0.5 rounded-full bg-rose-100 py-0.5 pr-1 pl-2.5 font-mono text-sm text-rose-700 [overflow-wrap:anywhere] dark:bg-rose-950 dark:text-rose-300">
          {item}
          <button type="button" aria-label={`Retirer ${item}`} onClick={() => onChange(value.filter((v) => v !== item))} className="rounded-full px-1.5 hover:bg-rose-200 dark:hover:bg-rose-900">
            ×
          </button>
        </span>
      ))}
      <input
        id={id}
        value={text}
        inputMode={numeric ? "numeric" : "text"}
        list={suggest ? `${id}-suggestions` : undefined}
        placeholder={numeric ? "Ajouter un identifiant…" : "Ajouter…"}
        spellCheck={false}
        autoComplete="off"
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit();
          } else if (e.key === "Backspace" && !text && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
        className="min-w-36 flex-1 bg-transparent px-1.5 py-1 outline-none"
      />
      {suggest && (
        <datalist id={`${id}-suggestions`}>
          {installed.filter((name) => !value.includes(name)).map((name) => <option key={name} value={name} />)}
        </datalist>
      )}
    </div>
  );
}

let modelsPromise = null; // une seule requête à Ollama pour toute la page
/** Modèles installés dans Ollama (vide si injoignable, ou si `enabled` est faux). */
function useOllamaModels(enabled) {
  const [models, setModels] = useState([]);
  useEffect(() => {
    if (!enabled) return undefined;
    modelsPromise ??= getModels().catch(() => []);
    let alive = true;
    modelsPromise.then((list) => alive && setModels(list));
    return () => {
      alive = false;
    };
  }, [enabled]);
  return models;
}

/** Un modèle = un fournisseur (parmi ceux activés dans Providers) + un nom. Valeur : « fournisseur:nom ». */
function ModelInput({ id, field, settings, value, onChange }) {
  const optional = field.default === ""; // vide permis : « même modèle que le principal »
  const [provider, name] = value ? splitModel(value) : ["", ""];
  const enabled = settings.valueOf(settings.fields.get("providers"));
  const possible = field.choices.length ? field.choices : Object.keys(PROVIDER_LABELS);
  const providers = possible.filter((p) => enabled.includes(p) || p === provider);
  const allowed = settings.valueOf(settings.fields.get("ollama_allowed_models"));
  const installed = useOllamaModels(provider === "ollama");
  const restricted = provider === "ollama" && allowed.length > 0;

  const pick = (next) => {
    if (!next) return onChange("");
    // nom repris seulement s'il a un sens chez ce fournisseur
    const first = next === "ollama" ? allowed[0] ?? installed[0] ?? "" : "";
    return onChange(`${next}:${first}`);
  };
  return (
    <div className="flex flex-wrap gap-2 sm:flex-nowrap">
      <select
        aria-label="Fournisseur"
        value={provider}
        onChange={(e) => pick(e.target.value)}
        className={`${inputClass} sm:w-40 sm:shrink-0`}
      >
        {optional && <option value="">(modèle principal)</option>}
        {providers.map((p) => (
          <option key={p} value={p}>{PROVIDER_LABELS[p]}{enabled.includes(p) ? "" : " (désactivé)"}</option>
        ))}
      </select>
      {provider && restricted && (
        <select id={id} value={name} onChange={(e) => onChange(`ollama:${e.target.value}`)} className={inputClass}>
          {!allowed.includes(name) && <option value={name}>{name ? `${name} (non autorisé)` : "Choisir…"}</option>}
          {allowed.map((model) => <option key={model} value={model}>{model}</option>)}
        </select>
      )}
      {provider && !restricted && (
        <>
          <input
            id={id}
            value={name}
            list={`${id}-models`}
            placeholder={MODEL_EXAMPLES[provider] ?? "nom du modèle"}
            spellCheck={false}
            autoComplete="off"
            onChange={(e) => onChange(`${provider}:${e.target.value}`)}
            className={inputClass}
          />
          <datalist id={`${id}-models`}>
            {(provider === "ollama" ? installed : []).map((model) => <option key={model} value={model} />)}
          </datalist>
        </>
      )}
    </div>
  );
}
