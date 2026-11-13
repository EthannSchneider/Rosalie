import { login } from "../../api/session.js";
import { useSession } from "../../context/SessionContext.jsx";
import AuthCard, { AuthField } from "./AuthCard.jsx";

export default function LoginPage() {
  const { setSession } = useSession();

  const submit = async ({ username, password }) => {
    setSession(await login(username, password)); // la garde mène à la page demandée avant
  };

  return (
    <AuthCard title="Connexion" submitLabel="Se connecter" onSubmit={submit}>
      <AuthField label="Nom d'utilisateur" name="username" required autoComplete="username" autoCapitalize="none" autoFocus />
      <AuthField label="Mot de passe" name="password" type="password" required autoComplete="current-password" />
    </AuthCard>
  );
}
