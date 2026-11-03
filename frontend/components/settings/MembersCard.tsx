import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Loader2, Trash2, UserPlus, Users } from "lucide-react";
import { api, type Member, type RoleRecord } from "@/lib/api";
import { useSession } from "@/components/auth/SessionProvider";

export default function MembersCard({
  onNotice,
  onError,
}: {
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { tenant, can, refresh } = useSession();
  const canManage = can("manage_members");

  const [members, setMembers] = useState<Member[]>([]);
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState("editor");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const roleData = await api.listRoles();
      const list = roleData.roles ?? [];
      setRoles(list);
      if (list.length) {
        setNewRole((prev) =>
          list.some((item) => item.key === prev) ? prev : list[list.length - 1].key,
        );
      }
      if (tenant) {
        const data = await api.listMembers(tenant);
        setMembers(data.members ?? []);
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "成员加载失败");
    } finally {
      setLoading(false);
    }
  }, [tenant, onError]);

  useEffect(() => {
    void load();
  }, [load]);

  const roleOptions = useMemo(
    () => roles.map((item) => ({ value: item.key, label: item.name })),
    [roles],
  );

  const addMember = async () => {
    if (!tenant || !email.trim()) return;
    setBusy(true);
    onError("");
    onNotice("");
    try {
      await api.addMember(tenant, {
        email: email.trim(),
        role: newRole as Member["role"],
      });
      setEmail("");
      onNotice("成员已添加");
      await load();
    } catch (err) {
      onError(err instanceof Error ? err.message : "添加失败");
    } finally {
      setBusy(false);
    }
  };

  const changeRole = async (userId: string, next: string) => {
    if (!tenant) return;
    onError("");
    try {
      await api.updateMemberRole(tenant, userId, next as Member["role"]);
      setMembers((prev) =>
        prev.map((item) =>
          item.user_id === userId ? { ...item, role: next as Member["role"] } : item,
        ),
      );
      onNotice("角色已更新");
      await refresh();
    } catch (err) {
      onError(err instanceof Error ? err.message : "更新失败");
    }
  };

  const removeMember = async (userId: string) => {
    if (!tenant) return;
    onError("");
    try {
      await api.removeMember(tenant, userId);
      setMembers((prev) => prev.filter((item) => item.user_id !== userId));
      onNotice("成员已移除");
    } catch (err) {
      onError(err instanceof Error ? err.message : "移除失败");
    }
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-3xl p-5 shadow-glass"
    >
      <div className="flex flex-wrap items-center gap-2">
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
          className="select w-full py-2 text-[12px] sm:w-auto"
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
  );
}
