import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Lock } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

type NoAccessCardProps = {
  title?: string;
  message?: string;
  backTo?: string;
  backLabel?: string;
};

export default function NoAccessCard({
  title,
  message,
  backTo = "/",
  backLabel,
}: NoAccessCardProps) {
  const { t } = useI18n();
  return (
    <div className="mx-auto w-full max-w-2xl">
      <motion.section
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-3xl p-8 text-center shadow-glass"
      >
        <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-slate-500/12 text-slate-500 dark:text-slate-300">
          <Lock size={20} />
        </span>
        <h2 className="mt-4 text-base font-semibold tracking-tight text-slate-900 dark:text-white">
          {title ?? t("noAccess.title")}
        </h2>
        <p className="mx-auto mt-2 max-w-md text-[12px] leading-relaxed text-slate-500 dark:text-slate-400">
          {message ?? t("noAccess.message")}
        </p>
        <Link to={backTo} className="btn btn-primary mt-5">
          <ArrowLeft size={14} />
          {backLabel ?? t("noAccess.back")}
        </Link>
      </motion.section>
    </div>
  );
}
