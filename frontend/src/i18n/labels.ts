import { zh } from "./dict";

export type Translate = (
  path: string,
  vars?: Record<string, string | number>,
) => string;

/**
 * Single source of truth for backend/product enum values rendered by the UI.
 *
 * Each group maps a raw value to the canonical dict path `<group>.<value>`.
 * `enumLabel` first tries the canonical key, then a legacy key that already
 * exists in the current dictionary, and finally falls back to the raw value.
 * That keeps the UI usable while the canonical keys are merged into dict.ts.
 */
const GROUPS: Record<string, readonly string[]> = {
  difficulty: ["beginner", "elementary", "intermediate", "advanced", "expert"],
  genre: ["article", "report", "essay", "tutorial", "custom"],
  policy: ["required", "preferred", "optional", "forbidden"],
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
    "kb_embed_backfill",
    "piece_video",
  ],
  jobStatus: ["queued", "running", "succeeded", "failed", "canceled"],
  providerKind: ["openai_compat", "dummy"],
  mode: ["strict", "loose"],
  mediaKind: [
    "generated",
    "uploaded",
    "searched",
    "video",
    "image",
    "audio",
  ],
  retrievalKind: ["embedding", "rerank"],
  exportFormat: ["md", "html", "epub", "pdf"],
  validator: ["citation", "length", "structure", "continuity"],
  strictness: ["relaxed", "normal", "strict"],
  pov: ["first", "third_limited", "third_omniscient"],
  tense: ["present", "past"],
  language: ["zh", "en", "bilingual"],
  shareLevel: ["read", "write", "use", "manage"],
  plan: ["free", "pro", "team"],
  serverStatus: ["ok", "degraded", "error"],
  unitName: [
    "lesson",
    "lessonPlural",
    "unit",
    "unitPlural",
    "chapter",
    "chapterPlural",
    "section",
    "sectionPlural",
    "part",
    "partPlural",
    "passage",
    "passagePlural",
  ],
};

/** Current dict keys that already carry the same meaning (pre-merge fallback). */
const LEGACY_KEYS: Record<string, Record<string, string>> = {
  difficulty: {
    beginner: "labels.difficulty.beginner",
    elementary: "labels.difficulty.elementary",
    intermediate: "labels.difficulty.intermediate",
    advanced: "labels.difficulty.advanced",
    expert: "labels.difficulty.expert",
  },
  policy: {
    required: "piece.citation.required",
    optional: "piece.citation.optional",
    forbidden: "piece.citation.forbidden",
  },
  role: {
    owner: "labels.role.owner",
    admin: "labels.role.admin",
    editor: "labels.role.editor",
    viewer: "labels.role.viewer",
  },
  unitStatus: {
    planned: "labels.unitStatus.planned",
    draft: "labels.unitStatus.draft",
    generated: "labels.unitStatus.generated",
    review: "labels.unitStatus.review",
    approved: "labels.unitStatus.approved",
    published: "labels.unitStatus.published",
    needs_revision: "labels.unitStatus.needs_revision",
    reverted: "labels.unitStatus.reverted",
  },
  jobKind: {
    research: "labels.jobKind.research",
    piece_create: "labels.jobKind.piece_create",
    piece_generate: "labels.jobKind.piece_generate",
    piece_rewrite: "labels.jobKind.piece_rewrite",
    unit_generate: "labels.jobKind.unit_generate",
    blueprint_generate: "labels.jobKind.blueprint_generate",
  },
  jobStatus: {
    queued: "labels.jobStatus.queued",
    running: "labels.jobStatus.running",
    succeeded: "labels.jobStatus.succeeded",
    failed: "labels.jobStatus.failed",
    canceled: "labels.jobStatus.canceled",
  },
  providerKind: {
    openai_compat: "labels.providerKind.openai_compat",
    dummy: "labels.providerKind.dummy",
  },
  mode: {
    strict: "labels.mode.strict",
    loose: "labels.mode.loose",
  },
  genre: {
    article: "piece.genre.article",
    report: "piece.genre.report",
    essay: "piece.genre.essay",
    tutorial: "piece.genre.tutorial",
    custom: "piece.genre.custom",
  },
  validator: {
    citation: "profiles.validator_citation",
    length: "profiles.validator_length",
    structure: "profiles.validator_structure",
    continuity: "profiles.validator_continuity",
  },
  strictness: {
    relaxed: "profiles.strictnessRelaxed",
    normal: "profiles.strictnessNormal",
    strict: "profiles.strictnessStrict",
  },
  pov: {
    first: "profiles.povFirst",
    third_limited: "profiles.povThirdLimited",
    third_omniscient: "profiles.povThirdOmniscient",
  },
  tense: {
    present: "profiles.tensePresent",
    past: "profiles.tensePast",
  },
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

function lookup(t: Translate, key: string): string | undefined {
  const value = t(key);
  return value === key ? undefined : value;
}

/**
 * Translate a raw enum value using `<group>.<value>`, with legacy-dict and
 * raw-value fallbacks. Unknown values (third-party free text) stay untouched.
 */
export function enumLabel(
  t: Translate,
  group: string,
  value: string,
  fallback?: string,
): string {
  const raw = value ?? "";
  if (!raw) return fallback ?? raw;
  const known = GROUPS[group];
  if (known && !known.includes(raw)) return fallback ?? raw;
  const direct = lookup(t, `${group}.${raw}`);
  if (direct !== undefined) return direct;
  const legacy = LEGACY_KEYS[group]?.[raw];
  if (legacy) {
    const mapped = lookup(t, legacy);
    if (mapped !== undefined) return mapped;
  }
  return fallback ?? raw;
}

export function roleLabel(
  t: Translate,
  role: string,
  fallback?: string,
): string {
  return enumLabel(t, "role", role, fallback ?? role);
}

export function unitStatusLabel(t: Translate, status: string): string {
  return enumLabel(t, "unitStatus", status || "draft");
}

export function jobKindLabel(t: Translate, kind: string): string {
  return enumLabel(t, "jobKind", kind);
}

export function jobStatusLabel(t: Translate, status: string): string {
  return enumLabel(t, "jobStatus", status);
}

export function providerKindLabel(t: Translate, kind: string): string {
  return enumLabel(t, "providerKind", kind);
}

export function modeLabel(t: Translate, mode: string): string {
  return enumLabel(t, "mode", mode || "strict");
}

export function difficultyLabel(t: Translate, value: string): string {
  return enumLabel(t, "difficulty", value || "intermediate");
}

export function genreLabel(t: Translate, value: string): string {
  return enumLabel(t, "genre", value || "article");
}

export function policyLabel(t: Translate, value: string): string {
  return enumLabel(t, "policy", value || "optional");
}

export const citationPolicyLabel = policyLabel;

export function validatorLabel(t: Translate, value: string): string {
  return enumLabel(t, "validator", value);
}

export function strictnessLabel(t: Translate, value: string): string {
  return enumLabel(t, "strictness", value || "normal");
}

export function povLabel(t: Translate, value: string): string {
  return enumLabel(t, "pov", value);
}

export function tenseLabel(t: Translate, value: string): string {
  return enumLabel(t, "tense", value);
}

const MEDIA_KIND_ALIASES: Record<string, string> = {
  generate: "generated",
  upload: "uploaded",
  search: "searched",
};

export function mediaKindLabel(t: Translate, kind: string): string {
  const value = MEDIA_KIND_ALIASES[kind] ?? kind;
  return enumLabel(t, "mediaKind", value);
}

export function retrievalKindLabel(t: Translate, kind: string): string {
  return enumLabel(t, "retrievalKind", kind);
}

export function exportFormatLabel(
  t: Translate,
  format: string,
  fallback?: string,
): string {
  return enumLabel(t, "exportFormat", format, fallback ?? format);
}

export function exportFormatHint(t: Translate, format: string): string {
  return lookup(t, `exportFormat.${format}Hint`) ?? "";
}

export function languageLabel(t: Translate, language: string): string {
  const value = language.toLowerCase();
  if (value === "zh" || value === "zh-cn" || value === "chinese") return enumLabel(t, "language", "zh");
  if (value === "en" || value === "english") return enumLabel(t, "language", "en");
  if (value === "bilingual") return enumLabel(t, "language", "bilingual");
  return language;
}

export function shareLevelLabel(t: Translate, level: string): string {
  return enumLabel(t, "shareLevel", level);
}

export function planLabel(t: Translate, plan: string): string {
  return enumLabel(t, "plan", plan || "free");
}

export function serverStatusLabel(t: Translate, status: string): string {
  return enumLabel(t, "serverStatus", status);
}

const UNIT_NAME_ALIASES: Record<string, string> = {
  lesson: "lesson",
  lessons: "lessonPlural",
  unit: "unit",
  units: "unitPlural",
  chapter: "chapter",
  chapters: "chapterPlural",
  section: "section",
  sections: "sectionPlural",
  part: "part",
  parts: "partPlural",
  passage: "passage",
  passages: "passagePlural",
};

export function unitNameLabel(t: Translate, name: string): string {
  if (!name) return name;
  const key = UNIT_NAME_ALIASES[name.trim().toLowerCase()];
  if (!key) return name;
  return enumLabel(t, "unitName", key, name);
}

export function unitPluralLabel(t: Translate, name: string): string {
  return unitNameLabel(t, name);
}

const BUILTIN_PROFILE_KEYS: Record<string, string> = {
  profile_builtin_tutorial: "tutorial",
  profile_builtin_article: "article",
  profile_builtin_novel: "novel",
  profile_builtin_report: "report",
  profile_builtin_essay: "essay",
};

const BUILTIN_PROFILE_UNIT_KEYS: Record<string, string> = {
  profile_builtin_tutorial: "lesson",
  profile_builtin_article: "section",
  profile_builtin_novel: "chapter",
  profile_builtin_report: "part",
  profile_builtin_essay: "passage",
};

type ProfileLike = {
  id: string;
  name: string;
  is_builtin?: boolean;
};

function builtinProfileKey(profile: ProfileLike | null | undefined): string | undefined {
  if (!profile) return undefined;
  return BUILTIN_PROFILE_KEYS[profile.id];
}

export function profileNameLabel(
  t: Translate,
  profile: ProfileLike | null | undefined,
): string {
  if (!profile) return "";
  const key = builtinProfileKey(profile);
  if (!key) return profile.name;
  return lookup(t, `profile.builtin.${key}.name`) ?? profile.name;
}

export function profileDescriptionLabel(
  t: Translate,
  profile: (ProfileLike & { description?: string }) | null | undefined,
  fallback = "",
): string {
  if (!profile) return fallback;
  const key = builtinProfileKey(profile);
  const raw = profile.description || fallback;
  if (!key) return raw;
  return lookup(t, `profile.builtin.${key}.description`) ?? raw;
}

export function profileUnitNameLabel(
  t: Translate,
  profile: ProfileLike | null | undefined,
  fallback = "",
): string {
  if (!profile) return fallback;
  const key = BUILTIN_PROFILE_UNIT_KEYS[profile.id];
  if (!key) return fallback;
  return enumLabel(t, "unitName", key, fallback);
}

export function profileUnitPluralLabel(
  t: Translate,
  profile: ProfileLike | null | undefined,
  fallback = "",
): string {
  if (!profile) return fallback;
  const key = BUILTIN_PROFILE_UNIT_KEYS[profile.id];
  if (!key) return fallback;
  return enumLabel(t, "unitName", `${key}Plural`, fallback);
}

const BUILTIN_TAGS = [
  "technical",
  "tutorial",
  "long-form",
  "novel",
  "narrative",
  "research",
  "report",
  "essay",
  "prose",
];

export function profileTagLabel(t: Translate, tag: string): string {
  const normalized = tag.trim().toLowerCase().replace(/\s+/g, "-");
  if (!BUILTIN_TAGS.includes(normalized)) return tag;
  return lookup(t, `tag.${normalized}`) ?? tag;
}

export const labelsZh: Translate = zhTranslate;
