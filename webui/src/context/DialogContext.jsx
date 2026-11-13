// Boîtes de dialogue natives (<dialog>) en promesse :
//   const name = await ask({ title, label, value })      -> texte ou null
//   const ok = await confirm({ title, message, danger })  -> true / false
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import Button from "../components/ui/Button.jsx";
import { inputClass } from "../components/ui/styles.js";

const DialogContext = createContext(null);

export function DialogProvider({ children }) {
  const [dialog, setDialog] = useState(null);

  const open = useCallback((options) => new Promise((resolve) => setDialog({ ...options, resolve })), []);
  const ask = useCallback((options) => open({ input: true, ...options }), [open]);
  const confirm = useCallback((options) => open({ input: false, ...options }).then((value) => value !== null), [open]);

  const close = (value) => {
    dialog?.resolve(value);
    setDialog(null);
  };

  return (
    <DialogContext.Provider value={{ ask, confirm }}>
      {children}
      {dialog && <Dialog {...dialog} onClose={close} />}
    </DialogContext.Provider>
  );
}

function Dialog({ title, label, message, value = "", input, type = "text", confirmLabel = "Valider", danger, onClose }) {
  const ref = useRef(null);
  const [text, setText] = useState(value);

  useEffect(() => {
    ref.current?.showModal();
  }, []);

  return (
    <dialog
      ref={ref}
      onCancel={(event) => {
        event.preventDefault();
        onClose(null);
      }}
      className="m-auto w-[min(420px,calc(100vw-2rem))] rounded-2xl border border-stone-200 bg-white p-5 text-stone-900 backdrop:bg-black/40 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
    >
      <form
        method="dialog"
        onSubmit={(event) => {
          event.preventDefault();
          onClose(input ? text.trim() : "");
        }}
      >
        <h3 className="mb-3 text-lg font-semibold">{title}</h3>
        {message && <p className="mb-3 text-sm text-stone-500 dark:text-stone-400">{message}</p>}
        {input && (
          <label className="flex flex-col gap-2 text-sm text-stone-500 dark:text-stone-400">
            {label}
            <input
              autoFocus
              type={type}
              value={text}
              onChange={(event) => setText(event.target.value)}
              autoComplete={type === "password" ? "new-password" : "off"}
              spellCheck={false}
              className={inputClass}
            />
          </label>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={() => onClose(null)}>
            Annuler
          </Button>
          <Button variant={danger ? "danger" : "primary"} type="submit">
            {confirmLabel}
          </Button>
        </div>
      </form>
    </dialog>
  );
}

export function useDialog() {
  return useContext(DialogContext);
}
