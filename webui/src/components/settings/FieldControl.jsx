// Le bon contrôle selon le type du réglage (libs/config/schema.py).
import { useEffect, useState } from "react";
import { getModels } from "../../api/settings.js";
import { useToast } from "../../context/ToastContext.jsx";
import Button from "../ui/Button.jsx";
import Toggle from "../ui/Toggle.jsx";
import { inputClass } from "../ui/styles.js";

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
    case "secret":
      return <SecretInput id={id} field={field} settings={settings} />;
    case "ids":
    case "list":
      return <ChipsInput id={id} numeric={field.kind === "ids"} value={value} onChange={set} />;
    case "persona":
      return (
        <select id={id} value={value} onChange={(e) => set(e.target.value)} className={inputClass}>
          {settings.state.personas.map((p) => (
            <option key={p.name} value={p.name}>{p.builtin ? `${p.name} (intégrée)` : p.name}</option>
          ))}
        </select>
      );
    case "model":
      return <ModelInput id={id} field={field} value={value} onChange={set} />;
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

function ChipsInput({ id, numeric, value, onChange }) {
  const toast = useToast();
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
    </div>
  );
}

let modelsPromise = null; // une seule requête à Ollama pour toute la page
function ModelInput({ id, field, value, onChange }) {
  const [models, setModels] = useState([]);
  useEffect(() => {
    modelsPromise ??= getModels().catch(() => []);
    let alive = true;
    modelsPromise.then((list) => alive && setModels(list));
    return () => {
      alive = false;
    };
  }, []);
  return (
    <>
      <input
        id={id}
        value={value}
        list={`${id}-models`}
        placeholder={field.key === "decider_model" ? "(même modèle)" : ""}
        spellCheck={false}
        autoComplete="off"
        onChange={(e) => onChange(e.target.value)}
        className={inputClass}
      />
      <datalist id={`${id}-models`}>
        {models.map((name) => <option key={name} value={name} />)}
      </datalist>
    </>
  );
}
