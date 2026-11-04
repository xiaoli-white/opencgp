import { useCallback, useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";
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
  { id: "md", label: "MD", available: true },
  { id: "html", label: "HTML", available: true },
  { id: "epub", label: "EPUB", available: true },
  { id: "pdf", label: "PDF", available: true },
];

export default function ExportMenu({
  sourceType,
  sourceId,
  fallbackName,
  className,
}: ExportMenuProps) {
  const [formats, setFormats] = useState<ExportFormat[]>([]);
  const [includeCitations, setIncludeCitations] = useState(true);
  const [busy, setBusy] = useState<ExportFormatId | "">("");
  const [error, setError] = useState("");

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
      } catch (err) {
        setError(
          err instanceof ApiError || err instanceof Error ? err.message : "导出失败",
        );
      } finally {
        setBusy("");
      }
    },
    [busy, sourceType, sourceId, includeCitations, fallbackName],
  );

  return (
    <div className={clsx("relative flex flex-wrap items-center gap-1", className)}>
      <span className="flex items-center gap-1 text-[11px] text-slate-400 dark:text-slate-500">
        <Download size={12} />
        导出
      </span>
      {options.map((item) => (
        <button
          key={item.id}
          type="button"
          disabled={!item.available || Boolean(busy)}
          onClick={() => void download(item.id)}
          title={item.available ? `导出 ${item.label}` : `${item.label} 不可用`}
          className={clsx(
            "rounded-lg border px-2 py-1 text-[11px] font-medium transition",
            item.available
              ? "border-slate-200/70 bg-white/70 text-slate-600 hover:border-indigo-300 hover:text-indigo-600 dark:border-white/10 dark:bg-white/[0.05] dark:text-slate-300 dark:hover:text-indigo-300"
              : "cursor-not-allowed border-slate-200/50 text-slate-300 dark:border-white/5 dark:text-slate-600",
          )}
        >
          {busy === item.id ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            item.label
          )}
        </button>
      ))}
      <label className="ml-1 flex cursor-pointer items-center gap-1 text-[10px] text-slate-400 dark:text-slate-500">
        <input
          type="checkbox"
          checked={includeCitations}
          onChange={(event) => setIncludeCitations(event.target.checked)}
          className="h-3 w-3 accent-indigo-500"
        />
        引用
      </label>
      {error ? (
        <span className="text-[10px] text-rose-500" title={error}>
          导出失败
        </span>
      ) : null}
    </div>
  );
}
