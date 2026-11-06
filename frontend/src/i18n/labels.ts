import { zh } from "./dict";

export type Translate = (
  path: string,
  vars?: Record<string, string | number>,
) => string;

const GROUPS: Record<string, string[]> = {
  role: ["owner", "admin", "editor", "viewer"],
  unitStatus: [
    "planned",
    "draft",
    "generated",
    "review",
    "approved",
    "published",
    "needs_revision",
    "reverted",
  ],
  jobKind: [
    "research",
    "piece_create",
    "piece_generate",
    "piece_rewrite",
    "unit_generate",
    "blueprint_generate",
  ],
  jobStatus: ["queued", "running", "succeeded", "failed", "canceled"],
  providerKind: ["openai_compat", "dummy"],
  mode: ["strict", "loose"],
  difficulty: ["beginner", "elementary", "intermediate", "advanced", "expert"],
};

function resolve(tree: unknown, path: string): string | undefined {
  let cursor: unknown = tree;
  for (const part of path.split(".")) {
    if (cursor === null || typeof cursor !== "object") return undefined;
    cursor = (cursor as Record<string, unknown>)[part];
  }
  return typeof cursor === "string" ? cursor : undefined;
}

const zhTranslate: Translate = (path, vars) => {
  const raw = resolve(zh, path);
  if (raw === undefined) return path;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in vars ? String(vars[key]) : match,
  );
};

let activeTranslate: Translate = zhTranslate;

export function setActiveTranslate(next: Translate): void {
  activeTranslate = next;
}

export function getActiveTranslate(): Translate {
  return activeTranslate;
}

function label(t: Translate, group: string, value: string): string {
  if (!value) return value;
  const known = GROUPS[group];
  if (!known || !known.includes(value)) return value;
  return t(`labels.${group}.${value}`);
}

export function roleLabel(t: Translate, role: string): string {
  return label(t, "role", role);
}

export function unitStatusLabel(t: Translate, status: string): string {
  return label(t, "unitStatus", status);
}

export function jobKindLabel(t: Translate, kind: string): string {
  return label(t, "jobKind", kind);
}

export function jobStatusLabel(t: Translate, status: string): string {
  return label(t, "jobStatus", status);
}

export function providerKindLabel(t: Translate, kind: string): string {
  return label(t, "providerKind", kind);
}

export function modeLabel(t: Translate, mode: string): string {
  return label(t, "mode", mode || "strict");
}

export function difficultyLabel(t: Translate, value: string): string {
  return label(t, "difficulty", value || "intermediate");
}

export const labelsZh: Translate = zhTranslate;
