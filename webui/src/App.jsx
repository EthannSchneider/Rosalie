// Les routes du site. Les gardes renvoient vers /setup ou /login selon la session, et cachent
// les pages réservées (réglages et comptes : superadmin).
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout.jsx";
import { RequireAuth, RequireGuest, RequirePermission } from "./components/layout/guards.jsx";
import { DialogProvider } from "./context/DialogContext.jsx";
import { SessionProvider } from "./context/SessionContext.jsx";
import { ToastProvider } from "./context/ToastContext.jsx";
import AccountPage from "./pages/account/AccountPage.jsx";
import LoginPage from "./pages/auth/LoginPage.jsx";
import SetupPage from "./pages/auth/SetupPage.jsx";
import ChatPage from "./pages/chat/ChatPage.jsx";
import SettingsPage, { SettingsIndex } from "./pages/settings/SettingsPage.jsx";
import SettingsSection from "./pages/settings/SettingsSection.jsx";
import UsersPage from "./pages/users/UsersPage.jsx";

const router = createBrowserRouter([
  { path: "/setup", element: <RequireGuest setup><SetupPage /></RequireGuest> },
  { path: "/login", element: <RequireGuest><LoginPage /></RequireGuest> },
  {
    element: <RequireAuth><AppLayout /></RequireAuth>,
    children: [
      { index: true, element: <Navigate to="/chat" replace /> },
      { path: "chat", element: <ChatPage /> },
      { path: "account", element: <AccountPage /> },
      {
        path: "settings",
        element: <RequirePermission permission="settings"><SettingsPage /></RequirePermission>,
        children: [
          { index: true, element: <SettingsIndex /> },
          { path: ":section", element: <SettingsSection /> },
        ],
      },
      { path: "users", element: <RequirePermission permission="users"><UsersPage /></RequirePermission> },
      { path: "*", element: <Navigate to="/chat" replace /> },
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
