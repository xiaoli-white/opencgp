import type { MediaAsset } from "@/lib/api";
import { API_BASE } from "@/lib/api";
import { getActiveTranslate, mediaKindLabel } from "@/i18n/labels";

const INTERNAL_HOST =
  "(?:localhost|127\\.0\\.0\\.1|0\\.0\\.0\\.0|\\[::1\\]|backend|host\\.docker\\.internal)";
const INTERNAL_MEDIA_URL = new RegExp(
  `^https?://${INTERNAL_HOST}(?::\\d+)?(/api/v1/media/.*)$`,
  "i",
);
const INTERNAL_BASE = new RegExp(`^https?://${INTERNAL_HOST}(?::\\d+)?$`, "i");

export function mediaSrc(url: string): string {
  if (!url) return "";
  const internal = INTERNAL_MEDIA_URL.exec(url);
  if (internal) return internal[1];
  if (url.startsWith("/api/v1/media/")) {
    return API_BASE && !INTERNAL_BASE.test(API_BASE) ? `${API_BASE}${url}` : url;
  }
  return url;
}

export function assetSrc(asset: MediaAsset): string {
  return mediaSrc(asset.url || `/api/v1/media/${asset.id}`);
}

export function assetMarkdown(asset: MediaAsset): string {
  const t = getActiveTranslate();
  const fallback = t("media.imageAlt");
  const alt = (asset.prompt || mediaKindLabel(t, asset.kind) || fallback)
    .replace(/[\r\n]+/g, " ")
    .replace(/[[\]]/g, "")
    .slice(0, 60)
    .trim();
  return `![${alt || fallback}](/api/v1/media/${asset.id})`;
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
