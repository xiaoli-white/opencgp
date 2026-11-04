import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  Globe2,
  Loader2,
  Server,
  X,
} from "lucide-react";
import clsx from "clsx";
import { api, type Health } from "@/lib/api";
import { useSession } from "@/components/auth/SessionProvider";
import { useI18n } from "@/i18n/I18nProvider";
import ServerProvidersCard from "@/components/settings/ServerProvidersCard";
import UserReviewCard from "@/components/settings/UserReviewCard";
import SettingsBreadcrumb from "@/components/settings/SettingsBreadcrumb";
import NoAccessCard from "@/components/common/NoAccessCard";

export default function ServerSettingsPage() {
  const { can } = useSession();
  const { t } = useI18n();
  const canServer = can("manage_server");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState("");
  const [loadingHealth, setLoadingHealth] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoadingHealth(true);
    api
      .health()
      .then((data) => {
        if (alive) {
          setHealth(data);
          setHealthError("");
        }
      })
      .catch((err) => {
        if (alive) setHealthError(err instanceof Error ? err.message : t("server.healthFailed"));
      })
      .finally(() => {
        if (alive) setLoadingHealth(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (!canServer) {
    return (
      <div className="mx-auto w-full max-w-4xl space-y-4">
        <SettingsBreadcrumb current={t("server.title")} />
        <NoAccessCard
          title={t("server.noAccessTitle")}
          message={t("server.noAccessMessage")}
          backTo="/settings"
          backLabel={t("server.backToProfile")}
        />
      </div>
    );
  }

  const adapterEntries = Object.entries(health?.adapters ?? {});

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4">
      <SettingsBreadcrumb current={t("server.title")} />

      <div className="flex items-start gap-2 rounded-2xl border border-indigo-400/25 bg-indigo-500/10 px-4 py-2.5 text-[11px] text-indigo-700 dark:text-indigo-200">
        <Globe2 size={13} className="mt-0.5 shrink-0" />
        <span className="flex-1">{t("server.hint")}</span>
      </div>

      {error ? (
        <div className="flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-2.5 text-[11px] text-rose-700 dark:text-rose-300">
          <AlertCircle size={13} className="mt-0.5 shrink-0" />
          <span className="flex-1">{error}</span>
          <button
            type="button"
            onClick={() => setError("")}
            className="text-rose-400 transition hover:text-rose-600"
            aria-label={t("common.close")}
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

      <UserReviewCard
        onNotice={(message) => {
          setError("");
          setNotice(message);
        }}
        onError={(message) => {
          setNotice("");
          setError(message);
        }}
      />

      <ServerProvidersCard
        canManage={canServer}
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
        transition={{ delay: 0.06 }}
        className="glass rounded-3xl p-5 shadow-glass"
      >
        <div className="flex flex-wrap items-center gap-2">
          <Server size={15} className="text-indigo-500 dark:text-indigo-300" />
          <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
            {t("server.overview")}
          </h2>
          <span className="chip-muted">{t("server.readOnly")}</span>
          {health ? (
            <span
              className={clsx(
                "rounded-full px-2 py-0.5 text-[10px] font-medium",
                health.status === "ok"
                  ? "bg-emerald-500/12 text-emerald-600 dark:text-emerald-300"
                  : "bg-amber-400/15 text-amber-600 dark:text-amber-300",
              )}
            >
              {health.status === "ok" ? t("server.running") : health.status}
            </span>
          ) : null}
        </div>

        {loadingHealth ? (
          <p className="mt-3 flex items-center gap-2 text-[11px] text-slate-400">
            <Loader2 size={12} className="animate-spin" />
            {t("server.loadingHealth")}
          </p>
        ) : healthError ? (
          <p className="mt-3 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[10.5px] text-amber-700 dark:text-amber-300">
            {healthError}
          </p>
        ) : (
          <>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              <div className="rounded-2xl border border-white/50 bg-white/45 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]">
                <span className="block text-[10px] uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
                  {t("server.app")}
                </span>
                <span className="mt-1 block truncate text-[12.5px] font-medium text-slate-800 dark:text-slate-100">
                  {health?.app || "—"}
                </span>
              </div>
              <div className="rounded-2xl border border-white/50 bg-white/45 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]">
                <span className="block text-[10px] uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
                  {t("server.env")}
                </span>
                <span className="mt-1 block truncate text-[12.5px] font-medium text-slate-800 dark:text-slate-100">
                  {health?.env || "—"}
                </span>
              </div>
              <div className="rounded-2xl border border-white/50 bg-white/45 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]">
                <span className="block text-[10px] uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
                  {t("server.status")}
                </span>
                <span className="mt-1 block truncate text-[12.5px] font-medium text-slate-800 dark:text-slate-100">
                  {health?.status || "—"}
                </span>
              </div>
            </div>

            <div className="mt-3">
              <span className="mb-1.5 block text-[11px] text-slate-500 dark:text-slate-400">
                {t("server.adapters")}
              </span>
              {adapterEntries.length === 0 ? (
                <p className="text-[11px] text-slate-400">{t("server.noAdapters")}</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {adapterEntries.map(([name, info]) => (
                    <span
                      key={name}
                      className={clsx(
                        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] ring-1",
                        info?.ok
                          ? "bg-emerald-500/10 text-emerald-700 ring-emerald-400/25 dark:text-emerald-300"
                          : "bg-amber-400/10 text-amber-700 ring-amber-400/25 dark:text-amber-300",
                      )}
                      title={info?.error || (info?.ok ? t("server.ok") : t("server.error"))}
                    >
                      {info?.ok ? <CheckCircle2 size={10} /> : <AlertCircle size={10} />}
                      {name}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </motion.section>
    </div>
  );
}
