import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Loader2, Lock, RefreshCw, ShieldCheck, Unlock } from "lucide-react";
import clsx from "clsx";
import {
  formatLockRemaining,
  type LessonLockState,
} from "@/lib/lock";

type LessonLockBannerProps = {
  state: LessonLockState;
  canTakeOver: boolean;
  readOnly: boolean;
  busy?: boolean;
  onRefresh: () => void;
  onTakeOver: () => void;
  onReacquire: () => void;
};

export default function LessonLockBanner({
  state,
  canTakeOver,
  readOnly,
  busy = false,
  onRefresh,
  onTakeOver,
  onReacquire,
}: LessonLockBannerProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (state.status !== "held") return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [state.status, state.status === "held" ? state.lock.expires_at : 0]);

  if (readOnly) return null;
  if (state.status === "idle" || state.status === "acquiring") {
    if (state.status === "acquiring") {
      return (
        <div className="mt-3 flex items-center gap-1.5 text-[11px] text-slate-400 dark:text-slate-500">
          <Loader2 size={11} className="animate-spin" />
          正在获取编辑锁…
        </div>
      );
    }
    return null;
  }

  const content =
    state.status === "held" ? (
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-emerald-400/35 bg-emerald-400/10 px-3.5 py-2 text-[11px] text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-400/10 dark:text-emerald-300">
        <Lock size={12} className="shrink-0" />
        <span className="min-w-0">
          你正在编辑 · 锁将在{" "}
          <span className="font-semibold tabular-nums">
            {formatLockRemaining(state.lock.expires_at, now)}
          </span>{" "}
          后过期
        </span>
        <span className="chip-muted !px-2 !py-0.5 !text-[10px]">
          {state.lock.user_name || "本人"}
        </span>
      </div>
    ) : state.status === "blocked" ? (
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-amber-400/40 bg-amber-400/12 px-3.5 py-2 text-[11px] text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-200">
        <AlertTriangle size={12} className="shrink-0" />
        <span className="min-w-0 flex-1">
          <span className="font-semibold">{state.name}</span> 正在编辑这一讲，写操作已锁定，正文可读。
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onRefresh}
            className="btn btn-ghost !px-2.5 !py-1 !text-[10.5px]"
          >
            <RefreshCw size={11} />
            刷新
          </button>
          {canTakeOver ? (
            <button
              type="button"
              onClick={onTakeOver}
              disabled={busy}
              className="btn btn-primary !px-2.5 !py-1 !text-[10.5px]"
            >
              {busy ? (
                <Loader2 size={11} className="animate-spin" />
              ) : (
                <ShieldCheck size={11} />
              )}
              接管编辑
            </button>
          ) : null}
        </div>
      </div>
    ) : (
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-300/60 bg-slate-500/8 px-3.5 py-2 text-[11px] text-slate-600 dark:border-white/12 dark:bg-white/[0.05] dark:text-slate-300">
        <Unlock size={12} className="shrink-0" />
        <span className="min-w-0 flex-1">编辑锁已失效，写操作暂时受限。</span>
        <button
          type="button"
          onClick={onReacquire}
          disabled={busy}
          className="btn btn-ghost !px-2.5 !py-1 !text-[10.5px]"
        >
          {busy ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            <Lock size={11} />
          )}
          重新加锁
        </button>
      </div>
    );

  return (
    <AnimatePresence initial={false}>
      <motion.div
        key={state.status}
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.18 }}
        className={clsx("mt-3")}
      >
        {content}
      </motion.div>
    </AnimatePresence>
  );
}
