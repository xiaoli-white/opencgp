import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
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
import { api, type ProviderSettings } from "@/lib/api";

type Props = {
  canWrite: boolean;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
};

type FormState = {
  backend: string;
  base_url: string;
  model: string;
  api_key: string;
  temperature: string;
  max_tokens: string;
};

const BACKENDS = [
  { value: "openai_compat", label: "openai_compat" },
  { value: "dummy", label: "dummy" },
];

function toForm(data: ProviderSettings): FormState {
  return {
    backend: data.backend || "openai_compat",
    base_url: data.base_url || "",
    model: data.model || "",
    api_key: "",
    temperature: String(data.temperature ?? 0.7),
    max_tokens: String(data.max_tokens && data.max_tokens > 0 ? data.max_tokens : 2048),
  };
}

export default function ProviderCard({ canWrite, onNotice, onError }: Props) {
  const [data, setData] = useState<ProviderSettings | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [test, setTest] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const next = await api.getProviderSettings();
      setData(next);
      setForm(toForm(next));
    } catch (err) {
      onError(err instanceof Error ? err.message : "模型服务配置加载失败");
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => {
    void load();
  }, [load]);

  const update = (patch: Partial<FormState>) =>
    setForm((prev) => (prev ? { ...prev, ...patch } : prev));

  const save = useCallback(async () => {
    if (!form) return null;
    setBusy(true);
    setTest(null);
    try {
      const payload = {
        backend: form.backend,
        base_url: form.base_url.trim(),
        model: form.model.trim(),
        api_key: form.api_key.trim(),
        temperature: Number(form.temperature) || 0,
        max_tokens: Math.max(1, Number(form.max_tokens) || 1),
      };
      const next = await api.saveProviderSettings(payload);
      setData(next);
      setForm(toForm(next));
      onNotice("模型服务配置已保存");
      return next;
    } catch (err) {
      onError(err instanceof Error ? err.message : "保存失败");
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
      const result = await api.testProvider();
      setTest({
        ok: result.ok,
        text: result.ok
          ? `连接正常 · ${result.latency_ms}ms · ${result.model || saved.model}`
          : result.detail || "连接失败",
      });
    } catch (err) {
      setTest({
        ok: false,
        text: err instanceof Error ? err.message : "测试失败",
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
      onNotice("已恢复服务器默认模型服务");
    } catch (err) {
      onError(err instanceof Error ? err.message : "恢复失败");
    } finally {
      setBusy(false);
    }
  }, [onError, onNotice]);

  const isUser = data?.source === "user";
  const server = data?.server;
  const keyPlaceholder =
    data?.has_key && data.api_key_masked
      ? `${data.api_key_masked}（留空沿用）`
      : "sk-...";
  const disabled = !canWrite || busy || loading || !form;

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.04 }}
      className="glass rounded-3xl p-5 shadow-glass"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Cpu size={15} className="text-indigo-500 dark:text-indigo-300" />
        <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
          模型服务
        </h2>
        <span
          className={clsx(
            "rounded-full px-2 py-0.5 text-[10px] font-medium",
            isUser
              ? "bg-gradient-to-r from-indigo-500 to-violet-500 text-white"
              : "bg-indigo-500/12 text-indigo-600 dark:text-indigo-300",
          )}
        >
          {isUser ? "使用我的配置" : "服务器默认"}
        </span>
        {server ? (
          <span className="text-[10px] text-slate-400">
            <Server size={10} className="mr-1 inline align-[-1px]" />
            {server.backend} · {server.model || "未设置"} ·{" "}
            {server.has_key ? "已配置密钥" : "无密钥"}
          </span>
        ) : null}
      </div>

      {!canWrite ? (
        <p className="mt-2 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[10.5px] text-amber-700 dark:text-amber-300">
          当前角色只读，模型服务配置仅可查看。
        </p>
      ) : null}

      {loading || !form ? (
        <p className="mt-3 text-[11px] text-slate-400">加载中…</p>
      ) : (
        <>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                接口协议
              </span>
              <select
                value={form.backend}
                onChange={(event) => update({ backend: event.target.value })}
                disabled={disabled}
                className="select"
              >
                {BACKENDS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                模型名称
              </span>
              <input
                value={form.model}
                onChange={(event) => update({ model: event.target.value })}
                placeholder={server?.model || "gpt-4o-mini"}
                disabled={disabled}
                className="input"
              />
            </label>
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                接口地址 Base URL
              </span>
              <input
                value={form.base_url}
                onChange={(event) => update({ base_url: event.target.value })}
                placeholder={server?.base_url || "https://api.openai.com/v1"}
                disabled={disabled}
                className="input"
              />
            </label>
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                API Key
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
                  aria-label={showKey ? "隐藏密钥" : "显示密钥"}
                >
                  {showKey ? <EyeOff size={13} /> : <Eye size={13} />}
                </button>
              </span>
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                温度 temperature（0-2）
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
                最大 token 数 max_tokens
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

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void save()}
              disabled={disabled}
              title={canWrite ? "" : "当前角色只读"}
              className="btn btn-primary px-3 py-1.5 text-[11px]"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
              保存
            </button>
            <button
              type="button"
              onClick={() => void runTest()}
              disabled={disabled || testing}
              title={canWrite ? "先保存当前表单，再用已保存配置发起测试" : "当前角色只读"}
              className="btn btn-ghost px-3 py-1.5 text-[11px]"
            >
              {testing ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
              测试连接
            </button>
            <button
              type="button"
              onClick={() => void reset()}
              disabled={disabled || !isUser}
              title={
                !canWrite
                  ? "当前角色只读"
                  : isUser
                    ? "删除我的配置，回退到服务器默认"
                    : "当前已使用服务器默认"
              }
              className="btn-quiet px-2.5 py-1.5 text-[11px]"
            >
              <RotateCcw size={12} />
              恢复服务器默认
            </button>
            <span className="text-[10px] text-slate-400">
              测试连接会先保存当前表单再校验
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
        密钥仅加密存储在服务端，接口只返回掩码，不会返回明文。
      </p>
    </motion.section>
  );
}
