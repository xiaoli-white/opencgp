import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, Loader2, RotateCcw, Save, Timer } from "lucide-react";
import clsx from "clsx";
import { api, type TimeoutsSnapshot } from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";

type Props = {
  canManage: boolean;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
};

const LABEL_KEYS: Record<string, string> = {
  "llm.timeout": "settings.timeouts.key.llm",
  "image.timeout": "settings.timeouts.key.image",
  "video.timeout": "settings.timeouts.key.video",
  "websearch.timeout": "settings.timeouts.key.websearch",
  "websearch.fetch_timeout": "settings.timeouts.key.websearchFetch",
  "embedding.timeout": "settings.timeouts.key.embedding",
  "rerank.timeout": "settings.timeouts.key.rerank",
};

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

function seconds(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return String(Number(value.toFixed(2)));
}

function toForm(snapshot: TimeoutsSnapshot): Record<string, string> {
  const next: Record<string, string> = {};
  for (const item of snapshot.items) {
    next[item.key] = seconds(item.value);
  }
  return next;
}

export default function TimeoutSettingsSection({ canManage, onNotice, onError }: Props) {
  const { t } = useI18n();
  const [snapshot, setSnapshot] = useState<TimeoutsSnapshot | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [resetting, setResetting] = useState("");
  const [localError, setLocalError] = useState("");
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLocalError("");
    try {
      const next = await api.getTimeoutSettings();
      if (!mounted.current) return;
      setSnapshot(next);
      setForm(toForm(next));
    } catch (err) {
      onError(errorText(err, t("settings.timeouts.loadFailed")));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [onError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = useCallback(async () => {
    if (!snapshot) return;
    setLocalError("");
    const changes: Record<string, number | null> = {};
    for (const item of snapshot.items) {
      const raw = (form[item.key] ?? "").trim();
      if (!raw) continue;
      const value = Number(raw);
      if (!Number.isFinite(value)) {
        setLocalError(t("settings.timeouts.invalidNumber", { label: t(LABEL_KEYS[item.key] ?? item.key) }));
        return;
      }
      if (value < item.minimum || value > item.maximum) {
        setLocalError(
          t("settings.timeouts.outOfRange", {
            label: t(LABEL_KEYS[item.key] ?? item.key),
            min: seconds(item.minimum),
            max: seconds(item.maximum),
          }),
        );
        return;
      }
      if (item.value === null || Math.abs(value - item.value) > 1e-9) {
        changes[item.key] = value;
      }
    }
    if (Object.keys(changes).length === 0) {
      onNotice(t("settings.timeouts.nothingToSave"));
      return;
    }
    setBusy(true);
    try {
      const next = await api.updateTimeoutSettings(changes);
      if (!mounted.current) return;
      setSnapshot(next);
      setForm(toForm(next));
      onNotice(t("settings.timeouts.saved"));
    } catch (err) {
      setLocalError(errorText(err, t("settings.timeouts.saveFailed")));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }, [form, onNotice, snapshot, t]);

  const reset = useCallback(
    async (key: string) => {
      setLocalError("");
      setResetting(key);
      try {
        const next = await api.updateTimeoutSettings({ [key]: null });
        if (!mounted.current) return;
        setSnapshot(next);
        setForm(toForm(next));
        onNotice(
          t("settings.timeouts.resetDone", {
            label: t(LABEL_KEYS[key] ?? key),
          }),
        );
      } catch (err) {
        setLocalError(errorText(err, t("settings.timeouts.saveFailed")));
      } finally {
        if (mounted.current) setResetting("");
      }
    },
    [onNotice, t],
  );

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      data-timeouts-section="true"
      className="glass rounded-3xl p-4 shadow-glass sm:p-5"
    >
      <div className="flex flex-wrap items-start gap-2">
        <Timer size={15} className="mt-0.5 shrink-0 text-indigo-500 dark:text-indigo-300" />
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
            {t("settings.timeouts.title")}
          </h2>
          <p className="mt-1 text-[10.5px] leading-relaxed text-slate-500 dark:text-slate-400">
            {t("settings.timeouts.description")}
          </p>
        </div>
        <span className="chip-muted">{t("settings.timeouts.serverLevel")}</span>
      </div>

      {!canManage ? (
        <p className="mt-2 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[10.5px] text-amber-700 dark:text-amber-300">
          {t("settings.timeouts.readOnly")}
        </p>
      ) : null}

      {localError ? (
        <div
          data-timeout-error="true"
          className="mt-3 flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[10.5px] text-rose-700 dark:text-rose-300"
        >
          <AlertCircle size={12} className="mt-0.5 shrink-0" />
          <span className="flex-1">{localError}</span>
        </div>
      ) : null}

      {loading ? (
        <p className="mt-3 flex items-center gap-2 text-[11px] text-slate-400">
          <Loader2 size={12} className="animate-spin" />
          {t("settings.timeouts.loading")}
        </p>
      ) : snapshot ? (
        <>
          <div className="mt-3 space-y-2">
            {snapshot.items.map((item) => {
              const label = t(LABEL_KEYS[item.key] ?? item.key);
              return (
                <div
                  key={item.key}
                  data-timeout-row={item.key}
                  className="rounded-2xl border border-white/60 bg-white/40 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.03]"
                >
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                    <div className="min-w-0 flex-1 basis-48">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[12px] font-medium text-slate-800 dark:text-slate-100">
                          {label}
                        </span>
                        <span
                          className={clsx(
                            "rounded-full px-1.5 py-0.5 text-[9.5px] font-medium",
                            item.overridden
                              ? "bg-indigo-500/12 text-indigo-600 dark:text-indigo-300"
                              : "bg-slate-500/10 text-slate-500 dark:text-slate-400",
                          )}
                        >
                          {item.overridden
                            ? t("settings.timeouts.overridden")
                            : t("settings.timeouts.inherited")}
                        </span>
                      </div>
                      <div className="mt-0.5 break-all font-mono text-[9.5px] text-slate-400">
                        {item.key}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-slate-500 dark:text-slate-400">
                        <span>
                          {t("settings.timeouts.effective")}:{" "}
                          <span className="font-semibold text-slate-700 dark:text-slate-200">
                            {t("settings.timeouts.secondsValue", {
                              value: seconds(item.value),
                            })}
                          </span>
                        </span>
                        <span>
                          {t("settings.timeouts.defaultValue")}:{" "}
                          {t("settings.timeouts.secondsValue", {
                            value: seconds(item.default),
                          })}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <input
                        data-timeout-input={item.key}
                        type="number"
                        inputMode="decimal"
                        min={item.minimum}
                        max={item.maximum}
                        step="0.1"
                        value={form[item.key] ?? ""}
                        onChange={(event) =>
                          setForm((prev) => ({ ...prev, [item.key]: event.target.value }))
                        }
                        placeholder={seconds(item.default)}
                        disabled={!canManage || busy}
                        aria-label={label}
                        className="input w-24 px-2 py-1 text-[11px]"
                      />
                      <span className="text-[10px] text-slate-400">
                        {t("settings.timeouts.secondsShort")}
                      </span>
                      <button
                        type="button"
                        data-timeout-reset={item.key}
                        onClick={() => void reset(item.key)}
                        disabled={!canManage || busy || resetting === item.key || !item.overridden}
                        className="btn btn-ghost shrink-0 px-2 py-1 text-[10px]"
                        title={t("settings.timeouts.reset")}
                      >
                        {resetting === item.key ? (
                          <Loader2 size={10} className="animate-spin" />
                        ) : (
                          <RotateCcw size={10} />
                        )}
                        {t("settings.timeouts.reset")}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <p className="min-w-0 flex-1 text-[9.5px] leading-relaxed text-slate-400">
              {t("settings.timeouts.hint")}
            </p>
            {canManage ? (
              <button
                type="button"
                data-timeout-save="true"
                onClick={() => void save()}
                disabled={busy}
                className="btn btn-primary shrink-0 px-3 py-1.5 text-[10.5px]"
              >
                {busy ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
                {busy ? t("settings.timeouts.saving") : t("settings.timeouts.save")}
              </button>
            ) : null}
          </div>
        </>
      ) : null}
    </motion.section>
  );
}
