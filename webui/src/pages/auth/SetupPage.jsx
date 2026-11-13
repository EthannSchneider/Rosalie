// Premier lancement : création du superadmin avec le code d'installation de la console.
import { setup } from "../../api/session.js";
import { useSession } from "../../context/SessionContext.jsx";
import AuthCard, { AuthField } from "./AuthCard.jsx";

export default function SetupPage() {
  const { setSession } = useSession();

  const submit = async ({ code, username, password, confirm }) => {
    if (password !== confirm) throw new Error("Les deux mots de passe sont différents.");
    setSession(await setup(code, username, password)); // la garde mène à Mon compte (lier Discord)
  };

  return (
    <AuthCard
      title="Bienvenue"
      intro={<>Crée le compte superadmin. Le code d'installation est affiché dans la console où tourne <code className="font-mono">python bot.py</code> (et dans le log).</>}
      submitLabel="Créer le superadmin"
      onSubmit={submit}
    >
      <AuthField label="Code d'installation" name="code" required autoComplete="off" placeholder="XXXX-XXXX" autoCapitalize="characters" autoFocus />
      <AuthField label="Nom d'utilisateur" name="username" required minLength={2} maxLength={32} autoComplete="username" autoCapitalize="none" />
      <AuthField label="Mot de passe (8 caractères min.)" name="password" type="password" required minLength={8} autoComplete="new-password" />
      <AuthField label="Confirmer le mot de passe" name="confirm" type="password" required minLength={8} autoComplete="new-password" />
    </AuthCard>
  );
}
