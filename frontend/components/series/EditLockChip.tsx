import { useEffect, useState } from "react";
import { AlertTriangle, Loader2, Lock, RefreshCw, Unlock } from "lucide-react";
import clsx from "clsx";
import {
  formatLockRemaining,
  type EditLockState,
} from "@/lib/editLock";
import { useI18n } from "@/i18n/I18nProvider";

type EditLockChipProps = {
  state: EditLockState;
  busy?: boolean;
  canTakeOver?: boolean;
  onReadOnly?: () => void;
  onRetry?: () => void;
  onTakeOver?: () => void;
  className?: string;
};

export default function EditLockChip({
  state,
  busy = false,
  canTakeOver = false,
  onReadOnly,
  onRetry,
  onTakeOver,
  className,
}: EditLockChipProps) {
  const { t } = useI18n();
  const [now, setNow] = useState(() => Date.now());
  const expiresAt =
    state.status === "held"
      ? state.holder.expiresAt
      : state.status === "blocked"
        ? state.expiresAt
        : null;

  useEffect(() => {
    if (!expiresAt) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [expiresAt]);

  if (state.status === "acquiring") {
    return (
      <span
        data-testid="lock-chip"
        data-lock-state="acquiring"
        className={clsx(
          "inline-flex items-center gap-1.5 rounded-full border border-indigo-300/40 bg-indigo-500/10 px-2.5 py-1 text-[10.5px] font-medium text-indigo-700 dark:border-indigo-300/20 dark:bg-indigo-400/10 dark:text-indigo-200",
          className,
        )}
      >
        <Loader2 size={11} className="animate-spin" />
        {t("series.editing")}
      </span>
    );
  }

  if (state.status === "held") {
    const remaining = formatLockRemaining(state.holder.expiresAt, now);
    return (
      <span
        data-testid="lock-chip"
        data-lock-state="mine"
        className={clsx(
          "inline-flex items-center gap-1.5 rounded-full border border-emerald-400/40 bg-emerald-400/10 px-2.5 py-1 text-[10.5px] font-medium text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-400/10 dark:text-emerald-200",
          className,
        )}
      >
        <Lock size={11} />
        <span>{t("series.editing")}</span>
        {remaining ? <span className="font-semibold tabular-nums">{remaining}</span> : null}
      </span>
    );
  }

  if (state.status === "blocked") {
    const remaining = formatLockRemaining(state.expiresAt, now);
    return (
      <span
        data-testid="lock-chip"
        data-lock-state="other"
        className={clsx(
          "inline-flex flex-wrap items-center gap-1.5 rounded-full border border-amber-400/45 bg-amber-400/12 px-2.5 py-1 text-[10.5px] font-medium text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-200",
          className,
        )}
      >
        <AlertTriangle size={11} />
        <span>{t("series.lockedBy", { name: state.name })}</span>
        {remaining ? (
          <span>
            {t("series.lockExpires", { time: remaining })}
          </span>
        ) : null}
        {canTakeOver ? (
          <button
            type="button"
            onClick={onTakeOver}
            disabled={busy}
            className="rounded-full px-1.5 py-0.5 text-[10px] underline decoration-amber-500/40 underline-offset-2 hover:text-amber-900 disabled:opacity-50 dark:hover:text-amber-100"
          >
            {t("series.lock.takeOver")}
          </button>
        ) : null}
        {onReadOnly ? (
          <button
            type="button"
            onClick={onReadOnly}
            className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] underline decoration-amber-500/40 underline-offset-2 hover:text-amber-900 dark:hover:text-amber-100"
          >
            <Unlock size={9} />
            {t("series.readOnly")}
          </button>
        ) : null}
      </span>
    );
  }

  if (state.status === "lost") {
    return (
      <span
        data-testid="lock-chip"
        data-lock-state="lost"
        className={clsx(
          "inline-flex items-center gap-1.5 rounded-full border border-rose-400/40 bg-rose-500/10 px-2.5 py-1 text-[10.5px] font-medium text-rose-700 dark:border-rose-300/25 dark:bg-rose-400/10 dark:text-rose-200",
          className,
        )}
      >
        <AlertTriangle size={11} />
        <span>{t("series.lockLost")}</span>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1 underline underline-offset-2"
        >
          <RefreshCw size={9} />
          {t("common.retry")}
        </button>
      </span>
    );
  }

  return (
    <span
      data-testid="lock-chip"
      data-lock-state="free"
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border border-slate-300/60 bg-slate-500/8 px-2.5 py-1 text-[10.5px] font-medium text-slate-500 dark:border-white/12 dark:bg-white/[0.05] dark:text-slate-300",
        className,
      )}
    >
      <Unlock size={11} />
      {t("series.readOnly")}
    </span>
  );
}
