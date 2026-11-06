import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2, X } from "lucide-react";
import { api, type Piece, type MediaAsset } from "@/lib/api";
import { assetMarkdown, assetSrc, formatBytes } from "@/lib/media";
import { useI18n } from "@/i18n/I18nProvider";

type ImagePickerDrawerProps = {
  open: boolean;
  piece: Piece | null;
  onClose: () => void;
  onInserted: (message: string) => void;
};

export default function ImagePickerDrawer({
  open,
  piece,
  onClose,
  onInserted,
}: ImagePickerDrawerProps) {
  const { t } = useI18n();
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [busyId, setBusyId] = useState("");

  useEffect(() => {
    if (!open) return;
    setError("");
    setSectionId(piece?.outline[piece.outline.length - 1]?.id ?? "");
    setLoading(true);
    let alive = true;
    void api
      .listMedia({ limit: 60 })
      .then((data) => {
        if (alive) setAssets(data.assets);
      })
      .catch((err) => {
        if (alive)
          setError(err instanceof Error ? err.message : t("media.loadFailed"));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [open, piece]);

  const insert = useCallback(
    async (asset: MediaAsset) => {
      if (!piece || !sectionId) return;
      setBusyId(asset.id);
      setError("");
      try {
        const fresh = await api.getPiece(piece.id);
        const section = fresh.outline.find((item) => item.id === sectionId);
        if (!section) throw new Error(t("media.sectionMissing"));
        const merged = `${section.content ?? ""}\n\n${assetMarkdown(asset)}\n`.trim();
        await api.updatePieceSection(fresh.id, sectionId, { content: merged });
        onInserted(t("media.insertedSection", { section: section.title }));
        onClose();
      } catch (err) {
        setError(err instanceof Error ? err.message : t("media.insertFailed"));
      } finally {
        setBusyId("");
      }
    },
    [piece, sectionId, onInserted, onClose, t],
  );

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[70] flex justify-end bg-slate-900/40 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.aside
            initial={{ x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            onClick={(event) => event.stopPropagation()}
            className="glass h-full w-full overflow-y-auto p-4 shadow-glass sm:max-w-md"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                  {t("media.pickerTitle")}
                </h2>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
                  {t("media.pickerSubtitle")}
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="btn-quiet grid h-8 w-8 shrink-0 place-items-center rounded-full"
                aria-label={t("common.close")}
              >
                <X size={14} />
              </button>
            </div>

            <label className="mt-3 block">
              <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                {t("media.fieldSection")}
              </span>
              <select
                value={sectionId}
                onChange={(event) => setSectionId(event.target.value)}
                className="select w-full"
              >
                {piece?.outline.length ? null : (
                  <option value="">{t("media.noSections")}</option>
                )}
                {piece?.outline.map((section, index) => (
                  <option key={section.id} value={section.id}>
                    {index + 1}. {section.title}
                  </option>
                ))}
              </select>
            </label>

            {error ? (
              <p className="mt-2 rounded-xl bg-rose-500/10 px-2.5 py-2 text-[11px] leading-relaxed text-rose-600 dark:text-rose-300">
                {error}
              </p>
            ) : null}

            {loading ? (
              <div className="mt-6 text-center text-[11px] text-slate-400 dark:text-slate-500">
                <Loader2 size={16} className="mx-auto animate-spin" />
              </div>
            ) : assets.length === 0 ? (
              <p className="mt-6 rounded-2xl border border-dashed border-white/60 p-6 text-center text-[11px] text-slate-400 dark:border-white/10 dark:text-slate-500">
                {t("media.emptyLibrary")}
              </p>
            ) : (
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {assets.map((asset) => (
                  <button
                    key={asset.id}
                    type="button"
                    onClick={() => void insert(asset)}
                    disabled={Boolean(busyId) || !sectionId}
                    className="group overflow-hidden rounded-2xl border border-white/50 bg-white/50 text-left transition hover:border-indigo-400/60 dark:border-white/10 dark:bg-white/[0.04]"
                  >
                    <span className="block aspect-[4/3] overflow-hidden bg-slate-500/5">
                      <img
                        src={assetSrc(asset)}
                        alt={asset.prompt || t("media.imageAlt")}
                        loading="lazy"
                        className="h-full w-full object-cover"
                      />
                    </span>
                    <span className="block px-1.5 py-1 text-[10px] text-slate-500 dark:text-slate-400">
                      {busyId === asset.id ? (
                        <span className="flex items-center gap-1">
                          <Loader2 size={10} className="animate-spin" />{" "}
                          {t("media.inserting")}
                        </span>
                      ) : (
                        <span className="block truncate">
                          {formatBytes(asset.bytes)} · {asset.width}×{asset.height}
                        </span>
                      )}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </motion.aside>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
