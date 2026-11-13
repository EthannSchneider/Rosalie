// Personnalités : les intégrées (personas/*.md) sont en lecture seule ; les autres se créent,
// se dupliquent, se modifient, se renomment, se suppriment et s'activent.
import { useEffect, useState } from "react";
import { activatePersona, deletePersona, getPersona, renamePersona, savePersona } from "../../api/settings.js";
import Badge from "../../components/ui/Badge.jsx";
import Button from "../../components/ui/Button.jsx";
import Card from "../../components/ui/Card.jsx";
import { hintClass } from "../../components/ui/styles.js";
import { useDialog } from "../../context/DialogContext.jsx";
import { useToast } from "../../context/ToastContext.jsx";

export default function PersonasSection({ settings }) {
  const toast = useToast();
  const { ask, confirm } = useDialog();
  const personas = settings.state.personas;
  const active = personas.find((p) => p.active)?.name;
  const [current, setCurrent] = useState(null); // { name, text, builtin, isNew }
  const [text, setText] = useState("");
  const dirty = current && !current.builtin && (current.isNew || text !== current.text);

  const open = async (name) => {
    if (dirty && !window.confirm("Abandonner les modifications de cette personnalité ?")) return;
    try {
      const persona = await getPersona(name);
      setCurrent({ ...persona, isNew: false });
      setText(persona.text);
    } catch (error) {
      toast(error.message, "error");
    }
  };

  // Au départ (et après une suppression) : on ouvre la personnalité active
  const first = active ?? personas[0]?.name;
  useEffect(() => {
    if (!current && first) open(first);
  }, [current, first]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (action, success) => {
    try {
      const result = await action();
      if (result?.state) settings.setState(result.state);
      if (success) toast(success);
      return true;
    } catch (error) {
      toast(error.message, "error");
      return false;
    }
  };

  const create = async (source) => {
    if (dirty && !window.confirm("Abandonner les modifications de cette personnalité ?")) return;
    const name = await ask(source
      ? { title: `Dupliquer « ${source.name} »`, label: "Nom de la copie", value: `${source.name}-perso` }
      : { title: "Nouvelle personnalité", label: "Nom (minuscules, chiffres, - et _)" });
    if (!name) return;
    setCurrent({ name: name.toLowerCase(), text: "", builtin: false, isNew: true });
    setText(source ? text : "");
  };

  const store = async () => {
    const ok = await run(() => savePersona(current.name, text, current.isNew), current.isNew ? `« ${current.name} » créée.` : "Personnalité enregistrée.");
    if (ok) setCurrent({ ...current, text, isNew: false });
  };

  const use = () => run(() => activatePersona(current.name), `Rosalie utilise maintenant « ${current.name} ».`);

  const rename = async () => {
    const name = await ask({ title: `Renommer « ${current.name} »`, label: "Nouveau nom", value: current.name });
    if (!name || name === current.name) return;
    if (await run(() => renamePersona(current.name, name), "Renommée.")) setCurrent({ ...current, name: name.toLowerCase() });
  };

  const remove = async () => {
    const ok = await confirm({
      title: `Supprimer « ${current.name} » ?`,
      message: current.name === active ? "C'est la personnalité active : Rosalie reviendra à « rosalie »." : "Cette action est définitive.",
      confirmLabel: "Supprimer",
      danger: true,
    });
    if (ok && (await run(() => deletePersona(current.name), "Supprimée."))) setCurrent(null);
  };

  const item = (selected) =>
    `flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left ${
      selected ? "border-stone-200 bg-white shadow-sm dark:border-stone-700 dark:bg-stone-900" : "border-transparent hover:bg-stone-200/60 dark:hover:bg-stone-800"
    }`;

  return (
    <section>
      <h1 className="mb-1.5 text-2xl font-bold">Personas</h1>
      <p className={`${hintClass} mb-4`}>
        Le prompt système de son personnage. Les personnalités intégrées (fichiers personas/*.md) sont en lecture seule :
        duplique-les pour partir d'elles.
      </p>
      <div className="grid items-start gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
        <div className="flex flex-wrap gap-1 lg:flex-col">
          {personas.map((p) => (
            <button key={p.name} type="button" onClick={() => open(p.name)} className={item(current?.name === p.name && !current?.isNew)}>
              <span className="font-mono text-sm [overflow-wrap:anywhere]">{p.name}</span>
              <span className="flex gap-1">
                {p.active && <Badge tone="accent">active</Badge>}
                {p.builtin && <Badge>intégrée</Badge>}
              </span>
            </button>
          ))}
          {current?.isNew && (
            <span className={item(true)}>
              <span className="font-mono text-sm">{current.name}</span>
              <Badge>nouvelle</Badge>
            </span>
          )}
          <Button variant="ghost" className="mt-2" onClick={() => create(null)}>+ Nouvelle personnalité</Button>
        </div>

        {current && (
          <Card className="p-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <h2 className="font-mono font-semibold">{current.name}</h2>
              {current.name === active && !current.isNew && <Badge tone="accent">active</Badge>}
              {current.builtin && <Badge>intégrée · lecture seule</Badge>}
              <div className="ml-auto flex flex-wrap gap-2">
                {!current.isNew && current.name !== active && <Button variant="ghost" size="sm" onClick={use}>Utiliser</Button>}
                {!current.isNew && <Button variant="ghost" size="sm" onClick={() => create(current)}>Dupliquer</Button>}
                {!current.builtin && !current.isNew && <Button variant="ghost" size="sm" onClick={rename}>Renommer</Button>}
                {!current.builtin && !current.isNew && <Button variant="danger" size="sm" onClick={remove}>Supprimer</Button>}
              </div>
            </div>
            <textarea
              value={text}
              readOnly={current.builtin}
              onChange={(e) => setText(e.target.value)}
              aria-label={`Texte de la personnalité ${current.name}`}
              className="min-h-[55vh] w-full resize-y rounded-lg border border-stone-300 bg-white p-3 font-mono text-sm leading-relaxed focus:border-rose-500 focus:ring-3 focus:ring-rose-500/20 focus:outline-none read-only:bg-stone-100 read-only:text-stone-500 dark:border-stone-700 dark:bg-stone-950 dark:read-only:bg-stone-900"
            />
            <div className="mt-3 flex items-center justify-between gap-3">
              <span className="text-sm text-stone-500">{text.length} caractères</span>
              {!current.builtin && <Button disabled={!dirty} onClick={store}>{current.isNew ? "Créer" : "Enregistrer"}</Button>}
            </div>
          </Card>
        )}
      </div>
    </section>
  );
}
