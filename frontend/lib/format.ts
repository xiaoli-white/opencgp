export function formatDateTime(timestamp: number): string {
  if (!timestamp) return "—";
  const date = new Date(timestamp * 1000);
  if (formatLocale === "en") {
    return new Intl.DateTimeFormat("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  }
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

let formatLocale: "zh" | "en" = "zh";

export function setFormatLocale(locale: "zh" | "en") {
  formatLocale = locale === "en" ? "en" : "zh";
}

export function formatRelative(timestamp: number): string {
  if (!timestamp) return "—";
  const diff = Date.now() / 1000 - timestamp;
  if (diff < 60) return "just now";
  if (diff < 3600) {
    const n = Math.floor(diff / 60);
    return `${n} min ago`;
  }
  if (diff < 86400) {
    const n = Math.floor(diff / 3600);
    return `${n} h ago`;
  }
  if (diff < 86400 * 30) {
    const n = Math.floor(diff / 86400);
    return `${n} d ago`;
  }
  if (formatLocale === "en") {
    return new Intl.DateTimeFormat("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    }).format(new Date(timestamp * 1000));
  }
  return formatDateTime(timestamp).slice(0, 10);
}

import {
  difficultyLabel as difficultyLabelI18n,
  getActiveTranslate,
  unitStatusLabel,
  modeLabel as modeLabelI18n,
} from "@/i18n/labels";

export function difficultyLabel(value: string): string {
  return difficultyLabelI18n(getActiveTranslate(), value);
}

export function statusLabel(value: string): string {
  return unitStatusLabel(getActiveTranslate(), value || "draft");
}

export type StatusTone =
  | "neutral"
  | "indigo"
  | "emerald"
  | "amber"
  | "rose";

const STATUS_TONES: Record<string, StatusTone> = {
  planned: "neutral",
  draft: "neutral",
  generated: "indigo",
  review: "indigo",
  approved: "emerald",
  published: "emerald",
  needs_revision: "amber",
  reverted: "rose",
};

export function statusTone(value: string): StatusTone {
  return STATUS_TONES[value] ?? "neutral";
}

export function formatChars(count: number): string {
  if (count >= 10000) return `${Math.round(count / 1000)}k chars`;
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k chars`;
  return `${count} chars`;
}

export function contentLength(content: string): number {
  return content ? content.replace(/\s/g, "").length : 0;
}

export function sourceLabel(name: string): string {
  if (!name) return "Unknown source";
  return name.length > 28 ? `${name.slice(0, 26)}…` : name;
}

// Loose-mode content carries a generated-by-model notice on its first line.
// Some backends still emit the notice in Chinese, so both spellings are matched.
// The Chinese literal is written with escapes to keep this file ASCII-only.
const LOOSE_NOTICE_MARKERS = [
  "\u7531\u5927\u6a21\u578b\u7f16\u5199",
  "written by ai",
  "written by a large language model",
  "written by an llm",
];

export const LOOSE_NOTICE_KEYWORD = LOOSE_NOTICE_MARKERS[0];

export function modeLabel(mode: string): string {
  return modeLabelI18n(getActiveTranslate(), mode);
}

export function splitLooseNotice(content: string): {
  body: string;
  notice: string;
} {
  if (!content) return { body: "", notice: "" };
  let notice = "";
  const kept: string[] = [];
  content.split("\n").forEach((line) => {
    const lowered = line.toLowerCase();
    if (LOOSE_NOTICE_MARKERS.some((marker) => lowered.includes(marker))) {
      if (!notice) {
        notice = line
          .replace(/^[>\s]+/, "")
          .replace(/[*\s]+$/, "")
          .trim();
      }
      return;
    }
    kept.push(line);
  });
  const body = kept.join("\n").replace(/^[\s]+/, "");
  return { body: body || content, notice };
}
