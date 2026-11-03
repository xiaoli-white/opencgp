import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { AlertCircle, ArrowRight, IdCard, Server, Users, X } from "lucide-react";
import { useSession } from "@/components/auth/SessionProvider";
import ProviderCard from "@/components/settings/ProviderCard";
import MyProvidersCard from "@/components/settings/MyProvidersCard";

export default function ProfileSettingsPage() {
  const { me, can, roleName, roleKey, tenantName, tenant } = useSession();
  const canServer = can("manage_server");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const displayName = me?.user.display_name || me?.user.email || "本地用户";
  const email = me?.user.email || "—";
  const roleText = roleName || roleKey || me?.role || "只读";

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4">
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-indigo-400/25 bg-indigo-500/10 px-4 py-2.5 text-[11px] text-indigo-700 dark:text-indigo-200">
        <IdCard size={13} className="shrink-0" />
        <span className="flex-1">
          个人设置只影响你自己：模型通道、个人密钥与账号信息。
        </span>
      </div>

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

      <ProviderCard
        canWrite={can("write")}
        canManageServer={canServer}
        onNotice={(message) => {
          setError("");
          setNotice(message);
        }}
        onError={(message) => {
          setNotice("");
          setError(message);
        }}
      />

      <MyProvidersCard
        canWrite={can("write")}
        onNotice={(message) => {
          setError("");
          setNotice(message);
        }}
        onError={(message) => {
          setNotice("");
          setError(message);
        }}
      />

      <motion.section
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.08 }}
        className="glass rounded-3xl p-5 shadow-glass"
      >
        <div className="flex items-center gap-2">
          <IdCard size={15} className="text-indigo-500 dark:text-indigo-300" />
          <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
            账号信息
          </h2>
          <span className="chip-muted">只读</span>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <div className="rounded-2xl border border-white/50 bg-white/45 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]">
            <span className="block text-[10px] uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
              显示名
            </span>
            <span className="mt-1 block truncate text-[12.5px] font-medium text-slate-800 dark:text-slate-100">
              {displayName}
            </span>
          </div>
          <div className="rounded-2xl border border-white/50 bg-white/45 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]">
            <span className="block text-[10px] uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
              邮箱
            </span>
            <span className="mt-1 block truncate text-[12.5px] font-medium text-slate-800 dark:text-slate-100">
              {email}
            </span>
          </div>
          <div className="rounded-2xl border border-white/50 bg-white/45 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]">
            <span className="block text-[10px] uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
              当前空间
            </span>
            <span className="mt-1 block truncate text-[12.5px] font-medium text-slate-800 dark:text-slate-100">
              {tenantName || tenant || "默认空间"}
            </span>
          </div>
          <div className="rounded-2xl border border-white/50 bg-white/45 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]">
            <span className="block text-[10px] uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
              角色
            </span>
            <span className="mt-1 block truncate text-[12.5px] font-medium text-slate-800 dark:text-slate-100">
              {roleText}
            </span>
          </div>
        </div>
      </motion.section>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.12 }}
        className="flex flex-wrap items-center gap-3 px-1 pb-2"
      >
        <Link
          to="/settings/workspace"
          className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-600 underline-offset-2 transition hover:underline dark:text-indigo-300"
        >
          <Users size={12} />
          空间设置
          <ArrowRight size={11} />
        </Link>
        {canServer ? (
          <Link
            to="/settings/server"
            className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-600 underline-offset-2 transition hover:underline dark:text-indigo-300"
          >
            <Server size={12} />
            服务器设置
            <ArrowRight size={11} />
          </Link>
        ) : null}
      </motion.div>
    </div>
  );
}
