import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { api, type Piece, type MediaAsset } from "@/lib/api";
import { assetMarkdown, assetSrc } from "@/lib/media";
import { useI18n } from "@/i18n/I18nProvider";
import { Modal } from "@/components/common/Dialogs";

type ImageInsertDialogProps = {
  asset: MediaAsset | null;
  lockedPieceId?: string;
  initialSectionId?: string;
  onClose: () => void;
  onInserted: (message: string) => void;
};

export default function ImageInsertDialog({
  asset,
  lockedPieceId,
  initialSectionId,
  onClose,
  onInserted,
}: ImageInsertDialogProps) {
  const { t } = useI18n();
  const [pieces, setPieces] = useState<Piece[]>([]);
  const [pieceId, setPieceId] = useState(lockedPieceId ?? "");
  const [detail, setDetail] = useState<Piece | null>(null);
  const [sectionId, setSectionId] = useState(initialSectionId ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const open = Boolean(asset);

  useEffect(() => {
    if (!open) return;
    setError("");
    setSectionId(initialSectionId ?? "");
    if (lockedPieceId) {
      setPieceId(lockedPieceId);
      return;
    }
    let alive = true;
    void api
      .listPieces()
      .then((data) => {
        if (!alive) return;
        setPieces(data.pieces);
        setPieceId((current) => current || data.pieces[0]?.id || "");
      })
      .catch((err) => {
        if (alive)
          setError(
            err instanceof Error ? err.message : t("media.piecesLoadFailed"),
          );
      });
    return () => {
      alive = false;
    };
  }, [open, lockedPieceId, initialSectionId]);

  useEffect(() => {
    if (!open || !pieceId) {
      setDetail(null);
      return;
    }
    let alive = true;
    void api
      .getPiece(pieceId)
      .then((data) => {
        if (!alive) return;
        setDetail(data);
        setSectionId((current) => {
          if (current && data.outline.some((item) => item.id === current)) return current;
          return data.outline[data.outline.length - 1]?.id ?? "";
        });
      })
      .catch((err) => {
        if (alive)
          setError(
            err instanceof Error ? err.message : t("media.pieceLoadFailed"),
          );
      });
    return () => {
      alive = false;
    };
  }, [open, pieceId]);

  const submit = async () => {
    if (!asset || !pieceId || !sectionId) return;
    setBusy(true);
    setError("");
    try {
      const fresh = await api.getPiece(pieceId);
      const section = fresh.outline.find((item) => item.id === sectionId);
      if (!section) throw new Error(t("media.sectionMissing"));
      const merged = `${section.content ?? ""}\n\n${assetMarkdown(asset)}\n`.trim();
      await api.updatePieceSection(pieceId, sectionId, { content: merged });
      onInserted(
        t("media.inserted", { title: fresh.title, section: section.title }),
      );
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("media.insertFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title={t("media.insertTitle")}
      subtitle={t("media.insertSubtitle")}
      onClose={onClose}
    >
      <div className="space-y-3">
        {asset ? (
          <div className="flex items-center gap-2.5 rounded-2xl border border-white/50 bg-white/50 p-2 dark:border-white/10 dark:bg-white/[0.04]">
            <img
              src={assetSrc(asset)}
              alt={asset.prompt || t("media.imageAlt")}
              className="h-12 w-16 shrink-0 rounded-xl object-cover"
            />
            <p className="min-w-0 flex-1 truncate text-[11px] text-slate-500 dark:text-slate-400">
              {asset.prompt || asset.id}
            </p>
          </div>
        ) : null}

        {lockedPieceId ? null : (
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
              {t("media.fieldPiece")}
            </span>
            <select
              value={pieceId}
              onChange={(event) => setPieceId(event.target.value)}
              className="select w-full"
            >
              {pieces.length === 0 ? (
                <option value="">{t("media.noPieces")}</option>
              ) : null}
              {pieces.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
        )}

        <label className="block">
          <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
            {t("media.fieldSection")}
          </span>
          <select
            value={sectionId}
            onChange={(event) => setSectionId(event.target.value)}
            className="select w-full"
          >
            {detail?.outline.length ? null : (
              <option value="">{t("media.selectSection")}</option>
            )}
            {detail?.outline.map((section, index) => (
              <option key={section.id} value={section.id}>
                {index + 1}. {section.title}
              </option>
            ))}
          </select>
        </label>

        {error ? (
          <p className="rounded-xl bg-rose-500/10 px-2.5 py-2 text-[11px] leading-relaxed text-rose-600 dark:text-rose-300">
            {error}
          </p>
        ) : null}

        <div className="flex items-center justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="btn btn-quiet">
            {t("common.cancel")}
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || !pieceId || !sectionId}
            className="btn btn-primary"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : null}
            {t("media.insert")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
