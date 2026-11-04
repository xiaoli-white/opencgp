import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, GitCompare, Loader2, X } from "lucide-react";
import clsx from "clsx";
import type { VersionDiffResult } from "@/lib/api";

type VersionDiffDialogProps = {
  open: boolean;
  title?: string;
  versions: number[];
  initialFrom?: number;
  initialTo?: number;
  fetchDiff: (from: number, to: number) => Promise<VersionDiffResult>;
  onClose: () => void;
};

export default function VersionDiffDialog({
  open,
  title = "版本对比",
  versions,
  initialFrom,
  initialTo,
  fetchDiff,
  onClose,
}: VersionDiffDialogProps) {
  const ordered = useMemo(
    () => [...versions].sort((a, b) => a - b),
    [versions],
  );
  const [from, setFrom] = useState<number>(1);
  const [to, setTo] = useState<number>(1);
  const [data, setData] = useState<VersionDiffResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    const fallbackTo = ordered[ordered.length - 1] ?? 1;
    const fallbackFrom = ordered[Math.max(0, ordered.length - 2)] ?? fallbackTo;
    setFrom(initialFrom ?? fallbackFrom);
    setTo(initialTo ?? fallbackTo);
    setData(null);
    setError("");
  }, [open, ordered, initialFrom, initialTo]);

  const fetchRef = useRef(fetchDiff);
  fetchRef.current = fetchDiff;

  useEffect(() => {
    if (!open) return;
    if (!from || !to) return;
    if (from === to) {
      setData(null);
      setError("请选择两个不同的版本");
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    fetchRef
      .current(from, to)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "对比失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, from, to]);

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
                  <GitCompare size={14} className="text-indigo-500" />
                  {title}
                </p>
                <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                  逐行对比两个历史版本，绿色为新增、红色为删除。
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-slate-400 transition hover:bg-white/70 hover:text-slate-600 dark:hover:bg-white/10 dark:hover:text-slate-200"
                aria-label="关闭对比"
              >
                <X size={16} />
              </button>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <select
                value={from}
                onChange={(event) => setFrom(Number(event.target.value))}
                className="select w-auto px-2 py-1 text-[11px]"
                aria-label="对比起始版本"
              >
                {ordered.map((version) => (
                  <option key={version} value={version}>
                    v{version}
                  </option>
                ))}
              </select>
              <span className="text-[11px] text-slate-400">→</span>
              <select
                value={to}
                onChange={(event) => setTo(Number(event.target.value))}
                className="select w-auto px-2 py-1 text-[11px]"
                aria-label="对比目标版本"
              >
                {ordered.map((version) => (
                  <option key={version} value={version}>
                    v{version}
                  </option>
                ))}
              </select>
              {data ? (
                <span className="ml-auto inline-flex items-center gap-2 text-[11px] font-medium">
                  <span className="rounded-full bg-emerald-500/12 px-2 py-0.5 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300">
                    +{data.added_chars} 字符
                  </span>
                  <span className="rounded-full bg-rose-500/12 px-2 py-0.5 text-rose-700 dark:bg-rose-400/15 dark:text-rose-300">
                    -{data.removed_chars} 字符
                  </span>
                </span>
              ) : null}
            </div>

            {error ? (
              <p className="mt-3 flex items-start gap-1.5 rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
                <AlertCircle size={12} className="mt-0.5 shrink-0" />
                <span className="flex-1 break-words">{error}</span>
              </p>
            ) : null}

            <div className="no-scrollbar mt-3 max-h-[58vh] overflow-y-auto rounded-2xl border border-white/50 bg-white/55 p-2 dark:border-white/10 dark:bg-white/[0.04]">
              {loading ? (
                <p className="flex items-center gap-2 px-2 py-3 text-[11px] text-slate-400">
                  <Loader2 size={12} className="animate-spin" />
                  正在对比…
                </p>
              ) : !data || data.hunks.length === 0 ? (
                <p className="px-2 py-3 text-[11px] text-slate-400">
                  没有可显示的内容差异。
                </p>
              ) : (
                <div className="space-y-0.5 font-mono text-[11.5px] leading-relaxed">
                  {data.hunks.map((hunk, index) => (
                    <div
                      key={`${index}-${hunk.type}`}
                      className={clsx(
                        "whitespace-pre-wrap break-words rounded-md px-2 py-1",
                        hunk.type === "add"
                          ? "bg-emerald-500/12 text-emerald-800 dark:bg-emerald-400/12 dark:text-emerald-200"
                          : hunk.type === "del"
                            ? "bg-rose-500/12 text-rose-800 line-through decoration-rose-400/50 dark:bg-rose-400/12 dark:text-rose-200"
                            : "text-slate-500 dark:text-slate-400",
                      )}
                    >
                      <span className="mr-1.5 select-none opacity-60">
                        {hunk.type === "add" ? "+" : hunk.type === "del" ? "-" : " "}
                      </span>
                      {hunk.text || " "}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
