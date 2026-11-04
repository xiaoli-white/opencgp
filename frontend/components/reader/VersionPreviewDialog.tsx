import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, Eye, GitCompare, Loader2, X } from "lucide-react";
import type { Citation } from "@/lib/api";
import MarkdownReader from "@/components/reader/MarkdownReader";

type VersionPreviewDialogProps = {
  open: boolean;
  title?: string;
  version: number | null;
  load: (version: number) => Promise<{ content: string; citations?: Citation[] }>;
  onClose: () => void;
  onCompare?: () => void;
};

export default function VersionPreviewDialog({
  open,
  title = "版本预览",
  version,
  load,
  onClose,
  onCompare,
}: VersionPreviewDialogProps) {
  const [content, setContent] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    if (!open || !version) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    setContent("");
    setCitations([]);
    loadRef
      .current(version)
      .then((result) => {
        if (cancelled) return;
        setContent(result.content ?? "");
        setCitations(result.citations ?? []);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, version]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto p-3 sm:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            className="absolute inset-0 bg-slate-900/45 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div
            initial={{ y: 16, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 12, opacity: 0, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 320, damping: 30 }}
            className="glass relative z-10 my-4 w-full max-w-3xl rounded-3xl p-4 shadow-glass sm:p-5"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 text-sm font-semibold text-slate-800 dark:text-slate-100">
                  <Eye size={14} className="text-indigo-500" />
                  {title}
                  <span className="chip-muted ml-1">v{version ?? 0}</span>
                </p>
                <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                  只读预览，不会修改当前内容。
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-slate-400 transition hover:bg-white/70 hover:text-slate-600 dark:hover:bg-white/10 dark:hover:text-slate-200"
                aria-label="关闭预览"
              >
                <X size={16} />
              </button>
            </div>

            {error ? (
              <p className="mt-3 flex items-start gap-1.5 rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
                <AlertCircle size={12} className="mt-0.5 shrink-0" />
                <span className="flex-1 break-words">{error}</span>
              </p>
            ) : null}

            <div className="no-scrollbar mt-3 max-h-[62vh] overflow-y-auto rounded-2xl border border-white/50 bg-white/55 p-3 dark:border-white/10 dark:bg-white/[0.04] sm:p-4">
              {loading ? (
                <p className="flex items-center gap-2 px-1 py-3 text-[11px] text-slate-400">
                  <Loader2 size={12} className="animate-spin" />
                  正在加载版本内容…
                </p>
              ) : content ? (
                <MarkdownReader content={content} citations={citations} />
              ) : (
                <p className="px-1 py-3 text-[11px] text-slate-400">
                  该版本没有正文内容。
                </p>
              )}
            </div>

            {onCompare ? (
              <div className="mt-3 flex justify-end">
                <button type="button" onClick={onCompare} className="btn-quiet">
                  <GitCompare size={12} />
                  与当前版本对比
                </button>
              </div>
            ) : null}
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
