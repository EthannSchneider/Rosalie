// Interrupteur oui / non (une vraie case à cocher, accessible au clavier).
export default function Toggle({ id, checked, onChange, label }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-3">
      <input id={id} type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span
        aria-hidden="true"
        className="relative h-6 w-11 rounded-full bg-stone-300 transition peer-checked:bg-rose-600 peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-rose-500 after:absolute after:top-1 after:left-1 after:h-4 after:w-4 after:rounded-full after:bg-white after:shadow after:transition peer-checked:after:translate-x-5 dark:bg-stone-700 dark:peer-checked:bg-rose-500"
      />
      <span className="text-sm text-stone-500 peer-checked:text-stone-900 dark:peer-checked:text-stone-100">
        {label ?? (checked ? "oui" : "non")}
      </span>
    </label>
  );
}
