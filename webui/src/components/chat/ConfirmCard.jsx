// Demande de confirmation de Rosalie (code à exécuter, action sensible).
import { useState } from "react";
import { answerConfirmation } from "../../api/chat.js";
import { useToast } from "../../context/ToastContext.jsx";
import Button from "../ui/Button.jsx";
import CodeBlock from "./CodeBlock.jsx";

const STATUS = {
  accepted: "✅ Confirmé",
  refused: "❌ Refusé",
  expired: "⌛ Sans réponse, annulé",
};

export default function ConfirmCard({ message, canAnswer }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const { status, code, language } = message.meta;
  const hasCode = code !== undefined;

  const answer = async (accept) => {
    setBusy(true);
    try {
      await answerConfirmation(message.id, accept);
    } catch (error) {
      toast(error.message, "error");
      setBusy(false);
    }
  };

  return (
    <div>
      <p className="font-semibold">⚠️ {message.text}</p>
      {hasCode && <CodeBlock code={code} language={language} />}
      {status === "pending" && canAnswer ? (
        <div className="mt-2 flex gap-2">
          <Button size="sm" disabled={busy} onClick={() => answer(true)}>{hasCode ? "Exécuter" : "Confirmer"}</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => answer(false)}>Annuler</Button>
        </div>
      ) : (
        STATUS[status] && <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">{STATUS[status]}</p>
      )}
    </div>
  );
}
