import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { api, type Longform, type MediaAsset } from "@/lib/api";
import { assetMarkdown, assetSrc } from "@/lib/media";
import { Modal } from "@/components/common/Dialogs";

type ImageInsertDialogProps = {
  asset: MediaAsset | null;
  lockedLongformId?: string;
  initialSectionId?: string;
  onClose: () => void;
  onInserted: (message: string) => void;
};

export default function ImageInsertDialog({
  asset,
  lockedLongformId,
  initialSectionId,
  onClose,
  onInserted,
}: ImageInsertDialogProps) {
  const [longforms, setLongforms] = useState<Longform[]>([]);
  const [longformId, setLongformId] = useState(lockedLongformId ?? "");
  const [detail, setDetail] = useState<Longform | null>(null);
  const [sectionId, setSectionId] = useState(initialSectionId ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const open = Boolean(asset);

  useEffect(() => {
    if (!open) return;
    setError("");
    setSectionId(initialSectionId ?? "");
    if (lockedLongformId) {
      setLongformId(lockedLongformId);
      return;
    }
    let alive = true;
    void api
      .listLongforms()
      .then((data) => {
        if (!alive) return;
        setLongforms(data.longforms);
        setLongformId((current) => current || data.longforms[0]?.id || "");
      })
      .catch((err) => {
        if (alive) setError(err instanceof Error ? err.message : "长篇列表加载失败");
      });
    return () => {
      alive = false;
    };
  }, [open, lockedLongformId, initialSectionId]);

  useEffect(() => {
    if (!open || !longformId) {
      setDetail(null);
      return;
    }
    let alive = true;
    void api
      .getLongform(longformId)
      .then((data) => {
        if (!alive) return;
        setDetail(data);
        setSectionId((current) => {
          if (current && data.outline.some((item) => item.id === current)) return current;
          return data.outline[data.outline.length - 1]?.id ?? "";
        });
      })
      .catch((err) => {
        if (alive) setError(err instanceof Error ? err.message : "长篇详情加载失败");
      });
    return () => {
      alive = false;
    };
  }, [open, longformId]);

  const submit = async () => {
    if (!asset || !longformId || !sectionId) return;
    setBusy(true);
    setError("");
    try {
      const fresh = await api.getLongform(longformId);
      const section = fresh.outline.find((item) => item.id === sectionId);
      if (!section) throw new Error("章节不存在");
      const merged = `${section.content ?? ""}\n\n${assetMarkdown(asset)}\n`.trim();
      await api.updateLongformSection(longformId, sectionId, { content: merged });
      onInserted(`图片已插入《${fresh.title}》· ${section.title}`);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "插入失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title="插入图片到长篇"
      subtitle="选择目标长篇与章节，图片以 Markdown 语法追加到该节末尾"
      onClose={onClose}
    >
      <div className="space-y-3">
        {asset ? (
          <div className="flex items-center gap-2.5 rounded-2xl border border-white/50 bg-white/50 p-2 dark:border-white/10 dark:bg-white/[0.04]">
            <img
              src={assetSrc(asset)}
              alt={asset.prompt || "图片"}
              className="h-12 w-16 shrink-0 rounded-xl object-cover"
            />
            <p className="min-w-0 flex-1 truncate text-[11px] text-slate-500 dark:text-slate-400">
              {asset.prompt || asset.id}
            </p>
          </div>
        ) : null}

        {lockedLongformId ? null : (
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
              长篇
            </span>
            <select
              value={longformId}
              onChange={(event) => setLongformId(event.target.value)}
              className="select w-full"
            >
              {longforms.length === 0 ? <option value="">暂无长篇</option> : null}
              {longforms.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
        )}

        <label className="block">
          <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
            章节
          </span>
          <select
            value={sectionId}
            onChange={(event) => setSectionId(event.target.value)}
            className="select w-full"
          >
            {detail?.outline.length ? null : <option value="">请选择章节</option>}
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
            取消
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || !longformId || !sectionId}
            className="btn btn-primary"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : null}
            插入
          </button>
        </div>
      </div>
    </Modal>
  );
}
