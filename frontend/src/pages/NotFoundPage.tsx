import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Compass, Home } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

export default function NotFoundPage() {
  const { t } = useI18n();

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="glass relative w-full max-w-lg overflow-hidden rounded-[2rem] p-8 text-center shadow-glass sm:p-10"
      >
        <div className="pointer-events-none absolute -right-16 -top-20 h-48 w-48 rounded-full bg-gradient-to-br from-indigo-400/30 to-violet-400/20 blur-3xl" />
        <div className="relative">
          <span className="brand-gradient mx-auto grid h-12 w-12 place-items-center rounded-2xl text-white shadow-brand">
            <Compass size={22} />
          </span>
          <p className="mt-5 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">
            404
          </p>
          <h1 className="mt-1.5 text-[22px] font-semibold tracking-tight text-slate-900 dark:text-white">
            {t("notFound.title")}
          </h1>
          <p className="mt-2 font-reading text-[14px] leading-relaxed text-slate-600 dark:text-slate-300">
            {t("notFound.desc")}
          </p>
          <Link to="/" className="btn btn-primary mt-6">
            <Home size={15} />
            {t("notFound.back")}
          </Link>
        </div>
      </motion.section>
    </div>
  );
}
