import clsx from "clsx";
import { Languages } from "lucide-react";
import { useI18n, type Locale } from "@/i18n/I18nProvider";

const OPTIONS: { value: Locale; label: string }[] = [
  { value: "zh", label: "ZH" },
  { value: "en", label: "EN" },
];

export default function LocaleToggle() {
  const { locale, setLocale } = useI18n();

  return (
    <div
      className="inline-flex shrink-0 items-center gap-0.5 rounded-full border border-white/60 bg-white/60 p-0.5 text-[11px] font-medium backdrop-blur-xl dark:border-white/10 dark:bg-white/5"
      role="group"
      aria-label="Language"
    >
      <Languages size={13} className="ml-1.5 shrink-0 text-slate-400 dark:text-slate-500" />
      {OPTIONS.map((option) => {
        const active = locale === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => setLocale(option.value)}
            aria-pressed={active}
            className={clsx(
              "grid h-7 min-w-[26px] place-items-center rounded-full px-1.5 transition",
              active
                ? "brand-gradient text-white shadow-[0_8px_18px_-12px_rgba(99,102,241,0.9)]"
                : "text-slate-500 hover:text-indigo-600 dark:text-slate-300 dark:hover:text-indigo-200",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
