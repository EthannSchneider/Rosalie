// Gardes de routes : selon la session, on affiche la page ou on redirige.
import { Navigate, useLocation } from "react-router-dom";
import { useSession } from "../../context/SessionContext.jsx";
import { can } from "../../lib/permissions.js";
import Loading from "../ui/Loading.jsx";

function Pending() {
  const { error } = useSession();
  return <Loading text={error ? `Oups : ${error}` : "Chargement…"} />;
}

/** Pages du site : il faut être connecté (et l'installation doit être faite). */
export function RequireAuth({ children }) {
  const { session } = useSession();
  const location = useLocation();
  if (!session) return <Pending />;
  if (session.setup) return <Navigate to="/setup" replace />;
  if (!session.user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}

/** Connexion / installation : seulement si on n'est pas déjà connecté. Une fois connecté, on
 * part vers la page demandée avant (ou Mon compte après l'installation, pour lier Discord). */
export function RequireGuest({ children, setup = false }) {
  const { session } = useSession();
  const location = useLocation();
  if (!session) return <Pending />;
  if (session.user) return <Navigate to={setup ? "/account" : location.state?.from ?? "/"} replace />;
  if (session.setup && !setup) return <Navigate to="/setup" replace />;
  if (!session.setup && setup) return <Navigate to="/login" replace />;
  return children;
}

/** Pages réservées : la permission (ou l'une des permissions) du rôle. */
export function RequirePermission({ permission, children }) {
  const { session } = useSession();
  if (!can(session?.user, permission)) return <Home />;
  return children;
}

/** Page d'accueil : le chat si le rôle le permet, sinon Mon compte. */
export function Home() {
  const { session } = useSession();
  return <Navigate to={can(session?.user, "chat") ? "/chat" : "/account"} replace />;
}
