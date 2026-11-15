// Évolution du code (permission « evolve », superadmin) : demander une modification au modèle de
// code, suivre chaque opération (analyse → modification → tests → pull request → fusion → mise à
// jour → redémarrage), fusionner, puis mettre à jour et redémarrer. Le serveur revérifie tout.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getEvolution, mergePull, requestChange, updateAndRestart } from "../../api/evolution.js";
import Badge from "../../components/ui/Badge.jsx";
import Button from "../../components/ui/Button.jsx";
import Card from "../../components/ui/Card.jsx";
import Loading from "../../components/ui/Loading.jsx";
import { hintClass, inputClass } from "../../components/ui/styles.js";
import { useDialog } from "../../context/DialogContext.jsx";
import { useToast } from "../../context/ToastContext.jsx";

// Les étapes d'une opération, dans l'ordre affiché
const STEPS = [
  { label: "Analyse", statuses: ["analysis"] },
  { label: "Modification", statuses: ["editing"] },
  { label: "Tests", statuses: ["testing"] },
  { label: "Pull request", statuses: ["pr_open"] },
  { label: "Fusion", statuses: ["merged"] },
  { label: "Mise à jour", statuses: ["updating"] },
  { label: "Redémarrage", statuses: ["restarting"] },
  { label: "Terminé", statuses: ["done"] },
];
const STATUS_LABELS = {
  analysis: "Analyse du code", editing: "Modification en cours", testing: "Tests en cours",
  pr_open: "Pull request ouverte, en attente de fusion", merged: "Fusionnée, prête à être appliquée",
  updating: "Mise à jour en cours", restarting: "Redémarrage en cours", done: "Réussite",
  failed: "Échec", closed: "Pull request fermée sans fusion", update_failed: "Mise à jour en échec",
};
const link = "text-rose-600 underline dark:text-rose-400";
const short = (sha) => (sha ? sha.slice(0, 10) : "—");
const when = (seconds) => new Date(seconds * 1000).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });

export default function EvolutionPage() {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [away, setAway] = useState(false); // site injoignable : Rosalie redémarre
  const busy = useRef(false);

  const load = useCallback(async () => {
    try {
      setData(await getEvolution());
      setAway(false);
      setError(null);
    } catch (failure) {
      if (failure.status === 0) setAway(true);
      else setError(failure.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Suivi en direct tant qu'une opération avance (ou que Rosalie redémarre)
  const active = away || Boolean(data?.busy);
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [active, load]);

  const run = useCallback(async (action, success) => {
    if (busy.current) return false;
    busy.current = true;
    try {
      setData(await action());
      if (success) toast(success);
      return true;
    } catch (failure) {
      toast(failure.message, "error");
      return false;
    } finally {
      busy.current = false;
    }
  }, [toast]);

  if (!data) return <Loading text={error ? `Oups : ${error}` : "Chargement…"} />;
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6">
      <h1 className="mb-1 text-2xl font-bold">Évolution du code</h1>
      <p className={`${hintClass} mb-5`}>
        Rosalie fait modifier son propre code par son modèle de code (<code>{data.code_model}</code>), dans une pull
        request sur <code>{data.repo}</code>. Rien n\u2019est fusionné ni appliqué sans une action d\u2019un superadmin.
      </p>

      {away && (
        <Card className="mb-5 border-amber-300 px-5 py-3 dark:border-amber-800" role="status">
          Rosalie ne répond pas pour l\u2019instant (elle redémarre peut-être) : cette page se met à jour toute seule.
        </Card>
      )}
      {data.problems.length > 0 && (
        <Card className="mb-5 px-5 py-3">
          <p className="font-medium">Pas encore prêt :</p>
          <ul className="ml-5 list-disc text-sm">
            {data.problems.map((problem) => <li key={problem}>{problem}</li>)}
          </ul>
          <p className={`${hintClass} mt-1`}>
            <Link className={link} to="/settings/evolution-du-code">Réglages → Évolution du code</Link>
          </p>
        </Card>
      )}
      {data.notice && <p className={`${hintClass} mb-3`}>⚠️ {data.notice}</p>}

      <div className={`${hintClass} mb-5 flex flex-wrap items-center gap-x-4 gap-y-1`}>
        <span>Version qui tourne : <code>{short(data.version)}</code></span>
        <span>
          Superviseur :{" "}
          {data.supervised ? <Badge tone="accent">actif</Badge> : <Badge tone="warn">absent</Badge>}
        </span>
        {!data.supervised && <span>(mise à jour d\u2019ici impossible : lance Rosalie avec <code>python bot.py supervise</code>)</span>}
      </div>

      <RequestForm data={data} onSubmit={(brief) => run(() => requestChange(brief), "Demande transmise au modèle de code")} />

      <h2 className="mt-8 mb-3 text-lg font-semibold">Opérations</h2>
      {data.operations.length === 0 && <p className={hintClass}>Aucune opération pour l\u2019instant.</p>}
      <div className="grid gap-4">
        {data.operations.map((operation) => (
          <Operation key={operation.id} operation={operation} data={data} run={run} />
        ))}
      </div>
    </main>
  );
}

function RequestForm({ data, onSubmit }) {
  const empty = { title: "", reason: "feature", objective: "", context: "", constraints: "", criteria: "" };
  const [brief, setBrief] = useState(empty);
  const [sending, setSending] = useState(false);
  const set = (key) => (event) => setBrief({ ...brief, [key]: event.target.value });
  const blocked = data.problems.length > 0 || data.busy;
  const area = (key, label, placeholder, rows = 2) => (
    <label className="grid gap-1 text-sm font-medium">
      {label}
      <textarea rows={rows} value={brief[key]} onChange={set(key)} placeholder={placeholder} className={inputClass} />
    </label>
  );
  return (
    <Card as="details" className="px-5 py-3">
      <summary className="cursor-pointer font-medium">Demander une modification</summary>
      <form
        className="mt-3 grid gap-3"
        onSubmit={async (event) => {
          event.preventDefault();
          setSending(true);
          if (await onSubmit(brief)) setBrief(empty);
          setSending(false);
        }}
      >
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_14rem]">
          <label className="grid gap-1 text-sm font-medium">
            Titre
            <input value={brief.title} onChange={set("title")} required minLength={4} maxLength={120} className={inputClass} />
          </label>
          <label className="grid gap-1 text-sm font-medium">
            Raison
            <select value={brief.reason} onChange={set("reason")} className={inputClass}>
              {data.reasons.map((reason) => <option key={reason.name} value={reason.name}>{reason.label}</option>)}
            </select>
          </label>
        </div>
        {area("objective", "Objectif", "Ce qui doit changer, précisément", 3)}
        {area("context", "Contexte", "Ce qu\u2019il faut savoir : ce qui s\u2019est passé, erreurs, fichiers concernés")}
        {area("constraints", "Contraintes", "Ce qu\u2019il ne faut pas faire ou pas casser")}
        {area("criteria", "Critères de réussite", "Comportement attendu, tests à ajouter")}
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={blocked || sending || brief.objective.trim().length < 10}>Lancer</Button>
          {data.busy && <span className={hintClass}>Une opération est déjà en cours : une seule à la fois.</span>}
        </div>
      </form>
    </Card>
  );
}

function Operation({ operation, data, run }) {
  const { confirm } = useDialog();
  const failed = ["failed", "closed", "update_failed"].includes(operation.status);
  const live = operation.working || operation.deploying;

  const merge = async () => {
    const ok = await confirm({
      title: "Fusionner la pull request ?",
      message: `« ${operation.title} » sera fusionnée dans ${data.base}. Relis-la d\u2019abord sur GitHub.`,
      confirmLabel: "Fusionner",
    });
    if (ok) run(() => mergePull(operation.id), "Pull request fusionnée");
  };
  const update = async () => {
    const ok = await confirm({
      title: "Mettre à jour et redémarrer ?",
      message: `Rosalie va s\u2019arrêter, passer à la version ${short(operation.merged_sha)}, puis redémarrer. `
        + "Si elle ne redémarre pas, la version précédente est restaurée.",
      confirmLabel: "Mettre à jour et redémarrer",
      danger: true,
    });
    if (ok) run(() => updateAndRestart(operation.id), "Mise à jour lancée");
  };

  return (
    <Card className="px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h3 className="font-semibold [overflow-wrap:anywhere]">
            <span className="text-stone-400">#{operation.id}</span> {operation.title}
          </h3>
          <p className={hintClass}>
            {operation.reason_label} · demandé par {operation.author} · {when(operation.created)}
          </p>
        </div>
        <Badge tone={failed ? "warn" : operation.status === "done" ? "accent" : "neutral"}>
          {STATUS_LABELS[operation.status] ?? operation.status}
        </Badge>
      </div>

      <Steps operation={operation} failed={failed} />
      {live && operation.detail && <p className={`${hintClass} mt-2`} role="status">… {operation.detail}</p>}
      {operation.error && (
        <p className="mt-2 text-sm text-red-700 [overflow-wrap:anywhere] dark:text-red-400">⚠️ {operation.error}</p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        {operation.pr_url && (
          <a className={link} href={operation.pr_url} target="_blank" rel="noreferrer noopener">
            Pull request #{operation.pr_number}
          </a>
        )}
        {operation.checks_ok === false && <Badge tone="warn">vérification en échec</Badge>}
        {operation.status === "pr_open" && operation.checks_ok && (
          <Button size="sm" variant="ghost" onClick={merge}>Fusionner</Button>
        )}
        {operation.status === "pr_open" && operation.checks_ok === false && (
          <span className={hintClass}>À relire et fusionner sur GitHub (pas d\u2019ici).</span>
        )}
        {["merged", "update_failed"].includes(operation.status) && (
          <Button size="sm" onClick={update} disabled={!data.supervised || data.busy}>
            {operation.status === "update_failed" ? "Réessayer la mise à jour" : "Mettre à jour et redémarrer"}
          </Button>
        )}
      </div>

      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-stone-500 dark:text-stone-400">Détails et historique</summary>
        <dl className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-[max-content_minmax(0,1fr)]">
          <Row label="Objectif" value={operation.brief.objective} />
          <Row label="Contexte" value={operation.brief.context} />
          <Row label="Contraintes" value={operation.brief.constraints} />
          <Row label="Critères de réussite" value={operation.brief.criteria} />
          <Row label="Résumé du modèle de code" value={operation.summary} />
          <Row label="Branche" value={operation.branch} code />
          <Row label="Commit poussé" value={operation.head_sha} code />
          <Row label="Commit de fusion" value={operation.merged_sha} code />
          <Row label="Version précédente" value={operation.previous_sha} code />
          <Row label="Version appliquée" value={operation.deployed_sha} code />
        </dl>
        {operation.checks.length > 0 && (
          <ul className="mt-3 grid gap-1">
            {operation.checks.map((check) => (
              <li key={check.name}>
                {check.ok ? "✅" : check.ok === null ? "⚠️ non lancée :" : "❌"} {check.name}
                {!check.ok && check.output && (
                  <pre className="mt-1 max-h-60 overflow-auto rounded-lg bg-stone-100 p-2 text-xs whitespace-pre-wrap dark:bg-stone-800">
                    {check.output}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        )}
        <ol className="mt-3 grid gap-0.5 text-stone-500 dark:text-stone-400">
          {operation.events.map((event, index) => (
            <li key={index}>
              {when(event.at)} — {event.message || STATUS_LABELS[event.status] || event.status}
              {event.by && ` (${event.by})`}
            </li>
          ))}
        </ol>
      </details>
    </Card>
  );
}

function Steps({ operation, failed }) {
  const reached = STEPS.findIndex((step) => step.statuses.includes(operation.status));
  // en échec : on montre jusqu'où l'opération est allée (dernière étape connue du journal)
  const last = failed
    ? Math.max(...operation.events.map((event) => STEPS.findIndex((step) => step.statuses.includes(event.status))))
    : reached;
  return (
    <ol className="mt-3 flex flex-wrap gap-1.5 text-xs" aria-label="Étapes">
      {STEPS.map((step, index) => {
        const state = index < last || operation.status === "done" ? "done" : index === last ? (failed ? "failed" : "current") : "todo";
        const tones = {
          done: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
          current: "bg-amber-100 font-semibold text-amber-800 dark:bg-amber-950 dark:text-amber-300",
          failed: "bg-red-100 font-semibold text-red-700 dark:bg-red-950 dark:text-red-400",
          todo: "bg-stone-100 text-stone-400 dark:bg-stone-800",
        };
        return (
          <li key={step.label} aria-current={state === "current" ? "step" : undefined} className={`rounded-full px-2.5 py-0.5 ${tones[state]}`}>
            {state === "done" ? "✓ " : state === "failed" ? "✕ " : ""}{step.label}
          </li>
        );
      })}
    </ol>
  );
}

function Row({ label, value, code }) {
  if (!value) return null;
  return (
    <div className="contents">
      <dt className="font-medium">{label}</dt>
      <dd className="whitespace-pre-wrap text-stone-600 [overflow-wrap:anywhere] dark:text-stone-300">
        {code ? <code className="text-xs">{value}</code> : value}
      </dd>
    </div>
  );
}
