// Mon compte (tout le monde) : profil, identifiant Discord lié, mot de passe.
// Les réglages de Rosalie elle-même sont dans Réglages (superadmin).
import { useState } from "react";
import { changePassword, linkDiscord } from "../../api/account.js";
import { Avatar } from "../../components/layout/AppLayout.jsx";
import Badge from "../../components/ui/Badge.jsx";
import Button from "../../components/ui/Button.jsx";
import Card from "../../components/ui/Card.jsx";
import { hintClass, inputClass } from "../../components/ui/styles.js";
import { useSession } from "../../context/SessionContext.jsx";
import { useToast } from "../../context/ToastContext.jsx";

const ROLE_TEXT = {
  superadmin: "Tu gères tout : réglages de Rosalie, personnalités, comptes. Elle agit pour toi.",
  admin: "Rosalie agit pour toi (outils, souvenirs, code avec ta confirmation), ici et sur Discord.",
  user: "Tu peux discuter avec Rosalie et lui faire chercher des infos ; elle n'agit pas pour toi.",
};

export default function AccountPage() {
  const { session } = useSession();
  const user = session.user;
  return (
    <main className="mx-auto w-full max-w-3xl space-y-5 px-4 py-6 sm:px-6">
      <h1 className="text-2xl font-bold">Mon compte</h1>
      <Card className="flex items-center gap-4 p-5">
        <Avatar name={user.username} size="lg" />
        <div>
          <p className="flex items-center gap-2 font-semibold">
            {user.username} <Badge tone="accent">{user.role}</Badge>
          </p>
          <p className={hintClass}>{ROLE_TEXT[user.role]}</p>
        </div>
      </Card>
      <LegacyOwners />
      <DiscordCard />
      <PasswordCard />
    </main>
  );
}

function useLink() {
  const { session, setSession } = useSession();
  const toast = useToast();
  return async (discordId) => {
    try {
      const updated = await linkDiscord(discordId);
      setSession(updated); // sans legacy_owners une fois lié : la bannière disparaît
      toast(discordId ? "Identifiant Discord lié." : "Identifiant Discord retiré.");
      return true;
    } catch (error) {
      toast(error.message, "error");
      return false;
    }
  };
}

function LegacyOwners() {
  const { session } = useSession();
  const link = useLink();
  const ids = session.legacy_owners ?? [];
  if (!ids.length) return null;
  return (
    <Card className="border-amber-400 bg-amber-50 p-5 dark:border-amber-700 dark:bg-amber-950/40">
      <h2 className="mb-1 font-semibold">Ancien réglage OWNER_IDS encore utilisé</h2>
      <p className={hintClass}>
        Sur Discord, Rosalie obéit encore aux identifiants de l'ancien .env, tant qu'aucun compte admin n'a lié le sien. Dès
        qu'un compte admin est lié, ils sont ignorés.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {ids.map((id) => (
          <Button key={id} size="sm" onClick={() => link(id)}>
            Lier {id} à mon compte
          </Button>
        ))}
      </div>
    </Card>
  );
}

function DiscordCard() {
  const { session } = useSession();
  const user = session.user;
  const link = useLink();
  const [value, setValue] = useState(user.discord_id ?? "");
  return (
    <Card className="p-5">
      <h2 className="mb-1 font-semibold">Discord</h2>
      <p className={hintClass}>
        Ton identifiant Discord : clic droit sur ton profil → Copier l'identifiant (active le mode développeur dans Paramètres →
        Avancés).{" "}
        {user.owner
          ? "Sur Discord, Rosalie t'obéira (commandes /rosalie, actions, boutons de confirmation)."
          : "Sur Discord, elle te reconnaîtra mais ne fera que discuter (compte « user »)."}
      </p>
      <form
        className="mt-3 flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          link(value.trim() || null);
        }}
      >
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          inputMode="numeric"
          placeholder="ex : 123456789012345678"
          aria-label="Identifiant Discord"
          autoComplete="off"
          spellCheck={false}
          className={`${inputClass} min-w-0 flex-[1_1_220px]`}
        />
        <Button type="submit">Enregistrer</Button>
        {user.discord_id && (
          <Button variant="ghost" onClick={async () => (await link(null)) && setValue("")}>
            Délier
          </Button>
        )}
      </form>
    </Card>
  );
}

function PasswordCard() {
  const toast = useToast();
  const [error, setError] = useState("");
  const submit = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const { current, password, again } = Object.fromEntries(new FormData(form));
    setError("");
    if (password !== again) return setError("Les deux mots de passe sont différents.");
    try {
      await changePassword(current, password);
      form.reset();
      toast("Mot de passe changé (tes autres sessions sont fermées).");
    } catch (failure) {
      setError(failure.message);
    }
  };
  const field = "flex flex-col gap-1.5 text-sm font-medium";
  return (
    <Card className="p-5">
      <h2 className="mb-3 font-semibold">Mot de passe</h2>
      <form onSubmit={submit} className="flex max-w-sm flex-col gap-3">
        <label className={field}>Mot de passe actuel<input name="current" type="password" required autoComplete="current-password" className={inputClass} /></label>
        <label className={field}>Nouveau (8 caractères min.)<input name="password" type="password" required minLength={8} autoComplete="new-password" className={inputClass} /></label>
        <label className={field}>Confirmer<input name="again" type="password" required minLength={8} autoComplete="new-password" className={inputClass} /></label>
        <p role="alert" className="min-h-5 text-sm text-red-600 dark:text-red-400">{error}</p>
        <div><Button type="submit">Changer le mot de passe</Button></div>
      </form>
    </Card>
  );
}
