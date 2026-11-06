import { Link } from "react-router-dom";
import { SlidersHorizontal } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

export default function SettingsBreadcrumb({ current }: { current: string }) {
  const { t } = useI18n();
  return (
    <div className="glass flex flex-wrap items-center gap-2 rounded-2xl px-3.5 py-2.5 shadow-glass">
      <h1 className="text-sm font-semibold tracking-tight text-slate-800 dark:text-slate-100">
        {current}
      </h1>
      <span className="flex-1" />
      <Link to="/settings" className="btn-quiet px-2 py-1 text-[10.5px]">
        <SlidersHorizontal size={11} />
        {t("server.backToProfile")}
      </Link>
    </div>
  );
}
