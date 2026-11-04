import { useCallback, useEffect, useState } from "react";
import { Database, Loader2, Pencil, Trash2 } from "lucide-react";
import { api, type KbSource } from "@/lib/api";
import { formatChars, formatDateTime } from "@/lib/format";
import { ConfirmDialog, PromptDialog } from "@/components/common/Dialogs";
import { useI18n } from "@/i18n/I18nProvider";

export default function SourcesCard({
  refreshKey,
  canWrite,
  onNotice,
  onError,
}: {
  refreshKey: number;
  canWrite: boolean;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { t } = useI18n();
  const [items, setItems] = useState<KbSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [renaming, setRenaming] = useState<KbSource | null>(null);
  const [removing, setRemoving] = useState<KbSource | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listKbSources();
      setItems(data.sources);
    } catch (err) {
      onError(err instanceof Error ? err.message : t("kb.sourcesLoadFailed"));
    } finally {
      setLoading(false);
    }
  }, [onError, t]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const rename = async (value: string) => {
    if (!renaming) return;
    setBusy(true);
    setDialogError("");
    try {
      await api.renameKbSource(renaming.source_id, value);
      setRenaming(null);
      onNotice(t("kb.sourceRenamed"));
      await load();
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("kb.renameFailed"));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!removing) return;
    setBusy(true);
    setDialogError("");
    try {
      await api.deleteKbSource(removing.source_id);
      setRemoving(null);
      onNotice(t("kb.sourceDeleted"));
      await load();
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("kb.deleteFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="glass rounded-3xl p-5 shadow-glass">
      <div className="flex items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-xl bg-indigo-500/12 text-indigo-600 dark:text-indigo-300">
          <Database size={15} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
            {t("kb.sourcesTitle")}
            <span className="chip-muted ml-1.5">{items.length}</span>
          </p>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            {t("kb.sourcesDesc")}
          </p>
        </div>
        {loading ? (
          <Loader2 size={13} className="animate-spin text-slate-400" />
        ) : null}
      </div>

      <div className="mt-3 space-y-1.5">
        {items.length === 0 && !loading ? (
          <p className="rounded-2xl border border-dashed border-white/60 bg-white/40 px-3 py-3 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-400">
            {t("kb.sourcesEmpty")}
          </p>
        ) : (
          items.map((source) => (
            <div
              key={source.source_id}
              className="flex items-center gap-2 rounded-2xl border border-white/50 bg-white/45 px-3 py-2 dark:border-white/10 dark:bg-white/[0.04]"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12px] font-medium text-slate-700 dark:text-slate-200">
                  {source.source_name}
                </p>
                <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px] text-slate-400 dark:text-slate-500">
                  <span>{t("kb.chunkCount", { count: source.chunk_count })}</span>
                  <span>·</span>
                  <span>{formatChars(source.char_count)}</span>
                  <span>·</span>
                  <span>{formatDateTime(source.created_at)}</span>
                </p>
              </div>
              {canWrite ? (
                <div className="flex shrink-0 items-center gap-0.5">
                  <button
                    type="button"
                    onClick={() => {
                      setDialogError("");
                      setRenaming(source);
                    }}
                    className="grid h-7 w-7 place-items-center rounded-lg text-slate-400 transition hover:bg-white/70 hover:text-indigo-600 dark:hover:bg-white/10 dark:hover:text-indigo-300"
                    aria-label={t("kb.renameSource")}
                  >
                    <Pencil size={12} />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setDialogError("");
                      setRemoving(source);
                    }}
                    className="grid h-7 w-7 place-items-center rounded-lg text-slate-400 transition hover:bg-rose-500/10 hover:text-rose-600"
                    aria-label={t("kb.deleteSource")}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ) : null}
            </div>
          ))
        )}
      </div>

      <PromptDialog
        open={Boolean(renaming)}
        title={t("kb.renameSource")}
        label={t("kb.sourceNameLabel")}
        initial={renaming?.source_name ?? ""}
        busy={busy}
        error={dialogError}
        onConfirm={(value) => void rename(value)}
        onClose={() => setRenaming(null)}
      />
      <ConfirmDialog
        open={Boolean(removing)}
        title={t("kb.deleteSource")}
        description={t("kb.deleteSourceDesc", {
          name: removing?.source_name ?? "",
          count: removing?.chunk_count ?? 0,
        })}
        busy={busy}
        error={dialogError}
        onConfirm={() => void remove()}
        onClose={() => setRemoving(null)}
      />
    </section>
  );
}
