import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  KeyRound,
  Loader2,
  Pencil,
  RefreshCcw,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserX,
  X,
} from "lucide-react";
import clsx from "clsx";
import { api, type AdminUser } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  ConfirmDialog,
  PromptDialog,
  RowMenu,
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
  const [tab, setTab] = useState<Tab>("pending");
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
    async (target: Tab = tab) => {
      setLoading(true);
      setError("");
      try {
        const [pending, list] = await Promise.all([
          api.listAdminUsers("pending"),
          target === "pending" ? Promise.resolve(null) : api.listAdminUsers(),
        ]);
        setPendingCount(pending?.count ?? (pending?.users ?? []).length);
        setUsers(target === "pending" ? pending?.users ?? [] : list?.users ?? []);
      } catch (err) {
        setError(err instanceof Error ? err.message : "用户列表加载失败");
      } finally {
        setLoading(false);
      }
    },
    [tab],
  );

  useEffect(() => {
    void load(tab);
  }, [load, tab]);

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

  const removeUser = async () => {
    if (!deleteTarget) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      await api.deleteAdminUser(deleteTarget.id);
      onNotice("用户已删除");
      setDeleteTarget(null);
      await load(tab);
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDialogBusy(false);
    }
  };

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
          onClick={() => void load(tab)}
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
                    {
                      label: "删除用户",
                      icon: <Trash2 size={11} />,
                      danger: true,
                      onClick: () => {
                        setDialogError("");
                        setDeleteTarget(user);
                      },
                    },
                  ]}
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

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="删除用户"
        description={`将删除 ${deleteTarget?.email ?? ""} 的账号，不可恢复。`}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={() => void removeUser()}
        onClose={() => setDeleteTarget(null)}
      />
    </motion.section>
  );
}
