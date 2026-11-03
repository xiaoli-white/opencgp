import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Pencil,
  Plus,
  Save,
  Share2,
  Star,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import clsx from "clsx";
import { api, type ServerProviderPayload, type UserProvider } from "@/lib/api";
import { useSession } from "@/components/auth/SessionProvider";
import SharePanel, { type ShareMember } from "@/components/sharing/SharePanel";

type Props = {
  canWrite: boolean;
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

function toForm(item: UserProvider): FormState {
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

function notifyChanged() {
  window.dispatchEvent(new CustomEvent("course-studio:providers-changed"));
}

export default function MyProvidersCard({ canWrite, onNotice, onError }: Props) {
  const [items, setItems] = useState<UserProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<FormState | null>(null);
  const [busy, setBusy] = useState(false);
  const [rowBusy, setRowBusy] = useState("");
  const [rowError, setRowError] = useState<{ id: string; text: string } | null>(null);
  const [rowTest, setRowTest] = useState<Record<string, { ok: boolean; text: string }>>({});
  const [showKey, setShowKey] = useState(false);

  const { tenant } = useSession();
  const [shareItem, setShareItem] = useState<UserProvider | null>(null);
  const [shareMembers, setShareMembers] = useState<ShareMember[]>([]);
  const [shareLevels, setShareLevels] = useState<Record<string, string | null>>({});
  const [shareLoading, setShareLoading] = useState(false);
  const [shareSaving, setShareSaving] = useState(false);
  const [shareError, setShareError] = useState("");

  const openShare = useCallback(
    async (item: UserProvider) => {
      setShareItem(item);
      setShareLoading(true);
      setShareError("");
      try {
        const [memberList, shareList] = await Promise.all([
          tenant ? api.listMembers(tenant) : Promise.resolve({ count: 0, members: [] }),
          api.getProviderShares(item.id),
        ]);
        setShareMembers(
          (memberList.members ?? []).map((member) => ({
            user_id: member.user_id,
            user_email: member.user_email,
            user_display_name: member.user_display_name,
            avatar_url: member.avatar_url,
            note: "空间成员",
          })),
        );
        const next: Record<string, string | null> = {};
        for (const member of memberList.members ?? []) next[member.user_id] = null;
        for (const share of shareList.shares ?? []) {
          next[share.user_id] = share.level === "manage" ? "manage" : "use";
        }
        setShareLevels(next);
      } catch (err) {
        setShareError(err instanceof Error ? err.message : "共享信息加载失败");
      } finally {
        setShareLoading(false);
      }
    },
    [tenant],
  );

  const saveShare = useCallback(
    async (entries: { user_id: string; level: string }[]) => {
      if (!shareItem) return;
      setShareSaving(true);
      setShareError("");
      try {
        await api.saveProviderShares(shareItem.id, entries);
        onNotice("通道共享已保存");
        setShareItem(null);
        notifyChanged();
      } catch (err) {
        setShareError(err instanceof Error ? err.message : "保存失败");
      } finally {
        setShareSaving(false);
      }
    },
    [onNotice, shareItem],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listMyProviders();
      setItems(data.providers ?? []);
    } catch (err) {
      onError(err instanceof Error ? err.message : "我的通道加载失败");
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
      setRowError({ id: form.id || "new", text: "通道名称不能为空" });
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
        await api.updateMyProvider(form.id, payload);
        onNotice("我的通道已更新");
      } else {
        await api.createMyProvider(payload);
        onNotice("我的通道已创建");
      }
      setForm(null);
      setShowKey(false);
      await load();
      notifyChanged();
    } catch (err) {
      setRowError({
        id: form.id || "new",
        text: err instanceof Error ? err.message : "保存失败",
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
        await api.deleteMyProvider(id);
        onNotice("我的通道已删除");
        if (form?.id === id) setForm(null);
        await load();
        notifyChanged();
      } catch (err) {
        setRowError({ id, text: err instanceof Error ? err.message : "删除失败" });
      } finally {
        setRowBusy("");
      }
    },
    [form?.id, load, onNotice],
  );

  const runTest = useCallback(async (item: UserProvider) => {
    setRowBusy(item.id);
    setRowTest((prev) => {
      const next = { ...prev };
      delete next[item.id];
      return next;
    });
    try {
      const result = await api.testMyProvider(item.id, { model: item.models?.[0] });
      setRowTest((prev) => ({
        ...prev,
        [item.id]: {
          ok: result.ok,
          text: result.ok
            ? `连接正常 · ${result.latency_ms}ms · ${result.model || item.models?.[0] || "默认模型"}`
            : result.detail || "连接失败",
        },
      }));
    } catch (err) {
      setRowTest((prev) => ({
        ...prev,
        [item.id]: {
          ok: false,
          text: err instanceof Error ? err.message : "测试失败",
        },
      }));
    } finally {
      setRowBusy("");
    }
  }, []);

  const toggleEnabled = useCallback(
    async (item: UserProvider) => {
      setRowBusy(item.id);
      setRowError(null);
      try {
        await api.updateMyProvider(item.id, { enabled: !item.enabled });
        setItems((prev) =>
          prev.map((row) => (row.id === item.id ? { ...row, enabled: !row.enabled } : row)),
        );
        notifyChanged();
        onNotice(item.enabled ? "通道已停用" : "通道已启用");
      } catch (err) {
        setRowError({ id: item.id, text: err instanceof Error ? err.message : "更新失败" });
      } finally {
        setRowBusy("");
      }
    },
    [onNotice],
  );

  return (
    <motion.section
      id="my-providers"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.045 }}
      className="glass scroll-mt-24 rounded-3xl p-5 shadow-glass"
    >
      <div className="flex flex-wrap items-center gap-2">
        <KeyRound size={15} className="text-indigo-500 dark:text-indigo-300" />
        <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
          我的模型通道
        </h2>
        <span className="chip-muted">{items.length} 个</span>
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => {
            setRowError(null);
            setShowKey(false);
            setForm({ ...EMPTY_FORM });
          }}
          disabled={!canWrite}
          title={canWrite ? "" : "当前角色只读"}
          className="btn btn-primary px-3 py-1.5 text-[11px]"
        >
          <Plus size={12} />
          新增通道
        </button>
      </div>

      <p className="mt-1.5 text-[10px] text-slate-400">
        个人通道仅你自己可见，可与服务器通道一起在「我的模型」里切换；未指定时使用服务器默认。
      </p>

      {!canWrite ? (
        <p className="mt-2 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[10.5px] text-amber-700 dark:text-amber-300">
          当前角色只读，我的通道仅可查看。
        </p>
      ) : null}

      {form ? (
        <div className="mt-3 rounded-2xl border border-indigo-400/25 bg-indigo-500/[0.04] p-3">
          <div className="flex items-center gap-2">
            <h3 className="text-[11.5px] font-semibold text-slate-800 dark:text-slate-100">
              {form.id ? "编辑我的通道" : "新增我的通道"}
            </h3>
            <span className="flex-1" />
            <button
              type="button"
              onClick={() => setForm(null)}
              className="text-slate-400 transition hover:text-slate-600"
              aria-label="取消"
            >
              <X size={13} />
            </button>
          </div>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                名称
              </span>
              <input
                value={form.name}
                onChange={(event) => patchForm({ name: event.target.value })}
                placeholder="例如 本地 Ollama"
                className="input"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                类型 kind
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
                placeholder="http://127.0.0.1:11434/v1"
                className="input"
              />
            </label>
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                API Key（留空沿用旧值）
              </span>
              <span className="relative block">
                <input
                  type={showKey ? "text" : "password"}
                  value={form.api_key}
                  onChange={(event) => patchForm({ api_key: event.target.value })}
                  placeholder={
                    form.id && items.find((row) => row.id === form.id)?.has_key
                      ? `${items.find((row) => row.id === form.id)?.api_key_masked || "已配置"}（留空沿用）`
                      : "sk-..."
                  }
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
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-[10.5px] text-slate-500 dark:text-slate-400">
                模型列表（逗号或换行分隔）
              </span>
              <textarea
                value={form.models}
                onChange={(event) => patchForm({ models: event.target.value })}
                rows={2}
                placeholder="qwen2.5, llama3"
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
              设为默认通道
            </label>
            <label className="flex items-center gap-1.5 text-[11px] text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) => patchForm({ enabled: event.target.checked })}
                className="h-3.5 w-3.5 accent-indigo-500"
              />
              启用
            </label>
            <span className="flex-1" />
            <button
              type="button"
              onClick={() => void save()}
              disabled={busy || !canWrite}
              className="btn btn-primary px-3 py-1.5 text-[11px]"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
              保存
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
          <p className="text-[11px] text-slate-400">加载中…</p>
        ) : items.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-white/60 bg-white/40 px-3 py-3 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-400">
            你还没有个人通道，可新增；也可直接使用服务器通道。
          </p>
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
                      默认
                    </span>
                  ) : null}
                  {!item.enabled ? (
                    <span className="rounded-full bg-amber-400/15 px-1.5 py-0.5 text-[9.5px] text-amber-700 dark:text-amber-300">
                      已停用
                    </span>
                  ) : null}
                  <span className="text-[10px] text-slate-400">
                    {item.has_key ? `密钥 ${item.api_key_masked || "已配置"}` : "无密钥"}
                  </span>
                  <span className="flex-1" />
                  <button
                    type="button"
                    onClick={() => {
                      setRowError(null);
                      setShowKey(false);
                      setForm(toForm(item));
                    }}
                    disabled={!canWrite}
                    title={canWrite ? "编辑通道" : "当前角色只读"}
                    className="btn-quiet px-2 py-1 text-[10.5px]"
                  >
                    <Pencil size={11} />
                    编辑
                  </button>
                  <button
                    type="button"
                    onClick={() => void openShare(item)}
                    className="btn-quiet px-2 py-1 text-[10.5px]"
                    title="共享给空间成员"
                  >
                    <Share2 size={11} />
                    共享
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
                    测试
                  </button>
                  <button
                    type="button"
                    onClick={() => void remove(item.id)}
                    disabled={!canWrite || rowBusy === item.id}
                    title={canWrite ? "删除通道" : "当前角色只读"}
                    className="btn-quiet px-2 py-1 text-[10.5px] text-rose-500"
                  >
                    <Trash2 size={11} />
                    删除
                  </button>
                  <label className="flex items-center gap-1 text-[10px] text-slate-500 dark:text-slate-400">
                    <input
                      type="checkbox"
                      checked={item.enabled}
                      onChange={() => void toggleEnabled(item)}
                      disabled={!canWrite}
                      className="h-3.5 w-3.5 accent-indigo-500"
                    />
                    启用
                  </label>
                </div>
                {item.base_url ? (
                  <p className="mt-1 truncate font-mono text-[10px] text-slate-400">
                    {item.base_url}
                  </p>
                ) : null}
                <div className="mt-1 flex flex-wrap items-center gap-1">
                  {shown.length === 0 ? (
                    <span className="text-[10px] text-slate-400">未登记模型，使用自定义输入</span>
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
                  {rest > 0 ? <span className="text-[9.5px] text-slate-400">+{rest}</span> : null}
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

      <SharePanel
        open={Boolean(shareItem)}
        title="共享我的通道"
        subtitle={shareItem?.name}
        note="被共享的成员可在「我的模型」里看到该通道；「可管理」还会允许其修改通道配置与共享。"
        members={shareMembers}
        value={shareLevels}
        options={[
          { value: "use", label: "可使用", desc: "可用该通道与模型" },
          { value: "manage", label: "可管理", desc: "还可修改通道配置" },
        ]}
        loading={shareLoading}
        saving={shareSaving}
        error={shareError}
        onClose={() => setShareItem(null)}
        onChange={(userId, level) =>
          setShareLevels((prev) => ({ ...prev, [userId]: level }))
        }
        onSave={saveShare}
      />
    </motion.section>
  );
}
