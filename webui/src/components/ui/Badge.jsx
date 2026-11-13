const TONES = {
  neutral: "border-stone-200 bg-stone-100 text-stone-600 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-400",
  accent: "border-transparent bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
  warn: "border-transparent bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
};

export default function Badge({ tone = "neutral", className = "", ...props }) {
  return (
    <span
      className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${TONES[tone]} ${className}`}
      {...props}
    />
  );
}
