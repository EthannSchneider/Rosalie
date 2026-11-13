// Utilisateurs (superadmin) : créer, rôle, identifiant Discord, mot de passe, supprimer.
import { useEffect, useState } from "react";
import { createUser, deleteUser, listUsers, updateUser } from "../../api/users.js";
import Badge from "../../components/ui/Badge.jsx";
import Button from "../../components/ui/Button.jsx";
import Card from "../../components/ui/Card.jsx";
import Loading from "../../components/ui/Loading.jsx";
import { hintClass, inputClass } from "../../components/ui/styles.js";
import { useDialog } from "../../context/DialogContext.jsx";
import { useSession } from "../../context/SessionContext.jsx";
import { useToast } from "../../context/ToastContext.jsx";

const ROLES = {
  superadmin: "tout : réglages de Rosalie, personnalités, comptes",
  admin: "la fait agir (outils, souvenirs, code), sur le chat web et sur Discord",
  user: "discute seulement, comme un invité (discussion et recherche)",
};

export default function UsersPage() {
  const toast = useToast();
  const [users, setUsers] = useState(null);

  useEffect(() => {
    listUsers().then(setUsers).catch((error) => toast(error.message, "error"));
  }, [toast]);

  /** Lance une action qui renvoie la liste à jour ; affiche le message si ça marche. */
  const run = async (action, success) => {
    try {
      setUsers(await action());
      if (success) toast(success);
      return true;
    } catch (error) {
      toast(error.message, "error");
      return false;
    }
  };

  if (!users) return <Loading />;
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6">
      <h1 className="mb-1 text-2xl font-bold">Utilisateurs</h1>
      <p className={`${hintClass} mb-5`}>
        Chaque compte a sa propre conversation avec Rosalie. Sur Discord, elle obéit aux comptes admin et superadmin liés à
        leur identifiant Discord. Rôles :{" "}
        {Object.entries(ROLES).map(([role, text], i) => (
          <span key={role}>
            {i > 0 && " · "}
            <strong>{role}</strong> — {text}
          </span>
        ))}
        .
      </p>
      <Card className="divide-y divide-stone-200 dark:divide-stone-800">
        {users.map((user) => <UserRow key={user.id} user={user} run={run} />)}
      </Card>
      <h2 className="mt-7 mb-2.5 font-semibold">Nouvel utilisateur</h2>
      <NewUser run={run} />
    </main>
  );
}

function UserRow({ user, run }) {
  const { session } = useSession();
  const { ask, confirm } = useDialog();
  const [discord, setDiscord] = useState(user.discord_id ?? "");
  const self = user.id === session.user.id;
  const seen = user.last_login
    ? `Dernière connexion : ${new Date(user.last_login * 1000).toLocaleString("fr-CH", { dateStyle: "medium", timeStyle: "short" })}`
    : "Jamais connecté";

  const saveDiscord = async () => {
    const value = discord.trim() || null;
    if (value === (user.discord_id ?? null)) return;
    const ok = await run(() => updateUser(user.id, { discord_id: value }),
      value ? `${user.username} lié à Discord.` : `Discord retiré pour ${user.username}.`);
    if (!ok) setDiscord(user.discord_id ?? "");
  };

  const resetPassword = async () => {
    const password = await ask({
      title: `Mot de passe de « ${user.username} »`,
      label: "Nouveau mot de passe (8 caractères min.). Ses sessions ouvertes seront fermées.",
      type: "password",
      confirmLabel: "Changer",
    });
    if (password) run(() => updateUser(user.id, { password }), "Mot de passe changé.");
  };

  const remove = async () => {
    const ok = await confirm({ title: `Supprimer « ${user.username} » ?`, message: "Le compte et ses sessions sont supprimés.", confirmLabel: "Supprimer", danger: true });
    if (ok) run(() => deleteUser(user.id), "Compte supprimé.");
  };

  return (
    <div className="grid grid-cols-2 items-center gap-3 px-5 py-3.5 md:grid-cols-[minmax(0,1fr)_200px_130px_220px]">
      <div className="col-span-2 min-w-0 md:col-span-1">
        <p className="flex items-center gap-2 font-semibold">
          {user.username} {self && <Badge tone="accent">toi</Badge>}
        </p>
        <p className="text-sm text-stone-500">{seen}</p>
      </div>
      <input
        value={discord}
        onChange={(event) => setDiscord(event.target.value)}
        onBlur={saveDiscord}
        onKeyDown={(event) => event.key === "Enter" && event.currentTarget.blur()}
        inputMode="numeric"
        placeholder="ID Discord"
        aria-label={`Identifiant Discord de ${user.username}`}
        autoComplete="off"
        spellCheck={false}
        className={inputClass}
      />
      <select
        value={user.role}
        aria-label={`Rôle de ${user.username}`}
        onChange={(event) => run(() => updateUser(user.id, { role: event.target.value }), `${user.username} est maintenant ${event.target.value}.`)}
        className={inputClass}
      >
        {Object.keys(ROLES).map((role) => <option key={role}>{role}</option>)}
      </select>
      <div className="col-span-2 flex gap-2 md:col-span-1 md:justify-end">
        <Button variant="ghost" size="sm" onClick={resetPassword}>Mot de passe</Button>
        {!self && <Button variant="danger" size="sm" onClick={remove}>Supprimer</Button>}
      </div>
    </div>
  );
}

function NewUser({ run }) {
  const submit = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    const ok = await run(
      () => createUser({ ...values, discord_id: values.discord_id.trim() || null }),
      `Compte « ${values.username} » créé.`,
    );
    if (ok) form.reset();
  };
  const label = "flex flex-col gap-1.5 text-sm font-medium";
  return (
    <Card as="form" onSubmit={submit} className="grid items-end gap-3 p-5 md:grid-cols-[repeat(4,minmax(0,1fr))_auto]">
      <label className={label}>Nom d'utilisateur<input name="username" required minLength={2} maxLength={32} autoComplete="off" spellCheck={false} autoCapitalize="none" className={inputClass} /></label>
      <label className={label}>Mot de passe (8 min.)<input name="password" type="password" required minLength={8} autoComplete="new-password" className={inputClass} /></label>
      <label className={label}>
        Rôle
        <select name="role" defaultValue="user" className={inputClass}>
          {Object.keys(ROLES).map((role) => <option key={role}>{role}</option>)}
        </select>
      </label>
      <label className={label}>ID Discord<input name="discord_id" inputMode="numeric" placeholder="facultatif" autoComplete="off" spellCheck={false} className={inputClass} /></label>
      <Button type="submit">Créer</Button>
    </Card>
  );
}
