import { Link } from "react-router-dom";
import { ChevronLeft, SlidersHorizontal } from "lucide-react";

export default function SettingsBreadcrumb({ current }: { current: string }) {
  return (
    <div className="glass flex flex-wrap items-center gap-2 rounded-2xl px-3.5 py-2.5 shadow-glass">
      <Link
        to="/settings"
        className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-600 transition hover:text-indigo-700 dark:text-indigo-300 dark:hover:text-indigo-200"
      >
        <ChevronLeft size={12} />
        设置
      </Link>
      <span className="text-[11px] text-slate-300 dark:text-slate-600">/</span>
      <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-200">
        {current}
      </span>
      <span className="flex-1" />
      <Link to="/settings" className="btn-quiet px-2 py-1 text-[10.5px]">
        <SlidersHorizontal size={11} />
        返回个人设置
      </Link>
    </div>
  );
}
