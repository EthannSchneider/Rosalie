// Une ligne de réglage : libellé, badges, aide, contrôle adapté au type, clé technique.
import Badge from "../ui/Badge.jsx";
import FieldControl from "./FieldControl.jsx";

function describe(value) {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "aucun";
  if (typeof value === "boolean") return value ? "oui" : "non";
  return value === "" ? "vide" : String(value);
}

export default function FieldRow({ field, settings }) {
  const id = `field-${field.key}`;
  const dirty = settings.draft.has(field.key);
  return (
    <div
      className={`grid gap-x-6 gap-y-2 border-l-3 px-4 py-4 sm:px-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)] ${
        dirty ? "border-l-amber-400" : "border-l-transparent"
      }`}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <label htmlFor={id} className="font-semibold">{field.label}</label>
          {field.restart && <Badge tone="warn" title="Pris en compte au prochain démarrage">redémarrage</Badge>}
          {field.modified && !dirty && (
            <button
              type="button"
              title={`Revenir à la valeur par défaut (${describe(field.default)})`}
              onClick={() => settings.change(field, null)}
              className="rounded-full border border-stone-200 bg-stone-100 px-2 py-0.5 text-xs text-stone-600 hover:border-rose-400 hover:text-rose-600 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-400"
            >
              ↺ défaut
            </button>
          )}
        </div>
        {field.help && <p className="mt-0.5 text-sm text-stone-500 dark:text-stone-400">{field.help}</p>}
        <code className="text-xs text-stone-400">{field.key}</code>
      </div>
      <div className="self-center">
        <FieldControl id={id} field={field} settings={settings} />
      </div>
    </div>
  );
}
