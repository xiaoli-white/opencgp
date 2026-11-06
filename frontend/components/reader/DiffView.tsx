import { useMemo } from "react";
import clsx from "clsx";
import { diffLines, diffStats } from "@/lib/diff";

type DiffViewProps = {
  before: string;
  after: string;
  beforeLabel?: string;
  afterLabel?: string;
};

export default function DiffView({
  before,
  after,
  beforeLabel = "Previous version",
  afterLabel = "New version",
}: DiffViewProps) {
  const lines = useMemo(() => diffLines(before, after), [before, after]);
  const stats = useMemo(() => diffStats(lines), [lines]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span className="chip-muted">{beforeLabel}</span>
        <span className="text-slate-400">→</span>
        <span className="chip">{afterLabel}</span>
        <span className="ml-auto inline-flex items-center gap-2">
          <span className="rounded-full bg-emerald-500/12 px-2 py-0.5 font-medium text-emerald-600 dark:text-emerald-300">
            +{stats.added}
          </span>
          <span className="rounded-full bg-rose-500/12 px-2 py-0.5 font-medium text-rose-600 dark:text-rose-300">
            -{stats.removed}
          </span>
        </span>
      </div>
      <div className="no-scrollbar max-h-[52vh] overflow-auto rounded-2xl border border-slate-200/70 bg-white/60 py-2 dark:border-white/10 dark:bg-slate-950/40">
        {lines.length === 0 ? (
          <p className="px-4 py-6 text-center text-xs text-slate-400">
            No differences between the two versions.
          </p>
        ) : (
          lines.map((line, index) => (
            <div
              key={`${line.type}-${index}`}
              className={clsx(
                "diff-line",
                line.type === "add" && "diff-add",
                line.type === "remove" && "diff-remove",
                line.type === "same" && "diff-same",
              )}
            >
              <span className="select-none opacity-60">
                {line.type === "add" ? "+" : line.type === "remove" ? "-" : " "}
              </span>
              <span>{line.text || " "}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
