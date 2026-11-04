import { useCallback, useEffect, useState } from "react";
import { ChevronDown, Loader2, MessagesSquare, Pencil, Trash2 } from "lucide-react";
import clsx from "clsx";
import { api, type ThreadSummary } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { ConfirmDialog, PromptDialog } from "@/components/common/Dialogs";
import { useI18n } from "@/i18n/I18nProvider";

export default function ThreadsPanel({
  courseId,
  canWrite,
  onNotice,
  onError,
}: {
  courseId: string;
  canWrite: boolean;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<ThreadSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [renaming, setRenaming] = useState<ThreadSummary | null>(null);
  const [removing, setRemoving] = useState<ThreadSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listThreads();
      setItems(data.threads.filter((item) => !courseId || item.course_id === courseId));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("course.threads.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [courseId, onError]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const rename = async (title: string) => {
    if (!renaming) return;
    setBusy(true);
    setDialogError("");
    try {
      await api.renameThread(renaming.id, title);
      setRenaming(null);
      onNotice(t("course.threads.renamed"));
      await load();
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("course.errors.rename"));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!removing) return;
    setBusy(true);
    setDialogError("");
    try {
      await api.deleteThread(removing.id);
      setRemoving(null);
      onNotice(t("course.threads.deleted"));
      await load();
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("course.errors.delete"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="glass rounded-3xl p-4 shadow-glass">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
          <MessagesSquare size={12} />
          {t("course.threads.title")}
        </span>
        <span className="flex items-center gap-1.5 text-[10px] text-slate-400 dark:text-slate-500">
          {loading ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            t("course.threads.count", { count: items.length })
          )}
          <ChevronDown
            size={13}
            className={clsx("transition", open && "rotate-180")}
          />
        </span>
      </button>
      {open ? (
        <div className="mt-2.5 space-y-1.5">
          {items.length === 0 ? (
            <p className="px-1 py-2 text-[11px] text-slate-400 dark:text-slate-500">
              {t("course.threads.empty")}
            </p>
          ) : (
            items.map((thread) => (
              <div
                key={thread.id}
                className="flex items-center gap-2 rounded-xl border border-white/45 bg-white/45 px-2.5 py-2 dark:border-white/10 dark:bg-white/[0.04]"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[11.5px] font-medium text-slate-700 dark:text-slate-200">
                    {thread.title}
                  </p>
                  <p className="mt-0.5 text-[10px] text-slate-400 dark:text-slate-500">
                    {t("course.threads.messages", {
                      count: thread.message_count ?? 0,
                    })}{" "}
                    · {formatRelative(thread.updated_at)}
                  </p>
                </div>
                {canWrite ? (
                  <div className="flex shrink-0 items-center gap-0.5">
                    <button
                      type="button"
                      onClick={() => {
                        setDialogError("");
                        setRenaming(thread);
                      }}
                      className="grid h-7 w-7 place-items-center rounded-lg text-slate-400 transition hover:bg-white/70 hover:text-indigo-600 dark:hover:bg-white/10 dark:hover:text-indigo-300"
                      aria-label={t("course.threads.renameTitle")}
                    >
                      <Pencil size={12} />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setDialogError("");
                        setRemoving(thread);
                      }}
                      className="grid h-7 w-7 place-items-center rounded-lg text-slate-400 transition hover:bg-rose-500/10 hover:text-rose-600"
                      aria-label={t("course.threads.deleteTitle")}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ) : null}
              </div>
            ))
          )}
        </div>
      ) : null}

      <PromptDialog
        open={Boolean(renaming)}
        title={t("course.threads.renameTitle")}
        label={t("course.threads.nameLabel")}
        initial={renaming?.title ?? ""}
        busy={busy}
        error={dialogError}
        onConfirm={(value) => void rename(value)}
        onClose={() => setRenaming(null)}
      />
      <ConfirmDialog
        open={Boolean(removing)}
        title={t("course.threads.deleteTitle")}
        description={t("course.threads.deleteDesc", {
          title: removing?.title ?? "",
        })}
        busy={busy}
        error={dialogError}
        onConfirm={() => void remove()}
        onClose={() => setRemoving(null)}
      />
    </section>
  );
}
