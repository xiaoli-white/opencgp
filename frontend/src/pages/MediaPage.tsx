import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import clsx from "clsx";
import {
  Check,
  Copy,
  Download,
  ImagePlus,
  Loader2,
  RefreshCw,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import {
  ApiError,
  api,
  mediaUrl,
  type MediaAsset,
} from "@/lib/api";
import { assetMarkdown, assetSrc, formatBytes, formatStamp } from "@/lib/media";
import { useSession } from "@/components/auth/SessionProvider";
import { ConfirmDialog, Modal } from "@/components/common/Dialogs";
import ImageInsertDialog from "@/components/media/ImageInsertDialog";
import { useI18n } from "@/i18n/I18nProvider";

const SIZES = ["512x512", "1024x1024", "1024x1536"];

export default function MediaPage() {
  const { can } = useSession();
  const { t } = useI18n();
  const writable = can("write");

  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [uploading, setUploading] = useState(false);
  const [copiedId, setCopiedId] = useState("");

  const [genOpen, setGenOpen] = useState(false);
  const [genPrompt, setGenPrompt] = useState("");
  const [genSize, setGenSize] = useState(SIZES[1]);
  const [genCount, setGenCount] = useState(1);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");
  const [genHint, setGenHint] = useState("");

  const [removeTarget, setRemoveTarget] = useState<MediaAsset | null>(null);
  const [insertTarget, setInsertTarget] = useState<MediaAsset | null>(null);

  const fileRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listMedia({ limit: 60 });
      setAssets(data.assets);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("media.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const upload = async (file: File) => {
    setUploading(true);
    setError("");
    try {
      const asset = await api.uploadMedia(file);
      setAssets((current) => [asset, ...current]);
      setNotice(t("media.uploaded"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("media.uploadFailed"));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const generate = async () => {
    if (!genPrompt.trim()) return;
    setGenerating(true);
    setGenError("");
    setGenHint("");
    try {
      const data = await api.generateMedia({
        prompt: genPrompt.trim(),
        size: genSize,
        n: genCount,
      });
      setAssets((current) => [...data.assets, ...current]);
      setNotice(t("media.generatedNotice", { count: data.assets.length }));
      setGenOpen(false);
      setGenPrompt("");
    } catch (err) {
      const message = err instanceof Error ? err.message : t("media.generateFailed");
      setGenError(message);
      if (err instanceof ApiError && err.status === 503) {
        setGenHint(t("media.genHint"));
      }
    } finally {
      setGenerating(false);
    }
  };

  const copyMarkdown = async (asset: MediaAsset) => {
    try {
      await navigator.clipboard.writeText(assetMarkdown(asset));
      setCopiedId(asset.id);
      window.setTimeout(() => setCopiedId(""), 1600);
    } catch {
      setError(t("media.copyFailed"));
    }
  };

  const download = (asset: MediaAsset) => {
    const anchor = document.createElement("a");
    anchor.href = assetSrc(asset);
    anchor.download = `${asset.id}.${(asset.content_type || "image/png").split("/")[1] || "png"}`;
    anchor.rel = "noreferrer";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  };

  const remove = async () => {
    if (!removeTarget) return;
    try {
      await api.deleteMedia(removeTarget.id);
      setAssets((current) => current.filter((item) => item.id !== removeTarget.id));
      setNotice(t("media.deleted"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("media.deleteFailed"));
    } finally {
      setRemoveTarget(null);
    }
  };

  const total = useMemo(
    () => assets.reduce((sum, asset) => sum + (asset.bytes || 0), 0),
    [assets],
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="space-y-4"
    >
      <div className="glass rounded-3xl p-5 shadow-glass sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
              {t("media.title")}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
              <span className="chip-muted">
                {assets.length === 1
                  ? t("media.countOne")
                  : t("media.count", { count: assets.length })}
              </span>
              <span className="chip-muted">
                {t("media.total", { size: formatBytes(total) })}
              </span>
            </div>
          </div>
          <div className="no-scrollbar -mx-1 flex w-full items-center gap-2 overflow-x-auto px-1 sm:w-auto">
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void upload(file);
              }}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={!writable || uploading}
              title={!writable ? t("common.readOnlyRole") : undefined}
              className="btn btn-quiet shrink-0 whitespace-nowrap"
            >
              {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
              {t("media.upload")}
            </button>
            <button
              type="button"
              onClick={() => {
                setGenError("");
                setGenHint("");
                setGenOpen(true);
              }}
              disabled={!writable}
              title={!writable ? t("common.readOnlyRole") : undefined}
              className="btn btn-primary shrink-0 whitespace-nowrap"
            >
              <Sparkles size={13} />
              {t("media.generateAi")}
            </button>
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="btn btn-quiet shrink-0"
              aria-label={t("common.refresh")}
            >
              {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            </button>
          </div>
        </div>
      </div>

      {error ? (
        <div className="rounded-2xl border border-rose-400/35 bg-rose-400/10 px-4 py-2.5 text-[11px] leading-relaxed text-rose-600 dark:text-rose-300">
          {error}
        </div>
      ) : null}
      <AnimatePresence>
        {notice ? (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-2xl border border-emerald-400/35 bg-emerald-400/10 px-4 py-2.5 text-[11px] text-emerald-700 dark:text-emerald-300"
          >
            {notice}
          </motion.div>
        ) : null}
      </AnimatePresence>

      {loading && assets.length === 0 ? (
        <div className="glass rounded-3xl p-10 text-center text-xs text-slate-400 shadow-glass dark:text-slate-500">
          <Loader2 size={18} className="mx-auto animate-spin" />
        </div>
      ) : assets.length === 0 ? (
        <div className="glass rounded-3xl p-10 text-center shadow-glass">
          <ImagePlus
            size={26}
            className="mx-auto text-slate-300 dark:text-slate-600"
          />
          <p className="mt-3 text-sm font-medium text-slate-700 dark:text-slate-200">
            {t("media.emptyTitle")}
          </p>
          <p className="mx-auto mt-1.5 max-w-md text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
            {t("media.emptyDesc")}
          </p>
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={!writable || uploading}
            className="btn btn-primary mx-auto mt-4"
          >
            <Upload size={13} />
            {t("media.uploadFirst")}
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {assets.map((asset) => (
            <motion.div
              key={asset.id}
              layout
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass overflow-hidden rounded-3xl shadow-glass"
            >
              <a
                href={assetSrc(asset)}
                target="_blank"
                rel="noreferrer"
                className="block aspect-[4/3] overflow-hidden bg-slate-500/5"
              >
                <img
                  src={assetSrc(asset)}
                  alt={asset.prompt || asset.id}
                  loading="lazy"
                  className="h-full w-full object-cover transition duration-300 hover:scale-[1.02]"
                />
              </a>
              <div className="space-y-2 p-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span
                    className={clsx(
                      "rounded-full px-2 py-0.5 text-[10px] font-medium",
                      asset.kind === "generated" || asset.kind === "generate"
                        ? "bg-indigo-500/15 text-indigo-700 dark:text-indigo-200"
                        : "bg-slate-500/10 text-slate-600 dark:text-slate-300",
                    )}
                  >
                    {asset.kind === "generated" || asset.kind === "generate"
                      ? t("media.kindGenerated")
                      : t("media.kindUpload")}
                  </span>
                  <span className="text-[10px] text-slate-400 dark:text-slate-500">
                    {asset.width}×{asset.height} · {formatBytes(asset.bytes)}
                  </span>
                  <span className="ml-auto text-[10px] text-slate-400 dark:text-slate-500">
                    {formatStamp(asset.created_at)}
                  </span>
                </div>
                <p className="line-clamp-2 min-h-[2.2em] text-[11px] leading-relaxed text-slate-600 dark:text-slate-300">
                  {asset.prompt || t("media.noPrompt")}
                </p>
                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => void copyMarkdown(asset)}
                    className="btn-quiet flex-1 text-[11px]"
                  >
                    {copiedId === asset.id ? <Check size={11} /> : <Copy size={11} />}
                    {copiedId === asset.id ? t("media.copied") : t("media.copyMarkdown")}
                  </button>
                  <button
                    type="button"
                    onClick={() => download(asset)}
                    className="btn-quiet text-[11px]"
                  >
                    <Download size={11} />
                    {t("common.download")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setInsertTarget(asset)}
                    disabled={!writable}
                    title={!writable ? t("common.readOnlyRole") : t("media.insertHint")}
                    className="btn-quiet text-[11px]"
                  >
                    <ImagePlus size={11} />
                    {t("media.insertTo")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setRemoveTarget(asset)}
                    disabled={!writable}
                    title={!writable ? t("common.readOnlyRole") : t("common.delete")}
                    className="btn-quiet text-[11px] text-rose-600 dark:text-rose-300"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
                <p className="truncate font-mono text-[10px] text-slate-300 dark:text-slate-600">
                  {mediaUrl(asset.id)}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      <Modal
        open={genOpen}
        title={t("media.generateTitle")}
        subtitle={t("media.generateSubtitle")}
        onClose={() => setGenOpen(false)}
      >
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
              {t("media.fieldPrompt")}
            </span>
            <textarea
              value={genPrompt}
              onChange={(event) => setGenPrompt(event.target.value)}
              rows={3}
              placeholder={t("media.promptPlaceholder")}
              className="input w-full resize-y"
            />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                {t("media.fieldSize")}
              </span>
              <select
                value={genSize}
                onChange={(event) => setGenSize(event.target.value)}
                className="select w-full"
              >
                {SIZES.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                {t("media.fieldCount")}
              </span>
              <select
                value={genCount}
                onChange={(event) => setGenCount(Number(event.target.value))}
                className="select w-full"
              >
                <option value={1}>{t("media.imageCount", { count: 1 })}</option>
                <option value={2}>{t("media.imageCount", { count: 2 })}</option>
              </select>
            </label>
          </div>
          {genError ? (
            <div className="rounded-xl border border-amber-400/40 bg-amber-400/10 px-2.5 py-2 text-[11px] leading-relaxed text-amber-800 dark:border-amber-300/25 dark:text-amber-200">
              <p>{genError}</p>
              {genHint ? <p className="mt-1 font-medium">{genHint}</p> : null}
            </div>
          ) : null}
          <div className="flex items-center justify-end gap-2">
            <button type="button" onClick={() => setGenOpen(false)} className="btn btn-quiet">
              {t("common.cancel")}
            </button>
            <button
              type="button"
              onClick={() => void generate()}
              disabled={generating || !genPrompt.trim()}
              className="btn btn-primary"
            >
              {generating ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
              {generating ? t("media.generating") : t("media.generate")}
            </button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(removeTarget)}
        title={t("media.deleteTitle")}
        description={t("media.deleteDesc", { id: removeTarget?.id ?? "" })}
        confirmLabel={t("common.delete")}
        onClose={() => setRemoveTarget(null)}
        onConfirm={() => void remove()}
      />

      <ImageInsertDialog
        asset={insertTarget}
        onClose={() => setInsertTarget(null)}
        onInserted={(message) => {
          setNotice(message);
          setError("");
        }}
      />
    </motion.div>
  );
}
