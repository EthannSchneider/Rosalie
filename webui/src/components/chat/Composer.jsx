// Zone de saisie : Entrée pour envoyer, Maj+Entrée pour aller à la ligne.
import { useEffect, useRef, useState } from "react";
import { sendMessage, sendTyping } from "../../api/chat.js";
import { useToast } from "../../context/ToastContext.jsx";
import Button from "../ui/Button.jsx";

export default function Composer({ name, onSent }) {
  const toast = useToast();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const lastTyping = useRef(0);
  const input = useRef(null);

  useEffect(() => {
    const el = input.current;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  const submit = async () => {
    const value = text.trim();
    if (!value || busy) return;
    setBusy(true);
    try {
      onSent(await sendMessage(value));
      setText("");
    } catch (error) {
      toast(error.message, "error");
    } finally {
      setBusy(false);
      input.current?.focus();
    }
  };

  const change = (event) => {
    setText(event.target.value);
    const now = Date.now();
    if (event.target.value && now - lastTyping.current > 4000) {
      lastTyping.current = now; // elle attend que tu aies fini d'écrire
      sendTyping().catch(() => {});
    }
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="flex items-end gap-2 rounded-2xl border border-stone-200 bg-white p-2.5 shadow-sm focus-within:border-rose-500 dark:border-stone-800 dark:bg-stone-900"
    >
      <textarea
        ref={input}
        rows={1}
        autoFocus
        value={text}
        onChange={change}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }}
        placeholder={`Écrire à ${name}…`}
        aria-label="Message"
        className="max-h-[200px] min-h-6 flex-1 resize-none bg-transparent px-2 py-1.5 leading-normal outline-none placeholder:text-stone-400"
      />
      <Button type="submit" disabled={busy || !text.trim()}>Envoyer</Button>
    </form>
  );
}
