export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"
).replace(/\/+$/, "");

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
  created_at: number;
  updated_at: number;
};

export type LessonVersion = {
  id: string;
  lesson_id: string;
  version: number;
  content: string;
  citations: Citation[];
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

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (init.body && !(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
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

  amendLesson: (lessonId: string, instruction: string, target?: string) =>
    request<AmendResult>(`/api/v1/lessons/${lessonId}/amend`, {
      method: "POST",
      body: JSON.stringify({ instruction, target: target ?? null }),
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
};
