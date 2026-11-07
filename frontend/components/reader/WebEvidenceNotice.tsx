import { Globe, Info } from "lucide-react";
import clsx from "clsx";
import type { Citation, EvidenceGatePayload } from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";

type WebEvidenceNoticeProps = {
  gate?: EvidenceGatePayload | null;
  citations?: Citation[];
  className?: string;
};

function countsFromCitations(citations: Citation[] | undefined) {
  let local = 0;
  let web = 0;
  for (const citation of citations ?? []) {
    const kind = String(citation.meta?.kind ?? "").toLowerCase();
    if (kind === "web") web += 1;
    else local += 1;
  }
  return { local, web };
}

/**
 * Shows where the evidence came from. Web passages are never presented as the
 * user's own knowledge base: the banner names the counts and asks the reader to
 * verify the archived passage.
 */
export default function WebEvidenceNotice({
  gate,
  citations,
  className,
}: WebEvidenceNoticeProps) {
  const { t } = useI18n();
  const fromCitations = countsFromCitations(citations);
  const local =
    typeof gate?.local_passages === "number"
      ? gate.local_passages
      : fromCitations.local;
  const web =
    typeof gate?.web_passages === "number" ? gate.web_passages : fromCitations.web;
  const reason = String(gate?.web_fallback?.error ?? "");

  if (web > 0) {
    return (
      <div
        data-testid="web-evidence-notice"
        data-web-passages={web}
        data-local-passages={local}
        data-origin={local > 0 ? "mixed" : "web"}
        className={clsx(
          "mt-3 flex items-start gap-2 rounded-2xl border border-amber-300/60 bg-amber-50/80 px-4 py-2.5 text-[11.5px] leading-relaxed text-amber-800 dark:border-amber-300/25 dark:bg-amber-400/10 dark:text-amber-200",
          className,
        )}
      >
        <Globe size={13} className="mt-0.5 shrink-0" />
        <div className="min-w-0">
          <p className="font-semibold">{t("webEvidence.title")}</p>
          <p className="mt-0.5">
            {local > 0
              ? t("webEvidence.mixed", { web, local })
              : t("webEvidence.webOnly", { web })}
          </p>
        </div>
      </div>
    );
  }

  if (gate?.profile_opted_out_web) {
    return (
      <div
        data-testid="web-evidence-notice"
        data-origin="opted-out"
        className={clsx(
          "mt-3 flex items-start gap-2 rounded-2xl border border-slate-300/60 bg-slate-100/70 px-4 py-2.5 text-[11.5px] leading-relaxed text-slate-600 dark:border-white/10 dark:bg-white/[0.06] dark:text-slate-300",
          className,
        )}
      >
        <Info size={13} className="mt-0.5 shrink-0" />
        <p>{t("webEvidence.optedOut")}</p>
      </div>
    );
  }

  if (gate?.web_fallback?.attempted && web === 0) {
    return (
      <div
        data-testid="web-evidence-notice"
        data-origin="web-failed"
        className={clsx(
          "mt-3 flex items-start gap-2 rounded-2xl border border-rose-300/50 bg-rose-50/70 px-4 py-2.5 text-[11.5px] leading-relaxed text-rose-700 dark:border-rose-300/25 dark:bg-rose-400/10 dark:text-rose-200",
          className,
        )}
      >
        <Info size={13} className="mt-0.5 shrink-0" />
        <p>{t("webEvidence.unavailable", { reason: reason || "no_results" })}</p>
      </div>
    );
  }

  return null;
}
