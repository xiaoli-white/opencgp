"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { GitCompare, History, Loader2, RotateCcw, X } from "lucide-react";
import clsx from "clsx";
import type { LessonVersion } from "@/lib/api";
import { contentLength, formatDateTime } from "@/lib/format";
import DiffView from "@/components/reader/DiffView";

type VersionPanelProps = {
  versions: LessonVersion[];
  currentVersion: number;
  loading: boolean;
  busyVersion: number | null;
  onRevert: (version: number) => Promise<void>;
  className?: string;
};

export default function VersionPanel({
  versions,
  currentVersion,
  loading,
  busyVersion,
  onRevert,
  className,
}: VersionPanelProps) {
  const [compareVersion, setCompareVersion] = useState<number | null>(null);

  const ordered = useMemo(
    () => [...versions].sort((a, b) => b.version - a.version),
    [versions],
  );

  const compareTarget = ordered.find(
    (version) => version.version === compareVersion,
  );
  const compareBase = compareTarget
    ? ordered.find((version) => version.version === compareTarget.version - 1)
    : undefined;

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
          版本历史
        </div>
        <span className="chip-muted">当前 v{currentVersion || 0}</span>
      </div>

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
            还没有版本。生成正文或提交一次修改后，会自动沉淀版本记录。
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
                        ? "非严格模式：允许模型自由写作，正文标注由大模型编写"
                        : "严格模式：必须带出处，无据不写"
                    }
                  >
                    {version.mode || "strict"}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[12px] text-slate-600 dark:text-slate-300">
                    {version.note || "自动存档"}
                  </span>
                  {isCurrent && (
                    <span className="text-[10px] font-medium text-indigo-500 dark:text-indigo-300">
                      当前
                    </span>
                  )}
                </div>
                <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500">
                  <span>{formatDateTime(version.created_at)}</span>
                  <span>{contentLength(version.content)} 字</span>
                </div>
                <div className="mt-2 flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setCompareVersion(version.version)}
                    className="btn-quiet"
                  >
                    <GitCompare size={12} />
                    对比
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
                    回滚
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      <AnimatePresence>
        {compareTarget && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div
              className="absolute inset-0 bg-slate-900/45 backdrop-blur-sm"
              onClick={() => setCompareVersion(null)}
            />
            <motion.div
              initial={{ y: 18, opacity: 0, scale: 0.98 }}
              animate={{ y: 0, opacity: 1, scale: 1 }}
              exit={{ y: 12, opacity: 0, scale: 0.98 }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
              className="glass relative z-10 w-full max-w-3xl rounded-3xl p-5 shadow-glass"
            >
              <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                    版本对比
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                    v{compareTarget.version - 1} → v{compareTarget.version} ·{" "}
                    {compareTarget.mode || "strict"} ·{" "}
                    {compareTarget.note || "自动存档"}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setCompareVersion(null)}
                  className="grid h-8 w-8 place-items-center rounded-full text-slate-400 transition hover:bg-white/70 hover:text-slate-600 dark:hover:bg-white/10 dark:hover:text-slate-200"
                  aria-label="关闭对比"
                >
                  <X size={16} />
                </button>
              </div>
              <DiffView
                before={compareBase?.content ?? ""}
                after={compareTarget.content}
                beforeLabel={compareBase ? `v${compareBase.version}` : "起稿前"}
                afterLabel={`v${compareTarget.version}`}
              />
              <div className="mt-4 flex items-center justify-between gap-3">
                <p className="text-[11px] text-slate-400 dark:text-slate-500">
                  回滚会基于该版本内容生成一个新版本，历史不会被覆盖。
                </p>
                <button
                  type="button"
                  onClick={() => {
                    onRevert(compareTarget.version);
                    setCompareVersion(null);
                  }}
                  disabled={compareTarget.version === currentVersion}
                  className="btn btn-primary disabled:opacity-40"
                >
                  <RotateCcw size={13} />
                  回滚到此版本
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
