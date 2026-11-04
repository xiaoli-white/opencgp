import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Loader2, Lock, RefreshCw, ShieldCheck, Unlock } from "lucide-react";
import clsx from "clsx";
import {
  formatLockRemaining,
  type LessonLockState,
} from "@/lib/lock";
import { useI18n } from "@/i18n/I18nProvider";

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
  const { t } = useI18n();
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
          {t("course.lock.acquiring")}
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
          {t("course.lock.heldPre")}{" "}
          <span className="font-semibold tabular-nums">
            {formatLockRemaining(state.lock.expires_at, now)}
          </span>{" "}
          {t("course.lock.heldPost")}
        </span>
        <span className="chip-muted !px-2 !py-0.5 !text-[10px]">
          {state.lock.user_name || t("course.lock.self")}
        </span>
      </div>
    ) : state.status === "blocked" ? (
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-amber-400/40 bg-amber-400/12 px-3.5 py-2 text-[11px] text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-200">
        <AlertTriangle size={12} className="shrink-0" />
        <span className="min-w-0 flex-1">
          {t("course.lock.blocked", { name: state.name })}
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onRefresh}
            className="btn btn-ghost !px-2.5 !py-1 !text-[10.5px]"
          >
            <RefreshCw size={11} />
            {t("common.refresh")}
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
              {t("course.lock.takeOver")}
            </button>
          ) : null}
        </div>
      </div>
    ) : (
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-300/60 bg-slate-500/8 px-3.5 py-2 text-[11px] text-slate-600 dark:border-white/12 dark:bg-white/[0.05] dark:text-slate-300">
        <Unlock size={12} className="shrink-0" />
        <span className="min-w-0 flex-1">{t("course.lock.lost")}</span>
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
          {t("course.lock.reacquire")}
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
