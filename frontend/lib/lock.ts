import { API_BASE, ApiError, api, type LessonLockInfo } from "@/lib/api";
import { getTenantId, getToken } from "@/lib/session";

export type { LessonLockInfo };

export type LessonLockState =
  | { status: "idle" }
  | { status: "acquiring" }
  | { status: "held"; lock: LessonLockInfo }
  | { status: "blocked"; name: string; lock: LessonLockInfo | null }
  | { status: "lost" };

export const LOCK_HEARTBEAT_MS = 45_000;

export async function acquireLessonLock(
  lessonId: string,
  force = false,
): Promise<LessonLockInfo> {
  const result = await api.acquireLessonLock(lessonId, force);
  return result.lock;
}

export async function heartbeat(
  lessonId: string,
  token: string,
): Promise<LessonLockInfo> {
  const result = await api.heartbeatLessonLock(lessonId, token);
  return result.lock;
}

export async function releaseLessonLock(
  lessonId: string,
  token: string,
): Promise<void> {
  await api.releaseLessonLock(lessonId, token);
}

export function releaseLessonLockBeacon(lessonId: string, token: string): void {
  if (!lessonId || !token) return;
  const headers: Record<string, string> = {};
  const auth = getToken();
  const tenant = getTenantId();
  if (auth) headers["Authorization"] = `Bearer ${auth}`;
  if (tenant) headers["X-Tenant-Id"] = tenant;
  try {
    void fetch(
      `${API_BASE}/api/v1/lessons/${lessonId}/lock?token=${encodeURIComponent(token)}`,
      { method: "DELETE", headers, keepalive: true },
    );
  } catch {
    return;
  }
}

export function lockHolderOf(error: unknown): {
  name: string;
  lock: LessonLockInfo | null;
} {
  if (!(error instanceof ApiError)) {
    return { name: "", lock: null };
  }
  const payload = error.payload;
  const raw = payload?.lock as LessonLockInfo | null | undefined;
  const lock = raw && typeof raw === "object" ? raw : null;
  const name =
    (lock?.user_name ?? "").trim() ||
    error.message.replace(/^该讲正被\s*/, "").replace(/\s*编辑.*$/, "").trim() ||
    "其他成员";
  return { name, lock };
}

export function isLockConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

export function formatLockRemaining(expiresAt: number, now = Date.now()): string {
  const seconds = Math.max(0, Math.round(expiresAt - now / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

export type LessonLockController = {
  start: () => Promise<void>;
  stop: (release?: boolean) => void;
  force: () => Promise<void>;
  retry: () => Promise<void>;
  token: () => string | null;
};

export function createLessonLockController(options: {
  lessonId: string;
  intervalMs?: number;
  onState: (state: LessonLockState) => void;
  onError?: (message: string) => void;
}): LessonLockController {
  const { lessonId, onState, onError } = options;
  const intervalMs = options.intervalMs ?? LOCK_HEARTBEAT_MS;
  let token: string | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let stopped = false;

  const clearTimer = () => {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };

  const schedule = () => {
    clearTimer();
    timer = setInterval(() => {
      const current = token;
      if (!current || stopped) return;
      void heartbeat(lessonId, current)
        .then((lock) => {
          token = lock.token;
          onState({ status: "held", lock });
        })
        .catch((error: unknown) => {
          token = null;
          clearTimer();
          if (isLockConflict(error)) {
            const holder = lockHolderOf(error);
            onState({ status: "blocked", name: holder.name, lock: holder.lock });
          } else {
            onState({ status: "lost" });
          }
        });
    }, intervalMs);
  };

  const acquire = async (force = false) => {
    stopped = false;
    onState({ status: "acquiring" });
    try {
      const lock = await acquireLessonLock(lessonId, force);
      token = lock.token;
      onState({ status: "held", lock });
      schedule();
    } catch (error) {
      token = null;
      clearTimer();
      if (isLockConflict(error)) {
        const holder = lockHolderOf(error);
        onState({ status: "blocked", name: holder.name, lock: holder.lock });
        return;
      }
      if (error instanceof ApiError && error.status === 403) {
        onState({ status: "lost" });
        onError?.(error.message);
        return;
      }
      onState({ status: "idle" });
      const message =
        error instanceof Error ? error.message : "编辑锁获取失败";
      onError?.(message);
    }
  };

  return {
    start: () => acquire(false),
    stop: (release = true) => {
      stopped = true;
      clearTimer();
      const current = token;
      token = null;
      if (release && current) releaseLessonLockBeacon(lessonId, current);
      onState({ status: "idle" });
    },
    force: () => acquire(true),
    retry: () => acquire(false),
    token: () => token,
  };
}
