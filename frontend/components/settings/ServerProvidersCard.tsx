import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Pencil,
  Plus,
  Save,
  Server,
  Star,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import clsx from "clsx";
import { api, type ServerProvider, type ServerProviderPayload } from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";

type Props = {
  canManage: boolean;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
};

type FormState = {
  id: string;
  name: string;
  kind: string;
  base_url: string;
  api_key: string;
  models: string;
  is_default: boolean;
  enabled: boolean;
};

const KINDS = [
  { value: "openai_compat", label: "openai_compat" },
  { value: "dummy", label: "dummy" },
];

const EMPTY_FORM: FormState = {
  id: "",
  name: "",
  kind: "openai_compat",
  base_url: "",
  api_key: "",
  models: "",
  is_default: false,
  enabled: true,
};

function splitModels(text: string): string[] {
  return text
    .split(/[\n,，;；]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toForm(item: ServerProvider): FormState {
  return {
    id: item.id,
    name: item.name,
    kind: item.kind || "openai_compat",
    base_url: item.base_url || "",
    api_key: "",
    models: (item.models ?? []).join(", "),
    is_default: item.is_default,
    enabled: item.enabled,
  };
}

export default function ServerProvidersCard({ canManage, onNotice, onError }: Props) {
  const { t } = useI18n();
  const [items, setItems] = useState<ServerProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<FormState | null>(null);
  const [busy, setBusy] = useState(false);
  const [rowBusy, setRowBusy] = useState<string>("");
  const [rowError, setRowError] = useState<{ id: string; text: string } | null>(null);
  const [rowTest, setRowTest] = useState<
    Record<string, { ok: boolean; text: string }>
  >({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listAdminProviders();
      setItems(data.providers ?? []);
    } catch (err) {
      onError(err instanceof Error ? err.message : t("serverProviders.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => {
    void load();
  }, [load]);

  const patchForm = (patch: Partial<FormState>) =>
    setForm((prev) => (prev ? { ...prev, ...patch } : prev));

  const save = useCallback(async () => {
    if (!form) return;
    if (!form.name.trim()) {
      setRowError({ id: form.id || "new", text: t("serverProviders.nameRequired") });
      return;
    }
    setBusy(true);
    setRowError(null);
    try {
      const payload: ServerProviderPayload = {
        name: form.name.trim(),
        kind: form.kind,
        base_url: form.base_url.trim(),
        models: splitModels(form.models),
        is_default: form.is_default,
        enabled: form.enabled,
      };
      if (form.api_key.trim()) payload.api_key = form.api_key.trim();
      if (form.id) {
        await api.updateAdminProvider(form.id, payload);
        onNotice(t("serverProviders.updated"));
      } else {
        await api.createAdminProvider(payload);
        onNotice(t("serverProviders.created"));
      }
      setForm(null);
      await load();
    } catch (err) {
      setRowError({
        id: form.id || "new",
        text: err instanceof Error ? err.message : t("serverProviders.saveFailed"),
      });
    } finally {
      setBusy(false);
    }
  }, [form, load, onNotice]);

  const remove = useCallback(
    async (id: string) => {
      setRowBusy(id);
      setRowError(null);
      try {
        await api.deleteAdminProvider(id);
        onNotice(t("serverProviders.deleted"));
        if (form?.id === id) setForm(null);
        await load();
      } catch (err) {
        setRowError({
          id,
          text: err instanceof Error ? err.message : t("serverProviders.deleteFailed"),
        });
      } finally {
        setRowBusy("");
      }
    },
    [form?.id, load, onNotice],
  );

  const runTest = useCallback(async (item: ServerProvider) => {
    setRowBusy(item.id);
    setRowTest((prev) => {
      const next = { ...prev };
      delete next[item.id];
      return next;
    });
    try {
      const result = await api.testAdminProvider(item.id, {
        model: item.models?.[0],
      });
      setRowTest((prev) => ({
        ...prev,
        [item.id]: {
          ok: result.ok,
          text: result.ok
            ? t("providers.testOk", {
          latency: result.latency_ms,
          model: result.model || item.models?.[0] || t("providers.defaultModel"),
        })
            : result.detail || t("providers.testFail"),
        },
      }));
    } catch (err) {
      setRowTest((prev) => ({
        ...prev,
        [item.id]: {
          ok: false,
          text: err instanceof Error ? err.message : t("serverProviders.testFailed"),
        },
      }));
    } finally {
      setRowBusy("");
    }
  }, []);

  const toggleEnabled = useCallback(
    async (item: ServerProvider) => {
      setRowBusy(item.id);
      setRowError(null);
      try {
        await api.updateAdminProvider(item.id, { enabled: !item.enabled });
        setItems((prev) =>
          prev.map((row) =>
            row.id === item.id ? { ...row, enabled: !row.enabled } : row,
          ),
        );
        onNotice(item.enabled ? t("serverProviders.disabledNotice") : t("serverProviders.enabledNotice"));
      } catch (err) {
        setRowError({
          id: item.id,
          text: err instanceof Error ? err.message : t("serverProviders.updateFailed"),
        });
      } finally {
        setRowBusy("");
      }
    },
    [onNotice],
  );

  return (
    <motion.section
      id="server-providers"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.05 }}
      className="glass scroll-mt-24 rounded-3xl p-5 shadow-glass"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Server size={15} className="text-indigo-500 dark:text-indigo-300" />
        <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
          {t("serverProviders.title")}
        </h2>
        <span className="chip-muted">{t("common.count", { count: items.length })}</span>
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => {
            setRowError(null);
            setForm({ ...EMPTY_FORM });
          }}
          disabled={!canManage}
          title={canManage ? "" : t("serverProviders.noManage")}
          className="btn btn-primary px-3 py-1.5 text-[11px]"
        >
          <Plus size={12} />
          {t("serverProviders.add")}
        </button>
      </div>

      <p className="mt-1.5 text-[10px] text-slate-400">
        {t("serverProviders.hint")}
      </p>

      {form ? (
        <div className="mt-3 rounded-2xl border border-indigo-400/25 bg-indigo-500/[0.04] p-3">
          <div className="flex items-center gap-2">
            <h3 className="text-[11.5px] font-semibold text-slate-800 dark:text-slate-100">
              {form.id ? t("serverProviders.edit") : t("serverProviders.add")}
            </h3>
            <span className="flex-1" />
            <button
              type="button"
              onClick={() => setForm(null)}
              className="text-slate-400 transition hover:text-slate-600"
              aria-label={t("common.cancel")}
            >
              <X size={13} />
            </button>
          </div>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                {t("common.name")}
              </span>
              <input
                value={form.name}
                onChange={(event) => patchForm({ name: event.target.value })}
                placeholder={t("serverProviders.namePlaceholder")}
                className="input"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                {t("common.type")}
              </span>
              <select
                value={form.kind}
                onChange={(event) => patchForm({ kind: event.target.value })}
                className="select"
              >
                {KINDS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                base_url
              </span>
              <input
                value={form.base_url}
                onChange={(event) => patchForm({ base_url: event.target.value })}
                placeholder="https://api.openai.com/v1"
                className="input"
              />
            </label>
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                {t("serverProviders.apiKey")}
              </span>
              <input
                type="password"
                value={form.api_key}
                onChange={(event) => patchForm({ api_key: event.target.value })}
                placeholder={t("serverProviders.apiKeyPlaceholder")}
                autoComplete="off"
                className="input"
              />
            </label>
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                {t("serverProviders.models")}
              </span>
              <textarea
                value={form.models}
                onChange={(event) => patchForm({ models: event.target.value })}
                rows={2}
                placeholder="gpt-4o-mini, gpt-4o"
                className="input"
              />
            </label>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1.5 text-[11px] text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(event) => patchForm({ is_default: event.target.checked })}
                className="h-3.5 w-3.5 accent-indigo-500"
              />
              {t("serverProviders.setDefault")}
            </label>
            <label className="flex items-center gap-1.5 text-[11px] text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) => patchForm({ enabled: event.target.checked })}
                className="h-3.5 w-3.5 accent-indigo-500"
              />
              {t("common.enable")}
            </label>
            <span className="flex-1" />
            <button
              type="button"
              onClick={() => void save()}
              disabled={busy || !canManage}
              className="btn btn-primary px-3 py-1.5 text-[11px]"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
              {t("common.save")}
            </button>
          </div>
          {rowError && rowError.id === (form.id || "new") ? (
            <p className="mt-2 flex items-start gap-1.5 rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[10.5px] text-rose-700 dark:text-rose-300">
              <AlertCircle size={12} className="mt-0.5 shrink-0" />
              <span className="flex-1 break-words">{rowError.text}</span>
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="mt-3 space-y-1.5">
        {loading ? (
          <p className="text-[11px] text-slate-400">{t("common.loading")}</p>
        ) : items.length === 0 ? (
          <p className="text-[11px] text-slate-400">{t("serverProviders.empty")}</p>
        ) : (
          items.map((item) => {
            const shown = (item.models ?? []).slice(0, 4);
            const rest = (item.models ?? []).length - shown.length;
            const test = rowTest[item.id];
            return (
              <div
                key={item.id}
                className="rounded-2xl border border-white/50 bg-white/50 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]"
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11.5px] font-semibold text-slate-800 dark:text-slate-100">
                    {item.name}
                  </span>
                  <span className="rounded-full bg-slate-500/10 px-1.5 py-0.5 text-[9.5px] text-slate-500 dark:text-slate-400">
                    {item.kind}
                  </span>
                  {item.is_default ? (
                    <span className="flex items-center gap-0.5 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-1.5 py-0.5 text-[9.5px] font-medium text-white">
                      <Star size={8} />
                      {t("common.default")}
                    </span>
                  ) : null}
                  {!item.enabled ? (
                    <span className="rounded-full bg-amber-400/15 px-1.5 py-0.5 text-[9.5px] text-amber-700 dark:text-amber-300">
                      {t("common.disabledTag")}
                    </span>
                  ) : null}
                  <span className="text-[10px] text-slate-400">
                    {item.has_key
                        ? t("myProviders.keyMaskedShort", {
                            masked: item.api_key_masked || t("serverProviders.keyConfigured"),
                          })
                        : t("serverProviders.keyNone")}
                  </span>
                  <span className="flex-1" />
                  <button
                    type="button"
                    onClick={() => {
                      setRowError(null);
                      setForm(toForm(item));
                    }}
                    disabled={!canManage}
                    title={canManage ? t("serverProviders.edit") : t("serverProviders.noManage")}
                    className="btn-quiet px-2 py-1 text-[10.5px]"
                  >
                    <Pencil size={11} />
                    {t("common.edit")}
                  </button>
                  <button
                    type="button"
                    onClick={() => void runTest(item)}
                    disabled={rowBusy === item.id}
                    className="btn-quiet px-2 py-1 text-[10.5px]"
                  >
                    {rowBusy === item.id ? (
                      <Loader2 size={11} className="animate-spin" />
                    ) : (
                      <Zap size={11} />
                    )}
                    {t("common.test")}
                  </button>
                  <button
                    type="button"
                    onClick={() => void remove(item.id)}
                    disabled={!canManage || item.is_default || rowBusy === item.id}
                    title={
                      !canManage
                        ? t("serverProviders.noManage")
                        : item.is_default
                          ? t("serverProviders.defaultUndeletable")
                          : t("serverProviders.delete")
                    }
                    className="btn-quiet px-2 py-1 text-[10.5px] text-rose-500"
                  >
                    <Trash2 size={11} />
                    {t("common.delete")}
                  </button>
                  <label className="flex items-center gap-1 text-[10px] text-slate-500 dark:text-slate-400">
                    <input
                      type="checkbox"
                      checked={item.enabled}
                      onChange={() => void toggleEnabled(item)}
                      disabled={!canManage}
                      className="h-3.5 w-3.5 accent-indigo-500"
                    />
                    {t("common.enable")}
                  </label>
                </div>
                {item.base_url ? (
                  <p className="mt-1 truncate font-mono text-[10px] text-slate-400">
                    {item.base_url}
                  </p>
                ) : null}
                <div className="mt-1 flex flex-wrap items-center gap-1">
                  {shown.length === 0 ? (
                    <span className="text-[10px] text-slate-400">{t("myProviders.disabledHint")}</span>
                  ) : (
                    shown.map((model) => (
                      <span
                        key={model}
                        className="rounded-full bg-indigo-500/10 px-1.5 py-0.5 font-mono text-[9.5px] text-indigo-600 dark:text-indigo-300"
                      >
                        {model}
                      </span>
                    ))
                  )}
                  {rest > 0 ? (
                    <span className="text-[9.5px] text-slate-400">+{rest}</span>
                  ) : null}
                </div>
                {test ? (
                  <p
                    className={clsx(
                      "mt-1.5 flex items-start gap-1.5 rounded-xl border px-2.5 py-1.5 text-[10px]",
                      test.ok
                        ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                        : "border-amber-400/30 bg-amber-400/10 text-amber-700 dark:text-amber-300",
                    )}
                  >
                    {test.ok ? (
                      <CheckCircle2 size={11} className="mt-0.5 shrink-0" />
                    ) : (
                      <AlertCircle size={11} className="mt-0.5 shrink-0" />
                    )}
                    <span className="flex-1 break-words">{test.text}</span>
                  </p>
                ) : null}
                {rowError && rowError.id === item.id ? (
                  <p className="mt-1.5 flex items-start gap-1.5 rounded-xl border border-rose-400/30 bg-rose-500/10 px-2.5 py-1.5 text-[10px] text-rose-700 dark:text-rose-300">
                    <AlertCircle size={11} className="mt-0.5 shrink-0" />
                    <span className="flex-1 break-words">{rowError.text}</span>
                  </p>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </motion.section>
  );
}
