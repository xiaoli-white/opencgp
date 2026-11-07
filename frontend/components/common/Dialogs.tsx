import { type ReactNode, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Loader2, MoreHorizontal, X } from "lucide-react";
import clsx from "clsx";
import { useI18n } from "@/i18n/I18nProvider";

export function Modal({
  open,
  title,
  subtitle,
  onClose,
  children,
  wide,
  inline = false,
  layer = "z-[70]",
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  /** Render as an in-flow card instead of a floating overlay. */
  inline?: boolean;
  layer?: string;
}) {
  const { t } = useI18n();
  useEffect(() => {
    if (!open) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const head = (
    <div className="mb-3 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</h2>
        {subtitle ? (
          <p className="mt-1 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
            {subtitle}
          </p>
        ) : null}
      </div>
      <button
        type="button"
        onClick={onClose}
        className="btn-quiet grid h-8 w-8 shrink-0 place-items-center rounded-full"
        aria-label={t("dialogs.close")}
      >
        <X size={14} />
      </button>
    </div>
  );

  return (
    <AnimatePresence>
      {open ? (
        inline ? (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className={clsx(
              "glass w-full overflow-hidden rounded-2xl border border-white/60 p-5 shadow-glass dark:border-white/10",
              wide ? "max-w-none" : "max-w-none sm:max-w-xl",
            )}
          >
            {head}
            {children}
          </motion.div>
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={
              "fixed inset-0 flex items-end justify-center bg-slate-900/40 p-0 backdrop-blur-sm sm:items-center sm:p-6 " +
              layer
            }
            onClick={onClose}
          >
            <motion.div
              initial={{ y: 16, opacity: 0, scale: 0.99 }}
              animate={{ y: 0, opacity: 1, scale: 1 }}
              exit={{ y: 10, opacity: 0 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              onClick={(event) => event.stopPropagation()}
              className={clsx(
                "glass max-h-[92vh] w-full overflow-y-auto rounded-t-3xl border border-white/50 p-5 shadow-glass dark:border-white/10 sm:rounded-3xl",
                wide ? "sm:max-w-2xl" : "sm:max-w-md",
              )}
            >
              {head}
              {children}
            </motion.div>
          </motion.div>
        )
      ) : null}
    </AnimatePresence>
  );
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  requireText,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  requireText?: string;
  busy?: boolean;
  error?: string;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [typed, setTyped] = useState("");

  useEffect(() => {
    if (open) setTyped("");
  }, [open]);

  const ready = !requireText || typed.trim() === requireText;

  return (
    <Modal open={open} title={title} onClose={onClose}>
      <div className="space-y-3">
        {description ? (
          <p className="flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] leading-relaxed text-rose-700 dark:text-rose-300">
            <AlertTriangle size={13} className="mt-0.5 shrink-0" />
            <span>{description}</span>
          </p>
        ) : null}
        {requireText ? (
          <label className="block text-[11px] text-slate-500 dark:text-slate-400">
            {t("common.confirmTyping", { name: requireText })}
            <input
              autoFocus
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              className="input mt-1"
              placeholder={requireText}
            />
          </label>
        ) : null}
        {error ? (
          <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
            {error}
          </p>
        ) : null}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn btn-quiet">
            {t("dialogs.cancel")}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!ready || busy}
            className="btn bg-rose-500 text-white shadow-[0_10px_22px_-14px_rgba(244,63,94,0.9)] hover:bg-rose-600 disabled:opacity-50"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : null}
            {confirmLabel || t("dialogs.confirmDelete")}
          </button>
        </div>
      </div>
    </Modal>
  );
}

export function PromptDialog({
  open,
  title,
  label,
  initial = "",
  placeholder,
  confirmLabel,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  label: string;
  initial?: string;
  placeholder?: string;
  confirmLabel?: string;
  busy?: boolean;
  error?: string;
  onConfirm: (value: string) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [value, setValue] = useState(initial);

  useEffect(() => {
    if (open) setValue(initial);
  }, [open, initial]);

  return (
    <Modal open={open} title={title} onClose={onClose}>
      <div className="space-y-3">
        <label className="block text-[11px] text-slate-500 dark:text-slate-400">
          {label}
          <input
            autoFocus
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder={placeholder}
            className="input mt-1"
          />
        </label>
        {error ? (
          <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
            {error}
          </p>
        ) : null}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn btn-quiet">
            {t("dialogs.cancel")}
          </button>
          <button
            type="button"
            onClick={() => onConfirm(value.trim())}
            disabled={!value.trim() || busy}
            className="btn btn-primary"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : null}
            {confirmLabel || t("dialogs.save")}
          </button>
        </div>
      </div>
    </Modal>
  );
}

export type MenuItem = {
  label: string;
  icon?: ReactNode;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
};

export function RowMenu({
  items,
  align = "right",
  label,
}: {
  items: MenuItem[];
  align?: "left" | "right";
  label?: string;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", handler);
    return () => window.removeEventListener("mousedown", handler);
  }, [open]);

  if (items.length === 0) return null;

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setOpen((prev) => !prev);
        }}
        className="grid h-7 w-7 place-items-center rounded-lg text-slate-400 transition hover:bg-white/70 hover:text-indigo-600 dark:hover:bg-white/10 dark:hover:text-indigo-300"
        aria-label={label || t("dialogs.actions")}
      >
        <MoreHorizontal size={14} />
      </button>
      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.14 }}
            className={clsx(
              "absolute top-8 z-40 w-40 overflow-hidden rounded-xl border border-white/60 bg-white/90 p-1 shadow-glass backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/90",
              align === "right" ? "right-0" : "left-0",
            )}
          >
            {items.map((item) => (
              <button
                key={item.label}
                type="button"
                disabled={item.disabled}
                onClick={(event) => {
                  event.stopPropagation();
                  setOpen(false);
                  item.onClick();
                }}
                className={clsx(
                  "flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-[11.5px] transition disabled:opacity-40",
                  item.danger
                    ? "text-rose-600 hover:bg-rose-500/10 dark:text-rose-300"
                    : "text-slate-600 hover:bg-indigo-500/10 hover:text-indigo-700 dark:text-slate-300 dark:hover:text-indigo-200",
                )}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
