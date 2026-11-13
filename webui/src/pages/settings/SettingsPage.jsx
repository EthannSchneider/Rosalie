// Réglages de Rosalie (superadmin) : une sous-page par groupe (/settings/ollama…), une page
// Outils et une page Personas. Les modifications s'accumulent dans une barre Enregistrer/Annuler.
import { useEffect } from "react";
import { Navigate, NavLink, Outlet, useBlocker, useOutletContext } from "react-router-dom";
import SaveBar from "../../components/settings/SaveBar.jsx";
import Loading from "../../components/ui/Loading.jsx";
import useSettings from "../../hooks/useSettings.js";

export default function SettingsPage() {
  const settings = useSettings();
  const dirty = settings.draft.size > 0;

  // Quitter la page avec des modifications non enregistrées : on demande
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    dirty && !nextLocation.pathname.startsWith("/settings") && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm("Quitter sans enregistrer les réglages ?")) blocker.proceed();
    else blocker.reset();
  }, [blocker]);
  useEffect(() => {
    const warn = (event) => dirty && event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  if (settings.error) return <Loading text={`Oups : ${settings.error}`} />;
  if (!settings.state) return <Loading />;

  const count = (label) => [...settings.draft.keys()].filter((key) => settings.fields.get(key)?.group === label).length;
  return (
    <div className="mx-auto grid w-full max-w-6xl gap-4 px-4 pt-4 pb-32 md:grid-cols-[210px_minmax(0,1fr)] md:gap-8 md:px-6 md:pt-6">
      <nav aria-label="Sections des réglages" className="-mx-4 flex gap-1 overflow-x-auto px-4 [scrollbar-width:none] md:sticky md:top-20 md:mx-0 md:flex-col md:self-start md:px-0">
        {settings.sections.map(({ label, slug }) => (
          <NavLink
            key={slug}
            to={`/settings/${slug}`}
            className={({ isActive }) =>
              `flex shrink-0 items-center justify-between gap-2 rounded-lg px-3 py-2 ${
                isActive
                  ? "bg-rose-100 font-semibold text-rose-700 dark:bg-rose-950 dark:text-rose-300"
                  : "text-stone-500 hover:bg-stone-200/60 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-100"
              }`
            }
          >
            {label}
            {count(label) > 0 && <span className="min-w-5 rounded-full bg-amber-400 px-1.5 text-center text-xs text-black">{count(label)}</span>}
          </NavLink>
        ))}
      </nav>
      <div className="min-w-0">
        <Outlet context={settings} />
      </div>
      <SaveBar settings={settings} />
    </div>
  );
}

/** /settings : première section. */
export function SettingsIndex() {
  const settings = useOutletContext();
  return <Navigate to={`/settings/${settings.sections[0].slug}`} replace />;
}
