const VARIANTS = {
  primary: "bg-rose-600 text-white hover:bg-rose-500 dark:bg-rose-500 dark:text-stone-950 dark:hover:bg-rose-400",
  ghost:
    "border border-stone-300 bg-white text-stone-800 hover:bg-stone-100 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 dark:hover:bg-stone-800",
  danger:
    "border border-red-300 bg-white text-red-700 hover:bg-red-50 dark:border-red-900 dark:bg-stone-900 dark:text-red-400 dark:hover:bg-red-950",
  plain: "text-stone-500 hover:bg-stone-100 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-100",
};
const SIZES = { sm: "px-2.5 py-1 text-sm", md: "px-4 py-2" };

export default function Button({ variant = "primary", size = "md", className = "", type = "button", ...props }) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium whitespace-nowrap transition disabled:cursor-default disabled:opacity-50 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    />
  );
}
