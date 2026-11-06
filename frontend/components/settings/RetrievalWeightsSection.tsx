import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  ChevronDown,
  ChevronUp,
  Gauge,
  KeyRound,
  Loader2,
  Save,
  Settings2,
  Trash2,
  X,
} from "lucide-react";
import clsx from "clsx";
import {
  api,
  type RetrievalScopeSettings,
  type RetrievalSettings,
  type RetrievalSettingsPayload,
} from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";
import { ConfirmDialog } from "@/components/common/Dialogs";

type Props = {
  scope: "user" | "tenant";
  canManage: boolean;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
};

type WeightForm = {
  vector: string;
  rerank: string;
  topN: string;
};

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

function toForm(values: RetrievalScopeSettings | undefined): WeightForm {
  return {
    vector:
      values?.vector_weight === null || values?.vector_weight === undefined
        ? ""
        : String(values.vector_weight),
    rerank:
      values?.rerank_weight === null || values?.rerank_weight === undefined
        ? ""
        : String(values.rerank_weight),
    topN:
      values?.rerank_top_n === null || values?.rerank_top_n === undefined
        ? ""
        : String(values.rerank_top_n),
  };
}

export default function RetrievalWeightsSection({ scope, canManage, onNotice, onError }: Props) {
  const { t } = useI18n();
  const [settings, setSettings] = useState<RetrievalSettings | null>(null);
  const [weightForm, setWeightForm] = useState<WeightForm>({ vector: "", rerank: "", topN: "" });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [diagnostics, setDiagnostics] = useState(false);
  const [clearScopeOpen, setClearScopeOpen] = useState(false);
  const [clearScopeBusy, setClearScopeBusy] = useState(false);
  const [clearScopeError, setClearScopeError] = useState("");
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const sourceText = useCallback(
    (value: string) => {
      if (value === "user") return t("retrieval.sourceUser");
      if (value === "tenant") return t("retrieval.sourceTenant");
      if (value === "global") return t("retrieval.scopeBadgeGlobal");
      return t("retrieval.sourceDefault");
    },
    [t],
  );

  const sourceBadgeClass = (value: string) =>
    value === "user"
      ? "bg-indigo-500/10 text-indigo-600 dark:text-indigo-300"
      : value === "tenant"
        ? "bg-violet-500/10 text-violet-600 dark:text-violet-300"
        : value === "global"
          ? "bg-amber-400/15 text-amber-700 dark:text-amber-300"
          : "chip-muted";

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const next = await api.getRetrievalSettings();
      if (!mounted.current) return;
      setSettings(next);
      setWeightForm(toForm(next.scopes?.[scope]));
    } catch (err) {
      onError(errorText(err, t("retrieval.loadFailed")));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [onError, scope, t]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const saveSettings = useCallback(async () => {
    const payload: RetrievalSettingsPayload = { scope };
    let count = 0;
    const vector = weightForm.vector.trim();
    if (vector) {
      const value = Number(vector);
      if (Number.isFinite(value)) {
        payload.vector_weight = Math.max(0, Math.min(1, value));
        count += 1;
      }
    }
    const rerank = weightForm.rerank.trim();
    if (rerank) {
      const value = Number(rerank);
      if (Number.isFinite(value)) {
        payload.rerank_weight = Math.max(0, Math.min(1, value));
        count += 1;
      }
    }
    const topN = weightForm.topN.trim();
    if (topN) {
      const value = Math.trunc(Number(topN));
      if (Number.isFinite(value)) {
        payload.rerank_top_n = Math.max(1, Math.min(50, value));
        count += 1;
      }
    }
    if (count === 0) {
      onNotice(t("retrieval.nothingToSave"));
      return;
    }
    setBusy(true);
    try {
      const next = await api.updateRetrievalSettings(payload);
      setSettings(next);
      setWeightForm(toForm(next.scopes?.[scope]));
      onNotice(t("retrieval.settingsSaved"));
    } catch (err) {
      onError(errorText(err, t("retrieval.saveFailed")));
    } finally {
      setBusy(false);
    }
  }, [onError, onNotice, scope, t, weightForm]);

  const clearField = useCallback(
    async (field: "vector_weight" | "rerank_weight" | "rerank_top_n") => {
      setBusy(true);
      try {
        const payload: RetrievalSettingsPayload = { scope };
        payload[field] = null;
        const next = await api.updateRetrievalSettings(payload);
        setSettings(next);
        setWeightForm(toForm(next.scopes?.[scope]));
        onNotice(t("retrieval.fieldCleared"));
      } catch (err) {
        onError(errorText(err, t("retrieval.saveFailed")));
      } finally {
        setBusy(false);
      }
    },
    [onError, onNotice, scope, t],
  );

  const clearScopeSettings = useCallback(async () => {
    setClearScopeBusy(true);
    setClearScopeError("");
    try {
      const next = await api.clearRetrievalSettings(scope);
      setSettings(next);
      setWeightForm(toForm(next.scopes?.[scope]));
      setClearScopeOpen(false);
      onNotice(t("retrieval.clearScopeDone", { scope: sourceText(scope) }));
    } catch (err) {
      setClearScopeError(errorText(err, t("retrieval.saveFailed")));
    } finally {
      setClearScopeBusy(false);
    }
  }, [onNotice, scope, sourceText, t]);

  const defaults = settings?.defaults ?? {
    vector_weight: 0.55,
    rerank_weight: 0.5,
    rerank_top_n: 12,
  };
  const activeScope = settings?.scopes?.[scope];
  const sources = settings?.sources ?? {};
  const effectiveWeights = settings?.effective?.weights ?? settings?.weights;
  const effectiveSources = settings?.effective?.weights?.sources ?? sources;
  const title =
    scope === "user" ? t("retrieval.weightsTitleUser") : t("retrieval.weightsTitleTenant");
  const description =
    scope === "user" ? t("retrieval.weightsDescUser") : t("retrieval.weightsDescTenant");

  const renderWeightField = (
    key: "vector_weight" | "rerank_weight" | "rerank_top_n",
    label: string,
    value: string,
    placeholder: string,
    onChange: (next: string) => void,
  ) => {
    const source = sources[key] || "env";
    return (
      <div className="rounded-2xl border border-white/60 bg-white/40 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.03]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] text-slate-600 dark:text-slate-300">{label}</span>
          <span className={clsx("chip", sourceBadgeClass(source))}>{sourceText(source)}</span>
          <span className="flex-1" />
          <span className="block w-36 shrink-0">
            <input
              data-weight-field={key}
              inputMode="decimal"
              value={value}
              onChange={(event) => onChange(event.target.value)}
              placeholder={placeholder}
              disabled={!canManage}
              className="input px-2 py-1 text-[11px]"
            />
          </span>
          <button
            type="button"
            data-clear-field={key}
            onClick={() => void clearField(key)}
            disabled={!canManage || busy}
            className="btn btn-ghost shrink-0 px-2 py-1 text-[10px]"
          >
            <X size={10} />
            {t("retrieval.clearField")}
          </button>
        </div>
      </div>
    );
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      data-weights-scope={scope}
      className="glass rounded-3xl p-4 shadow-glass sm:p-5"
    >
      <div className="flex flex-wrap items-start gap-2">
        <Settings2 size={15} className="mt-0.5 shrink-0 text-indigo-500 dark:text-indigo-300" />
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
            {title}
          </h2>
          <p className="mt-1 text-[10.5px] leading-relaxed text-slate-500 dark:text-slate-400">
            {description}
          </p>
        </div>
        <span
          className={clsx(
            "chip",
            scope === "user"
              ? "bg-indigo-500/10 text-indigo-600 dark:text-indigo-300"
              : "bg-violet-500/10 text-violet-600 dark:text-violet-300",
          )}
        >
          {scope === "user" ? t("retrieval.sourceUser") : t("retrieval.sourceTenant")}
        </span>
        <span className="chip-muted">
          {activeScope?.configured
            ? t("retrieval.scopeConfigured")
            : t("retrieval.scopeNotConfigured")}
        </span>
      </div>

      {scope === "tenant" ? (
        <p className="mt-1 text-[10px] text-slate-400">{t("retrieval.scopeHint")}</p>
      ) : null}

      {!canManage ? (
        <p className="mt-2 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[10.5px] text-amber-700 dark:text-amber-300">
          {t("retrieval.readOnly")}
        </p>
      ) : null}

      {loading ? (
        <p className="mt-3 flex items-center gap-2 text-[11px] text-slate-400">
          <Loader2 size={12} className="animate-spin" />
          {t("common.loading")}
        </p>
      ) : (
        <>
          <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_260px]">
            <div className="min-w-0 space-y-2">
              {renderWeightField(
                "vector_weight",
                t("retrieval.vectorWeight"),
                weightForm.vector,
                t("retrieval.inheritDefault", { value: defaults.vector_weight }),
                (next) => setWeightForm((prev) => ({ ...prev, vector: next })),
              )}
              {renderWeightField(
                "rerank_weight",
                t("retrieval.rerankWeight"),
                weightForm.rerank,
                t("retrieval.inheritDefault", { value: defaults.rerank_weight }),
                (next) => setWeightForm((prev) => ({ ...prev, rerank: next })),
              )}
              {renderWeightField(
                "rerank_top_n",
                t("retrieval.topN"),
                weightForm.topN,
                t("retrieval.inheritDefault", { value: defaults.rerank_top_n }),
                (next) => setWeightForm((prev) => ({ ...prev, topN: next })),
              )}
              {weightForm.vector.trim() === "0" ? (
                <p className="text-[10px] text-amber-600 dark:text-amber-300">
                  {t("retrieval.vectorZero")}
                </p>
              ) : null}
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => {
                    setClearScopeError("");
                    setClearScopeOpen(true);
                  }}
                  disabled={!canManage || busy}
                  className="btn btn-ghost px-2.5 py-1.5 text-[10.5px] text-rose-600 dark:text-rose-300"
                >
                  <Trash2 size={11} />
                  {t("retrieval.clearScope")}
                </button>
                <span className="flex-1" />
                {canManage ? (
                  <button
                    type="button"
                    onClick={() => void saveSettings()}
                    disabled={busy}
                    className="btn btn-primary px-3 py-1.5 text-[10.5px]"
                  >
                    {busy ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
                    {busy ? t("retrieval.saving") : t("retrieval.saveSettings")}
                  </button>
                ) : null}
              </div>
            </div>

            <aside className="min-w-0 self-start rounded-2xl border border-indigo-400/20 bg-indigo-500/[0.05] px-3 py-3 lg:sticky lg:top-4">
              <div className="flex items-center gap-1.5">
                <Gauge size={12} className="text-indigo-500 dark:text-indigo-300" />
                <span className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">
                  {t("retrieval.effectiveTitle")}
                </span>
              </div>
              <p className="mt-0.5 text-[9.5px] text-slate-400">{t("retrieval.effectiveHint")}</p>
              <div className="mt-2 space-y-1.5 font-mono text-[10.5px] text-slate-600 dark:text-slate-300">
                {[
                  {
                    key: "vector_weight",
                    label: t("retrieval.vectorShort"),
                    value: effectiveWeights?.vector,
                  },
                  {
                    key: "rerank_weight",
                    label: t("retrieval.rerankShort"),
                    value: effectiveWeights?.rerank,
                  },
                  {
                    key: "rerank_top_n",
                    label: t("retrieval.topNShort"),
                    value: effectiveWeights?.top_n,
                  },
                ].map((row) => (
                  <div key={row.key} className="flex flex-wrap items-center gap-1.5">
                    <span className="text-slate-400">{row.label}</span>
                    <span className="font-semibold">{row.value ?? "-"}</span>
                    <span
                      className={clsx(
                        "chip",
                        sourceBadgeClass(effectiveSources[row.key] || "env"),
                      )}
                    >
                      {sourceText(effectiveSources[row.key] || "env")}
                    </span>
                  </div>
                ))}
              </div>
              <div className="mt-2 space-y-1 border-t border-white/60 pt-2 text-[9.5px] text-slate-400 dark:border-white/10">
                <p className="break-all">
                  {t("retrieval.diagEmbedding")}: {settings?.effective?.embedding?.model || "-"}
                </p>
                <p className="break-all">
                  {t("retrieval.diagRerank")}: {settings?.effective?.rerank?.model || "-"}
                </p>
              </div>
            </aside>
          </div>

          <div className="mt-3 rounded-2xl border border-white/60 bg-white/30 dark:border-white/10 dark:bg-white/[0.02]">
            <button
              type="button"
              onClick={() => setDiagnostics((prev) => !prev)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[11px] font-medium text-slate-600 dark:text-slate-300"
            >
              <KeyRound size={12} className="text-slate-400" />
              {t("retrieval.diagnostics")}
              <span className="flex-1" />
              {diagnostics ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
            {diagnostics && settings ? (
              <div className="overflow-x-auto border-t border-white/60 px-3 py-2 dark:border-white/10">
                <div className="min-w-0 space-y-1 font-mono text-[10px] leading-relaxed text-slate-600 dark:text-slate-300">
                  <div className="break-all">
                    {t("retrieval.diagEmbedding")}: {t("retrieval.provider")}=
                    {settings.effective?.embedding?.provider_id || "-"}{" "}
                    {t("retrieval.modelShort")}={settings.effective?.embedding?.model || "-"}{" "}
                    {t("retrieval.dimShort")}={settings.effective?.embedding?.dim ?? "-"}{" "}
                    {t("retrieval.source")}=
                    {sourceText(
                      sources.embedding || settings.effective?.embedding?.source || "env",
                    )}
                  </div>
                  <div className="break-all">
                    {t("retrieval.diagRerank")}: {t("retrieval.provider")}=
                    {settings.effective?.rerank?.provider_id || "-"}{" "}
                    {t("retrieval.modelShort")}={settings.effective?.rerank?.model || "-"}{" "}
                    {t("retrieval.source")}=
                    {sourceText(sources.rerank || settings.effective?.rerank?.source || "env")}
                  </div>
                  <div className="break-all">
                    {t("retrieval.diagWeights")}: {t("retrieval.vectorShort")}=
                    {effectiveWeights?.vector} ({sourceText(sources.vector_weight || "env")}){" "}
                    {t("retrieval.rerankShort")}={effectiveWeights?.rerank} (
                    {sourceText(sources.rerank_weight || "env")}) {t("retrieval.topNShort")}=
                    {effectiveWeights?.top_n} ({sourceText(sources.rerank_top_n || "env")})
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </>
      )}

      <ConfirmDialog
        open={clearScopeOpen}
        title={t("retrieval.clearScopeTitle")}
        description={t("retrieval.clearScopeDesc", { scope: sourceText(scope) })}
        confirmLabel={t("retrieval.clearScope")}
        busy={clearScopeBusy}
        error={clearScopeError}
        onConfirm={() => void clearScopeSettings()}
        onClose={() => {
          if (clearScopeBusy) return;
          setClearScopeOpen(false);
          setClearScopeError("");
        }}
      />
    </motion.section>
  );
}
