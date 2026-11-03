"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, Loader2, ShieldCheck, Trash2, UserPlus, Users } from "lucide-react";
import { api, type Member, type Quota, type QuotaUsage } from "@/lib/api";
import { ROLE_LABEL, type Role } from "@/lib/session";
import { useSession } from "@/components/auth/SessionProvider";

const ROLES: Role[] = ["viewer", "editor", "admin", "owner"];

function formatBytes(value: number): string {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function SettingsPage() {
  const { tenant, role, can } = useSession();
  const canManage = can("manage_members");
  const canQuota = can("manage_quota");

  const [members, setMembers] = useState<Member[]>([]);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState<Role>("editor");
  const [limits, setLimits] = useState<QuotaUsage>({
    monthly_generations: 0,
    monthly_uploads: 0,
    storage_bytes: 0,
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (tenant) {
        const data = await api.listMembers(tenant);
        setMembers(data.members);
      }
      const q = await api.getQuota();
      setQuota(q);
      setLimits(q.limits);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [tenant]);

  useEffect(() => {
    void load();
  }, [load]);

  const addMember = useCallback(async () => {
    if (!tenant || !email.trim()) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.addMember(tenant, { email: email.trim(), role: newRole });
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
    async (userId: string, next: Role) => {
      if (!tenant) return;
      setError("");
      try {
        await api.updateMemberRole(tenant, userId, next);
        setMembers((prev) =>
          prev.map((item) => (item.user_id === userId ? { ...item, role: next } : item)),
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "更新失败");
      }
    },
    [tenant],
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

  const saveQuota = useCallback(async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const next = await api.updateQuota(limits);
      setQuota(next);
      setLimits(next.limits);
      setNotice("配额已更新");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }, [limits]);

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4">
      {!canManage ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-2.5 text-[11px] text-amber-700 dark:text-amber-300">
          你以 {role ? ROLE_LABEL[role] : "只读"} 身份访问该空间，成员与配额仅可查看。
        </div>
      ) : null}

      {error ? (
        <div className="flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-2.5 text-[11px] text-rose-700 dark:text-rose-300">
          <AlertCircle size={13} className="mt-0.5 shrink-0" />
          <span className="flex-1">{error}</span>
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
            className="input max-w-[240px]"
          />
          <select
            value={newRole}
            onChange={(event) => setNewRole(event.target.value as Role)}
            disabled={!canManage}
            className="select py-2 text-[12px]"
          >
            {ROLES.map((item) => (
              <option key={item} value={item}>
                {ROLE_LABEL[item]}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void addMember()}
            disabled={!canManage || busy || !email.trim()}
            title={canManage ? "" : "当前角色只读"}
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
                  onChange={(event) => void changeRole(member.user_id, event.target.value as Role)}
                  disabled={!canManage}
                  className="select py-1 text-[11px]"
                >
                  {ROLES.map((item) => (
                    <option key={item} value={item}>
                      {ROLE_LABEL[item]}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => void removeMember(member.user_id)}
                  disabled={!canManage}
                  title={canManage ? "移除成员" : "当前角色只读"}
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
        transition={{ delay: 0.05 }}
        className="glass rounded-3xl p-5 shadow-glass"
      >
        <div className="flex items-center gap-2">
          <ShieldCheck size={15} className="text-indigo-500 dark:text-indigo-300" />
          <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
            用量配额
          </h2>
          {quota ? <span className="chip-muted">周期 {quota.period}</span> : null}
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {(
            [
              { key: "monthly_generations" as const, label: "每月生成次数" },
              { key: "monthly_uploads" as const, label: "每月上传次数" },
              { key: "storage_bytes" as const, label: "存储上限（字节）" },
            ]
          ).map((field) => (
            <label key={field.key} className="block">
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                {field.label}
              </span>
              <input
                type="number"
                min={0}
                value={limits[field.key]}
                onChange={(event) =>
                  setLimits((prev) => ({ ...prev, [field.key]: Number(event.target.value) || 0 }))
                }
                disabled={!canQuota}
                className="input"
              />
              <span className="mt-1 block text-[10px] text-slate-400">
                已用 {quota ? quota.usage[field.key] : 0}
                {field.key === "storage_bytes" && quota ? ` · ${formatBytes(quota.usage.storage_bytes)}` : ""}
              </span>
            </label>
          ))}
        </div>

        <button
          type="button"
          onClick={() => void saveQuota()}
          disabled={!canQuota || busy}
          title={canQuota ? "" : "当前角色只读"}
          className="btn btn-primary mt-4"
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
          保存配额
        </button>
      </motion.section>
    </div>
  );
}
