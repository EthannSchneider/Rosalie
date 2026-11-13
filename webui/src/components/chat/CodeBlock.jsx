import { useState } from "react";

export default function CodeBlock({ code, language }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* presse-papiers refusé */
    }
  };
  return (
    <div className="my-2 overflow-hidden rounded-xl border border-stone-200 bg-stone-50 text-stone-900 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100">
      <div className="flex items-center justify-between border-b border-stone-200 py-1 pr-1.5 pl-3 text-xs text-stone-500 dark:border-stone-700">
        <span>{language || "code"}</span>
        <button type="button" onClick={copy} className="rounded-md px-2 py-0.5 hover:bg-stone-200 dark:hover:bg-stone-800">
          {copied ? "Copié" : "Copier"}
        </button>
      </div>
      <pre className="overflow-x-auto px-3 py-2.5 font-mono text-[0.84rem] leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}
