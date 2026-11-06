import { API_BASE, request } from "@/lib/api";
import { getTenantId, getToken } from "@/lib/session";

export type JobKind =
  | "research"
  | "piece_create"
  | "piece_generate"
  | "piece_rewrite"
  | "unit_generate"
  | "blueprint_generate";

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";

export type Job = {
  id: string;
  kind: JobKind | string;
  status: JobStatus | string;
  progress: number;
  error: string;
  result: Record<string, unknown> | null;
  payload: Record<string, unknown>;
  created_at: number;
  started_at: number;
  finished_at: number;
  attempts?: number;
  cancel_requested?: boolean;
};

export type JobEvent = {
  id: string;
  kind: string;
  status: JobStatus | string;
  progress: number;
  error: string;
  result: Record<string, unknown> | null;
};

export type JobList = {
  count: number;
  jobs: Job[];
};

export function isTerminal(status: string | undefined | null): boolean {
  return status === "succeeded" || status === "failed" || status === "canceled";
}

export function submitJob(kind: JobKind | string, payload: Record<string, unknown> = {}) {
  return request<Job>("/api/v1/jobs", {
    method: "POST",
    body: JSON.stringify({ kind, payload }),
  });
}

export function getJob(jobId: string) {
  return request<Job>(`/api/v1/jobs/${jobId}`);
}

export function listJobs(params?: {
  status?: string;
  kind?: string;
  limit?: number;
}): Promise<JobList> {
  const search = new URLSearchParams();
  if (params?.status) search.set("status", params.status);
  if (params?.kind) search.set("kind", params.kind);
  search.set("limit", String(params?.limit ?? 20));
  return request<JobList>(`/api/v1/jobs?${search.toString()}`);
}

export function cancelJob(jobId: string) {
  return request<Job>(`/api/v1/jobs/${jobId}/cancel`, { method: "POST" });
}

function parseFrame(frame: string): JobEvent | null {
  const lines = frame.split("\n");
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  const raw = dataLines.join("");
  if (!raw || raw === "[DONE]") return null;
  try {
    const parsed = JSON.parse(raw) as JobEvent;
    if (!parsed || typeof parsed !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

function delay(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error("aborted"));
      return;
    }
    const timer = window.setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(new Error("aborted"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

function jobToEvent(job: Job): JobEvent {
  return {
    id: job.id,
    kind: job.kind,
    status: job.status,
    progress: job.progress,
    error: job.error,
    result: job.result,
  };
}

async function pollJob(
  jobId: string,
  handlers: {
    onEvent?: (event: JobEvent) => void;
    signal?: AbortSignal;
  },
): Promise<Job> {
  for (;;) {
    const job = await getJob(jobId);
    handlers.onEvent?.(jobToEvent(job));
    if (isTerminal(job.status)) return job;
    await delay(1500, handlers.signal);
  }
}

export async function streamJob(
  jobId: string,
  handlers: {
    onEvent?: (event: JobEvent) => void;
    onError?: (error: Error) => void;
    signal?: AbortSignal;
  } = {},
): Promise<Job> {
  const headers: Record<string, string> = { Accept: "text/event-stream" };
  const token = getToken();
  const tenant = getTenantId();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (tenant) headers["X-Tenant-Id"] = tenant;

  let latest: Job | null = null;

  try {
    const response = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/events`, {
      method: "GET",
      headers,
      cache: "no-store",
      signal: handlers.signal,
    });
    if (!response.ok || !response.body) throw new Error(`sse ${response.status}`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const event = parseFrame(frame);
        if (!event) continue;
        handlers.onEvent?.(event);
        if (isTerminal(event.status)) {
          latest = await getJob(jobId).catch(() => null) ?? null;
          try {
            await reader.cancel();
          } catch {
            latest = null;
          }
          const job = latest ?? {
            id: event.id,
            kind: event.kind,
            status: event.status,
            progress: event.progress,
            error: event.error,
            result: event.result,
            payload: {},
            created_at: 0,
            started_at: 0,
            finished_at: 0,
          };
          return job;
        }
      }
    }
  } catch (err) {
    if (handlers.signal?.aborted) throw err instanceof Error ? err : new Error("aborted");
    handlers.onError?.(err instanceof Error ? err : new Error("进度流中断"));
  }

  return pollJob(jobId, handlers);
}

export async function runJob(
  kind: JobKind | string,
  payload: Record<string, unknown> = {},
  options: {
    onProgress?: (progress: number) => void;
    onEvent?: (event: JobEvent) => void;
    onJob?: (job: Job) => void;
    signal?: AbortSignal;
  } = {},
): Promise<Job> {
  const created = await submitJob(kind, payload);
  options.onJob?.(created);
  options.onProgress?.(created.progress ?? 0);

  const handleEvent = (event: JobEvent) => {
    options.onEvent?.(event);
    if (typeof event.progress === "number") options.onProgress?.(event.progress);
  };

  const finalJob = await streamJob(created.id, {
    onEvent: handleEvent,
    signal: options.signal,
  });

  if (finalJob.status === "failed") {
    throw new Error(finalJob.error || "任务执行失败");
  }
  if (finalJob.status === "canceled") {
    throw new Error(finalJob.error || "任务已取消");
  }
  return finalJob;
}

export function jobResultString(job: Job, key: string): string {
  const value = job.result?.[key] ?? job.payload?.[key];
  return typeof value === "string" ? value : "";
}

export function jobResultNumber(job: Job, key: string): number {
  const value = job.result?.[key];
  return typeof value === "number" ? value : 0;
}
