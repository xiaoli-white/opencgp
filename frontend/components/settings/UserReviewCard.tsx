import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  KeyRound,
  Loader2,
  Pencil,
  RefreshCcw,
  RotateCcw,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserX,
  X,
} from "lucide-react";
import clsx from "clsx";
import { api, ApiError, type AdminUser, type Member } from "@/lib/api";
import { useSession } from "@/components/auth/SessionProvider";
import { formatDateTime } from "@/lib/format";
import {
  Modal,
  PromptDialog,
  RowMenu,
  type MenuItem,
} from "@/components/common/Dialogs";

const ROLE_OPTIONS = [
  { value: "viewer", label: "只读" },
  { value: "editor", label: "编辑" },
  { value: "admin", label: "管理员" },
  { value: "owner", label: "所有者" },
];

type Tab = "pending" | "all";

export default function UserReviewCard({
  onNotice,
  onError,
}: {
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { tenant, me } = useSession();
  const [tab, setTab] = useState<Tab>("pending");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [transferTarget, setTransferTarget] = useState("");
  const [transferMembers, setTransferMembers] = useState<Member[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [rejecting, setRejecting] = useState<string>("");
  const [reason, setReason] = useState("");
  const [renameTarget, setRenameTarget] = useState<AdminUser | null>(null);
  const [pwdTarget, setPwdTarget] = useState<AdminUser | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);
  const [dialogBusy, setDialogBusy] = useState(false);
  const [dialogError, setDialogError] = useState("");

  const load = useCallback(
    async (target: Tab = tab, withDeleted = includeDeleted) => {
      setLoading(true);
      setError("");
      try {
        const [pending, list] = await Promise.all([
          api.listAdminUsers("pending"),
          target === "pending"
            ? Promise.resolve(null)
            : api.listAdminUsers(undefined, { includeDeleted: withDeleted }),
        ]);
        setPendingCount(pending?.count ?? (pending?.users ?? []).length);
        setUsers(target === "pending" ? pending?.users ?? [] : list?.users ?? []);
      } catch (err) {
        setError(err instanceof Error ? err.message : "用户列表加载失败");
      } finally {
        setLoading(false);
      }
    },
    [includeDeleted, tab],
  );

  useEffect(() => {
    void load(tab, includeDeleted);
  }, [load, tab, includeDeleted]);

  const approve = useCallback(
    async (user: AdminUser) => {
      setBusy(user.id);
      setError("");
      try {
        await api.approveAdminUser(user.id);
        onNotice(`已批准 ${user.display_name || user.email}`);
        await load(tab);
      } catch (err) {
        setError(err instanceof Error ? err.message : "批准失败");
      } finally {
        setBusy("");
      }
    },
    [load, onNotice, tab],
  );

  const reject = useCallback(
    async (user: AdminUser) => {
      setBusy(user.id);
      setError("");
      try {
        await api.rejectAdminUser(user.id, reason.trim());
        onNotice(`已拒绝 ${user.display_name || user.email}`);
        setRejecting("");
        setReason("");
        await load(tab);
      } catch (err) {
        setError(err instanceof Error ? err.message : "拒绝失败");
      } finally {
        setBusy("");
      }
    },
    [load, onNotice, reason, tab],
  );

  const statusLabel = (status: string) => {
    if (status === "pending") return "待审核";
    if (status === "active") return "已启用";
    if (status === "rejected") return "已拒绝";
    if (status === "deleted") return "已删除";
    return status;
  };

  const patchUser = async (payload: Record<string, string>) => {
    if (!renameTarget) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      await api.updateAdminUser(renameTarget.id, payload);
      onNotice("用户信息已更新");
      setRenameTarget(null);
      await load(tab);
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "更新失败");
    } finally {
      setDialogBusy(false);
    }
  };

  const changeRole = async (user: AdminUser, role: string) => {
    setError("");
    try {
      await api.updateAdminUser(user.id, { role });
      onNotice(`已将 ${user.display_name || user.email} 设为 ${ROLE_OPTIONS.find((item) => item.value === role)?.label ?? role}`);
      await load(tab);
    } catch (err) {
      setError(err instanceof Error ? err.message : "角色更新失败");
    }
  };

  const resetPassword = async (value: string) => {
    if (!pwdTarget) return;
    if (value.length < 8) {
      setDialogError("新密码至少 8 位");
      return;
    }
    setDialogBusy(true);
    setDialogError("");
    try {
      await api.resetAdminPassword(pwdTarget.id, value);
      onNotice(`已重置 ${pwdTarget.display_name || pwdTarget.email} 的密码`);
      setPwdTarget(null);
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "重置失败");
    } finally {
      setDialogBusy(false);
    }
  };

  const openDelete = useCallback(
    async (user: AdminUser) => {
      setDialogError("");
      setTransferTarget("");
      setDeleteTarget(user);
      if (!tenant) return;
      try {
        const result = await api.listMembers(tenant);
        setTransferMembers(
          (result.members ?? []).filter(
            (member) => member.user_id !== user.id && member.user_id !== me?.user?.id,
          ),
        );
      } catch {
        setTransferMembers([]);
      }
    },
    [me, tenant],
  );

  const removeUser = async (force = false) => {
    if (!deleteTarget) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      await api.deleteAdminUser(deleteTarget.id, {
        transfer_to_user_id: transferTarget || undefined,
        force,
      });
      onNotice(
        transferTarget
          ? `用户已删除，作品已转移（软删除可恢复）`
          : "用户已删除（软删除，可恢复）",
      );
      setDeleteTarget(null);
      setTransferTarget("");
      await load(tab, includeDeleted);
    } catch (err) {
      const message = err instanceof Error ? err.message : "删除失败";
      setDialogError(message);
      if (err instanceof ApiError && err.status === 409) {
        setDialogError(
          transferMembers.length === 0
            ? `${message}（当前空间暂无可转移成员，可选择「不转移直接删」）`
            : `${message}（请先在下方选择作品转移对象）`,
        );
      }
    } finally {
      setDialogBusy(false);
    }
  };

  const restoreUser = useCallback(
    async (user: AdminUser) => {
      setBusy(user.id);
      setError("");
      try {
        await api.restoreAdminUser(user.id);
        onNotice(`已恢复 ${user.display_name || user.email}`);
        await load(tab, includeDeleted);
      } catch (err) {
        setError(err instanceof Error ? err.message : "恢复失败");
      } finally {
        setBusy("");
      }
    },
    [includeDeleted, load, onNotice, tab],
  );

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-3xl p-5 shadow-glass"
    >
      <div className="flex flex-wrap items-center gap-2">
        <ShieldCheck size={15} className="text-indigo-500 dark:text-indigo-300" />
        <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
          用户管理
        </h2>
        <span
          className={clsx(
            "rounded-full px-2 py-0.5 text-[10px] font-medium",
            pendingCount > 0
              ? "bg-amber-400/20 text-amber-700 dark:bg-amber-300/15 dark:text-amber-300"
              : "chip-muted",
          )}
        >
          待审核 {pendingCount}
        </span>
        <span className="flex-1" />
        <div className="flex items-center gap-1 rounded-full bg-white/50 p-0.5 dark:bg-white/[0.06]">
          {(
            [
              { value: "pending", label: "待审核" },
              { value: "all", label: "全部" },
            ] as { value: Tab; label: string }[]
          ).map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => setTab(item.value)}
              className={clsx(
                "rounded-full px-2.5 py-1 text-[10.5px] font-medium transition",
                tab === item.value
                  ? "brand-gradient text-white shadow-sm"
                  : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setIncludeDeleted((prev) => !prev)}
          className={clsx(
            "btn-quiet px-2 py-1 text-[10.5px]",
            includeDeleted && "text-indigo-600 dark:text-indigo-300",
          )}
          title="是否显示已删除用户"
        >
          {includeDeleted ? "隐藏已删除" : "显示已删除"}
        </button>
        <button
          type="button"
          onClick={() => void load(tab, includeDeleted)}
          disabled={loading}
          className="btn-quiet px-2 py-1 text-[10.5px]"
          title="刷新"
        >
          {loading ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            <RefreshCcw size={11} />
          )}
          刷新
        </button>
      </div>

      {error ? (
        <p className="mt-2 flex items-start gap-1.5 rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[10.5px] text-rose-700 dark:text-rose-300">
          <AlertCircle size={12} className="mt-0.5 shrink-0" />
          <span className="flex-1 break-words">{error}</span>
          <button
            type="button"
            onClick={() => setError("")}
            className="shrink-0 text-rose-400 transition hover:text-rose-600"
            aria-label="关闭"
          >
            <X size={11} />
          </button>
        </p>
      ) : null}

      <div className="mt-3 space-y-1.5">
        {loading ? (
          <p className="flex items-center gap-2 text-[11px] text-slate-400">
            <Loader2 size={12} className="animate-spin" />
            加载中…
          </p>
        ) : users.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-white/60 bg-white/40 px-3 py-3 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-400">
            {tab === "pending" ? "暂无待审核用户" : "暂无用户"}
          </p>
        ) : (
          users.map((user) => (
            <div
              key={user.id}
              className="rounded-2xl border border-white/50 bg-white/45 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]"
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="brand-gradient grid h-7 w-7 shrink-0 place-items-center rounded-full text-[11px] font-semibold text-white">
                  {(user.display_name || user.email || "?").slice(0, 1).toUpperCase()}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[12px] font-medium text-slate-800 dark:text-slate-100">
                    {user.display_name || user.email}
                  </span>
                  <span className="block truncate text-[10px] text-slate-400">
                    {user.email} · 注册 {formatDateTime(user.created_at)}
                  </span>
                </span>
                <span
                  className={clsx(
                    "rounded-full px-1.5 py-0.5 text-[9.5px]",
                    user.status === "pending"
                      ? "bg-amber-400/20 text-amber-700 dark:text-amber-300"
                      : user.status === "active"
                        ? "bg-emerald-500/12 text-emerald-700 dark:text-emerald-300"
                        : "bg-slate-500/12 text-slate-500 dark:text-slate-400",
                  )}
                >
                  {statusLabel(user.status)}
                </span>
                <span className="flex-1" />
                {user.status === "pending" ? (
                  <>
                    <button
                      type="button"
                      onClick={() => void approve(user)}
                      disabled={busy === user.id}
                      className="btn btn-primary px-2.5 py-1 text-[10.5px]"
                    >
                      {busy === user.id ? (
                        <Loader2 size={11} className="animate-spin" />
                      ) : (
                        <UserCheck size={11} />
                      )}
                      批准
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setRejecting(rejecting === user.id ? "" : user.id);
                        setReason("");
                      }}
                      className="btn-quiet px-2 py-1 text-[10.5px] text-rose-500"
                    >
                      <UserX size={11} />
                      拒绝
                    </button>
                  </>
                ) : null}
                <RowMenu
                  label={`管理 ${user.display_name || user.email}`}
                  items={[
                    {
                      label: "修改显示名",
                      icon: <Pencil size={11} />,
                      onClick: () => {
                        setDialogError("");
                        setRenameTarget(user);
                      },
                    },
                    {
                      label: "重置密码",
                      icon: <KeyRound size={11} />,
                      onClick: () => {
                        setDialogError("");
                        setPwdTarget(user);
                      },
                    },
                    ...(user.status === "deleted"
                      ? [
                          {
                            label: "恢复用户",
                            icon: <RotateCcw size={11} />,
                            onClick: () => void restoreUser(user),
                          },
                        ]
                      : [
                          {
                            label: "删除用户",
                            icon: <Trash2 size={11} />,
                            danger: true,
                            onClick: () => void openDelete(user),
                          },
                        ]),
                  ] as MenuItem[]}
                />
                <select
                  value={user.role ?? "viewer"}
                  onChange={(event) => void changeRole(user, event.target.value)}
                  className="select w-auto px-1.5 py-1 text-[10.5px]"
                  title="修改系统角色"
                >
                  {ROLE_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>

              {rejecting === user.id ? (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <input
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    placeholder="拒绝原因（可选）"
                    className="input flex-1 py-1 text-[11px]"
                  />
                  <button
                    type="button"
                    onClick={() => void reject(user)}
                    disabled={busy === user.id}
                    className="btn btn-primary px-2.5 py-1 text-[10.5px]"
                  >
                    {busy === user.id ? (
                      <Loader2 size={11} className="animate-spin" />
                    ) : (
                      <CheckCircle2 size={11} />
                    )}
                    确认拒绝
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setRejecting("");
                      setReason("");
                    }}
                    className="btn-quiet px-2 py-1 text-[10.5px]"
                  >
                    取消
                  </button>
                </div>
              ) : null}
            </div>
          ))
        )}
      </div>

      <PromptDialog
        open={Boolean(renameTarget)}
        title="修改显示名"
        label="显示名"
        initial={renameTarget?.display_name ?? ""}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={(value) => void patchUser({ display_name: value })}
        onClose={() => setRenameTarget(null)}
      />

      <PromptDialog
        open={Boolean(pwdTarget)}
        title="重置密码"
        label="新密码（至少 8 位）"
        initial=""
        confirmLabel="重置"
        busy={dialogBusy}
        error={dialogError}
        onConfirm={(value) => void resetPassword(value)}
        onClose={() => setPwdTarget(null)}
      />

      <Modal
        open={Boolean(deleteTarget)}
        title="删除用户"
        subtitle={`${deleteTarget?.display_name || deleteTarget?.email || ""} 的账号将被软删除，可由「显示已删除」恢复。`}
        onClose={() => setDeleteTarget(null)}
      >
        <div className="space-y-3">
          <div className="rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[10.5px] leading-relaxed text-amber-700 dark:text-amber-300">
            该用户拥有的课程与长篇作品需要先转移给其他成员；选择「不转移直接删」可强制软删除。
          </div>
          <label className="block text-[11px] font-medium text-slate-500 dark:text-slate-400">
            作品转移到
            <select
              value={transferTarget}
              onChange={(event) => setTransferTarget(event.target.value)}
              className="select mt-1 w-full py-1.5 text-[11px]"
            >
              <option value="">不转移直接删</option>
              {transferMembers.map((member) => (
                <option key={member.user_id} value={member.user_id}>
                  {member.user_display_name || member.user_email}
                </option>
              ))}
            </select>
          </label>
          {transferMembers.length === 0 ? (
            <p className="text-[10px] text-slate-400 dark:text-slate-500">
              当前空间暂无可转移成员。
            </p>
          ) : null}
          {dialogError ? (
            <p className="flex items-start gap-1.5 rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[10.5px] text-rose-700 dark:text-rose-300">
              <AlertCircle size={12} className="mt-0.5 shrink-0" />
              <span className="flex-1 break-words">{dialogError}</span>
            </p>
          ) : null}
          <div className="flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={() => setDeleteTarget(null)}
              className="btn btn-quiet"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => void removeUser(true)}
              disabled={dialogBusy}
              className="btn btn-quiet text-rose-600 dark:text-rose-300"
            >
              强制软删除
            </button>
            <button
              type="button"
              onClick={() => void removeUser(false)}
              disabled={dialogBusy}
              className="btn btn-primary"
            >
              {dialogBusy ? <Loader2 size={13} className="animate-spin" /> : null}
              确认删除
            </button>
          </div>
        </div>
      </Modal>
    </motion.section>
  );
}
