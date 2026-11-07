import { useCallback, useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Download, FileText, Globe, BookOpen, Loader2 } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import { exportFormatHint, exportFormatLabel } from "@/i18n/labels";
import clsx from "clsx";
import {
  ApiError,
  api,
  exportDocument,
  type ExportFormat,
  type ExportFormatId,
  type ExportSourceType,
} from "@/lib/api";

type ExportMenuProps = {
  sourceType: ExportSourceType;
  sourceId: string;
  fallbackName?: string;
  className?: string;
};

const FALLBACK_FORMATS: ExportFormat[] = [
  { id: "md", label: "Markdown", available: true },
  { id: "html", label: "HTML", available: true },
  { id: "epub", label: "EPUB", available: true },
  { id: "pdf", label: "PDF", available: true },
];

const FORMAT_ICON: Record<string, typeof FileText> = {
  md: FileText,
  html: Globe,
  epub: BookOpen,
  pdf: FileText,
};

export default function ExportMenu({
  sourceType,
  sourceId,
  fallbackName,
  className,
}: ExportMenuProps) {
  const { t } = useI18n();
  const [formats, setFormats] = useState<ExportFormat[]>([]);
  const [includeCitations, setIncludeCitations] = useState(true);
  const [busy, setBusy] = useState<ExportFormatId | "">("");
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let alive = true;
    void api
      .getExportFormats()
      .then((data) => {
        if (alive && data.formats?.length) setFormats(data.formats);
      })
      .catch(() => {
        if (alive) setFormats(FALLBACK_FORMATS);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent | TouchEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("touchstart", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("touchstart", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const options = formats.length ? formats : FALLBACK_FORMATS;

  const download = useCallback(
    async (format: ExportFormatId) => {
      if (busy) return;
      setBusy(format);
      setError("");
      try {
        const result = await exportDocument(sourceType, sourceId, format, {
          theme: document.documentElement.classList.contains("dark") ? "dark" : "light",
          includeCitations,
          fallbackName,
        });
        const href = URL.createObjectURL(result.blob);
        const anchor = document.createElement("a");
        anchor.href = href;
        anchor.download = result.filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(href), 4000);
        setOpen(false);
      } catch (err) {
        setError(
          err instanceof ApiError || err instanceof Error ? err.message : t("export.failed"),
        );
      } finally {
        setBusy("");
      }
    },
    [busy, sourceType, sourceId, includeCitations, fallbackName, t],
  );

  return (
    <div ref={wrapRef} className={clsx("relative inline-flex", className)}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={clsx(
          "inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-[11px] font-medium transition",
          open
            ? "border-indigo-300 bg-white text-indigo-600 dark:border-indigo-400/40 dark:bg-white/10 dark:text-indigo-200"
            : "border-slate-200/70 bg-white/70 text-slate-600 hover:border-indigo-300 hover:text-indigo-600 dark:border-white/10 dark:bg-white/[0.05] dark:text-slate-300 dark:hover:text-indigo-300",
        )}
      >
        <Download size={13} />
        {t("export.label")}
        <ChevronDown
          size={12}
          className={clsx("transition", open && "rotate-180")}
        />
      </button>

      {open ? (
        <div
          role="menu"
          className="glass absolute right-0 top-[calc(100%+6px)] z-50 w-56 overflow-hidden rounded-2xl border border-white/60 p-1.5 text-left shadow-glass dark:border-white/10"
        >
          <p className="px-2.5 pb-1 pt-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
            {t("export.label")}
          </p>
          {options.map((item) => {
            const Icon = FORMAT_ICON[item.id] ?? FileText;
            return (
              <button
                key={item.id}
                type="button"
                role="menuitem"
                disabled={!item.available || Boolean(busy)}
                onClick={() => void download(item.id)}
                title={
                  item.available
                    ? t("export.one", {
                        label: exportFormatLabel(t, item.id, item.label),
                      })
                    : t("export.unavailable", {
                        label: exportFormatLabel(t, item.id, item.label),
                      })
                }
                className={clsx(
                  "flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition",
                  item.available
                    ? "text-slate-600 hover:bg-indigo-500/10 hover:text-indigo-600 dark:text-slate-300 dark:hover:text-indigo-200"
                    : "cursor-not-allowed text-slate-300 dark:text-slate-600",
                )}
              >
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-slate-500/8 text-slate-500 dark:bg-white/8 dark:text-slate-300">
                  {busy === item.id ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Icon size={13} />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12px] font-medium">
                    {exportFormatLabel(t, item.id, item.label)}
                  </span>
                  <span className="block truncate text-[10px] text-slate-400 dark:text-slate-500">
                    {exportFormatHint(t, item.id)}
                  </span>
                </span>
              </button>
            );
          })}
          <div className="mt-1 border-t border-slate-200/60 px-1 pt-1 dark:border-white/10">
            <label className="flex cursor-pointer items-center gap-2 rounded-xl px-1.5 py-1.5 text-[11px] text-slate-500 dark:text-slate-400">
              <span
                className={clsx(
                  "grid h-4 w-4 shrink-0 place-items-center rounded-[5px] border transition",
                  includeCitations
                    ? "border-indigo-500 bg-indigo-500 text-white"
                    : "border-slate-300 dark:border-white/20",
                )}
              >
                {includeCitations ? <Check size={11} /> : null}
              </span>
              <input
                type="checkbox"
                checked={includeCitations}
                onChange={(event) => setIncludeCitations(event.target.checked)}
                className="sr-only"
              />
              {t("export.citations")}
            </label>
          </div>
          {error ? (
            <p className="px-2.5 pb-1 pt-0.5 text-[10px] leading-relaxed text-rose-500" title={error}>
              {t("export.failed")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
