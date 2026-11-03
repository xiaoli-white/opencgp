import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertCircle,
  KeyRound,
  Loader2,
  Pencil,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import clsx from "clsx";
import {
  api,
  type Member,
  type Quota,
  type QuotaUsage,
  type RoleRecord,
  type RoleScope,
} from "@/lib/api";
import { useSession } from "@/components/auth/SessionProvider";
import SettingsBreadcrumb from "@/components/settings/SettingsBreadcrumb";
import type { RoleAction } from "@/lib/session";

const ACTIONS: { value: RoleAction; label: string }[] = [
  { value: "read", label: "读取" },
  { value: "write", label: "写作" },
  { value: "review", label: "审核" },
  { value: "manage_members", label: "成员管理" },
  { value: "manage_quota", label: "配额管理" },
  { value: "manage_server", label: "服务器管理" },
];

const ACTION_LABEL: Record<string, string> = {
  read: "读取",
  write: "写作",
  review: "审核",
  manage_members: "成员管理",
  manage_quota: "配额管理",
  manage_server: "服务器管理",
};

function formatBytes(value: number): string {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

type RoleForm = {
  id: string;
  name: string;
  actions: RoleAction[];
  scope: RoleScope;
  builtin: boolean;
};

const EMPTY_FORM: RoleForm = {
  id: "",
  name: "",
  actions: ["read"],
  scope: "all",
  builtin: false,
};

export default function WorkspaceSettingsPage() {
  const { tenant, role, roleName, can, refresh } = useSession();
  const canManage = can("manage_members");
  const canQuota = can("manage_quota");

  const [members, setMembers] = useState<Member[]>([]);
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [roleBusy, setRoleBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState<string>("editor");
  const [form, setForm] = useState<RoleForm | null>(null);
  const [limits, setLimits] = useState<QuotaUsage>({
    monthly_generations: 0,
    monthly_uploads: 0,
    storage_bytes: 0,
  });
  const [unlimited, setUnlimited] = useState({
    generations: false,
    uploads: false,
    storage: false,
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const roleData = await api.listRoles();
      setRoles(roleData.roles ?? []);
      if (roleData.roles?.length) {
        setNewRole((prev) =>
          roleData.roles.some((item) => item.key === prev)
            ? prev
            : roleData.roles[roleData.roles.length - 1].key,
        );
      }
      if (tenant) {
        const data = await api.listMembers(tenant);
        setMembers(data.members);
      }
      const q = await api.getQuota();
      setQuota(q);
      setLimits(q.limits);
      setUnlimited({
        generations: Boolean(q.unlimited?.generations) || (q.limits?.monthly_generations ?? 1) <= 0,
        uploads: Boolean(q.unlimited?.uploads) || (q.limits?.monthly_uploads ?? 1) <= 0,
        storage: Boolean(q.unlimited?.storage) || (q.limits?.storage_bytes ?? 1) <= 0,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [tenant]);

  useEffect(() => {
    void load();
  }, [load]);

  const roleOptions = useMemo(
    () => roles.map((item) => ({ value: item.key, label: item.name })),
    [roles],
  );

  const addMember = useCallback(async () => {
    if (!tenant || !email.trim()) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.addMember(tenant, {
        email: email.trim(),
        role: newRole as Member["role"],
      });
      setEmail("");
      setNotice("成员已添加");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "添加失败");
    } finally {
      setBusy(false);
    }
  }, [tenant, email, newRole, load]);

  const changeRole = useCallback(
    async (userId: string, next: string) => {
      if (!tenant) return;
      setError("");
      try {
        await api.updateMemberRole(tenant, userId, next as Member["role"]);
        setMembers((prev) =>
          prev.map((item) =>
            item.user_id === userId ? { ...item, role: next as Member["role"] } : item,
          ),
        );
        setNotice("角色已更新");
        await refresh();
        await load();
      } catch (err) {
        setError(err instanceof Error ? err.message : "更新失败");
      }
    },
    [tenant, refresh, load],
  );

  const removeMember = useCallback(
    async (userId: string) => {
      if (!tenant) return;
      setError("");
      try {
        await api.removeMember(tenant, userId);
        setMembers((prev) => prev.filter((item) => item.user_id !== userId));
        setNotice("成员已移除");
      } catch (err) {
        setError(err instanceof Error ? err.message : "移除失败");
      }
    },
    [tenant],
  );

  const saveRole = useCallback(async () => {
    if (!form) return;
    setRoleBusy(true);
    setError("");
    setNotice("");
    try {
      if (form.id) {
        await api.updateRole(form.id, {
          name: form.name.trim(),
          scope: form.scope,
          ...(form.builtin ? {} : { actions: form.actions }),
        });
        setNotice("角色已更新");
      } else {
        await api.createRole({
          name: form.name.trim(),
          actions: form.actions,
          scope: form.scope,
        });
        setNotice("角色已创建");
      }
      setForm(null);
      await load();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setRoleBusy(false);
    }
  }, [form, load, refresh]);

  const deleteRole = useCallback(
    async (roleId: string) => {
      setError("");
      setNotice("");
      try {
        await api.deleteRole(roleId);
        setNotice("角色已删除");
        await load();
      } catch (err) {
        setError(err instanceof Error ? err.message : "删除失败");
      }
    },
    [load],
  );

  const saveQuota = useCallback(async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload: QuotaUsage = {
        monthly_generations: unlimited.generations ? 0 : limits.monthly_generations,
        monthly_uploads: unlimited.uploads ? 0 : limits.monthly_uploads,
        storage_bytes: unlimited.storage ? 0 : limits.storage_bytes,
      };
      const next = await api.updateQuota(payload);
      setQuota(next);
      setLimits(next.limits);
      setUnlimited({
        generations: Boolean(next.unlimited?.generations) || (next.limits?.monthly_generations ?? 1) <= 0,
        uploads: Boolean(next.unlimited?.uploads) || (next.limits?.monthly_uploads ?? 1) <= 0,
        storage: Boolean(next.unlimited?.storage) || (next.limits?.storage_bytes ?? 1) <= 0,
      });
      setNotice("用量与配额已更新");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }, [limits, unlimited]);

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4">
      <SettingsBreadcrumb current="空间设置" />

      {!canManage ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-2.5 text-[11px] text-amber-700 dark:text-amber-300">
          你以 {roleName || "只读"} 身份访问，仅可读取，成员与配额信息可查看不可修改。
        </div>
      ) : null}

      {error ? (
        <div className="flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-2.5 text-[11px] text-rose-700 dark:text-rose-300">
          <AlertCircle size={13} className="mt-0.5 shrink-0" />
          <span className="flex-1">{error}</span>
          <button
            type="button"
            onClick={() => setError("")}
            className="text-rose-400 transition hover:text-rose-600"
            aria-label="关闭"
          >
            <X size={12} />
          </button>
        </div>
      ) : null}
      {notice ? (
        <div className="rounded-2xl border border-emerald-400/30 bg-emerald-500/10 px-4 py-2.5 text-[11px] text-emerald-700 dark:text-emerald-300">
          {notice}
        </div>
      ) : null}

      <motion.section
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.06 }}
        className="glass rounded-3xl p-5 shadow-glass"
      >
        <div className="flex flex-wrap items-center gap-2">
          <KeyRound size={15} className="text-indigo-500 dark:text-indigo-300" />
          <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
            角色
          </h2>
          <span className="chip-muted">{roles.length} 个</span>
          <span className="flex-1" />
          <button
            type="button"
            onClick={() => setForm({ ...EMPTY_FORM })}
            disabled={!canManage}
            title={canManage ? "" : "当前角色无权管理成员"}
            className="btn btn-primary px-3 py-1.5 text-[11px]"
          >
            <Plus size={12} />
            新建角色
          </button>
        </div>

        <div className="mt-3 space-y-1.5">
          {loading ? (
            <p className="text-[11px] text-slate-400">加载中…</p>
          ) : (
            roles.map((item) => (
              <div
                key={item.id}
                className="rounded-2xl border border-white/50 bg-white/45 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
                    {item.name}
                  </span>
                  <span className="chip-muted">{item.key}</span>
                  {item.builtin ? <span className="chip">内置</span> : null}
                  <span
                    className={clsx(
                      "rounded-full px-2 py-0.5 text-[10px] font-medium",
                      item.scope === "assigned"
                        ? "bg-violet-500/12 text-violet-600 dark:text-violet-300"
                        : "bg-indigo-500/12 text-indigo-600 dark:text-indigo-300",
                    )}
                  >
                    {item.scope === "assigned" ? "指定课程" : "全部课程"}
                  </span>
                  <span className="text-[10px] text-slate-400">
                    {item.member_count} 人
                  </span>
                  <span className="flex-1" />
                  <button
                    type="button"
                    onClick={() =>
                      setForm({
                        id: item.id,
                        name: item.name,
                        actions: [...item.actions],
                        scope: item.scope,
                        builtin: Boolean(item.builtin),
                      })
                    }
                    disabled={!canManage}
                    title={canManage ? "编辑角色" : "当前角色无权管理成员"}
                    className="btn-quiet px-1.5"
                  >
                    <Pencil size={12} />
                  </button>
                  <button
                    type="button"
                    onClick={() => void deleteRole(item.id)}
                    disabled={!canManage || Boolean(item.builtin)}
                    title={item.builtin ? "内置角色不可删除" : "删除角色"}
                    className="btn-quiet px-1.5"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {item.actions.length === 0 ? (
                    <span className="text-[10px] text-slate-400">无权限点</span>
                  ) : (
                    item.actions.map((action) => (
                      <span
                        key={action}
                        className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] text-slate-600 ring-1 ring-slate-200/70 dark:bg-white/[0.06] dark:text-slate-300 dark:ring-white/10"
                      >
                        {ACTION_LABEL[action] ?? action}
                      </span>
                    ))
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        {form ? (
          <div className="mt-3 rounded-2xl border border-white/60 bg-white/60 p-3.5 dark:border-white/10 dark:bg-white/[0.05]">
            <div className="flex items-center gap-2">
              <span className="text-[12px] font-semibold text-slate-800 dark:text-slate-100">
                {form.id ? "编辑角色" : "新建角色"}
              </span>
              <span className="flex-1" />
              <button
                type="button"
                onClick={() => setForm(null)}
                className="btn-quiet px-1.5"
                aria-label="取消"
              >
                <X size={12} />
              </button>
            </div>
            <div className="mt-2.5 space-y-2.5">
              <label className="block">
                <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                  角色名称
                </span>
                <input
                  value={form.name}
                  onChange={(event) =>
                    setForm((prev) => (prev ? { ...prev, name: event.target.value } : prev))
                  }
                  placeholder="如：评审员"
                  className="input"
                />
              </label>

              <div>
                <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                  权限点{form.builtin ? "（内置角色不可修改）" : ""}
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {ACTIONS.map((action) => {
                    const active = form.actions.includes(action.value);
                    return (
                      <button
                        key={action.value}
                        type="button"
                        disabled={form.builtin}
                        onClick={() =>
                          setForm((prev) => {
                            if (!prev) return prev;
                            const next = prev.actions.includes(action.value)
                              ? prev.actions.filter((item) => item !== action.value)
                              : [...prev.actions, action.value];
                            return { ...prev, actions: next };
                          })
                        }
                        className={clsx(
                          "rounded-full px-2.5 py-1 text-[11px] font-medium transition",
                          active
                            ? "brand-gradient text-white shadow-[0_10px_22px_-16px_rgba(99,102,241,0.9)]"
                            : "bg-white/70 text-slate-600 ring-1 ring-slate-200/70 hover:text-indigo-600 dark:bg-white/[0.06] dark:text-slate-300 dark:ring-white/10",
                          form.builtin && "opacity-60",
                        )}
                      >
                        {action.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                  可见范围
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {(
                    [
                      { value: "all" as RoleScope, label: "全部课程" },
                      { value: "assigned" as RoleScope, label: "仅授权课程" },
                    ]
                  ).map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() =>
                        setForm((prev) => (prev ? { ...prev, scope: option.value } : prev))
                      }
                      className={clsx(
                        "rounded-full px-2.5 py-1 text-[11px] font-medium transition",
                        form.scope === option.value
                          ? "brand-gradient text-white shadow-[0_10px_22px_-16px_rgba(99,102,241,0.9)]"
                          : "bg-white/70 text-slate-600 ring-1 ring-slate-200/70 hover:text-indigo-600 dark:bg-white/[0.06] dark:text-slate-300 dark:ring-white/10",
                      )}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              <button
                type="button"
                onClick={() => void saveRole()}
                disabled={roleBusy || !form.name.trim()}
                className="btn btn-primary"
              >
                {roleBusy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                保存角色
              </button>
            </div>
          </div>
        ) : null}
      </motion.section>

      <motion.section
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.04 }}
        className="glass rounded-3xl p-5 shadow-glass"
      >
        <div className="flex items-center gap-2">
          <Users size={15} className="text-indigo-500 dark:text-indigo-300" />
          <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
            空间成员
          </h2>
          <span className="chip-muted">{tenant || "default"}</span>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="成员邮箱"
            disabled={!canManage}
            className="input w-full sm:max-w-[240px]"
          />
          <select
            value={newRole}
            onChange={(event) => setNewRole(event.target.value)}
            disabled={!canManage}
            className="select py-2 text-[12px]"
          >
            {roleOptions.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void addMember()}
            disabled={!canManage || busy || !email.trim()}
            title={canManage ? "" : "当前角色无权管理成员"}
            className="btn btn-primary"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <UserPlus size={13} />}
            添加成员
          </button>
        </div>

        <div className="mt-4 space-y-1.5">
          {loading ? (
            <p className="text-[11px] text-slate-400">加载中…</p>
          ) : members.length === 0 ? (
            <p className="text-[11px] text-slate-400">暂无成员记录。</p>
          ) : (
            members.map((member) => (
              <div
                key={member.id}
                className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/50 bg-white/45 px-3 py-2 dark:border-white/10 dark:bg-white/[0.04]"
              >
                <span className="brand-gradient grid h-7 w-7 shrink-0 place-items-center rounded-full text-[11px] font-semibold text-white">
                  {(member.user_display_name || member.user_email || "?").slice(0, 1).toUpperCase()}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12px] font-medium text-slate-800 dark:text-slate-100">
                    {member.user_display_name || member.user_email}
                  </span>
                  <span className="block truncate text-[10px] text-slate-400">
                    {member.user_email}
                  </span>
                </span>
                <select
                  value={member.role}
                  onChange={(event) => void changeRole(member.user_id, event.target.value)}
                  disabled={!canManage}
                  className="select py-1 text-[11px]"
                >
                  {roleOptions.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => void removeMember(member.user_id)}
                  disabled={!canManage}
                  title={canManage ? "移除成员" : "当前角色无权管理成员"}
                  className="btn-quiet px-1.5"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))
          )}
        </div>
      </motion.section>

      <motion.section
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.08 }}
        className="glass rounded-3xl p-5 shadow-glass"
      >
        <div className="flex flex-wrap items-center gap-2">
          <ShieldCheck size={15} className="text-indigo-500 dark:text-indigo-300" />
          <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
            用量与配额
          </h2>
          {quota ? <span className="chip-muted">周期 {quota.period}</span> : null}
          {role ? <span className="chip-muted">{role}</span> : null}
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {(
            [
              {
                key: "monthly_generations" as const,
                flag: "generations" as const,
                usageKey: "generations" as const,
                label: "每月生成次数",
              },
              {
                key: "monthly_uploads" as const,
                flag: "uploads" as const,
                usageKey: "uploads" as const,
                label: "每月上传次数",
              },
              {
                key: "storage_bytes" as const,
                flag: "storage" as const,
                usageKey: "storage_bytes" as const,
                label: "存储上限",
              },
            ]
          ).map((field) => {
            const isUnlimited = unlimited[field.flag];
            const limitValue = limits[field.key];
            const remaining = quota?.remaining?.[field.usageKey];
            const used = quota?.usage?.[field.usageKey] ?? 0;
            const unlimitedFlag =
              Boolean(quota?.unlimited?.[field.flag]) || (limitValue ?? 0) <= 0 || (remaining ?? 0) < 0;
            const percent =
              unlimitedFlag || !limitValue
                ? 100
                : Math.min(100, Math.round((used / limitValue) * 100));
            return (
              <div key={field.key} className="block">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-[11px] text-slate-500 dark:text-slate-400">
                    {field.label}
                    {field.key === "storage_bytes" ? "（MB）" : ""}
                  </span>
                  <label className="flex cursor-pointer items-center gap-1 text-[10px] text-slate-500 dark:text-slate-400">
                    <input
                      type="checkbox"
                      checked={isUnlimited}
                      onChange={(event) =>
                        setUnlimited((prev) => ({ ...prev, [field.flag]: event.target.checked }))
                      }
                      disabled={!canQuota}
                      className="h-3 w-3 accent-indigo-500"
                    />
                    不限制
                  </label>
                </div>
                <input
                  type="number"
                  min={0}
                  step={field.key === "storage_bytes" ? 1 : 1}
                  value={
                    field.key === "storage_bytes"
                      ? Number((limitValue / 1024 / 1024).toFixed(1))
                      : limitValue
                  }
                  onChange={(event) => {
                    const raw = Number(event.target.value) || 0;
                    setLimits((prev) => ({
                      ...prev,
                      [field.key]:
                        field.key === "storage_bytes"
                          ? Math.round(raw * 1024 * 1024)
                          : raw,
                    }));
                  }}
                  disabled={!canQuota || isUnlimited}
                  className="input disabled:opacity-50"
                  placeholder={isUnlimited ? "不限" : ""}
                />
                <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-slate-400/20">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500"
                    style={{ width: `${percent}%` }}
                  />
                </div>
                <span className="mt-1 block text-[10px] text-slate-400">
                  {unlimitedFlag
                    ? `已用 ${field.key === "storage_bytes" ? formatBytes(used) : used} · 不限`
                    : `已用 ${field.key === "storage_bytes" ? formatBytes(used) : used} / ${
                        field.key === "storage_bytes" ? formatBytes(limitValue) : limitValue
                      }`}
                </span>
              </div>
            );
          })}
        </div>

        <button
          type="button"
          onClick={() => void saveQuota()}
          disabled={!canQuota || busy}
          title={canQuota ? "" : "当前角色无权管理配额"}
          className="btn btn-primary mt-4"
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
          保存配额
        </button>
      </motion.section>
    </div>
  );
}
