// Carte centrée commune aux pages d'installation et de connexion.
import { useState } from "react";
import { useSession } from "../../context/SessionContext.jsx";
import Button from "../../components/ui/Button.jsx";

export default function AuthCard({ title, intro, submitLabel, onSubmit, children }) {
  const { session } = useSession();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await onSubmit(Object.fromEntries(new FormData(event.currentTarget)));
    } catch (failure) {
      setError(failure.message);
      setBusy(false);
    }
  };

  return (
    <main className="grid min-h-dvh place-items-center px-4 py-6">
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-4 rounded-2xl border border-stone-200 bg-white p-7 shadow-sm dark:border-stone-800 dark:bg-stone-900">
        <div className="flex items-center gap-2 font-semibold text-rose-600 dark:text-rose-400">
          <img src="/favicon.svg" alt="" className="h-7 w-7" />
          {session?.name}
        </div>
        <h1 className="text-2xl font-bold">{title}</h1>
        {intro && <p className="text-sm text-stone-500 dark:text-stone-400">{intro}</p>}
        {children}
        <p role="alert" className="min-h-5 text-sm text-red-600 dark:text-red-400">{error}</p>
        <Button type="submit" disabled={busy} className="w-full py-2.5">
          {submitLabel}
        </Button>
      </form>
    </main>
  );
}

export function AuthField({ label, ...props }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm font-medium">
      {label}
      <input
        className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 font-normal focus:border-rose-500 focus:ring-3 focus:ring-rose-500/20 focus:outline-none dark:border-stone-700 dark:bg-stone-950"
        spellCheck={false}
        {...props}
      />
    </label>
  );
}
