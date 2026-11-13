// En-tête du site (onglets, menu du compte avec la section Superadmin) + la page courante.
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../../context/SessionContext.jsx";

const TABS = [{ to: "/chat", label: "Chat" }];

// Menu du compte (avatar en haut à droite) : Mon compte, puis les pages réservées (Superadmin)
const ACCOUNT = { to: "/account", label: "Mon compte" };
const SUPERADMIN = [
  { to: "/settings", label: "Réglages", permission: "settings" },
  { to: "/users", label: "Utilisateurs", permission: "users" },
];

export default function AppLayout() {
  const { session } = useSession();
  const user = session.user;
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-3 border-b border-stone-200 bg-stone-50/85 px-3 backdrop-blur sm:gap-5 sm:px-6 dark:border-stone-800 dark:bg-stone-950/85">
        <Link to="/chat" className="flex items-center gap-2 font-semibold">
          <img src="/favicon.svg" alt="" className="h-6 w-6" />
          <span className="hidden sm:inline">{session.name}</span>
        </Link>
        <nav aria-label="Pages" className="flex min-w-0 flex-1 gap-1 overflow-x-auto [scrollbar-width:none]">
          {TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) =>
                `rounded-lg px-3 py-1.5 whitespace-nowrap transition ${
                  isActive
                    ? "bg-rose-100 font-semibold text-rose-700 dark:bg-rose-950 dark:text-rose-300"
                    : "text-stone-500 hover:bg-stone-200/60 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-100"
                }`
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
        <AccountMenu user={user} />
      </header>
      <Outlet />
    </div>
  );
}

export function Avatar({ name, size = "sm" }) {
  const sizes = { sm: "h-8 w-8 text-sm", lg: "h-12 w-12 text-lg" };
  return (
    <span aria-hidden="true" className={`grid shrink-0 place-items-center rounded-full bg-rose-600 font-semibold text-white dark:bg-rose-500 dark:text-stone-950 ${sizes[size]}`}>
      {name[0].toUpperCase()}
    </span>
  );
}

function AccountMenu({ user }) {
  const { logout } = useSession();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const admin = SUPERADMIN.filter((page) => user[page.permission]);
  // page du menu ouverte : le bouton du compte l'affiche et la met en évidence
  const current = [ACCOUNT, ...admin].find((page) => pathname.startsWith(page.to));

  useEffect(() => {
    const close = (event) => ref.current && !ref.current.contains(event.target) && setOpen(false);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);

  const item = "w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-stone-100 dark:hover:bg-stone-800";
  const go = (to) => {
    setOpen(false);
    navigate(to);
  };
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-2 rounded-full p-1 pr-1 sm:pr-3 ${
          current ? "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300" : "hover:bg-stone-200/60 dark:hover:bg-stone-800"
        }`}
      >
        <Avatar name={user.username} />
        <span className="hidden sm:inline">{current ? current.label : user.username}</span>
        <span aria-hidden="true" className="text-xs text-stone-400">▾</span>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 mt-2 w-56 rounded-2xl border border-stone-200 bg-white p-2 shadow-xl dark:border-stone-700 dark:bg-stone-900">
          <p className="px-3 py-1.5 text-xs text-stone-500">Rôle : {user.role}</p>
          <button
            role="menuitem"
            aria-current={current === ACCOUNT ? "page" : undefined}
            className={`${item} ${current === ACCOUNT ? "bg-rose-50 font-semibold text-rose-700 dark:bg-rose-950 dark:text-rose-300" : ""}`}
            onClick={() => go(ACCOUNT.to)}
          >
            {ACCOUNT.label}
          </button>
          {admin.length > 0 && (
            <div role="group" aria-label="Superadmin" className="my-1 border-y border-stone-200 py-1 dark:border-stone-700">
              <p className="px-3 pt-1.5 pb-1 text-xs font-semibold tracking-wide text-stone-400 uppercase">Superadmin</p>
              {admin.map((page) => (
                <button
                  key={page.to}
                  role="menuitem"
                  aria-current={page === current ? "page" : undefined}
                  className={`${item} ${page === current ? "bg-rose-50 font-semibold text-rose-700 dark:bg-rose-950 dark:text-rose-300" : ""}`}
                  onClick={() => go(page.to)}
                >
                  {page.label}
                </button>
              ))}
            </div>
          )}
          <button role="menuitem" className={item} onClick={() => { setOpen(false); logout(); }}>
            Se déconnecter
          </button>
        </div>
      )}
    </div>
  );
}
