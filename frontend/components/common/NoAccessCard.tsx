import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Lock } from "lucide-react";

type NoAccessCardProps = {
  title?: string;
  message?: string;
  backTo?: string;
  backLabel?: string;
};

export default function NoAccessCard({
  title = "需要访问权限",
  message = "当前角色没有访问该页面的权限，请联系空间管理员申请。",
  backTo = "/",
  backLabel = "返回创作工作台",
}: NoAccessCardProps) {
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
          {title}
        </h2>
        <p className="mx-auto mt-2 max-w-md text-[12px] leading-relaxed text-slate-500 dark:text-slate-400">
          {message}
        </p>
        <Link to={backTo} className="btn btn-primary mt-5">
          <ArrowLeft size={14} />
          {backLabel}
        </Link>
      </motion.section>
    </div>
  );
}
