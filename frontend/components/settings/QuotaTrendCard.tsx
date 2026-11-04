import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, Loader2, RefreshCcw, TrendingUp } from "lucide-react";
import { api, type QuotaHistory } from "@/lib/api";

type Point = {
  date: string;
  generations: number;
  uploads: number;
};

export default function QuotaTrendCard({ days = 30 }: { days?: number }) {
  const [data, setData] = useState<QuotaHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hover, setHover] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await api.getQuotaHistory(days));
    } catch (err) {
      setError(err instanceof Error ? err.message : "用量趋势加载失败");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  const points: Point[] = useMemo(
    () =>
      (data?.days ?? []).map((day) => ({
        date: day.date,
        generations: day.generations ?? 0,
        uploads: day.uploads ?? 0,
      })),
    [data],
  );

  const totals = useMemo(() => {
    return points.reduce(
      (acc, item) => ({
        generations: acc.generations + item.generations,
        uploads: acc.uploads + item.uploads,
      }),
      { generations: 0, uploads: 0 },
    );
  }, [points]);

  const maxValue = useMemo(
    () => Math.max(1, ...points.map((item) => item.generations + item.uploads)),
    [points],
  );

  const active = hover !== null ? points[hover] : null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-3xl p-5 shadow-glass"
    >
      <div className="flex flex-wrap items-center gap-2">
        <TrendingUp size={15} className="text-indigo-500 dark:text-indigo-300" />
        <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
          用量趋势
        </h2>
        <span className="chip-muted">最近 {days} 天</span>
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="btn-quiet px-2 py-1 text-[10.5px]"
          title="刷新"
        >
          {loading ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            <RefreshCcw size={11} />
          )}
          刷新
        </button>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px]">
        <span className="rounded-full bg-indigo-500/12 px-2 py-0.5 font-medium text-indigo-700 dark:bg-indigo-400/15 dark:text-indigo-300">
          近 {days} 天生成 {totals.generations}
        </span>
        <span className="rounded-full bg-violet-500/12 px-2 py-0.5 font-medium text-violet-700 dark:bg-violet-400/15 dark:text-violet-300">
          上传 {totals.uploads}
        </span>
        <span className="text-slate-400 dark:text-slate-500">
          {active
            ? `${active.date} · 生成 ${active.generations} · 上传 ${active.uploads}`
            : "悬停柱状图查看每日明细"}
        </span>
      </div>

      {error ? (
        <p className="mt-3 flex items-start gap-1.5 rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
          <AlertCircle size={12} className="mt-0.5 shrink-0" />
          <span className="flex-1 break-words">{error}</span>
        </p>
      ) : null}

      {loading ? (
        <div className="mt-3 h-32 animate-pulse rounded-2xl bg-slate-200/50 dark:bg-white/5" />
      ) : points.length === 0 ? (
        <p className="mt-3 rounded-2xl border border-dashed border-white/60 bg-white/40 px-3 py-6 text-center text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-400">
          暂无用量
        </p>
      ) : (
        <div className="mt-3">
          <div className="flex h-32 items-end gap-[2px] overflow-hidden rounded-2xl border border-white/50 bg-white/40 p-2 dark:border-white/10 dark:bg-white/[0.03]">
            {points.map((item, index) => {
              const total = item.generations + item.uploads;
              const height = Math.max(3, Math.round((total / maxValue) * 100));
              return (
                <div
                  key={item.date}
                  className="group relative flex h-full flex-1 cursor-default flex-col justify-end"
                  onMouseEnter={() => setHover(index)}
                  onMouseLeave={() => setHover(null)}
                  title={`${item.date} · 生成 ${item.generations} · 上传 ${item.uploads}`}
                >
                  <div
                    className={
                      hover === index
                        ? "w-full rounded-t-[3px] brand-gradient opacity-100"
                        : "w-full rounded-t-[3px] brand-gradient opacity-70 transition group-hover:opacity-100"
                    }
                    style={{ height: `${height}%` }}
                  />
                </div>
              );
            })}
          </div>
          <div className="mt-1 flex items-center justify-between px-1 text-[9.5px] text-slate-400 dark:text-slate-500">
            <span>{points[0]?.date}</span>
            <span>{points[points.length - 1]?.date}</span>
          </div>
        </div>
      )}

      <p className="mt-2 text-[10px] leading-relaxed text-slate-400 dark:text-slate-500">
        数据来自租户用量记录，包含生成与上传次数；存储用量见上方配额卡。
      </p>
    </motion.section>
  );
}
