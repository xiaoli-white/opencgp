import {
  AUTH_REQUIRED_EVENT,
  getTenantId,
  getToken,
  type Role,
} from "@/lib/session";

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"
).replace(/\/+$/, "");

export type AuthUser = {
  id: string;
  email: string;
  display_name: string;
  created_at: number;
  is_active?: boolean;
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
  tenants: AuthTenant[];
  auth_mode: AuthMode;
};

export type AuthPayload = {
  token: string;
  user: AuthUser;
  tenants: AuthTenant[];
};

export type TenantList = {
  count: number;
  tenants: AuthTenant[];
};

export type Member = {
  id: string;
  tenant_id: string;
  user_id: string;
  role: Role;
  created_at: number;
  user_email: string;
  user_display_name: string;
};

export type QuotaUsage = {
  monthly_generations: number;
  monthly_uploads: number;
  storage_bytes: number;
};

export type Quota = {
  tenant_id: string;
  period: string;
  limits: QuotaUsage;
  usage: QuotaUsage & { period?: string };
  remaining: QuotaUsage;
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

export type IngestResult = {
  source_id: string;
  source_name: string;
  parser: string;
  chunk_count: number;
  char_count: number;
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

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type RequestOptions = {
  anonymous?: boolean;
};

async function request<T>(
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
      `无法连接后端服务（${API_BASE}）。请确认 FastAPI 已启动，或检查 NEXT_PUBLIC_API_BASE。`,
      0,
    );
  }
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const payload = await response.json();
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
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

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

  revertLesson: (lessonId: string, version: number, note = "") =>
    request<{
      lesson: Lesson;
      version: number;
      reverted_from: number;
      note: string;
    }>(`/api/v1/lessons/${lessonId}/revert`, {
      method: "POST",
      body: JSON.stringify({ version, note }),
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
  ) =>
    request<AmendResult>(`/api/v1/lessons/${lessonId}/amend`, {
      method: "POST",
      body: JSON.stringify({ instruction, target: target ?? null, mode }),
    }),

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
    } = {},
  ) =>
    request<Blueprint>(`/api/v1/courses/${courseId}/blueprint/generate`, {
      method: "POST",
      body: JSON.stringify({
        mode: payload.mode ?? "strict",
        top_k: payload.top_k ?? null,
        source_ids: payload.source_ids ?? null,
        focus: payload.focus ?? "",
      }),
    }),

  saveBlueprint: (courseId: string, blueprint: Blueprint) =>
    request<Blueprint>(`/api/v1/courses/${courseId}/blueprint`, {
      method: "PUT",
      body: JSON.stringify({ blueprint }),
    }),

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

  listTenants: () => request<TenantList>("/api/v1/tenants"),

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

  updateQuota: (payload: QuotaUsage) =>
    request<Quota>("/api/v1/quotas", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
};
