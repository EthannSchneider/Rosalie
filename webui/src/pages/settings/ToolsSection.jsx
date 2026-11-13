// Outils : cases à cocher (activé = proposé au modèle), filtre, tout activer / désactiver.
import { useState } from "react";
import Badge from "../../components/ui/Badge.jsx";
import Button from "../../components/ui/Button.jsx";
import Card from "../../components/ui/Card.jsx";
import { hintClass, inputClass } from "../../components/ui/styles.js";

export default function ToolsSection({ settings }) {
  const [filter, setFilter] = useState("");
  const field = settings.fields.get("disabled_tools");
  const tools = settings.state.tools;
  const disabled = new Set(settings.valueOf(field));
  const query = filter.trim().toLowerCase();
  const visible = tools.filter((t) => !query || t.name.includes(query) || t.description.toLowerCase().includes(query));

  const apply = (next) => settings.change(field, tools.map((t) => t.name).filter((name) => next.has(name)));
  const toggle = (name, enabled) => {
    const next = new Set(disabled);
    if (enabled) next.delete(name);
    else next.add(name);
    apply(next);
  };
  const toggleAll = (enabled) => {
    const next = new Set(disabled);
    for (const tool of visible) enabled ? next.delete(tool.name) : next.add(tool.name);
    apply(next);
  };

  const groups = new Map();
  for (const tool of visible) {
    const group = tool.requires ? `Interface ${tool.requires}` : "Général";
    groups.set(group, [...(groups.get(group) ?? []), tool]);
  }

  return (
    <section>
      <h1 className="mb-1.5 text-2xl font-bold">Outils</h1>
      <p className={`${hintClass} mb-4`}>
        {tools.length - disabled.size} / {tools.length} activés. {field.help}
      </p>
      <div className="mb-4 flex flex-wrap gap-2">
        <input type="search" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filtrer les outils…" className={`${inputClass} min-w-0 flex-[1_1_220px]`} />
        <Button variant="ghost" size="sm" onClick={() => toggleAll(true)}>Tout activer</Button>
        <Button variant="ghost" size="sm" onClick={() => toggleAll(false)}>Tout désactiver</Button>
      </div>
      {groups.size === 0 && <p className={hintClass}>Aucun outil ne correspond.</p>}
      {[...groups].map(([group, list]) => (
        <Card key={group} className="mb-4 p-2 pt-4">
          <h2 className="mb-1 px-3 font-semibold">{group}</h2>
          {list.map((tool) => (
            <label key={tool.name} className="flex cursor-pointer items-start gap-3 rounded-lg px-3 py-2.5 hover:bg-stone-100 dark:hover:bg-stone-800">
              <input type="checkbox" className="mt-1 h-4 w-4 shrink-0 accent-rose-600" checked={!disabled.has(tool.name)} onChange={(e) => toggle(tool.name, e.target.checked)} />
              <span className="min-w-0">
                <span className="flex flex-wrap items-center gap-1.5">
                  <code className="font-mono text-sm font-semibold">{tool.name}</code>
                  {tool.confirm && <Badge tone="warn" title="Demande ta confirmation">confirmation</Badge>}
                  {tool.guest && <Badge title="Permis aux non-owners">invités</Badge>}
                  {tool.web && <Badge title="Désactivé si l'accès internet est coupé">internet</Badge>}
                </span>
                <span className="block text-sm text-stone-500 dark:text-stone-400">{tool.description}</span>
              </span>
            </label>
          ))}
        </Card>
      ))}
    </section>
  );
}
