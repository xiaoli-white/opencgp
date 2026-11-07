import { useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, Loader2, Save, Share2, X } from "lucide-react";
import clsx from "clsx";
import { API_BASE } from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";

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
  const { t } = useI18n();
  const entries = useMemo(
    () =>
      Object.entries(value)
        .filter(([, level]) => Boolean(level))
        .map(([user_id, level]) => ({ user_id, level: level as string })),
    [value],
  );

  // Esc closes the panel, matching every other dialog in the app.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const granted = entries.length;
  const descriptionKeys = options.filter((item) => item.desc);

  return createPortal(
    <AnimatePresence>
      {open ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-40 flex justify-end bg-slate-900/50 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label={title}
            initial={{ x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            onClick={(event) => event.stopPropagation()}
            className="flex h-[100dvh] max-h-[100dvh] w-full flex-col bg-white shadow-2xl dark:bg-slate-900 sm:max-w-md sm:rounded-l-3xl"
          >
            {/* header */}
            <div className="flex shrink-0 items-start justify-between gap-2 border-b border-slate-200/80 px-4 py-3 dark:border-white/10">
              <div className="flex min-w-0 items-start gap-2">
                <Share2
                  size={15}
                  className="mt-0.5 shrink-0 text-indigo-500 dark:text-indigo-300"
                />
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
                    {title}
                  </h2>
                  {subtitle ? (
                    <p className="mt-0.5 text-[10.5px] leading-relaxed text-slate-400">
                      {subtitle}
                    </p>
                  ) : null}
                </div>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="btn-quiet shrink-0 px-1.5"
                aria-label={t("sharing.close")}
              >
                <X size={14} />
              </button>
            </div>

            {/* scrollable body */}
            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3">
              {note ? (
                <p className="rounded-2xl border border-slate-200/80 bg-slate-50 px-3 py-2 text-[10.5px] leading-relaxed text-slate-500 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-400">
                  {note}
                </p>
              ) : null}

              {error ? (
                <div className="flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
                  <AlertCircle size={13} className="mt-0.5 shrink-0" />
                  <span className="min-w-0 flex-1 break-words">{error}</span>
                </div>
              ) : null}

              {loading ? (
                <p className="flex items-center gap-2 px-1 py-2 text-[11px] text-slate-400">
                  <Loader2 size={12} className="animate-spin" />
                  {t("sharing.loading")}
                </p>
              ) : members.length === 0 ? (
                <p className="rounded-2xl border border-dashed border-slate-300 px-3 py-3 text-[11px] text-slate-500 dark:border-white/15 dark:text-slate-400">
                  {t("sharing.noMembers")}
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
                      className={clsx(
                        "flex items-center gap-2.5 rounded-2xl border px-3 py-2 transition",
                        current
                          ? "border-indigo-200 bg-indigo-50/60 dark:border-indigo-400/30 dark:bg-indigo-400/10"
                          : "border-slate-200/80 bg-white dark:border-white/10 dark:bg-white/[0.03]",
                      )}
                    >
                      {member.avatar_url ? (
                        <img
                          src={
                            member.avatar_url.startsWith("http")
                              ? member.avatar_url
                              : `${API_BASE}${member.avatar_url}`
                          }
                          alt={label}
                          className="h-8 w-8 shrink-0 rounded-full object-cover"
                        />
                      ) : (
                        <span className="brand-gradient grid h-8 w-8 shrink-0 place-items-center rounded-full text-[11px] font-semibold text-white">
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
                        aria-label={`${label} · ${t("sharing.permissionLabel")}`}
                        className={clsx(
                          "select w-[96px] shrink-0 px-2 py-1 text-[11px]",
                          current
                            ? "border-indigo-300 text-indigo-700 dark:border-indigo-400/40 dark:text-indigo-200"
                            : "text-slate-500 dark:text-slate-300",
                        )}
                      >
                        <option value="">{t("sharing.noPermission")}</option>
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

              {/* one legend only: shown when the caller did not pass a note */}
              {!note && descriptionKeys.length > 0 ? (
                <div className="flex flex-wrap gap-x-3 gap-y-1 px-1 pt-1 text-[10px] text-slate-400">
                  {descriptionKeys.map((item) => (
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
            </div>

            {/* sticky footer */}
            <div className="flex shrink-0 items-center justify-between gap-2 border-t border-slate-200/80 bg-white px-4 py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] dark:border-white/10 dark:bg-slate-900">
              <span className="text-[10.5px] text-slate-400">
                {t("sharing.authorized", { count: granted })}
              </span>
              <div className="flex items-center gap-2">
                <button type="button" onClick={onClose} className="btn btn-ghost">
                  {t("common.cancel")}
                </button>
                <button
                  type="button"
                  onClick={() => void onSave(entries)}
                  disabled={saving || loading}
                  className="btn btn-primary"
                >
                  {saving ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Save size={13} />
                  )}
                  {t("common.save")}
                </button>
              </div>
            </div>
          </motion.aside>
        </motion.div>
      ) : null}
    </AnimatePresence>,
    document.body,
  );
}
