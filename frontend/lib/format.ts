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
  draft: "草稿",
  review: "待审",
  approved: "已通过",
  published: "已发布",
};

export function statusLabel(value: string): string {
  return STATUS_LABELS[value] ?? (value || "草稿");
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
