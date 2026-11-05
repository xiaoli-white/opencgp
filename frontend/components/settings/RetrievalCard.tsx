import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Database,
  Gauge,
  KeyRound,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Settings2,
  Star,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import clsx from "clsx";
import {
  api,
  type EmbeddingStatus,
  type RetrievalKind,
  type RetrievalProvider,
  type RetrievalProviderPayload,
  type RetrievalSettings,
} from "@/lib/api";
import { getJob, isTerminal, type Job } from "@/lib/jobs";
import { useI18n } from "@/i18n/I18nProvider";
import { ConfirmDialog, Modal } from "@/components/common/Dialogs";

type Props = {
  canWrite: boolean;
  canManageServer: boolean;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
};

type Scope = "user" | "tenant";

type FormState = {
  id: string;
  kind: RetrievalKind;
  name: string;
  backend: string;
  base_url: string;
  model: string;
  dim: string;
  api_key: string;
  is_default: boolean;
};

type BackfillState = {
  progress: number;
  text: string;
  done: boolean;
  ok: boolean;
};

const RERANK_PRESETS: Record<string, { base_url: string; model: string }> = {
  cohere: {
    base_url: "https://api.cohere.com/v1/rerank",
    model: "rerank-v3.5",
  },
  jina: {
    base_url: "https://api.jina.ai/v1/rerank",
    model: "jina-reranker-v2-base-multilingual",
  },
  siliconflow: {
    base_url: "https://api.siliconflow.cn/v1/rerank",
    model: "BAAI/bge-reranker-v2-m3",
  },
  zhipu: {
    base_url: "https://open.bigmodel.cn/api/paas/v4/rerank",
    model: "rerank",
  },
  tei: {
    base_url: "http://127.0.0.1:8080/rerank",
    model: "BAAI/bge-reranker-v2-m3",
  },
  generic: { base_url: "", model: "" },
  llm: { base_url: "", model: "" },
};

const RERANK_BACKENDS = [
  "cohere",
  "jina",
  "siliconflow",
  "zhipu",
  "tei",
  "generic",
  "llm",
];

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

export default function RetrievalCard({
  canWrite,
  canManageServer,
  onNotice,
  onError,
}: Props) {
  const { t } = useI18n();
  const [embeddingItems, setEmbeddingItems] = useState<RetrievalProvider[]>([]);
  const [rerankItems, setRerankItems] = useState<RetrievalProvider[]>([]);
  const [settings, setSettings] = useState<RetrievalSettings | null>(null);
  const [statuses, setStatuses] = useState<Record<string, EmbeddingStatus>>({});
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<FormState | null>(null);
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [rowBusy, setRowBusy] = useState("");
  const [rowError, setRowError] = useState<{ id: string; text: string } | null>(null);
  const [rowTest, setRowTest] = useState<Record<string, { ok: boolean; text: string }>>({});
  const [backfills, setBackfills] = useState<Record<string, BackfillState>>({});
  const [deleteTarget, setDeleteTarget] = useState<RetrievalProvider | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [scope, setScope] = useState<Scope>("user");
  const [vectorWeight, setVectorWeight] = useState(0.55);
  const [rerankWeight, setRerankWeight] = useState(0.5);
  const [topN, setTopN] = useState(12);
  const [diagnostics, setDiagnostics] = useState(false);
  const [showKey, setShowKey] = useState(false);
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
      return t("retrieval.sourceDefault");
    },
    [t],
  );

  const loadStatuses = useCallback(async (items: RetrievalProvider[]) => {
    const pairs = await Promise.all(
      items.map(async (item) => {
        try {
          const status = await api.getEmbeddingStatus(item.id);
          return { id: item.id, status };
        } catch {
          return null;
        }
      }),
    );
    const next: Record<string, EmbeddingStatus> = {};
    for (const pair of pairs) {
      if (pair) next[pair.id] = pair.status;
    }
    if (mounted.current) setStatuses(next);
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [embeddings, reranks, effective] = await Promise.all([
        api.listRetrievalProviders("embedding"),
        api.listRetrievalProviders("rerank"),
        api.getRetrievalSettings(),
      ]);
      if (!mounted.current) return;
      setEmbeddingItems(embeddings.providers ?? []);
      setRerankItems(reranks.providers ?? []);
      setSettings(effective);
      setVectorWeight(effective.vector_weight);
      setRerankWeight(effective.rerank_weight);
      setTopN(effective.rerank_top_n);
      await loadStatuses(embeddings.providers ?? []);
    } catch (err) {
      onError(errorText(err, t("retrieval.loadFailed")));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [loadStatuses, onError, t]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const patchForm = useCallback((patch: Partial<FormState>) => {
    setForm((prev) => (prev ? { ...prev, ...patch } : prev));
  }, []);

  const openCreate = useCallback(
    (kind: RetrievalKind) => {
      setFormError("");
      setShowKey(false);
      if (kind === "embedding") {
        setForm({
          id: "",
          kind,
          name: "",
          backend: "openai",
          base_url: "",
          model: "",
          dim: "",
          api_key: "",
          is_default: false,
        });
        return;
      }
      const preset = RERANK_PRESETS.cohere;
      setForm({
        id: "",
        kind,
        name: "",
        backend: "cohere",
        base_url: preset.base_url,
        model: preset.model,
        dim: "",
        api_key: "",
        is_default: false,
      });
    },
    [],
  );

  const openEdit = useCallback((item: RetrievalProvider) => {
    setFormError("");
    setShowKey(false);
    setForm({
      id: item.id,
      kind: item.kind === "rerank" ? "rerank" : "embedding",
      name: item.name,
      backend: item.backend,
      base_url: item.base_url || "",
      model: item.model || "",
      dim: item.dim > 0 ? String(item.dim) : "",
      api_key: "",
      is_default: item.is_default,
    });
  }, []);

  const saveForm = useCallback(async () => {
    if (!form) return;
    if (!form.name.trim()) {
      setFormError(t("retrieval.nameRequired"));
      return;
    }
    if (form.kind === "embedding" && form.backend === "hash") {
      const dim = Number(form.dim);
      if (!Number.isFinite(dim) || dim <= 0) {
        setFormError(t("retrieval.dimRequired"));
        return;
      }
    }
    if (form.kind === "embedding" && form.backend === "openai") {
      if (!form.base_url.trim()) {
        setFormError(t("retrieval.baseUrlRequired"));
        return;
      }
      if (!form.model.trim()) {
        setFormError(t("retrieval.modelRequired"));
        return;
      }
    }
    setBusy(true);
    setFormError("");
    try {
      const dim = Number(form.dim);
      const payload: RetrievalProviderPayload = {
        name: form.name.trim(),
        base_url: form.base_url.trim(),
        model: form.model.trim(),
        dim: Number.isFinite(dim) && dim > 0 ? Math.trunc(dim) : 0,
        is_default: form.is_default,
      };
      if (form.api_key.trim()) payload.api_key = form.api_key.trim();
      if (form.id) {
        await api.updateRetrievalProvider(form.id, payload);
        onNotice(t("retrieval.updated"));
      } else {
        payload.kind = form.kind;
        payload.backend = form.backend;
        payload.scope = scope;
        await api.createRetrievalProvider(payload);
        onNotice(t("retrieval.created"));
      }
      setForm(null);
      setShowKey(false);
      await loadAll();
    } catch (err) {
      setFormError(errorText(err, t("retrieval.saveFailed")));
    } finally {
      setBusy(false);
    }
  }, [form, loadAll, onNotice, scope, t]);

  const testProvider = useCallback(
    async (item: RetrievalProvider) => {
      setRowBusy(item.id);
      setRowError(null);
      setRowTest((prev) => {
        const next = { ...prev };
        delete next[item.id];
        return next;
      });
      try {
        const result = await api.testRetrievalProvider(item.id);
        const text = result.ok
          ? t("retrieval.testOk", {
              latency: result.latency_ms,
              dim: result.dim ?? result.expected_dim ?? 0,
            })
          : result.error || t("retrieval.testFailed");
        setRowTest((prev) => ({ ...prev, [item.id]: { ok: result.ok, text } }));
      } catch (err) {
        setRowTest((prev) => ({
          ...prev,
          [item.id]: { ok: false, text: errorText(err, t("retrieval.testFailed")) },
        }));
      } finally {
        setRowBusy("");
      }
    },
    [t],
  );

  const setDefault = useCallback(
    async (item: RetrievalProvider) => {
      setRowBusy(item.id);
      setRowError(null);
      try {
        await api.updateRetrievalProvider(item.id, { is_default: true });
        const payload =
          item.kind === "rerank"
            ? { scope, rerank_provider_id: item.id }
            : { scope, embedding_provider_id: item.id };
        await api.updateRetrievalSettings(payload);
        onNotice(t("retrieval.defaultSaved"));
        await loadAll();
      } catch (err) {
        setRowError({ id: item.id, text: errorText(err, t("retrieval.saveFailed")) });
      } finally {
        setRowBusy("");
      }
    },
    [loadAll, onNotice, scope, t],
  );

  const removeProvider = useCallback(async () => {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    setDeleteError("");
    try {
      await api.deleteRetrievalProvider(deleteTarget.id);
      onNotice(t("retrieval.deleted"));
      setDeleteTarget(null);
      await loadAll();
    } catch (err) {
      setDeleteError(errorText(err, t("retrieval.deleteFailed")));
    } finally {
      setDeleteBusy(false);
    }
  }, [deleteTarget, loadAll, onNotice, t]);

  const startBackfill = useCallback(
    async (item: RetrievalProvider) => {
      setRowBusy(item.id);
      setRowError(null);
      setBackfills((prev) => ({
        ...prev,
        [item.id]: {
          progress: 0,
          text: t("retrieval.backfillQueued"),
          done: false,
          ok: true,
        },
      }));
      try {
        const created = await api.backfillEmbeddings(item.id);
        for (;;) {
          await new Promise((resolve) => window.setTimeout(resolve, 1200));
          if (!mounted.current) return;
          const job: Job = await getJob(created.job_id);
          const progress = Math.max(0, Math.min(1, Number(job.progress) || 0));
          if (!isTerminal(job.status)) {
            setBackfills((prev) => ({
              ...prev,
              [item.id]: {
                progress,
                text: t("retrieval.backfillRunning", {
                  percent: Math.round(progress * 100),
                }),
                done: false,
                ok: true,
              },
            }));
            continue;
          }
          if (job.status === "succeeded") {
            const result = job.result ?? {};
            const text = t("retrieval.backfillDone", {
              embedded: Number(result.embedded) || 0,
              failed: Number(result.failed) || 0,
              skipped: Number(result.skipped) || 0,
            });
            setBackfills((prev) => ({
              ...prev,
              [item.id]: { progress: 1, text, done: true, ok: true },
            }));
            onNotice(text);
            await loadStatuses(embeddingItems);
          } else {
            const text = job.error || t("retrieval.backfillFailed");
            setBackfills((prev) => ({
              ...prev,
              [item.id]: { progress, text, done: true, ok: false },
            }));
            setRowError({ id: item.id, text });
          }
          break;
        }
      } catch (err) {
        const text = errorText(err, t("retrieval.backfillFailed"));
        setBackfills((prev) => ({
          ...prev,
          [item.id]: { progress: 0, text, done: true, ok: false },
        }));
        setRowError({ id: item.id, text });
      } finally {
        if (mounted.current) setRowBusy("");
      }
    },
    [embeddingItems, loadStatuses, onNotice, t],
  );

  const saveSettings = useCallback(async () => {
    setBusy(true);
    try {
      await api.updateRetrievalSettings({
        scope,
        vector_weight: vectorWeight,
        rerank_weight: rerankWeight,
        rerank_top_n: topN,
      });
      onNotice(t("retrieval.settingsSaved"));
      await loadAll();
    } catch (err) {
      onError(errorText(err, t("retrieval.saveFailed")));
    } finally {
      setBusy(false);
    }
  }, [loadAll, onError, rerankWeight, scope, t, topN, vectorWeight]);

  const defaultSource = useMemo(
    () => sourceText(settings?.source || "env"),
    [settings?.source, sourceText],
  );

  const renderProviderRow = (item: RetrievalProvider) => {
    const status = statuses[item.id];
    const test = rowTest[item.id];
    const backfill = backfills[item.id];
    const coveragePercent = status
      ? Math.round(Math.max(0, Math.min(1, status.coverage)) * 100)
      : 0;
    return (
      <div
        key={item.id}
        data-provider-id={item.id}
        className="rounded-2xl border border-white/60 bg-white/45 px-3 py-3 dark:border-white/10 dark:bg-white/[0.03]"
      >
        <div className="flex flex-col gap-2.5 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              <span className="max-w-full break-all text-[12px] font-semibold text-slate-800 dark:text-slate-100">
                {item.name}
              </span>
              {item.is_default ? (
                <span className="chip bg-indigo-500/10 text-indigo-600 dark:text-indigo-300">
                  {t("retrieval.defaultBadge")}
                </span>
              ) : null}
              <span
                className={clsx(
                  "chip",
                  item.has_key
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-300"
                    : "chip-muted",
                )}
              >
                {item.has_key ? t("retrieval.hasKeyBadge") : t("retrieval.noKeyBadge")}
              </span>
            </div>
            <div className="flex min-w-0 flex-wrap gap-x-3 gap-y-1 text-[10.5px] text-slate-500 dark:text-slate-400">
              <span className="break-all">{item.backend}</span>
              <span className="break-all">{item.model || t("common.notConfigured")}</span>
              {item.kind === "embedding" ? (
                <span>dim {item.dim}</span>
              ) : null}
              <span className="break-all">{item.base_url || ""}</span>
            </div>
            {item.kind === "embedding" ? (
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2 text-[10.5px]">
                  <Database size={11} className="text-slate-400" />
                  {status ? (
                    <span className="font-mono text-slate-600 dark:text-slate-300">
                      {t("retrieval.coverageLabel", {
                        embedded: status.chunks_embedded,
                        total: status.chunks_total,
                        percent: coveragePercent,
                      })}
                    </span>
                  ) : (
                    <span className="text-slate-400">{t("retrieval.coverageUnavailable")}</span>
                  )}
                  {canWrite && status && status.chunks_total > 0 && status.coverage < 1 ? (
                    <button
                      type="button"
                      onClick={() => void startBackfill(item)}
                      disabled={rowBusy === item.id}
                      className="btn btn-ghost px-2 py-1 text-[10px]"
                    >
                      {rowBusy === item.id ? (
                        <Loader2 size={10} className="animate-spin" />
                      ) : (
                        <RefreshCw size={10} />
                      )}
                      {t("retrieval.backfill")}
                    </button>
                  ) : null}
                </div>
                {backfill ? (
                  <div className="space-y-1">
                    {!backfill.done ? (
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-white/10">
                        <div
                          className="h-full rounded-full bg-indigo-500 transition-all"
                          style={{ width: `${Math.round(backfill.progress * 100)}%` }}
                        />
                      </div>
                    ) : null}
                    <p
                      className={clsx(
                        "break-words text-[10px]",
                        backfill.ok
                          ? "text-emerald-600 dark:text-emerald-300"
                          : "text-rose-600 dark:text-rose-300",
                      )}
                    >
                      {backfill.text}
                    </p>
                  </div>
                ) : null}
              </div>
            ) : null}
            {test ? (
              <p
                className={clsx(
                  "flex items-start gap-1 break-words text-[10.5px]",
                  test.ok
                    ? "text-emerald-600 dark:text-emerald-300"
                    : "text-rose-600 dark:text-rose-300",
                )}
              >
                {test.ok ? (
                  <CheckCircle2 size={11} className="mt-0.5 shrink-0" />
                ) : (
                  <AlertCircle size={11} className="mt-0.5 shrink-0" />
                )}
                <span className="min-w-0 break-words">{test.text}</span>
              </p>
            ) : null}
            {rowError && rowError.id === item.id ? (
              <p className="flex items-start gap-1 break-words rounded-xl border border-rose-400/30 bg-rose-500/10 px-2 py-1.5 text-[10px] text-rose-700 dark:text-rose-300">
                <AlertCircle size={11} className="mt-0.5 shrink-0" />
                <span className="min-w-0 break-words">{rowError.text}</span>
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-1.5 sm:justify-end">
            <button
              type="button"
              onClick={() => void testProvider(item)}
              disabled={rowBusy === item.id}
              className="btn btn-ghost px-2 py-1 text-[10.5px]"
            >
              {rowBusy === item.id ? (
                <Loader2 size={11} className="animate-spin" />
              ) : (
                <Zap size={11} />
              )}
              {t("retrieval.test")}
            </button>
            {canWrite && !item.is_default ? (
              <button
                type="button"
                onClick={() => void setDefault(item)}
                disabled={rowBusy === item.id}
                className="btn btn-ghost px-2 py-1 text-[10.5px]"
              >
                <Star size={11} />
                {t("retrieval.setDefault")}
              </button>
            ) : null}
            {canWrite ? (
              <>
                <button
                  type="button"
                  onClick={() => openEdit(item)}
                  className="btn btn-ghost px-2 py-1 text-[10.5px]"
                >
                  <Pencil size={11} />
                  {t("retrieval.edit")}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDeleteError("");
                    setDeleteTarget(item);
                  }}
                  className="btn btn-ghost px-2 py-1 text-[10.5px] text-rose-600 dark:text-rose-300"
                >
                  <Trash2 size={11} />
                  {t("retrieval.delete")}
                </button>
              </>
            ) : null}
          </div>
        </div>
      </div>
    );
  };

  const renderSection = (kind: RetrievalKind) => {
    const items = kind === "embedding" ? embeddingItems : rerankItems;
    return (
      <div id={`retrieval-${kind}`} className="mt-4">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="flex items-center gap-1.5 text-[12px] font-semibold text-slate-800 dark:text-slate-100">
            {kind === "embedding" ? (
              <Database size={13} className="text-indigo-500 dark:text-indigo-300" />
            ) : (
              <Gauge size={13} className="text-indigo-500 dark:text-indigo-300" />
            )}
            {kind === "embedding"
              ? t("retrieval.embeddingTitle")
              : t("retrieval.rerankTitle")}
          </h3>
          <span className="chip-muted">{t("common.count", { count: items.length })}</span>
          <span className="flex-1" />
          {canWrite ? (
            <button
              type="button"
              onClick={() => openCreate(kind)}
              className="btn btn-primary px-2.5 py-1.5 text-[10.5px]"
            >
              <Plus size={11} />
              {t("retrieval.newProvider")}
            </button>
          ) : null}
        </div>
        <div className="mt-2 space-y-1.5">
          {loading ? (
            <p className="text-[11px] text-slate-400">{t("common.loading")}</p>
          ) : items.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-white/60 bg-white/35 px-3 py-3 text-[10.5px] text-slate-500 dark:border-white/10 dark:bg-white/[0.02] dark:text-slate-400">
              {kind === "embedding"
                ? t("retrieval.emptyEmbedding")
                : t("retrieval.emptyRerank")}
            </p>
          ) : (
            items.map(renderProviderRow)
          )}
        </div>
        {kind === "embedding" ? (
          <p className="mt-2 text-[10px] leading-relaxed text-slate-400">
            {t("retrieval.defaultHint")}
          </p>
        ) : null}
      </div>
    );
  };

  return (
    <motion.section
      id="retrieval-settings"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.05 }}
      className="glass scroll-mt-24 rounded-3xl p-5 shadow-glass"
    >
      <div className="flex flex-wrap items-start gap-2">
        <div className="flex min-w-0 flex-1 items-start gap-2">
          <Settings2 size={15} className="mt-0.5 shrink-0 text-indigo-500 dark:text-indigo-300" />
          <div className="min-w-0">
            <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
              {t("retrieval.title")}
            </h2>
            <p className="mt-1 text-[10.5px] leading-relaxed text-slate-500 dark:text-slate-400">
              {t("retrieval.description")}
            </p>
          </div>
        </div>
        <span className="chip bg-indigo-500/10 text-indigo-600 dark:text-indigo-300">
          {t("retrieval.sourceLabel")}: {defaultSource}
        </span>
      </div>

      {!canWrite ? (
        <p className="mt-2 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[10.5px] text-amber-700 dark:text-amber-300">
          {t("retrieval.readOnly")}
        </p>
      ) : null}

      {renderSection("embedding")}
      {renderSection("rerank")}

      <div className="mt-5 rounded-2xl border border-white/60 bg-white/40 p-3 dark:border-white/10 dark:bg-white/[0.03]">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-[12px] font-semibold text-slate-800 dark:text-slate-100">
            {t("retrieval.weightsTitle")}
          </h3>
          <span className="flex-1" />
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setScope("user")}
              className={clsx(
                "rounded-lg px-2 py-1 text-[10.5px] transition",
                scope === "user"
                  ? "bg-indigo-500 text-white"
                  : "bg-white/60 text-slate-600 hover:text-indigo-600 dark:bg-white/[0.06] dark:text-slate-300",
              )}
            >
              {t("retrieval.scopeUser")}
            </button>
            <button
              type="button"
              onClick={() => setScope("tenant")}
              disabled={!canManageServer}
              title={canManageServer ? "" : t("retrieval.scopeNeedServer")}
              className={clsx(
                "rounded-lg px-2 py-1 text-[10.5px] transition",
                scope === "tenant"
                  ? "bg-indigo-500 text-white"
                  : "bg-white/60 text-slate-600 hover:text-indigo-600 dark:bg-white/[0.06] dark:text-slate-300",
                !canManageServer && "cursor-not-allowed opacity-50",
              )}
            >
              {t("retrieval.scopeTenant")}
            </button>
          </div>
        </div>
        <p className="mt-1 text-[10px] text-slate-400">{t("retrieval.scopeHint")}</p>

        <div className="mt-3 space-y-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] text-slate-600 dark:text-slate-300">
                {t("retrieval.vectorWeight")}
              </span>
              <span className="flex-1" />
              <span className="font-mono text-[10.5px] text-indigo-600 dark:text-indigo-300">
                {t("retrieval.weightCurrent", { value: vectorWeight.toFixed(2) })}
              </span>
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={vectorWeight}
                data-field="vector-weight"
                onChange={(event) =>
                  setVectorWeight(Math.max(0, Math.min(1, Number(event.target.value) || 0)))
                }
                disabled={!canWrite}
                className="input w-20 px-2 py-1 text-[11px]"
              />
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={vectorWeight}
              onChange={(event) => setVectorWeight(Number(event.target.value))}
              disabled={!canWrite}
              className="mt-1 w-full accent-indigo-500"
            />
            {vectorWeight === 0 ? (
              <p className="mt-1 text-[10px] text-amber-600 dark:text-amber-300">
                {t("retrieval.vectorZero")}
              </p>
            ) : null}
          </div>

          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] text-slate-600 dark:text-slate-300">
                {t("retrieval.rerankWeight")}
              </span>
              <span className="flex-1" />
              <span className="font-mono text-[10.5px] text-indigo-600 dark:text-indigo-300">
                {t("retrieval.weightCurrent", { value: rerankWeight.toFixed(2) })}
              </span>
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={rerankWeight}
                data-field="rerank-weight"
                onChange={(event) =>
                  setRerankWeight(Math.max(0, Math.min(1, Number(event.target.value) || 0)))
                }
                disabled={!canWrite}
                className="input w-20 px-2 py-1 text-[11px]"
              />
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={rerankWeight}
              onChange={(event) => setRerankWeight(Number(event.target.value))}
              disabled={!canWrite}
              className="mt-1 w-full accent-indigo-500"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-slate-600 dark:text-slate-300">
              {t("retrieval.topN")}
            </span>
            <span className="flex-1" />
            <input
              type="number"
              min={1}
              max={50}
              value={topN}
              data-field="top-n"
              onChange={(event) =>
                setTopN(Math.max(1, Math.min(50, Math.trunc(Number(event.target.value) || 1))))
              }
              disabled={!canWrite}
              className="input w-20 px-2 py-1 text-[11px]"
            />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setVectorWeight(0.55);
              setRerankWeight(0.5);
              setTopN(12);
            }}
            disabled={!canWrite}
            className="btn btn-ghost px-2.5 py-1.5 text-[10.5px]"
          >
            {t("retrieval.restoreDefaults")}
          </button>
          <span className="flex-1" />
          {canWrite ? (
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
                {settings.embedding.provider_id || "-"} {t("retrieval.modelShort")}=
                {settings.embedding.model || "-"} {t("retrieval.dimShort")}=
                {settings.embedding.dim ?? "-"} {t("retrieval.source")}=
                {sourceText(settings.sources.embedding || settings.embedding.source)}
              </div>
              <div className="break-all">
                {t("retrieval.diagRerank")}: {t("retrieval.provider")}=
                {settings.rerank.provider_id || "-"} {t("retrieval.modelShort")}=
                {settings.rerank.model || "-"} {t("retrieval.source")}=
                {sourceText(settings.sources.rerank || settings.rerank.source)}
              </div>
              <div className="break-all">
                {t("retrieval.diagWeights")}: {t("retrieval.vectorShort")}=
                {settings.weights.vector} ({sourceText(settings.sources.vector_weight)}){" "}
                {t("retrieval.rerankShort")}={settings.weights.rerank} (
                {sourceText(settings.sources.rerank_weight)}) {t("retrieval.topNShort")}=
                {settings.weights.top_n} ({sourceText(settings.sources.rerank_top_n)})
              </div>
            </div>
          </div>
        ) : null}
      </div>

      <Modal
        open={Boolean(form)}
        title={form?.id ? t("retrieval.editTitle") : t("retrieval.createTitle")}
        subtitle={
          form?.kind === "rerank"
            ? t("retrieval.presetHint")
            : t("retrieval.defaultHint")
        }
        onClose={() => {
          if (busy) return;
          setForm(null);
          setFormError("");
        }}
        wide
      >
        {form ? (
          <div className="space-y-2.5">
            <div className="grid gap-2.5 sm:grid-cols-2">
              <label className="block min-w-0">
                <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                  {t("retrieval.name")}
                </span>
                <input
                  value={form.name}
                  onChange={(event) => patchForm({ name: event.target.value })}
                  placeholder={t("retrieval.namePlaceholder")}
                  className="input"
                />
              </label>
              <label className="block min-w-0">
                <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                  {t("retrieval.backend")}
                </span>
                <select
                  value={form.backend}
                  onChange={(event) => {
                    const value = event.target.value;
                    if (form.kind === "rerank") {
                      const preset = RERANK_PRESETS[value] ?? { base_url: "", model: "" };
                      patchForm({
                        backend: value,
                        base_url: preset.base_url,
                        model: preset.model,
                      });
                      return;
                    }
                    patchForm({ backend: value });
                  }}
                  disabled={Boolean(form.id)}
                  title={form.id ? t("retrieval.backendLocked") : ""}
                  className="select"
                >
                  {(form.kind === "embedding"
                    ? ["openai", "hash"]
                    : RERANK_BACKENDS
                  ).map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block min-w-0 sm:col-span-2">
                <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                  {t("retrieval.baseUrl")}
                </span>
                <input
                  value={form.base_url}
                  onChange={(event) => patchForm({ base_url: event.target.value })}
                  placeholder="https://api.example.com/v1"
                  className="input"
                />
              </label>
              <label className="block min-w-0">
                <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                  {t("retrieval.model")}
                </span>
                <input
                  value={form.model}
                  onChange={(event) => patchForm({ model: event.target.value })}
                  placeholder={t("retrieval.modelPlaceholder")}
                  className="input"
                />
              </label>
              {form.kind === "embedding" ? (
                <label className="block min-w-0">
                  <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                    {t("retrieval.dim")}
                    {form.backend === "hash" ? " *" : ""}
                    {form.backend === "openai" ? (
                      <span className="ml-1 text-[9.5px] text-slate-400">
                        {t("retrieval.optional")}
                      </span>
                    ) : null}
                  </span>
                  <input
                    type="number"
                    min={1}
                    value={form.dim}
                    onChange={(event) => patchForm({ dim: event.target.value })}
                    placeholder={t("retrieval.dimPlaceholder")}
                    className="input"
                  />
                </label>
              ) : null}
              <label className="block min-w-0 sm:col-span-2">
                <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                  {t("retrieval.apiKey")}
                </span>
                <span className="relative block">
                  <input
                    type={showKey ? "text" : "password"}
                    value={form.api_key}
                    onChange={(event) => patchForm({ api_key: event.target.value })}
                    placeholder={
                      form.id &&
                      [...embeddingItems, ...rerankItems].find((item) => item.id === form.id)
                        ?.has_key
                        ? t("retrieval.apiKeyConfigured")
                        : t("retrieval.apiKeyPlaceholder")
                    }
                    autoComplete="off"
                    className="input pr-9"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((prev) => !prev)}
                    className="absolute right-1 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-lg text-slate-400 transition hover:text-indigo-500"
                    aria-label={showKey ? t("retrieval.hide") : t("retrieval.show")}
                  >
                    {showKey ? <X size={12} /> : <KeyRound size={12} />}
                  </button>
                </span>
              </label>
            </div>

            {form.kind === "rerank" && form.backend === "llm" ? (
              <p className="rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[10.5px] text-amber-700 dark:text-amber-300">
                {t("retrieval.llmHint")}
              </p>
            ) : null}

            <label className="flex items-center gap-1.5 text-[11px] text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(event) => patchForm({ is_default: event.target.checked })}
                className="h-3.5 w-3.5 accent-indigo-500"
              />
              {t("retrieval.isDefault")}
            </label>

            {formError ? (
              <p className="flex items-start gap-1.5 break-words rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[10.5px] text-rose-700 dark:text-rose-300">
                <AlertCircle size={12} className="mt-0.5 shrink-0" />
                <span className="min-w-0 break-words">{formError}</span>
              </p>
            ) : null}

            <div className="flex flex-wrap items-center gap-2 pt-1">
              <span className="flex-1" />
              <button
                type="button"
                onClick={() => {
                  setForm(null);
                  setFormError("");
                }}
                disabled={busy}
                className="btn btn-ghost px-3 py-1.5 text-[11px]"
              >
                {t("common.cancel")}
              </button>
              <button
                type="button"
                onClick={() => void saveForm()}
                disabled={busy}
                className="btn btn-primary px-3 py-1.5 text-[11px]"
              >
                {busy ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                {t("common.save")}
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={t("retrieval.deleteTitle")}
        description={t("retrieval.deleteDesc")}
        confirmLabel={t("retrieval.delete")}
        busy={deleteBusy}
        error={deleteError}
        onConfirm={() => void removeProvider()}
        onClose={() => {
          if (deleteBusy) return;
          setDeleteTarget(null);
          setDeleteError("");
        }}
      />
    </motion.section>
  );
}
