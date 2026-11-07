import {
  AUTH_REQUIRED_EVENT,
  getTenantId,
  getToken,
  type Role,
  type RoleAction,
} from "@/lib/session";

export const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(
  /\/+$/,
  "",
);

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

export type SeriesGrant = {
  user_id: string;
  user_email: string;
  user_display_name: string;
  level: "read" | "write";
};

export type SeriesGrants = {
  series_id: string;
  count: number;
  grants: SeriesGrant[];
};

export type ShareEntry = {
  user_id: string;
  user_email: string;
  user_display_name: string;
  level: string;
};

export type PieceGrants = {
  piece_id: string;
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
  visible_series_ids: string[] | "all";
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

export type UnitVersionDetail = UnitVersion & {
  citation_count?: number;
  content_length?: number;
  approved_at?: number;
  reviewer_id?: string;
};

export type PieceVersionDetail = {
  id: string;
  piece_id: string;
  version: number;
  content: string;
  outline: PieceSection[];
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
  extra_body?: Record<string, unknown>;
  extra_headers?: Record<string, string>;
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
  extra_body?: Record<string, unknown>;
  extra_headers?: Record<string, string>;
  disable_reasoning?: boolean;
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

export type RetrievalKind = "embedding" | "rerank";

export type RetrievalProvider = {
  id: string;
  tenant_id?: string;
  user_id?: string;
  scope?: string;
  kind: RetrievalKind | string;
  name: string;
  backend: string;
  base_url: string;
  model: string;
  dim: number;
  enabled: boolean;
  is_default: boolean;
  has_key: boolean;
  meta?: Record<string, unknown>;
  version?: number;
  created_at?: number;
  updated_at?: number;
};

export type RetrievalProviderList = {
  count: number;
  providers: RetrievalProvider[];
};

export type RetrievalProviderPayload = {
  kind?: string;
  name?: string;
  backend?: string;
  base_url?: string;
  model?: string;
  dim?: number;
  api_key?: string;
  is_default?: boolean;
  enabled?: boolean;
  scope?: string;
  meta?: Record<string, unknown>;
};

export type RetrievalTestResult = {
  ok: boolean;
  latency_ms: number;
  dim?: number;
  expected_dim?: number;
  sample_score?: number;
  dim_updated?: boolean;
  error?: string;
};

export type RetrievalEffectiveProvider = {
  provider_id: string;
  model: string;
  dim?: number;
  backend: string;
  source: string;
  enabled: boolean;
  has_key: boolean;
  error?: string;
};

export type RetrievalScopeSettings = {
  embedding_provider_id: string | null;
  rerank_provider_id: string | null;
  vector_weight: number | null;
  rerank_weight: number | null;
  rerank_top_n: number | null;
  configured: boolean;
};

export type RetrievalDefaults = {
  vector_weight: number;
  rerank_weight: number;
  rerank_top_n: number;
};

export type RetrievalSettings = {
  effective: {
    embedding: RetrievalEffectiveProvider;
    rerank: RetrievalEffectiveProvider;
    weights: {
      vector: number;
      rerank: number;
      top_n: number;
      sources?: Record<string, string>;
    };
  };
  scopes: {
    user: RetrievalScopeSettings;
    tenant: RetrievalScopeSettings;
  };
  defaults: RetrievalDefaults;
  embedding: RetrievalEffectiveProvider;
  rerank: RetrievalEffectiveProvider;
  weights: {
    vector: number;
    rerank: number;
    top_n: number;
    sources: Record<string, string>;
  };
  source: string;
  sources: Record<string, string>;
  embedding_provider_id: string;
  rerank_provider_id: string;
  vector_weight: number;
  rerank_weight: number;
  rerank_top_n: number;
};

export type RetrievalSettingsPayload = {
  scope: "user" | "tenant";
  embedding_provider_id?: string | null;
  rerank_provider_id?: string | null;
  vector_weight?: number | null;
  rerank_weight?: number | null;
  rerank_top_n?: number | null;
};

export type EmbeddingStatus = {
  provider_id: string;
  provider_name: string;
  backend: string;
  current_backend: string;
  source: string;
  model: string;
  dim: number;
  chunks_total: number;
  chunks_embedded: number;
  coverage: number;
  models: { provider_id: string; model: string; dim: number; chunks: number }[];
  stale: { chunks: number; bytes: number };
  note?: string;
};

export type EmbeddingBackfillResult = {
  job_id: string;
  queued: boolean;
  provider_id: string;
  stale: { chunks: number; bytes: number };
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
  keyword_score?: number | null;
  vector_score?: number | null;
  rerank_score?: number | null;
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

export type ExportSourceType = "series" | "piece";

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

export type Series = {
  id: string;
  title: string;
  subtitle: string;
  brief: string;
  audience: string;
  difficulty: string;
  language: string;
  profile_id?: string;
  created_at: number;
  updated_at: number;
};

export type LockSummary = {
  user_id?: string;
  user_name?: string;
  token?: string;
  expires_at?: number;
  heartbeat_at?: number;
  is_mine?: boolean;
};

export type Unit = {
  id: string;
  series_id: string;
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
  lock?: LockSummary | null;
  lock_state?: string;
  locked_by_me?: boolean;
  locked_by_other?: boolean;
};

export type UnitVersion = {
  id: string;
  unit_id: string;
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
  unit_id: string;
  thread_id: string;
  title: string;
  message_count: number;
  messages: Message[];
  returned_count?: number;
  series_id?: string;
};

export type GenerationResult = {
  unit_id: string;
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
  unit_id: string;
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
  unit_id: string;
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

export type SeriesDetail = {
  series: Series;
  unit_count: number;
  units: Unit[];
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
  unit_id: string | null;
  status: string;
};

export type Blueprint = {
  series_id: string;
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

export type UnitReview = {
  id: string;
  unit_id: string;
  action: "approve" | "request_revision" | string;
  note: string;
  version: number;
  status: string;
  created_at: number;
};

export type SeriesProgress = {
  series_id: string;
  total: number;
  by_status: Record<string, number>;
  approved: number;
  pending_review: number;
  next_unit_id: string | null;
  blueprint_ready: boolean;
  blueprint_version: number;
};

export type GlossaryPayload = {
  series_id: string;
  count: number;
  glossary: GlossaryTerm[];
};

export type ApplyBlueprintResult = {
  created_units: Unit[];
  blueprint: Blueprint;
  created_count: number;
};

export type ReviewResult = {
  unit: Unit;
  review: UnitReview;
  series_progress: SeriesProgress;
};

export type UnitLockInfo = {
  unit_id: string;
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
  series_id: string;
  blueprint: Blueprint;
};

export type PieceGenre = "article" | "report" | "essay" | "tutorial" | "custom";

export type CitationPolicy = "required" | "optional" | "forbidden";

export type PieceProfile = {
  genre: string;
  tone: string;
  audience: string;
  pov: string;
  citation_policy: string;
  unit_name?: string;
};

export type PieceSection = {
  id: string;
  title: string;
  summary: string;
  target_words: number;
  content: string;
  status: string;
};

export type Piece = {
  id: string;
  tenant_id?: string;
  user_id?: string;
  title: string;
  brief?: string;
  profile: PieceProfile;
  outline: PieceSection[];
  content: string;
  status: string;
  current_version: number;
  target_words: number;
  last_mode: string;
  citations: Citation[];
  created_at: number;
  updated_at: number;
  lock?: LockSummary | null;
  lock_state?: string;
  locked_by_me?: boolean;
  locked_by_other?: boolean;
};

export type PieceVersion = {
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
      `Unable to reach the backend service (${API_BASE}). Make sure the FastAPI server is running, or check VITE_API_BASE.`,
      0,
    );
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
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
          .join("; ");
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

async function exportProfileFile(profileId: string): Promise<ExportResult> {
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE}/api/v1/profiles/${encodeURIComponent(profileId)}/export`,
      { headers: authHeaders(), cache: "no-store" },
    );
  } catch {
    throw new ApiError(`Unable to reach the backend service (${API_BASE})`, 0);
  }
  if (!response.ok) {
    let message = `Export failed (${response.status})`;
    try {
      const body = (await response.json()) as Record<string, unknown> | null;
      const detail = body?.detail;
      if (typeof detail === "string") message = detail;
    } catch {
      message = `${message} ${response.statusText}`.trim();
    }
    throw new ApiError(message, response.status);
  }
  const blob = await response.blob();
  const filename =
    filenameFromDisposition(response.headers.get("content-disposition")) ||
    `${profileId}.profile.json`;
  return { blob, filename };
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
    throw new ApiError(`Unable to reach the backend service (${API_BASE})`, 0);
  }
  if (!response.ok) {
    let message = `Export failed (${response.status})`;
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
    let message = `Upload failed (${response.status})`;
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

export type ProfileMetaSpec = {
  name?: string;
  description?: string;
  tags?: string[];
  icon?: string;
};

export type ProfileUnitSpec = {
  name?: string;
  plural?: string;
  min_units?: number;
  max_units?: number;
  default_words?: number;
};

export type ProfileStructureSpec = {
  depth?: number;
  sections_per_unit?: number[];
  requires_outline?: boolean;
};

export type ProfileVoiceSpec = {
  tone?: string;
  pov?: string;
  tense?: string;
  forbidden_phrases?: string[];
};

export type ProfileGroundingSpec = {
  citation_policy?: string;
  min_evidence?: number;
  allow_web?: boolean;
};

export type ProfileAssetsSpec = {
  glossary?: boolean;
  setting_book?: boolean;
  character_sheet?: boolean;
  auto_images?: boolean;
  max_images?: number;
  style?: string;
};

export type ProfileValidationSpec = {
  validators?: string[];
  strictness?: string;
};

export type ProfilePromptsSpec = {
  system?: string;
  outline?: string;
  unit?: string;
  revise?: string;
};

export type ProfileExportSpec = {
  default_format?: string;
  include_citations?: boolean;
};

export type ProfileSpec = {
  meta?: ProfileMetaSpec;
  unit?: ProfileUnitSpec;
  structure?: ProfileStructureSpec;
  voice?: ProfileVoiceSpec;
  grounding?: ProfileGroundingSpec;
  assets?: ProfileAssetsSpec;
  validation?: ProfileValidationSpec;
  prompts?: ProfilePromptsSpec;
  export?: ProfileExportSpec;
};

export type ProfileScope = "user" | "tenant" | "global";

export type WorkProfile = {
  id: string;
  tenant_id?: string;
  name: string;
  description: string;
  spec: ProfileSpec;
  scope?: ProfileScope | string;
  is_builtin: boolean;
  is_owner: boolean;
  can_edit?: boolean;
  is_shared: boolean;
  shared_by_owner?: boolean;
  shared_to_me?: boolean;
  share_level?: string;
  owner_name?: string;
  owner_user_id?: string;
  version: number;
  created_at?: number;
  updated_at?: number;
};

export type ProfileSampleIssue = {
  level: string;
  message: string;
  where?: string;
};

export type ProfileSampleResult = {
  name: string;
  passed: boolean;
  score: number;
  issues: ProfileSampleIssue[];
};

export type ProfileSampleReport = {
  results: ProfileSampleResult[];
  summary?: { passed?: number; warnings?: number; errors?: number };
};

export type ProfileSample = {
  text: string;
  chars: number;
  target_chars?: number;
  model: string;
  elapsed_ms: number;
  skipped?: string[];
  validation: ProfileSampleReport;
};

export type ProfileValidationIssue = {
  path: string;
  message: string;
};

export type ProfileValidation = {
  ok: boolean;
  errors: ProfileValidationIssue[];
  warnings: ProfileValidationIssue[];
  spec: ProfileSpec;
};

export type ProfilePreview = {
  profile_id?: string;
  unit_name?: string;
  system_prompt: string;
  outline_prompt: string;
  unit_prompt: string;
  revise_prompt?: string;
};

export type ProfileShareLevel = "read" | "use" | "manage";

export type ProfileShare = {
  user_id: string;
  user_email?: string;
  user_display_name?: string;
  level: ProfileShareLevel;
};

export type ProfileShareInput = {
  user_id: string;
  level: ProfileShareLevel;
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
  series_id?: string;
  unit_id?: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count?: number;
};

export type ShareResourceType = "series" | "piece";

export type ShareLink = {
  id: string;
  resource_type: ShareResourceType;
  resource_id: string;
  token: string;
  url: string;
  expires_at: number;
  revoked: boolean | number;
  view_count: number;
  created_at: number;
};

export type PublicShareChapter = {
  title: string;
  content: string;
};

export type PublicShareCitation = {
  source_name?: string;
  chunk_index?: number;
};

export type PublicShare = {
  resource_type: ShareResourceType;
  title: string;
  subtitle?: string;
  author?: string;
  created_at: number;
  chapters: PublicShareChapter[];
  citations?: PublicShareCitation[];
  expires_at: number;
  view_count: number;
};

export const api = {
  health: () => request<Health>("/health"),

  listSeries: () =>
    request<{ count: number; series: Series[] }>("/api/v1/series"),

  createSeries: (payload: {
    title: string;
    subtitle?: string;
    brief?: string;
    audience?: string;
    difficulty?: string;
    language?: string;
    profile_id?: string;
  }) =>
    request<Series>("/api/v1/series", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getSeries: (seriesId: string) =>
    request<SeriesDetail>(`/api/v1/series/${seriesId}`),

  createUnit: (
    seriesId: string,
    payload: {
      title: string;
      order_index?: number | null;
      learning_objectives?: string[];
      prerequisites?: string[];
      content?: string;
      note?: string;
    },
  ) =>
    request<{ unit: Unit; version: number }>(
      `/api/v1/series/${seriesId}/units`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  getUnit: (unitId: string) =>
    request<Unit>(`/api/v1/units/${unitId}`),

  generateUnit: (
    unitId: string,
    payload: {
      topic?: string;
      top_k?: number;
      note?: string;
      source_ids?: string[];
      mode?: GenerationMode;
      expected_version?: number | null;
    } = {},
  ) =>
    request<GenerationResult>(`/api/v1/units/${unitId}/generate`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listVersions: (unitId: string) =>
    request<{
      unit_id: string;
      current_version: number;
      count: number;
      versions: UnitVersion[];
    }>(`/api/v1/units/${unitId}/versions`),

  getUnitVersion: (unitId: string, version: number) =>
    request<{ unit_id: string; version: UnitVersionDetail }>(
      `/api/v1/units/${unitId}/versions/${version}`,
    ),

  diffUnitVersions: (unitId: string, from: number, to: number) =>
    request<VersionDiffResult>(
      `/api/v1/units/${unitId}/versions/diff?from=${from}&to=${to}`,
    ),

  revertUnit: (
    unitId: string,
    version: number,
    note = "",
    expectedVersion?: number | null,
  ) =>
    request<{
      unit: Unit;
      version: number;
      reverted_from: number;
      note: string;
    }>(`/api/v1/units/${unitId}/revert`, {
      method: "POST",
      body: JSON.stringify({
        version,
        note,
        expected_version: expectedVersion ?? null,
      }),
    }),

  askUnit: (unitId: string, question: string, selection?: string) =>
    request<AskResult>(`/api/v1/units/${unitId}/ask`, {
      method: "POST",
      body: JSON.stringify({
        question,
        selection: selection?.trim() ? selection.trim() : null,
      }),
    }),

  amendUnit: (
    unitId: string,
    instruction: string,
    target?: string,
    mode: GenerationMode = "strict",
    expectedVersion?: number | null,
  ) =>
    request<AmendResult>(`/api/v1/units/${unitId}/amend`, {
      method: "POST",
      body: JSON.stringify({
        instruction,
        target: target ?? null,
        mode,
        expected_version: expectedVersion ?? null,
      }),
    }),

  checkUnitCode: (unitId: string) =>
    request<{
      unit_id: string;
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
    }>(`/api/v1/units/${unitId}/code-check`, { method: "POST", body: JSON.stringify({}) }),

  getThread: (unitId: string) =>
    request<ThreadView>(`/api/v1/units/${unitId}/thread`),

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

  getBlueprint: (seriesId: string) =>
    request<BlueprintEnvelope>(`/api/v1/series/${seriesId}/blueprint`),

  generateBlueprint: (
    seriesId: string,
    payload: {
      mode?: GenerationMode;
      top_k?: number;
      source_ids?: string[];
      focus?: string;
      expected_version?: number | null;
    } = {},
  ) =>
    request<Blueprint>(`/api/v1/series/${seriesId}/blueprint/generate`, {
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
    seriesId: string,
    blueprint: Blueprint,
    expectedVersion?: number | null,
  ) =>
    request<Blueprint>(`/api/v1/series/${seriesId}/blueprint`, {
      method: "PUT",
      body: JSON.stringify({
        blueprint,
        expected_version: expectedVersion ?? null,
      }),
    }),

  getUnitLock: (unitId: string) =>
    request<{ lock: UnitLockInfo | null }>(
      `/api/v1/units/${unitId}/lock`,
    ),

  acquireUnitLock: (unitId: string, force = false) =>
    request<{ acquired: boolean; lock: UnitLockInfo }>(
      `/api/v1/units/${unitId}/lock`,
      { method: "POST", body: JSON.stringify({ force }) },
    ),

  heartbeatUnitLock: (unitId: string, token: string) =>
    request<{ lock: UnitLockInfo }>(
      `/api/v1/units/${unitId}/lock/heartbeat`,
      { method: "POST", body: JSON.stringify({ token }) },
    ),

  releaseUnitLock: (unitId: string, token: string) =>
    request<{ ok: boolean }>(
      `/api/v1/units/${unitId}/lock?token=${encodeURIComponent(token)}`,
      { method: "DELETE" },
    ),

  applyBlueprint: (seriesId: string) =>
    request<ApplyBlueprintResult>(
      `/api/v1/series/${seriesId}/blueprint/apply`,
      { method: "POST" },
    ),

  getGlossary: (seriesId: string) =>
    request<GlossaryPayload>(`/api/v1/series/${seriesId}/glossary`),

  saveGlossary: (seriesId: string, terms: GlossaryTerm[]) =>
    request<GlossaryPayload>(`/api/v1/series/${seriesId}/glossary`, {
      method: "PUT",
      body: JSON.stringify({ terms }),
    }),

  reviewUnit: (
    unitId: string,
    action: "approve" | "request_revision",
    note = "",
  ) =>
    request<ReviewResult>(`/api/v1/units/${unitId}/review`, {
      method: "POST",
      body: JSON.stringify({ action, note }),
    }),

  getProgress: (seriesId: string) =>
    request<SeriesProgress>(`/api/v1/series/${seriesId}/progress`),

  generateAllSeries: (seriesId: string, payload: { regenerate?: boolean } = {}) =>
    request<{
      job_ids?: string[];
      jobIds?: string[];
      jobs?: { id?: string; job_id?: string; unit_id?: string; unitId?: string }[];
      unit_jobs?: Record<string, string | { id?: string }>;
    }>(`/api/v1/series/${seriesId}/generate-all`, {
      method: "POST",
      body: JSON.stringify({ regenerate: payload.regenerate ?? false }),
    }),

  listUnitReviews: (unitId: string) =>
    request<{
      unit_id: string;
      count: number;
      reviews: UnitReview[];
    }>(`/api/v1/units/${unitId}/reviews`),

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

  getSeriesGrants: (seriesId: string) =>
    request<SeriesGrants>(`/api/v1/series/${seriesId}/grants`),

  saveSeriesGrants: (
    seriesId: string,
    grants: { user_id: string; level: "read" | "write" }[],
  ) =>
    request<SeriesGrants>(`/api/v1/series/${seriesId}/grants`, {
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

  listRetrievalProviders: (kind: RetrievalKind) =>
    request<RetrievalProviderList>(`/api/v1/settings/retrieval/providers?kind=${kind}`),

  createRetrievalProvider: (payload: RetrievalProviderPayload) =>
    request<RetrievalProvider>("/api/v1/settings/retrieval/providers", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateRetrievalProvider: (providerId: string, payload: RetrievalProviderPayload) =>
    request<RetrievalProvider>(`/api/v1/settings/retrieval/providers/${providerId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteRetrievalProvider: (providerId: string) =>
    request<{ id: string; deleted: boolean }>(
      `/api/v1/settings/retrieval/providers/${providerId}`,
      { method: "DELETE" },
    ),

  testRetrievalProvider: (providerId: string) =>
    request<RetrievalTestResult>(
      `/api/v1/settings/retrieval/providers/${providerId}/test`,
      { method: "POST" },
    ),

  getRetrievalSettings: () =>
    request<RetrievalSettings>("/api/v1/settings/retrieval/settings"),

  updateRetrievalSettings: (payload: RetrievalSettingsPayload) =>
    request<RetrievalSettings>("/api/v1/settings/retrieval/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  clearRetrievalSettings: (scope: "user" | "tenant") =>
    request<RetrievalSettings>(
      `/api/v1/settings/retrieval/settings?scope=${encodeURIComponent(scope)}`,
      { method: "DELETE" },
    ),

  getEmbeddingStatus: (providerId?: string) =>
    request<EmbeddingStatus>(
      `/api/v1/kb/embeddings/status${providerId ? `?provider_id=${encodeURIComponent(providerId)}` : ""}`,
    ),

  backfillEmbeddings: (providerId?: string) =>
    request<EmbeddingBackfillResult>("/api/v1/kb/embeddings/backfill", {
      method: "POST",
      body: JSON.stringify(providerId ? { provider_id: providerId } : {}),
    }),

  purgeEmbeddings: (providerId?: string) =>
    request<Record<string, unknown>>(
      `/api/v1/kb/embeddings/purge${providerId ? `?provider_id=${encodeURIComponent(providerId)}` : ""}`,
      { method: "POST" },
    ),

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
      create_series?: boolean;
      series_id?: string;
      series_title?: string;
      mode?: GenerationMode;
    },
  ) =>
    request<ResearchBlueprintResult>(`/api/v1/research/${runId}/blueprint`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  createPiece: (payload: {
    title: string;
    brief?: string;
    genre?: PieceGenre | string;
    tone?: string;
    audience?: string;
    pov?: string;
    citation_policy?: CitationPolicy | string;
    target_words?: number;
    mode?: GenerationMode;
    profile_id?: string;
  }) =>
    request<Piece>("/api/v1/pieces", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listPieces: () =>
    request<{ count: number; pieces: Piece[] }>("/api/v1/pieces"),

  getPiece: (pieceId: string) =>
    request<Piece>(`/api/v1/pieces/${pieceId}`),

  generateSection: (
    pieceId: string,
    sectionId: string,
    payload?: { mode?: GenerationMode; top_k?: number },
  ) =>
    request<{ section_id: string; content: string; piece: Piece }>(
      `/api/v1/pieces/${pieceId}/sections/${sectionId}/generate`,
      { method: "POST", body: JSON.stringify(payload ?? {}) },
    ),

  generatePiece: (
    pieceId: string,
    payload?: { mode?: GenerationMode; top_k?: number; expected_version?: number },
  ) =>
    request<Piece>(`/api/v1/pieces/${pieceId}/generate`, {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    }),

  rewritePiece: (
    pieceId: string,
    payload: {
      instruction: string;
      mode?: GenerationMode;
      expected_version?: number;
    },
  ) =>
    request<Piece>(`/api/v1/pieces/${pieceId}/rewrite`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listPieceVersions: (pieceId: string) =>
    request<{ count: number; versions: PieceVersion[] }>(
      `/api/v1/pieces/${pieceId}/versions`,
    ),

  getPieceVersion: (pieceId: string, version: number) =>
    request<{ piece_id: string; version: PieceVersionDetail }>(
      `/api/v1/pieces/${pieceId}/versions/${version}`,
    ),

  diffPieceVersions: (pieceId: string, from: number, to: number) =>
    request<VersionDiffResult>(
      `/api/v1/pieces/${pieceId}/versions/diff?from=${from}&to=${to}`,
    ),

  revertPiece: (pieceId: string, version: number) =>
    request<Piece>(`/api/v1/pieces/${pieceId}/revert`, {
      method: "POST",
      body: JSON.stringify({ version }),
    }),

  deletePiece: (pieceId: string) =>
    request<{ ok?: boolean }>(`/api/v1/pieces/${pieceId}`, {
      method: "DELETE",
    }),

  storageInfo: () => request<StorageInfo>("/api/v1/storage/info"),

  getPieceGrants: (pieceId: string) =>
    request<PieceGrants>(`/api/v1/pieces/${pieceId}/grants`),

  savePieceGrants: (
    pieceId: string,
    grants: { user_id: string; level: string }[],
  ) =>
    request<PieceGrants>(`/api/v1/pieces/${pieceId}/grants`, {
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

  updateSeries: (
    seriesId: string,
    payload: {
      title?: string;
      subtitle?: string;
      brief?: string;
      audience?: string;
      difficulty?: string;
      language?: string;
      profile_id?: string;
    },
  ) =>
    request<Series>(`/api/v1/series/${seriesId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteSeries: (seriesId: string) =>
    request<{ series_id: string; deleted: Record<string, number> }>(
      `/api/v1/series/${seriesId}`,
      { method: "DELETE" },
    ),

  updateUnit: (
    unitId: string,
    payload: {
      title?: string;
      learning_objectives?: string[];
      prerequisites?: string[];
      order_index?: number;
      status?: string;
      content?: string;
    },
  ) =>
    request<Unit>(`/api/v1/units/${unitId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteUnit: (unitId: string) =>
    request<{ unit_id: string; deleted_versions: number; deleted_threads: number }>(
      `/api/v1/units/${unitId}`,
      { method: "DELETE" },
    ),

  reorderUnits: (seriesId: string, unitIds: string[]) =>
    request<SeriesDetail>(`/api/v1/series/${seriesId}/units/reorder`, {
      method: "POST",
      body: JSON.stringify({ unit_ids: unitIds }),
    }),

  updatePiece: (
    pieceId: string,
    payload: {
      title?: string;
      brief?: string;
      profile?: Record<string, unknown>;
      target_words?: number;
    },
  ) =>
    request<Piece>(`/api/v1/pieces/${pieceId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  savePieceContent: (
    pieceId: string,
    payload: { content: string; note?: string; expected_version?: number | null },
  ) =>
    request<Piece>(`/api/v1/pieces/${pieceId}/content`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  createPieceSection: (
    pieceId: string,
    payload: {
      title: string;
      summary?: string;
      target_words?: number;
      after_id?: string | null;
    },
  ) =>
    request<{ section: PieceSection; piece: Piece }>(
      `/api/v1/pieces/${pieceId}/sections`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  updatePieceSection: (
    pieceId: string,
    sectionId: string,
    payload: {
      title?: string;
      summary?: string;
      target_words?: number;
      content?: string;
    },
  ) =>
    request<Piece>(`/api/v1/pieces/${pieceId}/sections/${sectionId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deletePieceSection: (pieceId: string, sectionId: string) =>
    request<Piece>(`/api/v1/pieces/${pieceId}/sections/${sectionId}`, {
      method: "DELETE",
    }),

  reorderPieceSections: (pieceId: string, sectionIds: string[]) =>
    request<Piece>(`/api/v1/pieces/${pieceId}/sections/reorder`, {
      method: "POST",
      body: JSON.stringify({ section_ids: sectionIds }),
    }),

  listWorkProfiles: () =>
    request<{ count: number; profiles: WorkProfile[] }>("/api/v1/profiles"),

  getWorkProfile: (profileId: string) =>
    request<WorkProfile>(`/api/v1/profiles/${profileId}`),

  createWorkProfile: (payload: {
    name: string;
    description?: string;
    spec?: ProfileSpec;
    is_shared?: boolean;
    scope?: ProfileScope | string;
  }) =>
    request<WorkProfile>("/api/v1/profiles", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateWorkProfile: (
    profileId: string,
    payload: {
      name?: string;
      description?: string;
      spec?: ProfileSpec;
      is_shared?: boolean;
    },
  ) =>
    request<WorkProfile>(`/api/v1/profiles/${profileId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteWorkProfile: (profileId: string) =>
    request<{ ok?: boolean; profile_id?: string }>(`/api/v1/profiles/${profileId}`, {
      method: "DELETE",
    }),

  duplicateWorkProfile: (profileId: string, payload?: { name?: string }) =>
    request<WorkProfile>(`/api/v1/profiles/${profileId}/duplicate`, {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    }),

  importWorkProfile: (
    data: Record<string, unknown>,
    payload?: { name?: string; scope?: ProfileScope | string },
  ) =>
    request<WorkProfile>("/api/v1/profiles/import", {
      method: "POST",
      body: JSON.stringify({ data, ...(payload ?? {}) }),
    }),

  exportWorkProfile: (profileId: string) => exportProfileFile(profileId),

  sampleWorkProfile: (profileId: string, payload: { topic?: string; chars?: number }) =>
    request<ProfileSample>(`/api/v1/profiles/${profileId}/sample`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  validateWorkProfile: (spec: ProfileSpec) =>
    request<ProfileValidation>("/api/v1/profiles/validate", {
      method: "POST",
      body: JSON.stringify({ spec }),
    }),

  previewWorkProfile: (
    profileId: string,
    payload?: { sample?: Record<string, unknown> },
  ) =>
    request<ProfilePreview>(`/api/v1/profiles/${profileId}/preview`, {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    }),

  getProfileShares: (profileId: string) =>
    request<{ profile_id: string; count: number; shares: ProfileShare[] }>(
      `/api/v1/profiles/${profileId}/shares`,
    ),

  saveProfileShares: (profileId: string, shares: ProfileShareInput[]) =>
    request<{ profile_id: string; count: number; shares: ProfileShare[] }>(
      `/api/v1/profiles/${profileId}/shares`,
      {
        method: "PUT",
        body: JSON.stringify({ shares }),
      },
    ),

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

  createShareLink: (payload: {
    resource_type: ShareResourceType;
    resource_id: string;
    expires_in_days?: number;
  }) =>
    request<ShareLink>("/api/v1/share-links", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listShareLinks: (
    params: { resource_type?: ShareResourceType | ""; resource_id?: string } = {},
  ) => {
    const search = new URLSearchParams();
    if (params.resource_type) search.set("resource_type", params.resource_type);
    if (params.resource_id) search.set("resource_id", params.resource_id);
    const query = search.toString();
    return request<{ count: number; links: ShareLink[] }>(
      `/api/v1/share-links${query ? `?${query}` : ""}`,
    );
  },

  deleteShareLink: (linkId: string) =>
    request<{ ok: boolean }>(`/api/v1/share-links/${encodeURIComponent(linkId)}`, {
      method: "DELETE",
    }),

  getPublicShare: (token: string) =>
    request<PublicShare>(
      `/api/v1/public/shares/${encodeURIComponent(token)}`,
      {},
      { anonymous: true },
    ),
};
