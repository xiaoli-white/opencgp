import clsx from "clsx";
import { statusTone, type StatusTone } from "@/lib/format";
import { unitStatusLabel } from "@/i18n/labels";
import { useI18n } from "@/i18n/I18nProvider";

const TONE_CLASS: Record<StatusTone, string> = {
  neutral:
    "bg-slate-400/15 text-slate-600 ring-slate-400/25 dark:bg-white/10 dark:text-slate-300 dark:ring-white/15",
  indigo:
    "bg-indigo-500/12 text-indigo-600 ring-indigo-400/25 dark:bg-indigo-400/15 dark:text-indigo-300 dark:ring-indigo-300/25",
  emerald:
    "bg-emerald-500/12 text-emerald-700 ring-emerald-500/25 dark:bg-emerald-400/15 dark:text-emerald-300 dark:ring-emerald-300/25",
  amber:
    "bg-amber-400/20 text-amber-700 ring-amber-500/30 dark:bg-amber-300/15 dark:text-amber-300 dark:ring-amber-300/25",
  rose:
    "bg-rose-500/12 text-rose-700 ring-rose-500/25 dark:bg-rose-400/15 dark:text-rose-300 dark:ring-rose-300/25",
};

const DOT_CLASS: Record<StatusTone, string> = {
  neutral: "bg-slate-400 dark:bg-slate-500",
  indigo: "bg-indigo-500 dark:bg-indigo-400",
  emerald: "bg-emerald-500 dark:bg-emerald-400",
  amber: "bg-amber-500 dark:bg-amber-400",
  rose: "bg-rose-500 dark:bg-rose-400",
};

export function statusBadgeClass(status: string, className?: string): string {
  return clsx(
    "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium ring-1",
    TONE_CLASS[statusTone(status)],
    className,
  );
}

export function statusDotClass(status: string): string {
  return DOT_CLASS[statusTone(status)];
}

export default function StatusBadge({
  status,
  className,
  withDot = false,
}: {
  status: string;
  className?: string;
  withDot?: boolean;
}) {
  const { t } = useI18n();
  return (
    <span className={statusBadgeClass(status, className)}>
      {withDot ? (
        <span
          className={clsx("h-1.5 w-1.5 rounded-full", statusDotClass(status))}
        />
      ) : null}
      {unitStatusLabel(t, status)}
    </span>
  );
}
