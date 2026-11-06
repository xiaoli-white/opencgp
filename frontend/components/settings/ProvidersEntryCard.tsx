import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Settings2 } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

type Props = {
  canManageServer: boolean;
  server?: boolean;
};

export default function ProvidersEntryCard({ canManageServer, server = false }: Props) {
  const { t } = useI18n();
  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-3xl p-5 shadow-glass"
    >
      <div className="flex flex-wrap items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-2xl bg-indigo-500/12 text-indigo-600 dark:text-indigo-300">
          <Settings2 size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
            {t("providersHub.title")}
          </h2>
          <p className="mt-1 text-[10.5px] leading-relaxed text-slate-500 dark:text-slate-400">
            {server ? t("providersHub.serverHint") : t("providersHub.desc")}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="chip-muted">{t("providersHub.tabLlm")}</span>
            <span className="chip-muted">{t("providersHub.tabEmbedding")}</span>
            <span className="chip-muted">{t("providersHub.tabRerank")}</span>
            <span className="chip-muted">{t("providersHub.tabWeights")}</span>
            {canManageServer ? (
              <span className="chip bg-emerald-500/10 text-emerald-600 dark:text-emerald-300">
                {t("providersHub.serverAvailable")}
              </span>
            ) : null}
          </div>
        </div>
        <Link
          to="/settings/providers"
          className="btn btn-primary shrink-0 px-3 py-1.5 text-[11px]"
        >
          {t("providersHub.open")}
          <ArrowRight size={12} />
        </Link>
      </div>
    </motion.section>
  );
}
