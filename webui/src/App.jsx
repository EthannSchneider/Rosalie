// Les routes du site. Les gardes renvoient vers /setup ou /login selon la session, et cachent
// les pages réservées selon les permissions du rôle (chat, personas, settings, users, roles).
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout.jsx";
import { Home, RequireAuth, RequireGuest, RequirePermission } from "./components/layout/guards.jsx";
import { DialogProvider } from "./context/DialogContext.jsx";
import { SessionProvider } from "./context/SessionContext.jsx";
import { ToastProvider } from "./context/ToastContext.jsx";
import AccountPage from "./pages/account/AccountPage.jsx";
import LoginPage from "./pages/auth/LoginPage.jsx";
import SetupPage from "./pages/auth/SetupPage.jsx";
import ChatPage from "./pages/chat/ChatPage.jsx";
import RolesPage from "./pages/roles/RolesPage.jsx";
import SettingsPage, { SettingsIndex } from "./pages/settings/SettingsPage.jsx";
import SettingsSection from "./pages/settings/SettingsSection.jsx";
import UsersPage from "./pages/users/UsersPage.jsx";

const router = createBrowserRouter([
  { path: "/setup", element: <RequireGuest setup><SetupPage /></RequireGuest> },
  { path: "/login", element: <RequireGuest><LoginPage /></RequireGuest> },
  {
    element: <RequireAuth><AppLayout /></RequireAuth>,
    children: [
      { index: true, element: <Home /> },
      { path: "chat", element: <RequirePermission permission="chat"><ChatPage /></RequirePermission> },
      { path: "account", element: <AccountPage /> },
      {
        path: "settings",
        element: <RequirePermission permission={["settings", "personas"]}><SettingsPage /></RequirePermission>,
        children: [
          { index: true, element: <SettingsIndex /> },
          { path: ":section", element: <SettingsSection /> },
        ],
      },
      { path: "users", element: <RequirePermission permission="users"><UsersPage /></RequirePermission> },
      { path: "roles", element: <RequirePermission permission="roles"><RolesPage /></RequirePermission> },
      { path: "*", element: <Home /> },
    ],
  },
]);

export default function App() {
  return (
    <ToastProvider>
      <DialogProvider>
        <SessionProvider>
          <RouterProvider router={router} />
        </SessionProvider>
      </DialogProvider>
    </ToastProvider>
  );
}
