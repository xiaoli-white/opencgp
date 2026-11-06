import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  AlertCircle,
  Cpu,
  Database,
  Gauge,
  Server,
  Settings2,
  X,
} from "lucide-react";
import clsx from "clsx";
import { useSession } from "@/components/auth/SessionProvider";
import { useI18n } from "@/i18n/I18nProvider";
import SettingsBreadcrumb from "@/components/settings/SettingsBreadcrumb";
import ProviderCard from "@/components/settings/ProviderCard";
import MyProvidersCard from "@/components/settings/MyProvidersCard";
import ServerProvidersCard from "@/components/settings/ServerProvidersCard";
import RetrievalCard from "@/components/settings/RetrievalCard";

type TabKey = "llm" | "embedding" | "rerank" | "weights";
type ChannelScope = "user" | "server";

const TAB_KEYS: TabKey[] = ["llm", "embedding", "rerank", "weights"];

function normalizeTab(value: string | null): TabKey {
  const lowered = (value || "").toLowerCase();
  return TAB_KEYS.includes(lowered as TabKey) ? (lowered as TabKey) : "llm";
}

export default function ProvidersSettingsPage() {
  const { can, roleName } = useSession();
  const { t } = useI18n();
  const canWrite = can("write");
  const canServer = can("manage_server");
  const [params, setParams] = useSearchParams();
  const tab = normalizeTab(params.get("tab"));
  const [channelScope, setChannelScope] = useState<ChannelScope>("user");
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

  useEffect(() => {
    if (!canServer && channelScope === "server") {
      setChannelScope("user");
    }
  }, [canServer, channelScope]);

  const selectTab = (next: TabKey) => {
    const search = new URLSearchParams(params);
    search.set("tab", next);
    setParams(search, { replace: true });
  };

  const tabs: { key: TabKey; label: string; icon: typeof Cpu }[] = [
    { key: "llm", label: t("providersHub.tabLlm"), icon: Cpu },
    { key: "embedding", label: t("providersHub.tabEmbedding"), icon: Database },
    { key: "rerank", label: t("providersHub.tabRerank"), icon: Gauge },
    { key: "weights", label: t("providersHub.tabWeights"), icon: Settings2 },
  ];

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4">
      <SettingsBreadcrumb current={t("providersHub.title")} />

      <div className="flex flex-wrap items-start gap-2 rounded-2xl border border-indigo-400/25 bg-indigo-500/10 px-4 py-2.5 text-[11px] text-indigo-700 dark:text-indigo-200">
        <Settings2 size={13} className="mt-0.5 shrink-0" />
        <span className="min-w-0 flex-1">{t("providersHub.pageHint")}</span>
      </div>

      {!canWrite ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-2.5 text-[11px] text-amber-700 dark:text-amber-300">
          {t("settings.readOnlyAs", { role: roleName || t("common.readOnly") })}
        </div>
      ) : null}

      {error ? (
        <div className="flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-2.5 text-[11px] text-rose-700 dark:text-rose-300">
          <AlertCircle size={13} className="mt-0.5 shrink-0" />
          <span className="min-w-0 flex-1 break-words">{error}</span>
          <button
            type="button"
            onClick={() => setError("")}
            className="shrink-0 text-rose-400 transition hover:text-rose-600"
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

      <div className="glass rounded-3xl p-2 shadow-glass">
        <div className="no-scrollbar -mx-1 overflow-x-auto px-1">
          <div className="flex min-w-max items-center gap-1">
            {tabs.map((item) => {
              const Icon = item.icon;
              const active = tab === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  data-tab={item.key}
                  onClick={() => selectTab(item.key)}
                  className={clsx(
                    "inline-flex shrink-0 items-center gap-1.5 rounded-2xl px-3 py-2 text-[11.5px] font-medium transition",
                    active
                      ? "brand-gradient text-white shadow-brand"
                      : "text-slate-600 hover:bg-white/55 hover:text-indigo-600 dark:text-slate-300 dark:hover:bg-white/10",
                  )}
                >
                  <Icon size={13} />
                  {item.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {tab === "llm" ? (
        <div className="space-y-4">
          <div className="glass flex flex-wrap items-center gap-1 rounded-2xl p-1.5 shadow-glass">
            <button
              type="button"
              data-channel-scope="user"
              onClick={() => setChannelScope("user")}
              className={clsx(
                "inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-[11px] font-medium transition",
                channelScope === "user"
                  ? "bg-indigo-500 text-white"
                  : "text-slate-600 hover:text-indigo-600 dark:text-slate-300",
              )}
            >
              <Cpu size={12} />
              {t("providersHub.personalChannels")}
            </button>
            <button
              type="button"
              data-channel-scope="server"
              onClick={() => setChannelScope("server")}
              disabled={!canServer}
              title={canServer ? "" : t("providersHub.serverTabNeedServer")}
              className={clsx(
                "inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-[11px] font-medium transition",
                channelScope === "server"
                  ? "bg-indigo-500 text-white"
                  : "text-slate-600 hover:text-indigo-600 dark:text-slate-300",
                !canServer && "cursor-not-allowed opacity-50",
              )}
            >
              <Server size={12} />
              {t("providersHub.serverChannels")}
            </button>
          </div>

          {channelScope === "user" || !canServer ? (
            <>
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
            </>
          ) : (
            <ServerProvidersCard
              canManage={canServer}
              onNotice={handleNotice}
              onError={handleError}
            />
          )}
        </div>
      ) : null}

      {tab === "embedding" ? (
        <RetrievalCard
          section="embedding"
          canWrite={canWrite}
          canManageServer={canServer}
          onNotice={handleNotice}
          onError={handleError}
        />
      ) : null}

      {tab === "rerank" ? (
        <RetrievalCard
          section="rerank"
          canWrite={canWrite}
          canManageServer={canServer}
          onNotice={handleNotice}
          onError={handleError}
        />
      ) : null}

      {tab === "weights" ? (
        <RetrievalCard
          section="weights"
          canWrite={canWrite}
          canManageServer={canServer}
          onNotice={handleNotice}
          onError={handleError}
        />
      ) : null}

      {!canServer ? (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="px-1 text-[10px] text-slate-400"
        >
          {t("providersHub.serverTabNeedServer")}
        </motion.p>
      ) : null}
    </div>
  );
}
