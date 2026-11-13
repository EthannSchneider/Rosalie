// Un Markdown réduit pour les messages de Rosalie, rendu en éléments React (jamais en HTML) :
// blocs ```code```, `code`, **gras**, *italique*, ~~barré~~, liens http(s), listes, titres, citations.
import { Fragment } from "react";
import CodeBlock from "./CodeBlock.jsx";

export default function Markdown({ text }) {
  return <>{blocks(text)}</>;
}

function blocks(text) {
  const lines = text.split("\n");
  const out = [];
  let paragraph = [];
  let list = null;
  const key = () => out.length;

  const flushParagraph = () => {
    if (paragraph.length) out.push(<p key={key()} className="mb-2 last:mb-0">{inline(paragraph.join("\n"))}</p>);
    paragraph = [];
  };
  const flushList = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    out.push(
      <Tag key={key()} className={`mb-2 pl-5 last:mb-0 ${list.ordered ? "list-decimal" : "list-disc"}`}>
        {list.items.map((item, i) => <li key={i}>{inline(item)}</li>)}
      </Tag>,
    );
    list = null;
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const fence = line.match(/^\s*```\s*([\w+-]*)\s*$/);
    if (fence) {
      flushParagraph();
      flushList();
      const code = [];
      index += 1;
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) {
        code.push(lines[index]);
        index += 1;
      }
      out.push(<CodeBlock key={key()} code={code.join("\n")} language={fence[1]} />);
      continue;
    }
    const item = line.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/);
    if (item) {
      flushParagraph();
      const ordered = Boolean(item[1]);
      if (list && list.ordered !== ordered) flushList();
      list ??= { ordered, items: [] };
      list.items.push(item[2]);
    } else if (/^#{1,4}\s/.test(line)) {
      flushParagraph();
      flushList();
      out.push(<p key={key()} className="mb-2 font-semibold">{inline(line.replace(/^#+\s*/, ""))}</p>);
    } else if (/^>\s?/.test(line)) {
      flushParagraph();
      flushList();
      out.push(
        <blockquote key={key()} className="mb-2 border-l-3 border-stone-300 pl-3 text-stone-500 dark:border-stone-600 dark:text-stone-400">
          {inline(line.replace(/^>\s?/, ""))}
        </blockquote>,
      );
    } else if (!line.trim()) {
      flushParagraph();
      flushList();
    } else {
      flushList();
      paragraph.push(line);
    }
  }
  flushParagraph();
  flushList();
  return out;
}

const TOKEN =
  /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(~~[^~\n]+~~)|(\*[^*\s][^*\n]*\*|_[^_\s][^_\n]*_)|(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"»])/g;

function inline(text) {
  const out = [];
  let last = 0;
  for (const match of text.matchAll(TOKEN)) {
    if (match.index > last) out.push(withBreaks(text.slice(last, match.index), out.length));
    const [token] = match;
    const k = out.length;
    if (match[1]) out.push(<code key={k} className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[0.85em] dark:bg-stone-800">{token.slice(1, -1)}</code>);
    else if (match[2]) out.push(<strong key={k}>{inline(token.slice(2, -2))}</strong>);
    else if (match[3]) out.push(<s key={k}>{inline(token.slice(2, -2))}</s>);
    else if (match[4]) out.push(<em key={k}>{inline(token.slice(1, -1))}</em>);
    else if (match[5]) {
      const [, label, url] = token.match(/^\[([^\]]+)\]\((.+)\)$/);
      out.push(<ExternalLink key={k} href={url}>{label}</ExternalLink>);
    } else out.push(<ExternalLink key={k} href={token}>{token}</ExternalLink>);
    last = match.index + token.length;
  }
  if (last < text.length) out.push(withBreaks(text.slice(last), out.length));
  return out;
}

function ExternalLink({ href, children }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-rose-600 underline underline-offset-2 dark:text-rose-400">
      {children}
    </a>
  );
}

export function withBreaks(text, key = 0) {
  return (
    <Fragment key={key}>
      {text.split("\n").map((part, i) => (
        <Fragment key={i}>
          {i > 0 && <br />}
          {part}
        </Fragment>
      ))}
    </Fragment>
  );
}
