// Petites notifications en haut à droite : toast("Enregistré.") ou toast(message, "error").
import { createContext, useCallback, useContext, useRef, useState } from "react";

const ToastContext = createContext(() => {});

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null);
  const timer = useRef(null);

  const show = useCallback((message, kind = "ok") => {
    clearTimeout(timer.current);
    setToast({ message, kind, id: Date.now() });
    timer.current = setTimeout(() => setToast(null), kind === "error" ? 6000 : 3500);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed top-4 right-4 z-50 max-w-[min(420px,calc(100vw-2rem))]">
        {toast && (
          <div
            key={toast.id}
            role="status"
            className={`rounded-xl border border-stone-200 border-l-4 bg-white px-4 py-3 shadow-lg dark:border-stone-700 dark:bg-stone-900 ${
              toast.kind === "error" ? "border-l-red-500" : "border-l-emerald-500"
            }`}
          >
            {toast.message}
          </div>
        )}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
