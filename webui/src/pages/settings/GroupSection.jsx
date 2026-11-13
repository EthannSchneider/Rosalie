import { Link } from "react-router-dom";
import FieldRow from "../../components/settings/FieldRow.jsx";
import Badge from "../../components/ui/Badge.jsx";
import Card from "../../components/ui/Card.jsx";
import { hintClass } from "../../components/ui/styles.js";

export default function GroupSection({ settings, group, first }) {
  const fields = settings.state.fields.filter((field) => field.group === group);
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
          À qui elle obéit sur Discord : aux comptes admin et superadmin liés à leur identifiant Discord (
          <Link className="text-rose-600 underline dark:text-rose-400" to="/users">Utilisateurs</Link> ou{" "}
          <Link className="text-rose-600 underline dark:text-rose-400" to="/account">Mon compte</Link>).
        </p>
      )}
      <Card className="divide-y divide-stone-200 overflow-hidden dark:divide-stone-800">
        {fields.map((field) => <FieldRow key={field.key} field={field} settings={settings} />)}
      </Card>
      {group === "Personnalité" && (
        <p className={`${hintClass} mt-3`}>
          Créer ou modifier une personnalité : <Link className="text-rose-600 underline dark:text-rose-400" to="/settings/personas">Personas</Link>.
        </p>
      )}
    </section>
  );
}
