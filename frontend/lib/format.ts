export function formatDateTime(timestamp: number): string {
  if (!timestamp) return "—";
  const date = new Date(timestamp * 1000);
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
  const en = formatLocale === "en";
  if (diff < 60) return en ? "just now" : "刚刚";
  if (diff < 3600) {
    const n = Math.floor(diff / 60);
    return en ? `${n} min ago` : `${n} 分钟前`;
  }
  if (diff < 86400) {
    const n = Math.floor(diff / 3600);
    return en ? `${n} h ago` : `${n} 小时前`;
  }
  if (diff < 86400 * 30) {
    const n = Math.floor(diff / 86400);
    return en ? `${n} d ago` : `${n} 天前`;
  }
  return formatDateTime(timestamp).slice(0, 10);
}

import {
  difficultyLabel as difficultyLabelI18n,
  getActiveTranslate,
  lessonStatusLabel,
  modeLabel as modeLabelI18n,
} from "@/i18n/labels";

export function difficultyLabel(value: string): string {
  return difficultyLabelI18n(getActiveTranslate(), value);
}

export function statusLabel(value: string): string {
  return lessonStatusLabel(getActiveTranslate(), value || "draft");
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
  if (formatLocale === "en") {
    if (count >= 10000) return `${Math.round(count / 1000)}k chars`;
    if (count >= 1000) return `${(count / 1000).toFixed(1)}k chars`;
    return `${count} chars`;
  }
  if (count >= 10000) return `${(count / 10000).toFixed(1)} 万字`;
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k 字`;
  return `${count} 字`;
}

export function contentLength(content: string): number {
  return content ? content.replace(/\s/g, "").length : 0;
}

export function sourceLabel(name: string): string {
  if (!name) return "未知来源";
  return name.length > 28 ? `${name.slice(0, 26)}…` : name;
}

export const LOOSE_NOTICE_KEYWORD = "由大模型编写";

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
    if (line.includes(LOOSE_NOTICE_KEYWORD)) {
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
