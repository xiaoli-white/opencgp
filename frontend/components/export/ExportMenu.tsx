import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import clsx from "clsx";
import { Check, Download, Loader2 } from "lucide-react";
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

export default function ExportMenu({
  sourceType,
  sourceId,
  fallbackName,
  className,
}: ExportMenuProps) {
  const [open, setOpen] = useState(false);
  const [formats, setFormats] = useState<ExportFormat[]>([]);
  const [format, setFormat] = useState<ExportFormatId>("md");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [includeCitations, setIncludeCitations] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let alive = true;
    void api
      .getExportFormats()
      .then((data) => {
        if (!alive) return;
        if (data.formats?.length) setFormats(data.formats);
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
    const onDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const options = formats.length ? formats : FALLBACK_FORMATS;

  const download = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const result = await exportDocument(sourceType, sourceId, format, {
        theme,
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
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "导出失败",
      );
    } finally {
      setBusy(false);
    }
  }, [sourceType, sourceId, format, theme, includeCitations, fallbackName]);

  return (
    <div ref={rootRef} className={clsx("relative shrink-0", className)}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="btn btn-ghost whitespace-nowrap"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Download size={13} />
        导出
      </button>
      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="absolute right-0 z-40 mt-2 w-[268px] rounded-2xl border border-white/60 bg-white/85 p-3 shadow-xl backdrop-blur-2xl dark:border-white/10 dark:bg-slate-900/85"
            role="menu"
          >
            <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
              导出格式
            </p>
            <div className="mt-1.5 space-y-0.5">
              {options.map((item) => {
                const active = format === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    disabled={!item.available}
                    onClick={() => setFormat(item.id)}
                    className={clsx(
                      "flex w-full items-center justify-between rounded-xl px-2.5 py-1.5 text-left text-[12px] transition",
                      !item.available
                        ? "cursor-not-allowed text-slate-300 dark:text-slate-600"
                        : active
                          ? "bg-indigo-500/10 font-medium text-indigo-700 dark:text-indigo-200"
                          : "text-slate-600 hover:bg-slate-500/5 dark:text-slate-300 dark:hover:bg-white/5",
                    )}
                  >
                    <span>{item.label}</span>
                    {active && item.available ? (
                      <Check size={13} className="text-indigo-500 dark:text-indigo-300" />
                    ) : null}
                    {!item.available ? (
                      <span className="text-[10px]">不可用</span>
                    ) : null}
                  </button>
                );
              })}
            </div>
            <div className="mt-2.5 border-t border-slate-500/10 pt-2.5 dark:border-white/10">
              <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
                主题
              </p>
              <div className="mt-1.5 inline-flex w-full items-center gap-0.5 rounded-full border border-slate-200/70 bg-white/60 p-0.5 dark:border-white/10 dark:bg-white/[0.05]">
                {(["light", "dark"] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setTheme(item)}
                    className={clsx(
                      "flex-1 rounded-full px-3 py-1 text-[11px] font-medium transition",
                      theme === item
                        ? "brand-gradient text-white"
                        : "text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-300",
                    )}
                  >
                    {item === "light" ? "浅色" : "深色"}
                  </button>
                ))}
              </div>
              <label className="mt-2 flex cursor-pointer items-center justify-between px-1 text-[11px] text-slate-600 dark:text-slate-300">
                <span>包含引用</span>
                <input
                  type="checkbox"
                  checked={includeCitations}
                  onChange={(event) => setIncludeCitations(event.target.checked)}
                  className="h-3.5 w-3.5 accent-indigo-500"
                />
              </label>
            </div>
            {error ? (
              <p className="mt-2 rounded-xl bg-rose-500/10 px-2 py-1.5 text-[11px] leading-relaxed text-rose-600 dark:text-rose-300">
                {error}
              </p>
            ) : null}
            <button
              type="button"
              onClick={() => void download()}
              disabled={busy}
              className="btn btn-primary mt-2.5 w-full justify-center"
            >
              {busy ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Download size={13} />
              )}
              {busy ? "正在导出…" : "下载"}
            </button>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
