import { AlertTriangle } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

export default function EvidenceGapNotice({ gaps }: { gaps: string[] }) {
  const { t } = useI18n();
  if (gaps.length === 0) return null;
  const shown = gaps.slice(0, 3);
  const remaining = gaps.length - shown.length;
  return (
    <div
      data-testid="unit-gap-notice"
      className="mt-3 rounded-2xl border border-amber-300/60 bg-amber-50/80 p-4 dark:border-amber-400/25 dark:bg-amber-400/10"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <AlertTriangle size={13} className="text-amber-600 dark:text-amber-300" />
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-700 dark:text-amber-300">
          {t("reader.evidenceGapTitle")}
        </p>
        <span className="rounded-full bg-amber-400/25 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 dark:bg-amber-300/15 dark:text-amber-200">
          {t("reader.evidenceGapTag")}
        </span>
      </div>
      <p className="mt-1.5 text-[11.5px] leading-relaxed text-amber-800/90 dark:text-amber-100/80">
        {t("reader.evidenceGapBody", { count: gaps.length })}
      </p>
      <ul className="mt-2 space-y-1">
        {shown.map((gap, index) => (
          <li key={`${index}-${gap.slice(0, 24)}`} className="flex items-start gap-1.5 text-[11px] leading-relaxed text-amber-900/80 dark:text-amber-100/70">
            <span className="mt-0.5 shrink-0 font-medium">
              {t("reader.evidenceGapItem", { index: index + 1 })}
            </span>
            <span className="min-w-0">{gap}</span>
          </li>
        ))}
      </ul>
      {remaining > 0 ? (
        <p className="mt-1.5 text-[10.5px] text-amber-700/80 dark:text-amber-200/70">
          {t("reader.evidenceGapMore", { count: remaining })}
        </p>
      ) : null}
    </div>
  );
}
