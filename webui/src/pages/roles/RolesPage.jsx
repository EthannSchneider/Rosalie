// Rôles (permission « roles ») : leurs permissions, créer, supprimer.
// superadmin est verrouillé (toujours toutes les permissions). On ne donne ni ne retire une
// permission qu'on n'a pas soi-même (même règle que le serveur).
import { useCallback, useEffect, useState } from "react";
import { createRole, deleteRole, listRoles, updateRole } from "../../api/roles.js";
import Badge from "../../components/ui/Badge.jsx";
import Button from "../../components/ui/Button.jsx";
import Card from "../../components/ui/Card.jsx";
import Loading from "../../components/ui/Loading.jsx";
import { hintClass, inputClass } from "../../components/ui/styles.js";
import { useDialog } from "../../context/DialogContext.jsx";
import { useSession } from "../../context/SessionContext.jsx";
import { useToast } from "../../context/ToastContext.jsx";

export default function RolesPage() {
  const toast = useToast();
  const [data, setData] = useState(null);

  useEffect(() => {
    listRoles().then(setData).catch((error) => toast(error.message, "error"));
  }, [toast]);

  const run = useCallback(async (action, success) => {
    try {
      setData(await action());
      if (success) toast(success);
      return true;
    } catch (error) {
      toast(error.message, "error");
      return false;
    }
  }, [toast]);

  if (!data) return <Loading />;
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6">
      <h1 className="mb-1 text-2xl font-bold">Rôles</h1>
      <p className={`${hintClass} mb-5`}>
        Chaque utilisateur a un rôle ; un rôle est une liste de permissions. « Superadmin » est verrouillé : il a toujours
        tout. Tu ne peux donner ou retirer que des permissions que tu as toi-même.
      </p>
      <Card as="details" className="mb-5 px-5 py-3">
        <summary className="cursor-pointer font-medium">Ce que permet chaque permission</summary>
        {groupsOf(data.permissions).map(([group, list]) => (
          <div key={group} className="mt-3">
            <p className="mb-1 text-xs font-semibold tracking-wide text-stone-400 uppercase">{group}</p>
            <dl className="grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[max-content_minmax(0,1fr)]">
              {list.map((p) => (
                <div key={p.name} className="contents">
                  <dt className="font-medium">{p.label} <code className="text-xs text-stone-400">{p.name}</code></dt>
                  <dd className="text-stone-500 dark:text-stone-400">{p.description}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
        <p className="mt-3 text-sm text-stone-500 dark:text-stone-400">
          Avec au moins une permission « Faire agir Rosalie », elle traite la personne comme sa créatrice ou son créateur ;
          sans aucune, comme une invitée : elle discute, et fait des recherches web seulement avec « Recherche web ». Les
          personnes sans compte (inconnus sur Discord) dépendent du réglage Discord « Recherche web pour les invités ».
        </p>
      </Card>
      <div className="space-y-4">
        {data.roles.map((role) => <RoleCard key={role.name} role={role} permissions={data.permissions} run={run} />)}
      </div>
      <h2 className="mt-8 mb-2.5 font-semibold">Nouveau rôle</h2>
      <NewRole permissions={data.permissions} run={run} />
    </main>
  );
}

// Permissions groupées (Site, Faire agir Rosalie, Administration) en cases compactes ; la
// description est en info-bulle et dans la légende. « Tout » coche / décoche un groupe.
function groupsOf(permissions) {
  const groups = new Map();
  for (const p of permissions) groups.set(p.group, [...(groups.get(p.group) ?? []), p]);
  return [...groups];
}

function PermissionList({ permissions, value, onChange, disabled }) {
  const { session } = useSession();
  const mine = (name) => session.user.permissions.includes(name);
  return (
    <div className="space-y-3">
      {groupsOf(permissions).map(([group, list]) => {
        const editable = list.filter((p) => !disabled && mine(p.name));
        const all = list.every((p) => value.includes(p.name));
        return (
          <div key={group} role="group" aria-label={group}>
            <div className="mb-1.5 flex items-center gap-3">
              <span className="text-xs font-semibold tracking-wide text-stone-400 uppercase">{group}</span>
              {list.length > 1 && editable.length > 0 && (
                <button
                  type="button"
                  className="text-xs text-rose-600 hover:underline dark:text-rose-400"
                  onClick={() => {
                    const names = editable.map((p) => p.name);
                    onChange(all ? value.filter((v) => !names.includes(v)) : [...new Set([...value, ...names])]);
                  }}
                >
                  {all ? "aucune" : "tout"}
                </button>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {list.map((p) => {
                const checked = value.includes(p.name);
                const off = disabled || !mine(p.name);
                return (
                  <label
                    key={p.name}
                    title={off && !disabled ? `${p.description} (tu n'as pas cette permission)` : p.description}
                    className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition ${
                      checked
                        ? "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200"
                        : "border-stone-200 dark:border-stone-700"
                    } ${off ? "opacity-60" : "cursor-pointer hover:border-rose-400"}`}
                  >
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-rose-600"
                      checked={checked}
                      disabled={off}
                      onChange={(event) => onChange(event.target.checked ? [...value, p.name] : value.filter((v) => v !== p.name))}
                    />
                    {p.label}
                  </label>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RoleCard({ role, permissions, run }) {
  const { confirm } = useDialog();
  const [label, setLabel] = useState(role.label);
  const [description, setDescription] = useState(role.description);
  const [granted, setGranted] = useState(role.permissions);
  useEffect(() => {
    setLabel(role.label);
    setDescription(role.description);
    setGranted(role.permissions);
  }, [role]);

  const dirty = label !== role.label || description !== role.description
    || [...granted].sort().join() !== [...role.permissions].sort().join();

  const save = () => run(() => updateRole(role.name, { label, description, permissions: granted }), `Rôle « ${label} » enregistré.`);
  const remove = async () => {
    const ok = await confirm({ title: `Supprimer le rôle « ${role.label} » ?`, message: "Cette action est définitive.", confirmLabel: "Supprimer", danger: true });
    if (ok) run(() => deleteRole(role.name), "Rôle supprimé.");
  };

  return (
    <Card className="p-5">
      <div className="mb-3 flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          {role.locked ? (
            <h2 className="text-lg font-semibold">{role.label}</h2>
          ) : (
            <input value={label} onChange={(e) => setLabel(e.target.value)} aria-label="Libellé du rôle" className={`${inputClass} max-w-xs text-lg font-semibold`} />
          )}
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-stone-500">
            <code>{role.name}</code>
            <Badge>{role.users} utilisateur{role.users > 1 ? "s" : ""}</Badge>
            {role.locked && <Badge tone="warn">verrouillé</Badge>}
          </p>
        </div>
        {!role.locked && (
          <div className="flex gap-2">
            <Button variant="danger" size="sm" onClick={remove} disabled={role.users > 0} title={role.users > 0 ? "Encore attribué à des utilisateurs" : undefined}>
              Supprimer
            </Button>
            <Button size="sm" onClick={save} disabled={!dirty}>Enregistrer</Button>
          </div>
        )}
      </div>
      {role.locked ? (
        <p className={`${hintClass} mb-3`}>{role.description}</p>
      ) : (
        <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (facultative)" aria-label="Description du rôle" className={`${inputClass} mb-3`} />
      )}
      <PermissionList permissions={permissions} value={granted} onChange={setGranted} disabled={role.locked} />
    </Card>
  );
}

function NewRole({ permissions, run }) {
  const [granted, setGranted] = useState(["chat"]);
  const submit = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    const ok = await run(() => createRole({ ...values, permissions: granted }), `Rôle « ${values.label} » créé.`);
    if (ok) {
      form.reset();
      setGranted(["chat"]);
    }
  };
  const label = "flex flex-col gap-1.5 text-sm font-medium";
  return (
    <Card as="form" onSubmit={submit} className="space-y-4 p-5">
      <div className="grid gap-3 md:grid-cols-[180px_220px_minmax(0,1fr)]">
        <label className={label}>Identifiant<input name="name" required pattern="[a-z0-9][a-z0-9_\-]{1,31}" placeholder="ex : editeur" autoComplete="off" spellCheck={false} autoCapitalize="none" className={inputClass} /></label>
        <label className={label}>Libellé<input name="label" required maxLength={40} placeholder="ex : Éditeur" className={inputClass} /></label>
        <label className={label}>Description<input name="description" placeholder="facultative" className={inputClass} /></label>
      </div>
      <PermissionList permissions={permissions} value={granted} onChange={setGranted} />
      <Button type="submit">Créer le rôle</Button>
    </Card>
  );
}
