// État du chat : historique (paginé), messages en direct (Server-Sent Events), « écrit… ».
// Après une coupure, l'historique est rechargé pour rattraper ce qui a été dit entre-temps.
import { useCallback, useEffect, useRef, useState } from "react";
import { EVENTS_URL, PAGE, getMessages } from "../api/chat.js";

export default function useChat(enabled) {
  const [messages, setMessages] = useState(new Map()); // id -> message
  const [typing, setTyping] = useState(false);
  const [status, setStatus] = useState("");
  const [complete, setComplete] = useState(false);
  const oldest = useRef(null);

  const upsert = useCallback((message) => {
    setMessages((current) => new Map(current).set(message.id, message));
  }, []);

  const reload = useCallback(async () => {
    try {
      const page = await getMessages();
      oldest.current = page[0]?.id ?? null;
      setComplete(page.length < PAGE);
      setMessages(new Map(page.map((m) => [m.id, m])));
    } catch (error) {
      setStatus(error.message);
    }
  }, []);

  const loadOlder = useCallback(async () => {
    if (complete || oldest.current === null) return false;
    const page = await getMessages(oldest.current);
    setComplete(page.length < PAGE);
    if (!page.length) return false;
    oldest.current = page[0].id;
    setMessages((current) => new Map([...page.map((m) => [m.id, m]), ...current]));
    return true;
  }, [complete]);

  const clear = useCallback(() => {
    setMessages(new Map());
    setComplete(true);
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
    reload();
    const events = new EventSource(EVENTS_URL);
    let failed = false;
    events.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "typing") setTyping(data.on);
      else if (data.message) {
        if (data.type === "message" && data.message.author === "rosalie") setTyping(false);
        upsert(data.message);
      }
    };
    events.onerror = () => {
      failed = true;
      setStatus("Connexion perdue, reconnexion…");
    };
    events.onopen = () => {
      setStatus("");
      if (failed) reload();
      failed = false;
    };
    return () => events.close();
  }, [enabled, reload, upsert]);

  const sorted = [...messages.values()].sort((a, b) => a.id - b.id);
  return { messages: sorted, typing, status, complete, upsert, loadOlder, clear };
}
