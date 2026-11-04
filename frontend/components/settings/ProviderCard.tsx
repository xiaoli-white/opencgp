import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  Cpu,
  Eye,
  EyeOff,
  Loader2,
  RotateCcw,
  Save,
  Server,
  Zap,
} from "lucide-react";
import clsx from "clsx";
import { useI18n } from "@/i18n/I18nProvider";
import { api, type ProviderOption, type ProviderSettings } from "@/lib/api";

type Props = {
  canWrite: boolean;
  canManageServer: boolean;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
};

type FormState = {
  provider_id: string;
  model: string;
  api_key: string;
  temperature: string;
  max_tokens: string;
  extra_headers: string;
  extra_body: string;
  disable_reasoning: boolean;
};

function toForm(data: ProviderSettings): FormState {
  return {
    provider_id:
      data.active_provider_id ||
      data.provider_id ||
      data.server?.provider_id ||
      data.server?.id ||
      "",
    model: data.model || "",
    api_key: "",
    temperature: String(data.temperature ?? 0.7),
    max_tokens: String(data.max_tokens && data.max_tokens > 0 ? data.max_tokens : 2048),
    extra_headers: JSON.stringify(data.extra_headers ?? {}, null, 0),
    extra_body: JSON.stringify(data.extra_body ?? {}, null, 0),
    disable_reasoning:
      (data.extra_body as { thinking?: { type?: string } } | undefined)?.thinking?.type ===
      "disabled",
  };
}

type TFn = (path: string, vars?: Record<string, string | number>) => string;

function optionLabel(item: ProviderOption, t: TFn): string {
  const prefix = item.scope === "user" ? t("providers.prefixMine") : "";
  const star = item.is_default ? t("providers.dotDefault") : "";
  const off = item.enabled === false ? t("providers.dotDisabled") : "";
  const shared =
    item.scope === "shared"
      ? t("providers.sharedFrom", { name: item.owner_name || t("providers.other") })
      : "";
  return `${prefix}${item.name}（${item.kind}）${star}${off}${shared}`;
}

type PickerProps = {
  value: string;
  mine: ProviderOption[];
  server: ProviderOption[];
  shared: ProviderOption[];
  disabled: boolean;
  onChange: (id: string) => void;
};

function ProviderPicker({ value, mine, server, shared, disabled, onChange }: PickerProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const all = [...mine, ...server, ...shared];
  const current = all.find((item) => item.id === value);

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  const groups: { label: string; items: ProviderOption[] }[] = [
    { label: t("providers.groupMine"), items: mine },
    { label: t("providers.groupServer"), items: server },
    ...(shared.length > 0 ? [{ label: t("providers.groupShared"), items: shared }] : []),
  ];

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        disabled={disabled || all.length === 0}
        className="select flex w-full items-center gap-1 text-left disabled:opacity-60"
      >
        <span className="flex-1 truncate">
          {current ? optionLabel(current, t) : all.length === 0 ? t("providers.noChannels") : t("providers.selectChannel")}
        </span>
        <ChevronDown
          size={13}
          className={clsx("shrink-0 text-slate-400 transition", open && "rotate-180")}
        />
      </button>
      {open ? (
        <>
          <div
            className="fixed inset-0 z-20"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute left-0 right-0 z-30 mt-1 max-h-64 overflow-y-auto rounded-xl border border-white/60 bg-white/90 p-1 shadow-glass backdrop-blur-xl dark:border-white/10 dark:bg-[#131a2e]/95">
            {groups.map((group) => (
              <div key={group.label}>
                <p className="px-2 pb-0.5 pt-1.5 text-[9.5px] uppercase tracking-wide text-slate-400">
                  {group.label}
                  <span className="ml-1 normal-case">（{group.items.length}）</span>
                </p>
                {group.items.length === 0 ? (
                  <p className="px-2 pb-1 text-[10px] text-slate-400">{t("common.none")}</p>
                ) : (
                  group.items.map((item) => {
                    const active = item.id === value;
                    const off = item.enabled === false;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          onChange(item.id);
                          setOpen(false);
                        }}
                        className={clsx(
                          "flex w-full items-center gap-1 rounded-lg px-2 py-1.5 text-left text-[11px] transition",
                          active
                            ? "bg-gradient-to-r from-indigo-500 to-violet-500 text-white"
                            : "text-slate-700 hover:bg-indigo-500/10 dark:text-slate-200",
                          off && !active && "opacity-55",
                        )}
                      >
                        <span className="flex-1 truncate">{optionLabel(item, t)}</span>
                        {active ? <Check size={11} className="shrink-0" /> : null}
                      </button>
                    );
                  })
                )}
              </div>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}

export default function ProviderCard({
  canWrite,
  canManageServer,
  onNotice,
  onError,
}: Props) {
  const { t } = useI18n();
  const [data, setData] = useState<ProviderSettings | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [test, setTest] = useState<{ ok: boolean; text: string } | null>(null);
  const [showMine, setShowMine] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const next = await api.getProviderSettings();
      setData(next);
      setForm(toForm(next));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("providers.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const handler = () => void load();
    window.addEventListener("course-studio:providers-changed", handler);
    return () => window.removeEventListener("course-studio:providers-changed", handler);
  }, [load]);

  const providers: ProviderOption[] = useMemo(() => data?.providers ?? [], [data]);
  const mine = useMemo(
    () => providers.filter((item) => item.scope === "user"),
    [providers],
  );
  const serverList = useMemo(
    () => providers.filter((item) => item.scope === "server" || !item.scope),
    [providers],
  );
  const sharedList = useMemo(
    () => providers.filter((item) => item.scope === "shared"),
    [providers],
  );

  const activeProvider = useMemo(() => {
    if (!providers.length) return null;
    return providers.find((item) => item.id === form?.provider_id) ?? providers[0];
  }, [providers, form?.provider_id]);

  const modelOptions = activeProvider?.models ?? [];
  const useModelSelect = modelOptions.length > 0;

  const update = (patch: Partial<FormState>) =>
    setForm((prev) => (prev ? { ...prev, ...patch } : prev));

  const pickProvider = (providerId: string) => {
    const target = providers.find((item) => item.id === providerId);
    update({
      provider_id: providerId,
      model: target?.models?.[0] ?? "",
    });
  };

  const save = useCallback(async () => {
    if (!form) return null;
    setBusy(true);
    setTest(null);
    try {
      let parsedHeaders: Record<string, string> = {};
      let parsedBody: Record<string, unknown> = {};
      try {
        parsedHeaders = form.extra_headers.trim() ? JSON.parse(form.extra_headers) : {};
        parsedBody = form.extra_body.trim() ? JSON.parse(form.extra_body) : {};
      } catch {
        onError(t("providers.invalidJson"));
        setBusy(false);
        return null;
      }
      const payload = {
        provider_id: form.provider_id || undefined,
        model: form.model.trim(),
        api_key: form.api_key.trim(),
        temperature: Number(form.temperature) || 0,
        max_tokens: Math.max(1, Number(form.max_tokens) || 1),
        extra_headers: parsedHeaders,
        extra_body: parsedBody,
        disable_reasoning: form.disable_reasoning,
      };
      const next = await api.saveProviderSettings(payload);
      setData(next);
      setForm(toForm(next));
      onNotice(t("providers.saved"));
      return next;
    } catch (err) {
      onError(err instanceof Error ? err.message : t("providers.saveFailed"));
      return null;
    } finally {
      setBusy(false);
    }
  }, [form, onError, onNotice]);

  const runTest = useCallback(async () => {
    setTesting(true);
    setTest(null);
    try {
      const saved = await save();
      if (!saved) return;
      const result = await api.testProvider({ model: saved.model || undefined });
      setTest({
        ok: result.ok,
        text: result.ok
          ? t("providers.testOk", {
          latency: result.latency_ms,
          model: result.model || saved.model || t("providers.defaultModel"),
        })
          : result.detail || t("providers.testFail"),
      });
    } catch (err) {
      setTest({
        ok: false,
        text: err instanceof Error ? err.message : t("providers.testFailed"),
      });
    } finally {
      setTesting(false);
    }
  }, [save]);

  const reset = useCallback(async () => {
    setBusy(true);
    setTest(null);
    try {
      const next = await api.resetProviderSettings();
      setData(next);
      setForm(toForm(next));
      onNotice(t("providers.restored"));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("providers.restoreFailed"));
    } finally {
      setBusy(false);
    }
  }, [onError, onNotice]);

  const isUser = data?.source === "user";
  const server = data?.server;
  const keyPlaceholder =
    data?.has_key && data.api_key_masked
        ? t("providers.apiKeyPlaceholderMasked", { masked: data.api_key_masked })
      : activeProvider?.has_key
        ? t("providers.apiKeyPlaceholder")
        : "sk-...";
  const disabled = !canWrite || busy || loading || !form;
  const summary = `${data?.provider_name || activeProvider?.name || t("providers.serverDefault")} · ${data?.model || t("providers.defaultModel")}`;

  const jumpTo = (id: string) => {
    const target = document.getElementById(id);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const toggleMine = () => {
    setShowMine((prev) => {
      const next = !prev;
      if (next) setTimeout(() => jumpTo("my-providers"), 60);
      return next;
    });
  };

  return (
    <motion.section
      id="my-model"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.04 }}
      className="glass scroll-mt-24 rounded-3xl p-5 shadow-glass"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Cpu size={15} className="text-indigo-500 dark:text-indigo-300" />
        <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
          {t("providers.title")}
        </h2>
        <span
          className={clsx(
            "rounded-full px-2 py-0.5 text-[10px] font-medium",
            isUser
              ? "bg-gradient-to-r from-indigo-500 to-violet-500 text-white"
              : "bg-indigo-500/12 text-indigo-600 dark:text-indigo-300",
          )}
        >
          {isUser ? t("providers.usingMine") : t("providers.serverDefault")}
        </span>
        <span className="text-[10px] text-slate-400">
          <Server size={10} className="mr-1 inline align-[-1px]" />
          {summary} · {data?.has_key ? t("providers.personalKey") : t("providers.channelKey")}
        </span>
      </div>

      {!canWrite ? (
        <p className="mt-2 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[10.5px] text-amber-700 dark:text-amber-300">
          {t("providers.readOnlyHint")}
        </p>
      ) : null}

      {loading || !form ? (
        <p className="mt-3 text-[11px] text-slate-400">{t("common.loading")}</p>
      ) : (
        <>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div className="block">
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                {t("providers.channel")}
              </span>
              <ProviderPicker
                value={form.provider_id}
                mine={mine}
                server={serverList}
                shared={sharedList}
                disabled={disabled}
                onChange={pickProvider}
              />
              <span className="mt-1 block text-[10px] text-slate-400">
                {t("providers.channelCounts", { mine: mine.length, server: serverList.length })}
                {sharedList.length > 0
                  ? t("providers.sharedSuffix", { count: sharedList.length })
                  : ""}
              </span>
            </div>
            <label className="block">
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                {t("providers.model")}
              </span>
              {useModelSelect ? (
                <select
                  value={form.model}
                  onChange={(event) => update({ model: event.target.value })}
                  disabled={disabled}
                  className="select"
                >
                  {form.model && !modelOptions.includes(form.model) ? (
                    <option value={form.model}>
                      {form.model}
                      {t("providers.customModelSuffix")}
                    </option>
                  ) : null}
                  {modelOptions.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  value={form.model}
                  onChange={(event) => update({ model: event.target.value })}
                  placeholder={server?.model || t("providers.modelPlaceholder")}
                  disabled={disabled}
                  className="input"
                />
              )}
            </label>
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                {t("providers.apiKeyOverride")}
              </span>
              <span className="relative block">
                <input
                  type={showKey ? "text" : "password"}
                  value={form.api_key}
                  onChange={(event) => update({ api_key: event.target.value })}
                  placeholder={keyPlaceholder}
                  disabled={disabled}
                  autoComplete="off"
                  className="input pr-9"
                />
                <button
                  type="button"
                  onClick={() => setShowKey((prev) => !prev)}
                  className="absolute right-1 top-1/2 grid h-10 w-10 -translate-y-1/2 place-items-center rounded-lg text-slate-400 transition hover:text-indigo-500"
                  aria-label={showKey ? t("myProviders.hideKey") : t("myProviders.showKey")}
                >
                  {showKey ? <EyeOff size={13} /> : <Eye size={13} />}
                </button>
              </span>
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                {t("providers.temperature")}
              </span>
              <input
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={form.temperature}
                onChange={(event) => update({ temperature: event.target.value })}
                disabled={disabled}
                className="input"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                {t("providers.maxTokens")}
              </span>
              <input
                type="number"
                min={1}
                step={1}
                value={form.max_tokens}
                onChange={(event) => update({ max_tokens: event.target.value })}
                disabled={disabled}
                className="input"
              />
            </label>
          </div>

          <div className="mt-4 rounded-2xl border border-slate-200/70 bg-white/50 p-3 dark:border-white/10 dark:bg-white/[0.03]">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                {t("providers.advancedParams")}
              </span>
              <label className="flex items-center gap-1.5 text-[11px] text-slate-600 dark:text-slate-300">
                <input
                  type="checkbox"
                  checked={form.disable_reasoning}
                  onChange={(event) => update({ disable_reasoning: event.target.checked })}
                  disabled={disabled}
                />
                {t("providers.disableThinking")}
              </label>
            </div>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1 block text-[10px] uppercase tracking-[0.14em] text-slate-400">
                  {t("providers.headersJson")}
                </span>
                <textarea
                  rows={3}
                  value={form.extra_headers}
                  onChange={(event) => update({ extra_headers: event.target.value })}
                  disabled={disabled}
                  placeholder='{"X-Custom": "1"}'
                  className="input font-mono text-[11px]"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-[10px] uppercase tracking-[0.14em] text-slate-400">
                  {t("providers.bodyJson")}
                </span>
                <textarea
                  rows={3}
                  value={form.extra_body}
                  onChange={(event) => update({ extra_body: event.target.value })}
                  disabled={disabled}
                  placeholder='{"reasoning_effort": "none"}'
                  className="input font-mono text-[11px]"
                />
              </label>
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-slate-400">
                {t("providers.paramsHint")}
            </p>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void save()}
              disabled={disabled}
              title={canWrite ? "" : t("common.readOnlyRole")}
              className="btn btn-primary px-3 py-1.5 text-[11px]"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
              {t("providers.save")}
            </button>
            <button
              type="button"
              onClick={() => void runTest()}
              disabled={disabled || testing}
              title={canWrite ? t("providers.testTitle") : t("common.readOnlyRole")}
              className="btn btn-ghost px-3 py-1.5 text-[11px]"
            >
              {testing ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
              {t("providers.test")}
            </button>
            <button
              type="button"
              onClick={() => void reset()}
              disabled={disabled || !isUser}
              title={
                !canWrite
                  ? t("common.readOnlyRole")
                  : isUser
                    ? t("providers.restoreTitle")
                    : t("providers.restoreDisabledTitle")
              }
              className="btn-quiet px-2.5 py-1.5 text-[11px]"
            >
              <RotateCcw size={12} />
              {t("providers.restore")}
            </button>
            <button
              type="button"
              onClick={toggleMine}
              className="btn-quiet px-2.5 py-1.5 text-[11px]"
            >
              {t("providers.manageMine")}
              <ChevronDown
                size={12}
                className={clsx("transition", showMine && "rotate-180")}
              />
            </button>
            {canManageServer ? (
              <Link
                to="/settings/server"
                className="text-[10.5px] text-indigo-500 underline-offset-2 transition hover:underline dark:text-indigo-300"
              >
                {t("providers.gotoServer")}
                <ArrowRight size={10} className="ml-1 inline align-[-1px]" />
              </Link>
            ) : null}
            <span className="text-[10px] text-slate-400">
              {t("providers.testHint")}
            </span>
          </div>

          {test ? (
            <p
              className={clsx(
                "mt-2 flex items-start gap-1.5 rounded-xl border px-3 py-2 text-[10.5px]",
                test.ok
                  ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                  : "border-amber-400/30 bg-amber-400/10 text-amber-700 dark:text-amber-300",
              )}
            >
              {test.ok ? (
                <CheckCircle2 size={12} className="mt-0.5 shrink-0" />
              ) : (
                <AlertCircle size={12} className="mt-0.5 shrink-0" />
              )}
              <span className="flex-1 break-words">{test.text}</span>
            </p>
          ) : null}
        </>
      )}

      <p className="mt-3 text-[10px] text-slate-400">
        {t("providers.keyEncrypted")}
      </p>
    </motion.section>
  );
}
