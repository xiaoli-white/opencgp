import {
  AUTH_REQUIRED_EVENT,
  getTenantId,
  getToken,
  type Role,
  type RoleAction,
} from "@/lib/session";

export const API_BASE = (
  import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export type AuthUser = {
  id: string;
  email: string;
  display_name: string;
  created_at: number;
  is_active?: boolean;
  status?: string;
  role?: string;
  avatar_url?: string;
};

export type TenantInfo = {
  id: string;
  name: string;
  slug?: string;
  plan?: string;
};

export type TenantRef = TenantInfo | string;

export type AuthTenant = {
  tenant: TenantRef;
  role: Role;
  can_transfer?: boolean;
};

export type TenantKind = "system" | "personal" | "team";

export type TenantSummary = {
  id: string;
  name: string;
  slug?: string;
  plan?: string;
  kind?: TenantKind | string;
  owner_user_id?: string;
  member_count?: number;
  is_system?: boolean;
  created_at?: number;
};

export type TenantMembership = {
  tenant: TenantSummary;
  role: Role;
  can_transfer?: boolean;
};

export function tenantId(value: TenantRef | null | undefined): string {
  if (!value) return "";
  return typeof value === "string" ? value : value.id ?? "";
}

export function tenantName(value: TenantRef | null | undefined): string {
  if (!value) return "";
  return typeof value === "string" ? value : value.name || value.slug || value.id || "";
}

export type AuthMode = "disabled" | "required";

export type MeResponse = {
  user: AuthUser;
  tenant: TenantRef;
  role: Role;
  role_key?: string;
  role_name?: string;
  actions?: RoleAction[];
  scope?: RoleScope;
  can?: Partial<Record<RoleAction, boolean>>;
  avatar_url?: string;
  tenants: AuthTenant[];
  auth_mode: AuthMode;
};

export type RoleScope = "all" | "assigned";

export type RoleRecord = {
  id: string;
  key: string;
  name: string;
  actions: RoleAction[];
  scope: RoleScope;
  builtin: boolean | number;
  member_count: number;
};

export type RoleList = {
  count: number;
  roles: RoleRecord[];
};

export type CourseGrant = {
  user_id: string;
  user_email: string;
  user_display_name: string;
  level: "read" | "write";
};

export type CourseGrants = {
  course_id: string;
  count: number;
  grants: CourseGrant[];
};

export type ShareEntry = {
  user_id: string;
  user_email: string;
  user_display_name: string;
  level: string;
};

export type LongformGrants = {
  longform_id: string;
  count: number;
  grants: ShareEntry[];
};

export type ProviderShares = {
  provider_id: string;
  count: number;
  shares: ShareEntry[];
};

export type AdminUser = {
  id: string;
  email: string;
  display_name: string;
  status: string;
  created_at: number;
  last_login_at?: number | null;
  role?: string;
  avatar_url?: string;
};

export type AdminUserList = {
  count: number;
  users: AdminUser[];
};

export type Capabilities = {
  user_id: string;
  tenant_id: string;
  role: {
    key: string;
    name: string;
    actions: RoleAction[];
    scope: RoleScope;
  };
  can: Record<RoleAction, boolean>;
  visible_course_ids: string[] | "all";
};

export type AuthPayload = {
  token: string;
  user: AuthUser;
  tenants: AuthTenant[];
};

export type TenantList = {
  count: number;
  tenants: TenantMembership[];
};

export type Member = {
  id: string;
  tenant_id: string;
  user_id: string;
  role: Role;
  created_at: number;
  user_email: string;
  user_display_name: string;
  avatar_url?: string;
};

export type QuotaUsage = {
  monthly_generations: number;
  monthly_uploads: number;
  storage_bytes: number;
};

export type QuotaConsumption = {
  generations: number;
  uploads: number;
  storage_bytes: number;
};

export type QuotaUnlimited = {
  generations: boolean;
  uploads: boolean;
  storage: boolean;
};

export type Quota = {
  tenant_id: string;
  period: string;
  limits: QuotaUsage;
  usage: QuotaConsumption & { period?: string };
  remaining: QuotaConsumption;
  unlimited?: QuotaUnlimited;
};

export type VersionHunkType = "same" | "add" | "del";

export type VersionDiffHunk = {
  type: VersionHunkType;
  text: string;
};

export type VersionDiffResult = {
  owner_id?: string;
  from: number;
  to: number;
  added_chars: number;
  removed_chars: number;
  hunks: VersionDiffHunk[];
};

export type LessonVersionDetail = LessonVersion & {
  citation_count?: number;
  content_length?: number;
  approved_at?: number;
  reviewer_id?: string;
};

export type LongformVersionDetail = {
  id: string;
  longform_id: string;
  version: number;
  content: string;
  outline: LongformSection[];
  citations: Citation[];
  mode: string;
  note: string;
  created_at: number;
};

export type QuotaHistoryDay = {
  date: string;
  generations: number;
  uploads: number;
  storage_bytes: number;
  exec: number;
  image: number;
};

export type QuotaHistory = {
  tenant_id: string;
  period: string;
  days: QuotaHistoryDay[];
  totals: Omit<QuotaHistoryDay, "date">;
};

export type ProviderKind = "openai_compat" | "dummy";

export type ServerProvider = {
  id: string;
  name: string;
  kind: string;
  base_url: string;
  models: string[];
  enabled: boolean;
  is_default: boolean;
  has_key: boolean;
  api_key_masked: string;
  updated_at?: number | null;
};

export type UserProvider = {
  id: string;
  name: string;
  kind: string;
  base_url: string;
  models: string[];
  enabled: boolean;
  is_default: boolean;
  has_key: boolean;
  api_key_masked: string;
  updated_at?: number | null;
};

export type ProviderOption = {
  id: string;
  name: string;
  kind: string;
  models: string[];
  has_key: boolean;
  is_default: boolean;
  enabled?: boolean;
  scope?: "user" | "server" | "shared";
  shared_level?: "use" | "manage";
  owner_name?: string;
  can_manage?: boolean;
};

export type ProviderServerInfo = {
  id?: string;
  provider_id?: string;
  name?: string;
  kind?: string;
  backend?: string;
  base_url?: string;
  model: string;
  models?: string[];
  has_key: boolean;
};

export type ProviderSettings = {
  source: "user" | "server";
  provider_id?: string;
  provider_name?: string;
  active_provider_id?: string;
  active_scope?: "user" | "server";
  scope?: "user" | "server";
  backend?: string;
  base_url?: string;
  model: string;
  models?: string[];
  providers?: ProviderOption[];
  temperature: number;
  max_tokens: number;
  has_key: boolean;
  api_key_masked: string;
  updated_at?: number | string | null;
  server: ProviderServerInfo;
};

export type ProviderPayload = {
  provider_id?: string;
  model?: string;
  api_key?: string;
  temperature?: number;
  max_tokens?: number;
  backend?: string;
  base_url?: string;
};

export type ServerProviderPayload = {
  name?: string;
  kind?: string;
  base_url?: string;
  api_key?: string;
  models?: string[];
  enabled?: boolean;
  is_default?: boolean;
};

export type ProviderTestResult = {
  ok: boolean;
  latency_ms: number;
  provider: string;
  model: string;
  detail: string;
};

export type Citation = {
  source_id: string;
  source_name: string;
  chunk_id: string;
  chunk_index: number;
  text: string;
  snippet: string;
  score: number;
  start: number;
  end: number;
  meta: Record<string, unknown>;
};

export type Evidence = {
  marker: string;
  citation: Citation;
};

export type ExportFormatId = "md" | "html" | "epub" | "pdf";

export type ExportFormat = {
  id: ExportFormatId;
  label: string;
  available: boolean;
};

export type ExportSourceType = "course" | "longform";

export type ExportResult = {
  blob: Blob;
  filename: string;
};

export type MediaAsset = {
  id: string;
  kind: string;
  prompt: string;
  url: string;
  content_type: string;
  bytes: number;
  width: number;
  height: number;
  created_at: number;
};

export type GenerationMode = "strict" | "loose";

export type Course = {
  id: string;
  title: string;
  subtitle: string;
  audience: string;
  difficulty: string;
  language: string;
  created_at: number;
  updated_at: number;
};

export type Lesson = {
  id: string;
  course_id: string;
  order_index: number;
  title: string;
  learning_objectives: string[];
  prerequisites: string[];
  content: string;
  status: string;
  current_version: number;
  last_mode: GenerationMode | "";
  created_at: number;
  updated_at: number;
};

export type LessonVersion = {
  id: string;
  lesson_id: string;
  version: number;
  content: string;
  citations: Citation[];
  mode: GenerationMode | "";
  note: string;
  created_at: number;
};

export type Message = {
  id: string;
  thread_id: string;
  role: string;
  content: string;
  citations: Citation[];
  created_at: number;
};

export type ThreadView = {
  lesson_id: string;
  thread_id: string;
  title: string;
  message_count: number;
  messages: Message[];
  returned_count?: number;
  course_id?: string;
};

export type GenerationResult = {
  lesson_id: string;
  version: number;
  topic: string;
  top_k: number;
  mode: GenerationMode;
  content: string;
  citations: Citation[];
  evidence: Evidence[];
  grounded: boolean;
  provider: string;
  prompt: string;
};

export type AskResult = {
  lesson_id: string;
  thread_id: string;
  question: string;
  answer: string;
  user_message_id: string;
  assistant_message_id: string;
  citations: Citation[];
  grounded: boolean;
  provider: string;
  prompt: string;
};

export type AmendResult = {
  lesson_id: string;
  instruction: string;
  target: string;
  version: number;
  previous_version: number;
  mode: GenerationMode;
  content: string;
  citations: Citation[];
  note: string;
  provider: string;
  prompt: string;
};

export type StorageInfo = {
  backend: string;
  bucket?: string;
  endpoint?: string;
  prefix?: string;
  objects: number;
  ok?: boolean;
};

export type IngestResult = {
  source_id: string;
  source_name: string;
  parser: string;
  chunk_count: number;
  char_count: number;
  object_key?: string;
  meta: Record<string, unknown>;
};

export type SearchResponse = {
  query: string;
  top_k: number;
  count: number;
  citations: Citation[];
};

export type CourseDetail = {
  course: Course;
  lesson_count: number;
  lessons: Lesson[];
};

export type Health = {
  status: string;
  app: string;
  env: string;
  adapters: Record<string, { ok: boolean; error?: string }>;
};

export type GlossaryTerm = {
  term: string;
  definition: string;
  aliases: string[];
  node_ids: string[];
};

export type LearningStage = {
  id: string;
  title: string;
  goal: string;
  node_ids: string[];
  estimated_minutes: number;
};

export type OutlineNode = {
  id: string;
  stage_id: string;
  title: string;
  summary: string;
  objectives: string[];
  prerequisites: string[];
  estimated_minutes: number;
  lesson_id: string | null;
  status: string;
};

export type Blueprint = {
  course_id: string;
  version: number;
  overview: string;
  mode: GenerationMode | "";
  grounded: boolean;
  learning_path: LearningStage[];
  outline: OutlineNode[];
  glossary: GlossaryTerm[];
  provider: string;
  warning: string;
  updated_at: number;
};

export type BlueprintEnvelope = {
  exists: boolean;
  blueprint: Blueprint | null;
};

export type LessonReview = {
  id: string;
  lesson_id: string;
  action: "approve" | "request_revision" | string;
  note: string;
  version: number;
  status: string;
  created_at: number;
};

export type CourseProgress = {
  course_id: string;
  total: number;
  by_status: Record<string, number>;
  approved: number;
  pending_review: number;
  next_lesson_id: string | null;
  blueprint_ready: boolean;
  blueprint_version: number;
};

export type GlossaryPayload = {
  course_id: string;
  count: number;
  glossary: GlossaryTerm[];
};

export type ApplyBlueprintResult = {
  created_lessons: Lesson[];
  blueprint: Blueprint;
  created_count: number;
};

export type ReviewResult = {
  lesson: Lesson;
  review: LessonReview;
  course_progress: CourseProgress;
};

export type LessonLockInfo = {
  lesson_id: string;
  tenant_id?: string;
  user_id: string;
  user_name: string;
  token: string;
  heartbeat_at?: number;
  expires_at: number;
};

export type VersionConflictPayload = {
  detail?: string;
  expected_version?: number;
  current_version?: number;
};

export type ResearchFinding = {
  title: string;
  detail: string;
  evidence: string[];
};

export type ResearchContradiction = {
  claim: string;
  evidence: string[];
};

export type ResearchBrief = {
  summary: string;
  findings: ResearchFinding[];
  contradictions: ResearchContradiction[];
  gaps: string[];
  next_steps: string[];
};

export type ResearchRun = {
  id: string;
  tenant_id?: string;
  user_id?: string;
  topic: string;
  depth: number;
  status: string;
  brief: ResearchBrief;
  citations: Citation[];
  questions: string[];
  provider: string;
  warning: string;
  web_used?: number;
  created_at: number;
  updated_at?: number;
};

export type ResearchBlueprintResult = {
  research_id: string;
  course_id: string;
  blueprint: Blueprint;
};

export type LongformGenre = "article" | "report" | "essay" | "tutorial" | "custom";

export type CitationPolicy = "required" | "optional" | "forbidden";

export type LongformProfile = {
  genre: string;
  tone: string;
  audience: string;
  pov: string;
  citation_policy: string;
  unit_name?: string;
};

export type LongformSection = {
  id: string;
  title: string;
  summary: string;
  target_words: number;
  content: string;
  status: string;
};

export type Longform = {
  id: string;
  tenant_id?: string;
  user_id?: string;
  title: string;
  profile: LongformProfile;
  outline: LongformSection[];
  content: string;
  status: string;
  current_version: number;
  target_words: number;
  last_mode: string;
  citations: Citation[];
  created_at: number;
  updated_at: number;
};

export type LongformVersion = {
  id: string;
  version: number;
  note: string;
  mode: string;
  created_at: number;
  content_length: number;
};

export class ApiError extends Error {
  status: number;
  payload: Record<string, unknown> | null;

  constructor(
    message: string,
    status: number,
    payload: Record<string, unknown> | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }

  conflict(): VersionConflictPayload | null {
    if (this.status !== 409 || !this.payload) return null;
    const current = this.payload.current_version;
    if (typeof current !== "number") return null;
    const expected = this.payload.expected_version;
    return {
      detail: this.message,
      current_version: current,
      expected_version: typeof expected === "number" ? expected : undefined,
    };
  }
}

type RequestOptions = {
  anonymous?: boolean;
};

export async function request<T>(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (init.body && !(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (!options.anonymous) {
    const token = getToken();
    const tenantId = getTenantId();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (tenantId) headers["X-Tenant-Id"] = tenantId;
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      `无法连接后端服务（${API_BASE}）。请确认 FastAPI 已启动，或检查 VITE_API_BASE。`,
      0,
    );
  }
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    let body: Record<string, unknown> | null = null;
    try {
      const payload = (await response.json()) as Record<string, unknown> | null;
      body = payload;
      const detail = payload?.detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail)) {
        message = detail
          .map((item: { msg?: string }) => item?.msg ?? "")
          .filter(Boolean)
          .join("；");
      }
    } catch {
      message = `${message} ${response.statusText}`.trim();
    }
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
    }
    throw new ApiError(message, response.status, body);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  const token = getToken();
  const tenantId = getTenantId();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (tenantId) headers["X-Tenant-Id"] = tenantId;
  return headers;
}

export function mediaUrl(assetId: string): string {
  return `${API_BASE}/api/v1/media/${encodeURIComponent(assetId)}`;
}

function filenameFromDisposition(header: string | null): string {
  if (!header) return "";
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded?.[1]) {
    const raw = encoded[1].trim().replace(/^"|"$/g, "");
    try {
      return decodeURIComponent(raw);
    } catch {
      return raw;
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1] ? plain[1].trim() : "";
}

export async function exportDocument(
  sourceType: ExportSourceType,
  sourceId: string,
  format: ExportFormatId,
  options: {
    theme?: "light" | "dark";
    includeCitations?: boolean;
    fallbackName?: string;
  } = {},
): Promise<ExportResult> {
  const params = new URLSearchParams({ format });
  params.set("theme", options.theme ?? "light");
  params.set("include_citations", options.includeCitations === false ? "false" : "true");
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE}/api/v1/export/${sourceType}/${encodeURIComponent(sourceId)}?${params.toString()}`,
      { headers: authHeaders(), cache: "no-store" },
    );
  } catch {
    throw new ApiError(`无法连接后端服务（${API_BASE}）`, 0);
  }
  if (!response.ok) {
    let message = `导出失败（${response.status}）`;
    let payload: Record<string, unknown> | null = null;
    try {
      const body = (await response.json()) as Record<string, unknown> | null;
      payload = body;
      const detail = body?.detail;
      if (typeof detail === "string") message = detail;
    } catch {
      message = `${message} ${response.statusText}`.trim();
    }
    throw new ApiError(message, response.status, payload);
  }
  const blob = await response.blob();
  const filename =
    filenameFromDisposition(response.headers.get("content-disposition")) ||
    `${options.fallbackName || sourceType}.${format}`;
  return { blob, filename };
}

export async function uploadMediaFile(file: File): Promise<MediaAsset> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/api/v1/media/upload`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `上传失败（${response.status}）`;
    let payload: Record<string, unknown> | null = null;
    try {
      const body = (await response.json()) as Record<string, unknown> | null;
      payload = body;
      const detail = body?.detail;
      if (typeof detail === "string") message = detail;
    } catch {
      message = `${message} ${response.statusText}`.trim();
    }
    throw new ApiError(message, response.status, payload);
  }
  return (await response.json()) as MediaAsset;
}

export type CreationProfile = {
  id: string;
  name: string;
  genre: string;
  tone: string;
  audience: string;
  pov: string;
  citation_policy: string;
  target_words: number;
  is_shared: boolean;
  is_owner: boolean;
  created_at?: number;
  updated_at?: number;
};

export type KbSource = {
  source_id: string;
  source_name: string;
  chunk_count: number;
  char_count: number;
  tenant_id?: string;
  object_key?: string;
  created_at: number;
};

export type ThreadSummary = {
  id: string;
  course_id?: string;
  lesson_id?: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count?: number;
};

export const api = {
  health: () => request<Health>("/health"),

  listCourses: () =>
    request<{ count: number; courses: Course[] }>("/api/v1/courses"),

  createCourse: (payload: {
    title: string;
    subtitle?: string;
    audience?: string;
    difficulty?: string;
    language?: string;
  }) =>
    request<Course>("/api/v1/courses", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getCourse: (courseId: string) =>
    request<CourseDetail>(`/api/v1/courses/${courseId}`),

  createLesson: (
    courseId: string,
    payload: {
      title: string;
      order_index?: number | null;
      learning_objectives?: string[];
      prerequisites?: string[];
      content?: string;
      note?: string;
    },
  ) =>
    request<{ lesson: Lesson; version: number }>(
      `/api/v1/courses/${courseId}/lessons`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  getLesson: (lessonId: string) =>
    request<Lesson>(`/api/v1/lessons/${lessonId}`),

  generateLesson: (
    lessonId: string,
    payload: {
      topic?: string;
      top_k?: number;
      note?: string;
      source_ids?: string[];
      mode?: GenerationMode;
      expected_version?: number | null;
    } = {},
  ) =>
    request<GenerationResult>(`/api/v1/lessons/${lessonId}/generate`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listVersions: (lessonId: string) =>
    request<{
      lesson_id: string;
      current_version: number;
      count: number;
      versions: LessonVersion[];
    }>(`/api/v1/lessons/${lessonId}/versions`),

  getLessonVersion: (lessonId: string, version: number) =>
    request<{ lesson_id: string; version: LessonVersionDetail }>(
      `/api/v1/lessons/${lessonId}/versions/${version}`,
    ),

  diffLessonVersions: (lessonId: string, from: number, to: number) =>
    request<VersionDiffResult>(
      `/api/v1/lessons/${lessonId}/versions/diff?from=${from}&to=${to}`,
    ),

  revertLesson: (
    lessonId: string,
    version: number,
    note = "",
    expectedVersion?: number | null,
  ) =>
    request<{
      lesson: Lesson;
      version: number;
      reverted_from: number;
      note: string;
    }>(`/api/v1/lessons/${lessonId}/revert`, {
      method: "POST",
      body: JSON.stringify({
        version,
        note,
        expected_version: expectedVersion ?? null,
      }),
    }),

  askLesson: (lessonId: string, question: string, selection?: string) =>
    request<AskResult>(`/api/v1/lessons/${lessonId}/ask`, {
      method: "POST",
      body: JSON.stringify({
        question,
        selection: selection?.trim() ? selection.trim() : null,
      }),
    }),

  amendLesson: (
    lessonId: string,
    instruction: string,
    target?: string,
    mode: GenerationMode = "strict",
    expectedVersion?: number | null,
  ) =>
    request<AmendResult>(`/api/v1/lessons/${lessonId}/amend`, {
      method: "POST",
      body: JSON.stringify({
        instruction,
        target: target ?? null,
        mode,
        expected_version: expectedVersion ?? null,
      }),
    }),

  checkLessonCode: (lessonId: string) =>
    request<{
      lesson_id: string;
      blocks: {
        index: number;
        language: string;
        ok: boolean;
        stdout: string;
        stderr: string;
        exit_code: number;
        duration_ms: number;
      }[];
      summary: {
        total: number;
        executed: number;
        passed: number;
        failed: number;
        skipped: number;
        backend: string;
      };
    }>(`/api/v1/lessons/${lessonId}/code-check`, { method: "POST", body: JSON.stringify({}) }),

  getThread: (lessonId: string) =>
    request<ThreadView>(`/api/v1/lessons/${lessonId}/thread`),

  uploadKb: (file: File, sourceName?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (sourceName?.trim()) {
      form.append("source_name", sourceName.trim());
    }
    return request<IngestResult>("/api/v1/kb/upload", {
      method: "POST",
      body: form,
    });
  },

  searchKb: (query: string, topK = 5) =>
    request<SearchResponse>("/api/v1/kb/search", {
      method: "POST",
      body: JSON.stringify({ query, top_k: topK }),
    }),

  deleteKbSource: (sourceId: string) =>
    request<{ source_id: string; deleted_chunks: number }>(
      `/api/v1/kb/sources/${encodeURIComponent(sourceId)}`,
      { method: "DELETE" },
    ),

  getBlueprint: (courseId: string) =>
    request<BlueprintEnvelope>(`/api/v1/courses/${courseId}/blueprint`),

  generateBlueprint: (
    courseId: string,
    payload: {
      mode?: GenerationMode;
      top_k?: number;
      source_ids?: string[];
      focus?: string;
      expected_version?: number | null;
    } = {},
  ) =>
    request<Blueprint>(`/api/v1/courses/${courseId}/blueprint/generate`, {
      method: "POST",
      body: JSON.stringify({
        mode: payload.mode ?? "strict",
        top_k: payload.top_k ?? null,
        source_ids: payload.source_ids ?? null,
        focus: payload.focus ?? "",
        expected_version: payload.expected_version ?? null,
      }),
    }),

  saveBlueprint: (
    courseId: string,
    blueprint: Blueprint,
    expectedVersion?: number | null,
  ) =>
    request<Blueprint>(`/api/v1/courses/${courseId}/blueprint`, {
      method: "PUT",
      body: JSON.stringify({
        blueprint,
        expected_version: expectedVersion ?? null,
      }),
    }),

  getLessonLock: (lessonId: string) =>
    request<{ lock: LessonLockInfo | null }>(
      `/api/v1/lessons/${lessonId}/lock`,
    ),

  acquireLessonLock: (lessonId: string, force = false) =>
    request<{ acquired: boolean; lock: LessonLockInfo }>(
      `/api/v1/lessons/${lessonId}/lock`,
      { method: "POST", body: JSON.stringify({ force }) },
    ),

  heartbeatLessonLock: (lessonId: string, token: string) =>
    request<{ lock: LessonLockInfo }>(
      `/api/v1/lessons/${lessonId}/lock/heartbeat`,
      { method: "POST", body: JSON.stringify({ token }) },
    ),

  releaseLessonLock: (lessonId: string, token: string) =>
    request<{ ok: boolean }>(
      `/api/v1/lessons/${lessonId}/lock?token=${encodeURIComponent(token)}`,
      { method: "DELETE" },
    ),

  applyBlueprint: (courseId: string) =>
    request<ApplyBlueprintResult>(
      `/api/v1/courses/${courseId}/blueprint/apply`,
      { method: "POST" },
    ),

  getGlossary: (courseId: string) =>
    request<GlossaryPayload>(`/api/v1/courses/${courseId}/glossary`),

  saveGlossary: (courseId: string, terms: GlossaryTerm[]) =>
    request<GlossaryPayload>(`/api/v1/courses/${courseId}/glossary`, {
      method: "PUT",
      body: JSON.stringify({ terms }),
    }),

  reviewLesson: (
    lessonId: string,
    action: "approve" | "request_revision",
    note = "",
  ) =>
    request<ReviewResult>(`/api/v1/lessons/${lessonId}/review`, {
      method: "POST",
      body: JSON.stringify({ action, note }),
    }),

  getProgress: (courseId: string) =>
    request<CourseProgress>(`/api/v1/courses/${courseId}/progress`),

  listLessonReviews: (lessonId: string) =>
    request<{
      lesson_id: string;
      count: number;
      reviews: LessonReview[];
    }>(`/api/v1/lessons/${lessonId}/reviews`),

  register: (payload: {
    email: string;
    password: string;
    display_name: string;
  }) =>
    request<AuthPayload>(
      "/api/v1/auth/register",
      { method: "POST", body: JSON.stringify(payload) },
      { anonymous: true },
    ),

  login: (payload: { email: string; password: string }) =>
    request<AuthPayload>(
      "/api/v1/auth/login",
      { method: "POST", body: JSON.stringify(payload) },
      { anonymous: true },
    ),

  logout: () => request<{ ok: boolean }>("/api/v1/auth/logout", { method: "POST" }),

  getMe: () => request<MeResponse>("/api/v1/auth/me"),

  updateProfile: (payload: { display_name?: string; email?: string }) =>
    request<{ user: AuthUser; tenants: TenantMembership[] }>("/api/v1/auth/me", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  changePassword: (payload: { current_password: string; new_password: string }) =>
    request<{ ok: boolean }>("/api/v1/auth/password", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  uploadAvatar: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ ok: boolean; avatar_url: string }>("/api/v1/auth/avatar", {
      method: "PUT",
      body: form,
    });
  },

  listTenants: () => request<TenantList>("/api/v1/tenants"),

  createTenant: (payload: { name: string; kind: "personal" | "team" }) =>
    request<{ tenant: TenantSummary; role: Role }>("/api/v1/tenants", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  renameTenant: (targetTenantId: string, name: string) =>
    request<TenantSummary>(`/api/v1/tenants/${targetTenantId}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),

  deleteTenant: (targetTenantId: string) =>
    request<{ ok: boolean }>(`/api/v1/tenants/${targetTenantId}`, {
      method: "DELETE",
    }),

  transferTenant: (targetTenantId: string, userId: string) =>
    request<{ ok: boolean; owner_user_id?: string }>(
      `/api/v1/tenants/${targetTenantId}/transfer`,
      { method: "POST", body: JSON.stringify({ user_id: userId }) },
    ),

  listMembers: (tenantId: string) =>
    request<{ count: number; members: Member[] }>(
      `/api/v1/tenants/${tenantId}/members`,
    ),

  addMember: (tenantId: string, payload: { email: string; role: Role }) =>
    request<Member>(`/api/v1/tenants/${tenantId}/members`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateMemberRole: (tenantId: string, userId: string, role: Role) =>
    request<Member>(`/api/v1/tenants/${tenantId}/members/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),

  removeMember: (tenantId: string, userId: string) =>
    request<{ ok?: boolean }>(`/api/v1/tenants/${tenantId}/members/${userId}`, {
      method: "DELETE",
    }),

  getQuota: () => request<Quota>("/api/v1/quotas"),

  getQuotaHistory: (days = 30) =>
    request<QuotaHistory>(`/api/v1/quotas/history?days=${days}`),

  listRoles: () => request<RoleList>("/api/v1/roles"),

  createRole: (payload: {
    name: string;
    actions: RoleAction[];
    scope: RoleScope;
  }) =>
    request<RoleRecord>("/api/v1/roles", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateRole: (
    roleId: string,
    payload: { name?: string; actions?: RoleAction[]; scope?: RoleScope },
  ) =>
    request<RoleRecord>(`/api/v1/roles/${roleId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteRole: (roleId: string) =>
    request<{ ok?: boolean }>(`/api/v1/roles/${roleId}`, { method: "DELETE" }),

  getCourseGrants: (courseId: string) =>
    request<CourseGrants>(`/api/v1/courses/${courseId}/grants`),

  saveCourseGrants: (
    courseId: string,
    grants: { user_id: string; level: "read" | "write" }[],
  ) =>
    request<CourseGrants>(`/api/v1/courses/${courseId}/grants`, {
      method: "PUT",
      body: JSON.stringify({ grants }),
    }),

  getCapabilities: () => request<Capabilities>("/api/v1/me/capabilities"),

  updateQuota: (payload: QuotaUsage) =>
    request<Quota>("/api/v1/quotas", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  getProviderSettings: () => request<ProviderSettings>("/api/v1/settings/provider"),

  saveProviderSettings: (payload: ProviderPayload) =>
    request<ProviderSettings>("/api/v1/settings/provider", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  resetProviderSettings: () =>
    request<ProviderSettings>("/api/v1/settings/provider", { method: "DELETE" }),

  testProvider: (payload?: { model?: string }) =>
    request<ProviderTestResult>("/api/v1/settings/provider/test", {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    }),

  listAdminProviders: () =>
    request<{ count: number; providers: ServerProvider[] }>("/api/v1/admin/providers"),

  createAdminProvider: (payload: ServerProviderPayload) =>
    request<ServerProvider>("/api/v1/admin/providers", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateAdminProvider: (providerId: string, payload: ServerProviderPayload) =>
    request<ServerProvider>(`/api/v1/admin/providers/${providerId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteAdminProvider: (providerId: string) =>
    request<{ ok?: boolean }>(`/api/v1/admin/providers/${providerId}`, {
      method: "DELETE",
    }),

  testAdminProvider: (providerId: string, payload?: { model?: string }) =>
    request<ProviderTestResult>(`/api/v1/admin/providers/${providerId}/test`, {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    }),

  listMyProviders: () =>
    request<{ count: number; providers: UserProvider[] }>("/api/v1/settings/providers"),

  createMyProvider: (payload: ServerProviderPayload) =>
    request<UserProvider>("/api/v1/settings/providers", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateMyProvider: (providerId: string, payload: ServerProviderPayload) =>
    request<UserProvider>(`/api/v1/settings/providers/${providerId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteMyProvider: (providerId: string) =>
    request<{ ok?: boolean }>(`/api/v1/settings/providers/${providerId}`, {
      method: "DELETE",
    }),

  testMyProvider: (providerId: string, payload?: { model?: string }) =>
    request<ProviderTestResult>(`/api/v1/settings/providers/${providerId}/test`, {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    }),

  runResearch: (payload: {
    topic: string;
    depth?: number;
    top_k?: number;
    source_ids?: string[];
  }) =>
    request<ResearchRun>("/api/v1/research", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listResearch: () =>
    request<{ count: number; runs: ResearchRun[] }>("/api/v1/research"),

  getResearch: (runId: string) => request<ResearchRun>(`/api/v1/research/${runId}`),

  deleteResearch: (runId: string) =>
    request<{ ok?: boolean }>(`/api/v1/research/${runId}`, { method: "DELETE" }),

  researchToBlueprint: (
    runId: string,
    payload: {
      create_course?: boolean;
      course_id?: string;
      course_title?: string;
      mode?: GenerationMode;
    },
  ) =>
    request<ResearchBlueprintResult>(`/api/v1/research/${runId}/blueprint`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  createLongform: (payload: {
    title: string;
    genre?: LongformGenre | string;
    tone?: string;
    audience?: string;
    pov?: string;
    citation_policy?: CitationPolicy | string;
    target_words?: number;
    mode?: GenerationMode;
    profile_id?: string;
  }) =>
    request<Longform>("/api/v1/longforms", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listLongforms: () =>
    request<{ count: number; longforms: Longform[] }>("/api/v1/longforms"),

  getLongform: (longformId: string) =>
    request<Longform>(`/api/v1/longforms/${longformId}`),

  generateSection: (
    longformId: string,
    sectionId: string,
    payload?: { mode?: GenerationMode; top_k?: number },
  ) =>
    request<{ section_id: string; content: string; longform: Longform }>(
      `/api/v1/longforms/${longformId}/sections/${sectionId}/generate`,
      { method: "POST", body: JSON.stringify(payload ?? {}) },
    ),

  generateLongform: (
    longformId: string,
    payload?: { mode?: GenerationMode; top_k?: number; expected_version?: number },
  ) =>
    request<Longform>(`/api/v1/longforms/${longformId}/generate`, {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    }),

  rewriteLongform: (
    longformId: string,
    payload: {
      instruction: string;
      mode?: GenerationMode;
      expected_version?: number;
    },
  ) =>
    request<Longform>(`/api/v1/longforms/${longformId}/rewrite`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listLongformVersions: (longformId: string) =>
    request<{ count: number; versions: LongformVersion[] }>(
      `/api/v1/longforms/${longformId}/versions`,
    ),

  getLongformVersion: (longformId: string, version: number) =>
    request<{ longform_id: string; version: LongformVersionDetail }>(
      `/api/v1/longforms/${longformId}/versions/${version}`,
    ),

  diffLongformVersions: (longformId: string, from: number, to: number) =>
    request<VersionDiffResult>(
      `/api/v1/longforms/${longformId}/versions/diff?from=${from}&to=${to}`,
    ),

  revertLongform: (longformId: string, version: number) =>
    request<Longform>(`/api/v1/longforms/${longformId}/revert`, {
      method: "POST",
      body: JSON.stringify({ version }),
    }),

  deleteLongform: (longformId: string) =>
    request<{ ok?: boolean }>(`/api/v1/longforms/${longformId}`, {
      method: "DELETE",
    }),

  storageInfo: () => request<StorageInfo>("/api/v1/storage/info"),

  getLongformGrants: (longformId: string) =>
    request<LongformGrants>(`/api/v1/longforms/${longformId}/grants`),

  saveLongformGrants: (
    longformId: string,
    grants: { user_id: string; level: string }[],
  ) =>
    request<LongformGrants>(`/api/v1/longforms/${longformId}/grants`, {
      method: "PUT",
      body: JSON.stringify({ grants }),
    }),

  getProviderShares: (providerId: string) =>
    request<ProviderShares>(`/api/v1/settings/providers/${providerId}/shares`),

  saveProviderShares: (
    providerId: string,
    shares: { user_id: string; level: string }[],
  ) =>
    request<ProviderShares>(`/api/v1/settings/providers/${providerId}/shares`, {
      method: "PUT",
      body: JSON.stringify({ shares }),
    }),

  listAdminUsers: (status?: string, options?: { includeDeleted?: boolean }) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (options?.includeDeleted) params.set("include_deleted", "true");
    const query = params.toString();
    return request<AdminUserList>(
      `/api/v1/admin/users${query ? `?${query}` : ""}`,
    );
  },

  approveAdminUser: (userId: string) =>
    request<{ ok?: boolean }>(`/api/v1/admin/users/${userId}/approve`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  rejectAdminUser: (userId: string, reason?: string) =>
    request<{ ok?: boolean }>(`/api/v1/admin/users/${userId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? "" }),
    }),

  updateCourse: (
    courseId: string,
    payload: {
      title?: string;
      subtitle?: string;
      audience?: string;
      difficulty?: string;
      language?: string;
    },
  ) =>
    request<Course>(`/api/v1/courses/${courseId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteCourse: (courseId: string) =>
    request<{ course_id: string; deleted: Record<string, number> }>(
      `/api/v1/courses/${courseId}`,
      { method: "DELETE" },
    ),

  updateLesson: (
    lessonId: string,
    payload: {
      title?: string;
      learning_objectives?: string[];
      prerequisites?: string[];
      order_index?: number;
      status?: string;
    },
  ) =>
    request<Lesson>(`/api/v1/lessons/${lessonId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteLesson: (lessonId: string) =>
    request<{ lesson_id: string; deleted_versions: number; deleted_threads: number }>(
      `/api/v1/lessons/${lessonId}`,
      { method: "DELETE" },
    ),

  reorderLessons: (courseId: string, lessonIds: string[]) =>
    request<CourseDetail>(`/api/v1/courses/${courseId}/lessons/reorder`, {
      method: "POST",
      body: JSON.stringify({ lesson_ids: lessonIds }),
    }),

  updateLongform: (
    longformId: string,
    payload: {
      title?: string;
      profile?: Record<string, unknown>;
      target_words?: number;
    },
  ) =>
    request<Longform>(`/api/v1/longforms/${longformId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  saveLongformContent: (
    longformId: string,
    payload: { content: string; note?: string; expected_version?: number | null },
  ) =>
    request<Longform>(`/api/v1/longforms/${longformId}/content`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  createLongformSection: (
    longformId: string,
    payload: {
      title: string;
      summary?: string;
      target_words?: number;
      after_id?: string | null;
    },
  ) =>
    request<{ section: LongformSection; longform: Longform }>(
      `/api/v1/longforms/${longformId}/sections`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  updateLongformSection: (
    longformId: string,
    sectionId: string,
    payload: {
      title?: string;
      summary?: string;
      target_words?: number;
      content?: string;
    },
  ) =>
    request<Longform>(`/api/v1/longforms/${longformId}/sections/${sectionId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteLongformSection: (longformId: string, sectionId: string) =>
    request<Longform>(`/api/v1/longforms/${longformId}/sections/${sectionId}`, {
      method: "DELETE",
    }),

  reorderLongformSections: (longformId: string, sectionIds: string[]) =>
    request<Longform>(`/api/v1/longforms/${longformId}/sections/reorder`, {
      method: "POST",
      body: JSON.stringify({ section_ids: sectionIds }),
    }),

  listCreationProfiles: () =>
    request<{ count: number; profiles: CreationProfile[] }>(
      "/api/v1/creation-profiles",
    ),

  createCreationProfile: (payload: {
    name: string;
    genre?: string;
    tone?: string;
    audience?: string;
    pov?: string;
    citation_policy?: string;
    target_words?: number;
    is_shared?: boolean;
  }) =>
    request<CreationProfile>("/api/v1/creation-profiles", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateCreationProfile: (
    profileId: string,
    payload: {
      name?: string;
      genre?: string;
      tone?: string;
      audience?: string;
      pov?: string;
      citation_policy?: string;
      target_words?: number;
      is_shared?: boolean;
    },
  ) =>
    request<CreationProfile>(`/api/v1/creation-profiles/${profileId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteCreationProfile: (profileId: string) =>
    request<{ ok?: boolean }>(`/api/v1/creation-profiles/${profileId}`, {
      method: "DELETE",
    }),

  updateAdminUser: (
    userId: string,
    payload: {
      display_name?: string;
      email?: string;
      status?: string;
      role?: string;
    },
  ) =>
    request<AdminUser>(`/api/v1/admin/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteAdminUser: (
    userId: string,
    payload?: { transfer_to_user_id?: string; force?: boolean },
  ) =>
    request<{ ok?: boolean; transferred?: number }>(
      `/api/v1/admin/users/${userId}`,
      {
        method: "DELETE",
        body: JSON.stringify(payload ?? {}),
      },
    ),

  restoreAdminUser: (userId: string) =>
    request<{ ok?: boolean; user?: AdminUser }>(
      `/api/v1/admin/users/${userId}/restore`,
      {
        method: "POST",
        body: JSON.stringify({}),
      },
    ),

  resetAdminPassword: (userId: string, newPassword: string) =>
    request<{ ok?: boolean }>(`/api/v1/admin/users/${userId}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ new_password: newPassword }),
    }),

  listKbSources: () =>
    request<{ count: number; sources: KbSource[] }>("/api/v1/kb/sources"),

  renameKbSource: (sourceId: string, sourceName: string) =>
    request<{ source_id: string; source_name: string }>(
      `/api/v1/kb/sources/${encodeURIComponent(sourceId)}`,
      { method: "PATCH", body: JSON.stringify({ source_name: sourceName }) },
    ),

  listThreads: () =>
    request<{ count: number; threads: ThreadSummary[] }>("/api/v1/threads"),

  renameThread: (threadId: string, title: string) =>
    request<{ ok?: boolean }>(`/api/v1/threads/${threadId}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),

  deleteThread: (threadId: string) =>
    request<{ ok?: boolean }>(`/api/v1/threads/${threadId}`, {
      method: "DELETE",
    }),

  deleteJob: (jobId: string) =>
    request<{ ok?: boolean }>(`/api/v1/jobs/${jobId}`, { method: "DELETE" }),

  updateResearch: (runId: string, topic: string) =>
    request<ResearchRun>(`/api/v1/research/${runId}`, {
      method: "PATCH",
      body: JSON.stringify({ topic }),
    }),

  getExportFormats: () =>
    request<{ formats: ExportFormat[] }>("/api/v1/export/formats"),

  listMedia: (params: { kind?: string; limit?: number } = {}) => {
    const search = new URLSearchParams();
    if (params.kind) search.set("kind", params.kind);
    if (params.limit) search.set("limit", String(params.limit));
    const query = search.toString();
    return request<{ count: number; assets: MediaAsset[] }>(
      `/api/v1/media${query ? `?${query}` : ""}`,
    );
  },

  uploadMedia: (file: File) => uploadMediaFile(file),

  generateMedia: (payload: { prompt: string; size?: string; n?: number }) =>
    request<{ assets: MediaAsset[] }>("/api/v1/media/generate", {
      method: "POST",
      body: JSON.stringify({
        prompt: payload.prompt,
        size: payload.size ?? "1024x1024",
        n: payload.n ?? 1,
      }),
    }),

  deleteMedia: (assetId: string) =>
    request<{ ok?: boolean }>(`/api/v1/media/${assetId}`, { method: "DELETE" }),
};
