import { useMemo } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, Loader2, Save, Share2, X } from "lucide-react";
import clsx from "clsx";
import { API_BASE } from "@/lib/api";

export type ShareMember = {
  user_id: string;
  user_email: string;
  user_display_name: string;
  avatar_url?: string;
  note?: string;
};

export type ShareOption = {
  value: string;
  label: string;
  desc?: string;
};

type Props = {
  open: boolean;
  title: string;
  subtitle?: string;
  note?: string;
  members: ShareMember[];
  value: Record<string, string | null>;
  options: ShareOption[];
  loading?: boolean;
  saving?: boolean;
  error?: string;
  onClose: () => void;
  onChange: (userId: string, level: string | null) => void;
  onSave: (entries: { user_id: string; level: string }[]) => void | Promise<void>;
};

export default function SharePanel({
  open,
  title,
  subtitle,
  note,
  members,
  value,
  options,
  loading = false,
  saving = false,
  error,
  onClose,
  onChange,
  onSave,
}: Props) {
  const entries = useMemo(
    () =>
      Object.entries(value)
        .filter(([, level]) => Boolean(level))
        .map(([user_id, level]) => ({ user_id, level: level as string })),
    [value],
  );

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-40 flex justify-end bg-slate-900/25 backdrop-blur-[2px]"
          onClick={onClose}
        >
          <motion.aside
            initial={{ x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            onClick={(event) => event.stopPropagation()}
            className="glass no-scrollbar h-full w-full overflow-y-auto p-4 pb-24 shadow-glass sm:max-w-md sm:p-5"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex min-w-0 items-start gap-2">
                <Share2 size={15} className="mt-0.5 shrink-0 text-indigo-500 dark:text-indigo-300" />
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
                    {title}
                  </h2>
                  {subtitle ? (
                    <p className="mt-0.5 truncate text-[10.5px] text-slate-400">{subtitle}</p>
                  ) : null}
                </div>
              </div>
              <button type="button" onClick={onClose} className="btn-quiet shrink-0 px-1.5" aria-label="关闭">
                <X size={14} />
              </button>
            </div>

            {note ? (
              <p className="mt-2 rounded-2xl border border-white/50 bg-white/45 px-3 py-2 text-[10.5px] leading-relaxed text-slate-500 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-400">
                {note}
              </p>
            ) : null}

            {error ? (
              <div className="mt-3 flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
                <AlertCircle size={13} className="mt-0.5 shrink-0" />
                <span className="flex-1 break-words">{error}</span>
              </div>
            ) : null}

            <div className="mt-3 space-y-1.5">
              {loading ? (
                <p className="flex items-center gap-2 text-[11px] text-slate-400">
                  <Loader2 size={12} className="animate-spin" />
                  加载中…
                </p>
              ) : members.length === 0 ? (
                <p className="rounded-2xl border border-dashed border-white/60 bg-white/40 px-3 py-3 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-400">
                  当前空间暂无其他成员。
                </p>
              ) : (
                members.map((member) => {
                  const current = value[member.user_id] ?? "";
                  const label =
                    member.user_display_name || member.user_email || member.user_id;
                  const initial = (label || "?").slice(0, 1).toUpperCase();
                  return (
                    <div
                      key={member.user_id}
                      className="flex items-center gap-2 rounded-2xl border border-white/50 bg-white/45 px-3 py-2 dark:border-white/10 dark:bg-white/[0.04]"
                    >
                      {member.avatar_url ? (
                        <img
                          src={
                            member.avatar_url.startsWith("http")
                              ? member.avatar_url
                              : `${API_BASE}${member.avatar_url}`
                          }
                          alt={label}
                          className="h-7 w-7 shrink-0 rounded-full object-cover"
                        />
                      ) : (
                        <span className="brand-gradient grid h-7 w-7 shrink-0 place-items-center rounded-full text-[11px] font-semibold text-white">
                          {initial}
                        </span>
                      )}
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12px] font-medium text-slate-800 dark:text-slate-100">
                          {label}
                        </span>
                        <span className="block truncate text-[10px] text-slate-400">
                          {member.user_email}
                          {member.note ? ` · ${member.note}` : ""}
                        </span>
                      </span>
                      <select
                        value={current}
                        onChange={(event) =>
                          onChange(member.user_id, event.target.value || null)
                        }
                        className={clsx(
                          "select shrink-0 py-1 text-[11px]",
                          current ? "text-indigo-600 dark:text-indigo-300" : "",
                        )}
                      >
                        <option value="">无权限</option>
                        {options.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  );
                })
              )}
            </div>

            {options.some((item) => item.desc) ? (
              <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-slate-400">
                {options
                  .filter((item) => item.desc)
                  .map((item) => (
                    <span key={item.value}>
                      <span className="font-medium text-slate-500 dark:text-slate-300">
                        {item.label}
                      </span>
                      {" · "}
                      {item.desc}
                    </span>
                  ))}
              </div>
            ) : null}

            <div className="mt-4 flex items-center justify-between gap-2">
              <span className="text-[10px] text-slate-400">已授权 {entries.length} 人</span>
              <button
                type="button"
                onClick={() => void onSave(entries)}
                disabled={saving || loading}
                className="btn btn-primary"
              >
                {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                保存
              </button>
            </div>
          </motion.aside>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
