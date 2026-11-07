import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, ArrowRight, Loader2, RefreshCw, X } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

export type VersionConflict = {
  expectedVersion: number;
  currentVersion: number;
  label: string;
  retry: () => void | Promise<void>;
};

type ConflictDialogProps = {
  conflict: VersionConflict | null;
  busy?: boolean;
  onLoadLatest: () => void;
  onRetry: () => void;
  onClose: () => void;
};

export default function ConflictDialog({
  conflict,
  busy = false,
  onLoadLatest,
  onRetry,
  onClose,
}: ConflictDialogProps) {
  const { t } = useI18n();
  return (
    <AnimatePresence>
      {conflict ? (
        <motion.div
          className="fixed inset-0 z-[60] grid place-items-center px-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            className="absolute inset-0 bg-slate-900/45 backdrop-blur-sm"
            onClick={() => {
              if (!busy) onClose();
            }}
          />
          <motion.div
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 320, damping: 30 }}
            className="glass relative w-full max-w-md rounded-3xl p-6 shadow-glass"
          >
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="absolute right-4 top-4 grid h-7 w-7 place-items-center rounded-full text-slate-400 transition hover:bg-slate-500/10 hover:text-slate-600 disabled:opacity-40 dark:hover:text-slate-200"
              aria-label={t("common.close")}
            >
              <X size={14} />
            </button>
            <div className="flex items-start gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-amber-400/15 text-amber-600 dark:text-amber-300">
                <AlertTriangle size={18} />
              </span>
              <div className="min-w-0">
                <h3 className="text-base font-semibold text-slate-900 dark:text-white">
                  {t("conflict.title")}
                </h3>
                <p className="mt-1 text-[12px] leading-relaxed text-slate-500 dark:text-slate-400">
                  {t("conflict.desc", { label: conflict.label })}
                </p>
              </div>
            </div>

            <div className="mt-4 flex items-center justify-center gap-3 rounded-2xl border border-slate-200/70 bg-white/50 px-4 py-3 text-[12px] dark:border-white/10 dark:bg-white/[0.04]">
              <span className="text-slate-500 dark:text-slate-400">
                {t("conflict.yourBaseline")}{" "}
                <span className="font-semibold text-slate-700 tabular-nums dark:text-slate-200">
                  {t("common.versionTag", { version: conflict.expectedVersion })}
                </span>
              </span>
              <ArrowRight size={13} className="text-slate-300 dark:text-slate-600" />
              <span className="text-slate-500 dark:text-slate-400">
                {t("conflict.current")}{" "}
                <span className="font-semibold text-indigo-600 tabular-nums dark:text-indigo-300">
                  {t("common.versionTag", { version: conflict.currentVersion })}
                </span>
              </span>
            </div>

            <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                onClick={onLoadLatest}
                disabled={busy}
                className="btn btn-ghost"
              >
                <RefreshCw size={13} />
                {t("conflict.loadLatest")}
              </button>
              <button
                type="button"
                onClick={onRetry}
                disabled={busy}
                className="btn btn-primary"
              >
                {busy ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <ArrowRight size={13} />
                )}
                {t("conflict.retryLatest")}
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
