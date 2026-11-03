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

export function formatRelative(timestamp: number): string {
  if (!timestamp) return "—";
  const diff = Date.now() / 1000 - timestamp;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)} 天前`;
  return formatDateTime(timestamp).slice(0, 10);
}

const DIFFICULTY_LABELS: Record<string, string> = {
  beginner: "入门",
  elementary: "入门",
  intermediate: "进阶",
  advanced: "高级",
  expert: "专家",
};

export function difficultyLabel(value: string): string {
  return DIFFICULTY_LABELS[value] ?? (value || "进阶");
}

const STATUS_LABELS: Record<string, string> = {
  planned: "待生成",
  draft: "草稿",
  generated: "已生成",
  review: "待审",
  approved: "已通过",
  published: "已发布",
  needs_revision: "待修改",
  reverted: "已回滚",
};

export function statusLabel(value: string): string {
  return STATUS_LABELS[value] ?? (value || "草稿");
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

const MODE_LABELS: Record<string, string> = {
  strict: "严格",
  loose: "非严格",
};

export function modeLabel(mode: string): string {
  return MODE_LABELS[mode] ?? "严格";
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
