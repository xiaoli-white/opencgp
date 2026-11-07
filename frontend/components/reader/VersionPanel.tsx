import { useMemo, useState } from "react";
import { Eye, GitCompare, History, Loader2, RotateCcw } from "lucide-react";
import clsx from "clsx";
import { api, type UnitVersion } from "@/lib/api";
import { contentLength, formatDateTime } from "@/lib/format";
import VersionDiffDialog from "@/components/reader/VersionDiffDialog";
import VersionPreviewDialog from "@/components/reader/VersionPreviewDialog";
import { useI18n } from "@/i18n/I18nProvider";
import { modeLabel } from "@/i18n/labels";

type VersionPanelProps = {
  versions: UnitVersion[];
  currentVersion: number;
  loading: boolean;
  busyVersion: number | null;
  onRevert: (version: number) => Promise<void>;
  unitId?: string;
  className?: string;
};

export default function VersionPanel({
  versions,
  currentVersion,
  loading,
  busyVersion,
  onRevert,
  unitId,
  className,
}: VersionPanelProps) {
  const { t } = useI18n();
  const [previewVersion, setPreviewVersion] = useState<number | null>(null);
  const [diffOpen, setDiffOpen] = useState(false);
  const [diffAnchor, setDiffAnchor] = useState<number | null>(null);

  const ordered = useMemo(
    () => [...versions].sort((a, b) => b.version - a.version),
    [versions],
  );

  const versionNumbers = useMemo(
    () => ordered.map((version) => version.version),
    [ordered],
  );

  const loadPreview = async (version: number) => {
    if (unitId) {
      const detail = await api.getUnitVersion(unitId, version);
      return {
        content: detail.version.content ?? "",
        citations: detail.version.citations ?? [],
      };
    }
    const local = versions.find((item) => item.version === version);
    return { content: local?.content ?? "", citations: local?.citations ?? [] };
  };

  const fetchDiff = async (from: number, to: number) => {
    if (!unitId) throw new Error(t("reader.missingUnit"));
    return api.diffUnitVersions(unitId, from, to);
  };

  const openDiff = (version?: number) => {
    setDiffAnchor(version ?? null);
    setDiffOpen(true);
  };

  return (
    <div
      className={clsx(
        "glass flex min-h-0 flex-col rounded-3xl p-4 shadow-glass",
        className,
      )}
    >
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
          <History size={13} />
          {t("reader.versions")}
        </div>
        <span className="chip-muted">
          {t("reader.currentVersion", { version: currentVersion || 0 })}
        </span>
      </div>

      {versionNumbers.length > 1 ? (
        <button
          type="button"
          onClick={() => openDiff()}
          className="btn-quiet mt-2 w-full justify-center text-[11px]"
        >
          <GitCompare size={12} />
          {t("reader.compareAny")}
        </button>
      ) : null}

      <div className="no-scrollbar mt-3 flex-1 space-y-1.5 overflow-y-auto pr-1">
        {loading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((item) => (
              <div
                key={item}
                className="h-14 animate-pulse rounded-2xl bg-slate-200/50 dark:bg-white/5"
              />
            ))}
          </div>
        ) : ordered.length === 0 ? (
          <p className="px-1 py-4 text-[11px] leading-relaxed text-slate-400 dark:text-slate-500">
            {t("reader.versionsEmpty")}
          </p>
        ) : (
          ordered.map((version) => {
            const isCurrent = version.version === currentVersion;
            return (
              <div
                key={version.id}
                className={clsx(
                  "rounded-2xl border p-2.5 transition",
                  isCurrent
                    ? "border-indigo-400/40 bg-indigo-500/8 dark:border-indigo-400/30 dark:bg-indigo-400/10"
                    : "border-slate-200/60 bg-white/40 hover:border-indigo-300/60 hover:bg-white/70 dark:border-white/10 dark:bg-white/[0.03] dark:hover:border-indigo-400/30 dark:hover:bg-white/[0.06]",
                )}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={clsx(
                      "grid h-6 min-w-[1.9rem] place-items-center rounded-lg px-1 text-[11px] font-semibold",
                      isCurrent
                        ? "brand-gradient text-white"
                        : "bg-slate-200/70 text-slate-500 dark:bg-white/10 dark:text-slate-300",
                    )}
                  >
                    v{version.version}
                  </span>
                  <span
                    className={clsx(
                      "shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-semibold tracking-wide",
                      version.mode === "loose"
                        ? "bg-amber-400/22 text-amber-700 ring-1 ring-amber-400/30 dark:bg-amber-300/15 dark:text-amber-300 dark:ring-amber-300/25"
                        : "bg-indigo-500/12 text-indigo-600 ring-1 ring-indigo-400/20 dark:bg-indigo-400/14 dark:text-indigo-300 dark:ring-indigo-300/20",
                    )}
                    title={
                      version.mode === "loose"
                        ? t("reader.modeLooseTip")
                        : t("reader.modeStrictTip")
                    }
                  >
                    {modeLabel(t, version.mode)}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[12px] text-slate-600 dark:text-slate-300">
                    {version.note || t("reader.autoArchive")}
                  </span>
                  {isCurrent && (
                    <span className="text-[10px] font-medium text-indigo-500 dark:text-indigo-300">
                      {t("reader.currentShort")}
                    </span>
                  )}
                </div>
                <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500">
                  <span>{formatDateTime(version.created_at)}</span>
                  <span>
                    {t("reader.chars", {
                      count: contentLength(version.content),
                    })}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setPreviewVersion(version.version)}
                    className="btn-quiet"
                  >
                    <Eye size={12} />
                    {t("reader.preview")}
                  </button>
                  <button
                    type="button"
                    onClick={() => openDiff(version.version)}
                    className="btn-quiet"
                  >
                    <GitCompare size={12} />
                    {t("reader.compare")}
                  </button>
                  <button
                    type="button"
                    onClick={() => onRevert(version.version)}
                    disabled={isCurrent || busyVersion !== null}
                    className="btn-quiet disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {busyVersion === version.version ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      <RotateCcw size={12} />
                    )}
                    {t("reader.revert")}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      <VersionPreviewDialog
        open={previewVersion !== null}
        version={previewVersion}
        load={loadPreview}
        onClose={() => setPreviewVersion(null)}
        onCompare={() => {
          const target = previewVersion;
          setPreviewVersion(null);
          if (target !== null) openDiff(target);
        }}
      />

      <VersionDiffDialog
        open={diffOpen}
        versions={versionNumbers}
        initialFrom={
          diffAnchor !== null
            ? Math.max(1, diffAnchor - 1)
            : versionNumbers[0]
        }
        initialTo={
          diffAnchor ??
          (currentVersion || versionNumbers[versionNumbers.length - 1])
        }
        fetchDiff={fetchDiff}
        onClose={() => setDiffOpen(false)}
      />
    </div>
  );
}
