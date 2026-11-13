import { useEffect } from "react";
import { useToast } from "../../context/ToastContext.jsx";
import Button from "../ui/Button.jsx";

export default function SaveBar({ settings }) {
  const toast = useToast();
  const count = settings.draft.size;

  const save = async () => {
    try {
      const changed = await settings.save();
      const later = changed.filter((key) => settings.fields.get(key)?.restart);
      toast(later.length ? `Enregistré. À redémarrer pour : ${later.join(", ")}` : "Enregistré — Rosalie l'applique tout de suite.");
    } catch (error) {
      toast(error.message, "error");
    }
  };

  useEffect(() => {
    const shortcut = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "s" && count) {
        event.preventDefault();
        save();
      }
    };
    document.addEventListener("keydown", shortcut);
    return () => document.removeEventListener("keydown", shortcut);
  });

  if (!count) return null;
  return (
    <div className="fixed inset-x-4 bottom-5 z-30 mx-auto flex max-w-xl flex-wrap items-center justify-between gap-3 rounded-2xl bg-stone-900 py-2.5 pr-2.5 pl-5 text-stone-50 shadow-2xl dark:bg-stone-100 dark:text-stone-900">
      <span>{count > 1 ? `${count} modifications non enregistrées` : "1 modification non enregistrée"}</span>
      <div className="flex gap-2">
        <Button variant="plain" className="text-stone-300 hover:bg-white/10 hover:text-white dark:text-stone-600 dark:hover:bg-black/10 dark:hover:text-black" disabled={settings.saving} onClick={settings.discard}>
          Annuler
        </Button>
        <Button disabled={settings.saving} onClick={save}>{settings.saving ? "…" : "Enregistrer"}</Button>
      </div>
    </div>
  );
}
