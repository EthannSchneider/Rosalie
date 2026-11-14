import { Link } from "react-router-dom";
import { PROVIDER_LABELS } from "../../components/settings/FieldControl.jsx";
import FieldRow from "../../components/settings/FieldRow.jsx";
import Badge from "../../components/ui/Badge.jsx";
import Card from "../../components/ui/Card.jsx";
import { hintClass } from "../../components/ui/styles.js";

export default function GroupSection({ settings, group, first }) {
  const all = settings.state.fields.filter((field) => field.group === group);
  // Providers : le choix des fournisseurs, puis une carte de configuration par fournisseur activé
  const byProvider = group === "Providers";
  const fields = byProvider ? all.filter((field) => field.key === "providers") : all;
  const enabled = byProvider ? settings.valueOf(settings.fields.get("providers")) : [];
  return (
    <section>
      <h1 className="mb-1.5 text-2xl font-bold">{group}</h1>
      {first && (
        <p className={`${hintClass} mb-4`}>
          Les changements sont appliqués à chaud (au plus une seconde après). Ceux marqués <Badge tone="warn">redémarrage</Badge>{" "}
          attendent le prochain lancement.
        </p>
      )}
      {group === "Discord" && (
        <p className={`${hintClass} mb-4`}>
          À qui elle obéit sur Discord : aux comptes liés à leur identifiant Discord dont le rôle a la permission
          « Faire agir Rosalie » (<Link className="text-rose-600 underline dark:text-rose-400" to="/users">Utilisateurs</Link>,{" "}
          <Link className="text-rose-600 underline dark:text-rose-400" to="/roles">Rôles</Link> ou{" "}
          <Link className="text-rose-600 underline dark:text-rose-400" to="/account">Mon compte</Link>).
        </p>
      )}
      {group === "Modèles" && (
        <p className={`${hintClass} mb-4`}>
          Chaque usage a son modèle, chez le fournisseur de ton choix : on peut mélanger (par exemple un modèle
          principal OpenAI et des embeddings Ollama). Les fournisseurs proposés sont ceux activés dans{" "}
          <Link className="text-rose-600 underline dark:text-rose-400" to="/settings/providers">Providers</Link>.
        </p>
      )}
      <Card className="divide-y divide-stone-200 overflow-hidden dark:divide-stone-800">
        {fields.map((field) => <FieldRow key={field.key} field={field} settings={settings} />)}
      </Card>
      {enabled.map((provider) => (
        <div key={provider}>
          <h2 className="mt-6 mb-2 text-lg font-semibold">{PROVIDER_LABELS[provider]}</h2>
          <Card className="divide-y divide-stone-200 overflow-hidden dark:divide-stone-800">
            {all.filter((field) => field.key.startsWith(`${provider}_`)).map((field) => (
              <FieldRow key={field.key} field={field} settings={settings} />
            ))}
          </Card>
        </div>
      ))}
      {byProvider && (
        <p className={`${hintClass} mt-3`}>
          Quel modèle pour quel usage : <Link className="text-rose-600 underline dark:text-rose-400" to="/settings/modeles">Modèles</Link>.
        </p>
      )}
      {group === "Personnalité" && (
        <p className={`${hintClass} mt-3`}>
          Créer ou modifier une personnalité : <Link className="text-rose-600 underline dark:text-rose-400" to="/settings/personas">Personas</Link>.
        </p>
      )}
    </section>
  );
}
