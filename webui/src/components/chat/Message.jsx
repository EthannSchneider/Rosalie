import { fileUrl } from "../../api/chat.js";
import ConfirmCard from "./ConfirmCard.jsx";
import Markdown, { withBreaks } from "./Markdown.jsx";

export default function Message({ message, canAnswer }) {
  const mine = message.author === "user";
  const time = new Date(message.created * 1000).toLocaleTimeString("fr-CH", { hour: "2-digit", minute: "2-digit" });
  const reactions = message.meta.reactions ?? [];
  return (
    <div className={`flex max-w-[92%] flex-col sm:max-w-[min(85%,640px)] ${mine ? "items-end self-end" : "self-start"}`}>
      <div
        className={`rounded-[18px] px-3.5 py-2 leading-relaxed [overflow-wrap:anywhere] ${
          mine
            ? "rounded-br-md bg-rose-600 text-white dark:bg-rose-500 dark:text-stone-950"
            : "rounded-bl-md border border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900"
        }`}
      >
        {message.kind === "confirm" ? (
          <ConfirmCard message={message} canAnswer={canAnswer} />
        ) : mine ? (
          withBreaks(message.text)
        ) : (
          <Markdown text={message.text} />
        )}
        {(message.meta.files ?? []).map((file) => <Attachment key={file.id} file={file} />)}
      </div>
      <div className="flex gap-2 px-2 pt-0.5 text-[0.7rem] text-stone-500">
        {reactions.length > 0 && <span className="text-sm">{reactions.join(" ")}</span>}
        <time>{time}</time>
      </div>
    </div>
  );
}

function Attachment({ file }) {
  const url = fileUrl(file.id);
  if (file.type?.startsWith("image/") && file.type !== "image/svg+xml") {
    return (
      <a href={url} target="_blank" rel="noopener">
        <img src={url} alt={file.name} loading="lazy" className="mt-1.5 block max-h-80 max-w-full rounded-xl" />
      </a>
    );
  }
  return (
    <a href={url} download={file.name} className="mt-1.5 inline-block underline">
      📎 {file.name}
    </a>
  );
}
