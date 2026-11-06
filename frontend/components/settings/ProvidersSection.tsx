import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  Database,
  Gauge,
  Info,
  KeyRound,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Save,
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
} from "@/lib/api";
import { getJob, isTerminal, type Job } from "@/lib/jobs";
import { useI18n } from "@/i18n/I18nProvider";
import { ConfirmDialog } from "@/components/common/Dialogs";

type Props = {
  kind: "embedding" | "rerank";
  scopeFilter: "user" | "server";
  canManage: boolean;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
};

type PanelState = { mode: "create" } | { mode: "edit"; id: string } | null;

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
  scope: string;
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

function emptyForm(kind: RetrievalKind, scope: string): FormState {
  if (kind === "rerank") {
    const preset = RERANK_PRESETS.cohere;
    return {
      id: "",
      kind,
      name: "",
      backend: "cohere",
      base_url: preset.base_url,
      model: preset.model,
      dim: "",
      api_key: "",
      is_default: false,
      scope,
    };
  }
  return {
    id: "",
    kind,
    name: "",
    backend: "openai",
    base_url: "",
    model: "",
    dim: "",
    api_key: "",
    is_default: false,
    scope,
  };
}

export default function ProvidersSection({
  kind,
  scopeFilter,
  canManage,
  onNotice,
  onError,
}: Props) {
  const { t } = useI18n();
  const [items, setItems] = useState<RetrievalProvider[]>([]);
  const [statuses, setStatuses] = useState<Record<string, EmbeddingStatus>>({});
  const [loading, setLoading] = useState(true);
  const [panel, setPanel] = useState<PanelState>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [formError, setFormError] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [rowBusy, setRowBusy] = useState("");
  const [rowError, setRowError] = useState<{ id: string; text: string } | null>(null);
  const [rowTest, setRowTest] = useState<Record<string, { ok: boolean; text: string }>>({});
  const [backfills, setBackfills] = useState<Record<string, BackfillState>>({});
  const [deleteTarget, setDeleteTarget] = useState<RetrievalProvider | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const visible = items.filter((item) =>
    scopeFilter === "user" ? item.scope === "user" : item.scope !== "user",
  );

  const scopeBadge = (value: string | undefined) => {
    if (value === "tenant") {
      return {
        label: t("retrieval.scopeBadgeTenant"),
        className: "bg-violet-500/10 text-violet-600 dark:text-violet-300",
      };
    }
    if (value === "global") {
      return {
        label: t("retrieval.scopeBadgeGlobal"),
        className: "bg-amber-400/15 text-amber-700 dark:text-amber-300",
      };
    }
    return {
      label: t("retrieval.scopeBadgeUser"),
      className: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-300",
    };
  };

  const loadStatuses = useCallback(async (list: RetrievalProvider[]) => {
    if (kind !== "embedding") {
      setStatuses({});
      return;
    }
    const eligible = list.filter((item) => item.dim > 0 && item.enabled !== false);
    const pairs = await Promise.all(
      eligible.map(async (item) => {
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
  }, [kind]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.listRetrievalProviders(kind);
      if (!mounted.current) return;
      const providers = list.providers ?? [];
      setItems(providers);
      await loadStatuses(providers);
    } catch (err) {
      onError(errorText(err, t("retrieval.loadFailed")));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [kind, loadStatuses, onError, t]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const patchForm = useCallback((patch: Partial<FormState>) => {
    setForm((prev) => (prev ? { ...prev, ...patch } : prev));
  }, []);

  const closePanel = useCallback(() => {
    setPanel(null);
    setForm(null);
    setFormError("");
    setShowKey(false);
  }, []);

  const openCreate = useCallback(() => {
    if (!canManage) return;
    setFormError("");
    setShowKey(false);
    setPanel({ mode: "create" });
    setForm(emptyForm(kind, scopeFilter === "user" ? "user" : "tenant"));
  }, [canManage, kind, scopeFilter]);

  const openEdit = useCallback((item: RetrievalProvider) => {
    if (!canManage) return;
    setFormError("");
    setShowKey(false);
    setPanel({ mode: "edit", id: item.id });
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
      scope: item.scope || (scopeFilter === "user" ? "user" : "tenant"),
    });
  }, [canManage, scopeFilter]);

  const switchKind = useCallback((next: RetrievalKind) => {
    setShowKey(false);
    setForm((prev) => {
      if (!prev) return prev;
      if (next === "rerank") {
        const preset = RERANK_PRESETS.cohere;
        return {
          ...prev,
          kind: next,
          backend: "cohere",
          base_url: preset.base_url,
          model: preset.model,
          dim: "",
        };
      }
      return {
        ...prev,
        kind: next,
        backend: "openai",
        base_url: "",
        model: "",
        dim: "",
      };
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
      if (!form.dim.trim() || !Number.isFinite(dim) || dim <= 0) {
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
    if (form.kind === "rerank" && form.backend !== "llm" && !form.base_url.trim()) {
      setFormError(t("retrieval.baseUrlRequired"));
      return;
    }
    setBusy(true);
    setFormError("");
    try {
      const dim = Number(form.dim);
      const payload: RetrievalProviderPayload = {
        name: form.name.trim(),
        base_url: form.base_url.trim(),
        model: form.model.trim(),
        dim: form.dim.trim() && Number.isFinite(dim) && dim > 0 ? Math.trunc(dim) : 0,
        is_default: form.is_default,
      };
      if (form.api_key.trim()) payload.api_key = form.api_key.trim();
      if (form.id) {
        await api.updateRetrievalProvider(form.id, payload);
        onNotice(t("retrieval.updated"));
      } else {
        payload.kind = form.kind;
        payload.backend = form.backend;
        payload.scope = form.scope;
        await api.createRetrievalProvider(payload);
        onNotice(t("retrieval.created"));
      }
      closePanel();
      await loadAll();
    } catch (err) {
      setFormError(errorText(err, t("retrieval.saveFailed")));
    } finally {
      setBusy(false);
    }
  }, [closePanel, form, loadAll, onNotice, t]);

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
        if (result.ok && result.dim_updated) {
          await loadAll();
          onNotice(t("retrieval.dimUpdated", { dim: result.dim ?? 0 }));
        }
      } catch (err) {
        setRowTest((prev) => ({
          ...prev,
          [item.id]: { ok: false, text: errorText(err, t("retrieval.testFailed")) },
        }));
      } finally {
        if (mounted.current) setRowBusy("");
      }
    },
    [loadAll, onNotice, t],
  );

  const setDefault = useCallback(
    async (item: RetrievalProvider) => {
      setRowBusy(item.id);
      setRowError(null);
      try {
        await api.updateRetrievalProvider(item.id, { is_default: true });
        await api.updateRetrievalSettings(
          item.kind === "rerank"
            ? { scope: item.scope === "user" ? "user" : "tenant", rerank_provider_id: item.id }
            : {
                scope: item.scope === "user" ? "user" : "tenant",
                embedding_provider_id: item.id,
              },
        );
        onNotice(t("retrieval.defaultSaved"));
        await loadAll();
      } catch (err) {
        setRowError({ id: item.id, text: errorText(err, t("retrieval.saveFailed")) });
      } finally {
        if (mounted.current) setRowBusy("");
      }
    },
    [loadAll, onNotice, t],
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
            await loadStatuses(visible);
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
    [loadStatuses, onNotice, t, visible],
  );

  const renderDimBadge = (item: RetrievalProvider) => {
    if (item.kind !== "embedding") return null;
    const dimSource = typeof item.meta?.dim_source === "string" ? item.meta.dim_source : "";
    if (item.dim <= 0 || dimSource === "unknown") {
      return (
        <span
          data-dim-state="unknown"
          className="chip bg-amber-400/15 text-amber-700 dark:text-amber-300"
        >
          {t("retrieval.dimUnknown")}
        </span>
      );
    }
    if (dimSource === "probe") {
      return (
        <span
          data-dim-state="probe"
          className="chip bg-sky-500/10 text-sky-600 dark:text-sky-300"
        >
          {item.dim} · {t("retrieval.dimAuto")}
        </span>
      );
    }
    return (
      <span data-dim-state="normal" className="chip-muted">
        {item.dim}
      </span>
    );
  };

  const renderPanel = (open: boolean) => {
    if (!form) return null;
    const editing = Boolean(form.id);
    const scope = scopeBadge(form.scope);
    return (
      <div
        className={clsx(
          "grid overflow-hidden transition-all duration-300 ease-out",
          open ? "mt-2 max-h-[1200px] opacity-100" : "max-h-0 opacity-0",
        )}
      >
        <div
          data-inline-panel={editing ? "edit" : "create"}
          className="rounded-2xl border border-indigo-400/35 bg-indigo-500/[0.05] p-3 dark:border-indigo-300/20 dark:bg-indigo-300/[0.04]"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10.5px] text-slate-500 dark:text-slate-400">
              {t("retrieval.kind")}
            </span>
            <span className="block w-36">
              <select
                data-field="provider-kind"
                value={form.kind}
                onChange={(event) => switchKind(event.target.value as RetrievalKind)}
                disabled={editing}
                className="select py-1 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <option value="embedding">embedding</option>
                <option value="rerank">rerank</option>
              </select>
            </span>
            {editing ? (
              <span className="text-[10px] text-slate-400">{t("retrieval.immutableHint")}</span>
            ) : null}
            <span className="flex-1" />
            {!editing && scopeFilter === "server" ? (
              <>
                <span className="text-[10.5px] text-slate-500 dark:text-slate-400">
                  {t("retrieval.scopeLabel")}
                </span>
                <span className="block w-28">
                  <select
                    data-field="provider-scope"
                    value={form.scope}
                    onChange={(event) => patchForm({ scope: event.target.value })}
                    className="select py-1 text-[11px]"
                  >
                    <option value="tenant">{t("retrieval.scopeBadgeTenant")}</option>
                    <option value="global">{t("retrieval.scopeBadgeGlobal")}</option>
                  </select>
                </span>
              </>
            ) : (
              <span className={clsx("chip", scope.className)}>{scope.label}</span>
            )}
          </div>

          <div className="mt-2.5 grid gap-2.5 sm:grid-cols-2">
            <label className="block min-w-0">
              <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                {t("retrieval.name")}
              </span>
              <input
                data-field="provider-name"
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
                data-field="provider-backend"
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
                disabled={editing}
                className="select disabled:cursor-not-allowed disabled:opacity-60"
              >
                {(form.kind === "embedding" ? ["openai", "hash"] : RERANK_BACKENDS).map(
                  (value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ),
                )}
              </select>
            </label>
            <label className="block min-w-0">
              <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                {t("retrieval.baseUrl")}
              </span>
              <input
                data-field="provider-base-url"
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
                data-field="provider-model"
                value={form.model}
                onChange={(event) => patchForm({ model: event.target.value })}
                placeholder={t("retrieval.modelPlaceholder")}
                className="input"
              />
            </label>
            {form.kind === "embedding" ? (
              <label className="block min-w-0">
                <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                  {t("retrieval.dim")}{" "}
                  {form.backend === "hash" ? (
                    <span className="text-rose-500">*</span>
                  ) : (
                    <span className="text-slate-400">（{t("retrieval.optional")}）</span>
                  )}
                </span>
                <input
                  data-field="provider-dim"
                  inputMode="numeric"
                  value={form.dim}
                  onChange={(event) => patchForm({ dim: event.target.value })}
                  placeholder={
                    form.backend === "openai"
                      ? t("retrieval.dimPlaceholderAuto")
                      : t("retrieval.dimPlaceholder")
                  }
                  className="input"
                />
              </label>
            ) : null}
            <label className={clsx("block min-w-0", form.kind !== "embedding" && "sm:col-span-2")}>
              <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                {t("retrieval.apiKey")}
              </span>
              <span className="relative block">
                <input
                  data-field="provider-api-key"
                  type={showKey ? "text" : "password"}
                  value={form.api_key}
                  onChange={(event) => patchForm({ api_key: event.target.value })}
                  placeholder={
                    editing && items.find((item) => item.id === form.id)?.has_key
                      ? t("retrieval.apiKeyConfigured")
                      : t("retrieval.apiKeyPlaceholder")
                  }
                  autoComplete="off"
                  className="input pr-9"
                />
                <button
                  type="button"
                  onClick={() => setShowKey((prev) => !prev)}
                  className="absolute right-1 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-lg text-slate-400 transition hover:text-indigo-500"
                  aria-label={showKey ? t("retrieval.hide") : t("retrieval.show")}
                >
                  {showKey ? <X size={12} /> : <KeyRound size={12} />}
                </button>
              </span>
            </label>
          </div>

          {form.kind === "rerank" && form.backend === "llm" ? (
            <p className="mt-2 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[10px] text-amber-700 dark:text-amber-300">
              {t("retrieval.llmHint")}
            </p>
          ) : null}

          {formError ? (
            <p className="mt-2 flex items-start gap-1.5 break-words rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[10.5px] text-rose-700 dark:text-rose-300">
              <AlertCircle size={12} className="mt-0.5 shrink-0" />
              <span className="min-w-0 break-words">{formError}</span>
            </p>
          ) : null}

          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5 text-[11px] text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                data-field="provider-default"
                checked={form.is_default}
                onChange={(event) => patchForm({ is_default: event.target.checked })}
                className="h-3.5 w-3.5 accent-indigo-500"
              />
              {t("retrieval.isDefault")}
            </label>
            <span className="flex-1" />
            <button
              type="button"
              onClick={closePanel}
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
              {busy ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
              {t("common.save")}
            </button>
          </div>
        </div>
      </div>
    );
  };

  const renderProviderRow = (item: RetrievalProvider) => {
    const status = statuses[item.id];
    const test = rowTest[item.id];
    const backfill = backfills[item.id];
    const dimSource = typeof item.meta?.dim_source === "string" ? item.meta.dim_source : "";
    const dimUnknown = item.kind === "embedding" && (item.dim <= 0 || dimSource === "unknown");
    const coveragePercent = status
      ? Math.round(Math.max(0, Math.min(1, status.coverage)) * 100)
      : 0;
    const expanded = panel?.mode === "edit" && panel.id === item.id;
    const scope = scopeBadge(item.scope);
    return (
      <div
        key={item.id}
        data-provider-id={item.id}
        className={clsx(
          "rounded-2xl border px-3 py-3 transition-colors",
          expanded
            ? "border-indigo-400/70 bg-indigo-500/[0.06] ring-1 ring-indigo-400/25 dark:border-indigo-300/40"
            : "border-white/60 bg-white/45 dark:border-white/10 dark:bg-white/[0.03]",
        )}
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
              <span className={clsx("chip", scope.className)}>{scope.label}</span>
              {renderDimBadge(item)}
            </div>
            <div className="flex min-w-0 flex-wrap gap-x-3 gap-y-1 text-[10.5px] text-slate-500 dark:text-slate-400">
              <span className="break-all">{item.backend}</span>
              <span className="break-all">{item.model || t("common.notConfigured")}</span>
              <span className="break-all">{item.base_url || ""}</span>
            </div>
            {dimUnknown ? (
              <p className="flex items-start gap-1 text-[10px] text-amber-700 dark:text-amber-300">
                <Info size={11} className="mt-0.5 shrink-0" />
                <span>{t("retrieval.dimUnknownHint")}</span>
              </p>
            ) : null}
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
                  {canManage && status && status.chunks_total > 0 && status.coverage < 1 ? (
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
            {canManage && !item.is_default ? (
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
            {canManage ? (
              <>
                <button
                  type="button"
                  data-action="edit-provider"
                  onClick={() => (expanded ? closePanel() : openEdit(item))}
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
        {expanded ? renderPanel(true) : null}
      </div>
    );
  };

  const title =
    kind === "embedding"
      ? scopeFilter === "user"
        ? t("retrieval.myEmbeddingTitle")
        : t("retrieval.serverEmbeddingTitle")
      : scopeFilter === "user"
        ? t("retrieval.myRerankTitle")
        : t("retrieval.serverRerankTitle");
  const description =
    scopeFilter === "user"
      ? t("retrieval.userProvidersDesc")
      : t("retrieval.serverProvidersDesc");
  const Icon = kind === "embedding" ? Database : Gauge;

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      data-providers-section={`${scopeFilter}-${kind}`}
      className="glass rounded-3xl p-4 shadow-glass sm:p-5"
    >
      <div className="flex flex-wrap items-start gap-2">
        <Icon size={15} className="mt-0.5 shrink-0 text-indigo-500 dark:text-indigo-300" />
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
            scopeFilter === "user"
              ? "bg-indigo-500/10 text-indigo-600 dark:text-indigo-300"
              : "bg-violet-500/10 text-violet-600 dark:text-violet-300",
          )}
        >
          {scopeFilter === "user"
            ? t("retrieval.scopeBadgeUser")
            : t("retrieval.scopeBadgeTenant")}
        </span>
        <button
          type="button"
          data-action="new-provider"
          onClick={() => (panel?.mode === "create" ? closePanel() : openCreate())}
          disabled={!canManage}
          title={canManage ? "" : t("retrieval.readOnly")}
          className="btn btn-primary px-2.5 py-1.5 text-[10.5px]"
        >
          <Plus size={11} />
          {t("retrieval.newProvider")}
        </button>
      </div>

      {!canManage ? (
        <p className="mt-2 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[10.5px] text-amber-700 dark:text-amber-300">
          {t("retrieval.readOnly")}
        </p>
      ) : null}

      <p className="mt-2 text-[10px] text-slate-400">
        {kind === "embedding" ? t("retrieval.defaultHint") : t("retrieval.presetHint")}
      </p>

      <div className="mt-2 space-y-2">
        {panel?.mode === "create" ? (
          <div
            className={clsx(
              "rounded-2xl border px-3 py-3 transition-colors",
              "border-indigo-400/70 bg-indigo-500/[0.06] ring-1 ring-indigo-400/25 dark:border-indigo-300/40",
            )}
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[12px] font-semibold text-slate-800 dark:text-slate-100">
                {t("retrieval.createTitle")}
              </span>
              <span className="chip-muted">{t("retrieval.inlineHint")}</span>
            </div>
            {renderPanel(true)}
          </div>
        ) : null}

        {loading ? (
          <p className="flex items-center gap-2 text-[11px] text-slate-400">
            <Loader2 size={12} className="animate-spin" />
            {t("common.loading")}
          </p>
        ) : visible.length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-300/60 px-3 py-3 text-[10.5px] text-slate-400 dark:border-white/10">
            {kind === "embedding" ? t("retrieval.emptyEmbedding") : t("retrieval.emptyRerank")}
          </p>
        ) : (
          visible.map((item) => renderProviderRow(item))
        )}
      </div>

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
