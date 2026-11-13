// Ta conversation privée avec Rosalie, en temps réel.
import { useLayoutEffect, useRef } from "react";
import { clearMessages } from "../../api/chat.js";
import Composer from "../../components/chat/Composer.jsx";
import Message from "../../components/chat/Message.jsx";
import Button from "../../components/ui/Button.jsx";
import { useDialog } from "../../context/DialogContext.jsx";
import { useSession } from "../../context/SessionContext.jsx";
import { useToast } from "../../context/ToastContext.jsx";
import useChat from "../../hooks/useChat.js";
import { can } from "../../lib/permissions.js";

export default function ChatPage() {
  const { session } = useSession();
  if (!session.chat) return <ChatUnavailable />;
  return <Chat session={session} />;
}

function Chat({ session }) {
  const { messages, typing, status, upsert, loadOlder, clear } = useChat(true);
  const { confirm } = useDialog();
  const toast = useToast();
  const list = useRef(null);
  const stick = useRef(true); // collé en bas : on suit les nouveaux messages
  const keepFrom = useRef(null); // hauteur avant de charger l'historique plus ancien

  useLayoutEffect(() => {
    const el = list.current;
    if (!el) return;
    if (keepFrom.current !== null) {
      el.scrollTop = el.scrollHeight - keepFrom.current; // garde la position de lecture
      keepFrom.current = null;
    } else if (stick.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, typing]);

  const onScroll = async () => {
    const el = list.current;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    if (el.scrollTop < 80 && keepFrom.current === null) {
      keepFrom.current = el.scrollHeight;
      if (!(await loadOlder())) keepFrom.current = null;
    }
  };

  const reset = async () => {
    const ok = await confirm({
      title: "Effacer la conversation ?",
      message: "L'historique de ce chat et sa mémoire courte de la conversation sont effacés. Ses souvenirs à long terme restent.",
      confirmLabel: "Effacer",
      danger: true,
    });
    if (!ok) return;
    try {
      await clearMessages();
      clear();
      toast("Conversation effacée.");
    } catch (error) {
      toast(error.message, "error");
    }
  };

  const user = session.user;
  return (
    <main className="mx-auto flex h-[calc(100dvh-3.5rem)] w-full max-w-3xl flex-col px-3 sm:px-4">
      <div className="flex items-center justify-between gap-3 border-b border-stone-200 py-3 dark:border-stone-800">
        <div>
          <h1 className="text-xl font-bold">{session.name}</h1>
          <p className="text-sm text-stone-500 dark:text-stone-400">
            {can(user, "act")
              ? "Elle peut agir pour toi (outils, souvenirs, code avec ta confirmation)."
              : "Discussion et recherches seulement (ton rôle ne lui permet pas d'agir pour toi)."}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={reset}>Effacer la conversation</Button>
      </div>

      <div ref={list} onScroll={onScroll} role="log" aria-live="polite" className="flex flex-1 flex-col gap-1.5 overflow-y-auto overscroll-contain px-1 py-4">
        {messages.length === 0 ? (
          <div className="m-auto text-center text-stone-500">
            <img src="/favicon.svg" alt="" className="mx-auto mb-2 h-12 w-12 opacity-80" />
            Dis bonjour à {session.name} !
          </div>
        ) : (
          withDays(messages).map((item) =>
            item.day ? (
              <div key={item.day} className="my-3 self-center rounded-full bg-stone-200/70 px-3 py-0.5 text-xs text-stone-500 dark:bg-stone-800">
                {item.label}
              </div>
            ) : (
              <Message key={item.message.id} message={item.message} canAnswer={can(user, "act")} />
            ),
          )
        )}
      </div>

      {typing && (
        <div className="flex items-center gap-2 px-1 pb-1.5 text-sm text-stone-500">
          <span className="flex gap-1">
            {[0, 150, 300].map((delay) => (
              <i key={delay} style={{ animationDelay: `${delay}ms` }} className="h-1.5 w-1.5 animate-blink rounded-full bg-stone-400 motion-reduce:animate-none" />
            ))}
          </span>
          {session.name} écrit…
        </div>
      )}
      {status && <p className="px-1 pb-1 text-xs text-amber-700 dark:text-amber-400">{status}</p>}
      <Composer name={session.name} onSent={upsert} />
      <p className="hidden py-2 text-center text-xs text-stone-500 sm:block">Entrée pour envoyer · Maj+Entrée pour aller à la ligne</p>
      <div className="h-3 sm:hidden" />
    </main>
  );
}

function withDays(messages) {
  const out = [];
  let day = null;
  for (const message of messages) {
    const date = new Date(message.created * 1000);
    const key = date.toDateString();
    if (key !== day) {
      day = key;
      out.push({ day: key, label: date.toLocaleDateString("fr-CH", { weekday: "long", day: "numeric", month: "long" }) });
    }
    out.push({ message });
  }
  return out;
}

function ChatUnavailable() {
  return (
    <main className="mx-auto my-16 max-w-xl px-4">
      <h1 className="mb-2 text-2xl font-bold">Chat indisponible</h1>
      <p className="text-stone-500 dark:text-stone-400">
        Le chat n'existe que quand Rosalie tourne avec l'interface web (<code className="font-mono">python bot.py</code>).
        Ici, seul le site est lancé (<code className="font-mono">python bot.py web</code>).
      </p>
    </main>
  );
}
