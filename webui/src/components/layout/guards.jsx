// Gardes de routes : selon la session, on affiche la page ou on redirige.
import { Navigate, useLocation } from "react-router-dom";
import { useSession } from "../../context/SessionContext.jsx";
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
  if (session.user) return <Navigate to={setup ? "/account" : location.state?.from ?? "/chat"} replace />;
  if (session.setup && !setup) return <Navigate to="/setup" replace />;
  if (!session.setup && setup) return <Navigate to="/login" replace />;
  return children;
}

/** Pages réservées : permission « settings » ou « users » (superadmin). */
export function RequirePermission({ permission, children }) {
  const { session } = useSession();
  if (!session?.user?.[permission]) return <Navigate to="/chat" replace />;
  return children;
}
