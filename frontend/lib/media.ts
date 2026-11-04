import type { MediaAsset } from "@/lib/api";
import { API_BASE } from "@/lib/api";

export function assetSrc(asset: MediaAsset): string {
  const url = asset.url || `/api/v1/media/${asset.id}`;
  return /^https?:\/\//i.test(url) ? url : `${API_BASE}${url}`;
}

export function assetMarkdown(asset: MediaAsset): string {
  const alt = (asset.prompt || asset.kind || "图片")
    .replace(/[\r\n]+/g, " ")
    .replace(/[[\]]/g, "")
    .slice(0, 60)
    .trim();
  return `![${alt || "图片"}](/api/v1/media/${asset.id})`;
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatStamp(value: number): string {
  if (!value) return "—";
  const ms = value > 1e12 ? value : value * 1000;
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return "—";
  const pad = (input: number) => String(input).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

export const MEDIA_KIND_LABEL: Record<string, string> = {
  generated: "生成",
  generate: "生成",
  upload: "上传",
  uploaded: "上传",
};

export function mediaKindLabel(kind: string): string {
  return MEDIA_KIND_LABEL[kind] ?? kind ?? "图片";
}
