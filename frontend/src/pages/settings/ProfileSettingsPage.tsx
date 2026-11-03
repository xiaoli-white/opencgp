import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { AlertCircle, ArrowRight, IdCard, Server, X } from "lucide-react";
import { useSession } from "@/components/auth/SessionProvider";
import AccountCard from "@/components/settings/AccountCard";
import ProviderCard from "@/components/settings/ProviderCard";
import MyProvidersCard from "@/components/settings/MyProvidersCard";
import SpacesCard from "@/components/settings/SpacesCard";
import CreationProfilesCard from "@/components/settings/CreationProfilesCard";
import RolesCard from "@/components/settings/RolesCard";
import MembersCard from "@/components/settings/MembersCard";
import QuotaCard from "@/components/settings/QuotaCard";

export default function ProfileSettingsPage() {
  const { can, roleName } = useSession();
  const canServer = can("manage_server");
  const canWrite = can("write");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const handleNotice = useCallback((message: string) => {
    setError("");
    setNotice(message);
  }, []);

  const handleError = useCallback((message: string) => {
    setNotice("");
    setError(message);
  }, []);

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4">
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-indigo-400/25 bg-indigo-500/10 px-4 py-2.5 text-[11px] text-indigo-700 dark:text-indigo-200">
        <IdCard size={13} className="shrink-0" />
        <span className="flex-1">
          个人设置只影响你自己：账号、模型通道与个人密钥。
        </span>
      </div>

      {!canWrite ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-2.5 text-[11px] text-amber-700 dark:text-amber-300">
          你以 {roleName || "只读"} 身份访问，仅可读取。
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

      <AccountCard canWrite={canWrite} onNotice={handleNotice} onError={handleError} />

      <ProviderCard
        canWrite={canWrite}
        canManageServer={canServer}
        onNotice={handleNotice}
        onError={handleError}
      />

      <MyProvidersCard
        canWrite={canWrite}
        onNotice={handleNotice}
        onError={handleError}
      />

      <SpacesCard onNotice={handleNotice} onError={handleError} />

      <CreationProfilesCard
        canWrite={canWrite}
        onNotice={handleNotice}
        onError={handleError}
      />

      <RolesCard onNotice={handleNotice} onError={handleError} />

      <MembersCard onNotice={handleNotice} onError={handleError} />

      <QuotaCard onNotice={handleNotice} onError={handleError} />

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-wrap items-center gap-3 px-1 pb-2"
      >
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
