// Session : qui est connecté (et ce qu'il peut faire), installation à faire, chat disponible.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { onUnauthorized } from "../api/client.js";
import { getSession, logout as apiLogout } from "../api/session.js";

const SessionContext = createContext(null);

export function SessionProvider({ children }) {
  const [session, setSession] = useState(null);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try {
      setSession(await getSession());
      setError(null);
    } catch (failure) {
      setError(failure.message);
    }
  }, []);

  const logout = useCallback(async () => {
    await apiLogout().catch(() => {});
    await refresh();
  }, [refresh]);

  useEffect(() => {
    refresh();
    onUnauthorized(() => refresh()); // session expirée : les gardes renvoient vers /login
  }, [refresh]);

  useEffect(() => {
    if (session?.name) document.title = session.name;
  }, [session?.name]);

  const value = useMemo(() => ({ session, setSession, refresh, logout, error }), [session, refresh, logout, error]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  return useContext(SessionContext);
}
