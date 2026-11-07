import { API_BASE, ApiError, api, type UnitLockInfo } from "@/lib/api";
import { getTenantId, getToken } from "@/lib/session";
import { request } from "@/lib/api";

export type EditLockKind = "unit" | "piece";

export const LOCK_HEARTBEAT_MS = 45_000;

export type LockHolder = {
  kind: EditLockKind;
  id: string;
  token: string;
  userId: string;
  userName: string;
  expiresAt: number;
  supported: boolean;
};

export type EditLockState =
  | { status: "idle" }
  | { status: "acquiring" }
  | { status: "held"; holder: LockHolder }
  | { status: "blocked"; name: string; expiresAt: number | null }
  | { status: "lost" }
  | { status: "unsupported" };

type AcquireOutcome =
  | { kind: "held"; holder: LockHolder }
  | { kind: "blocked"; name: string; expiresAt: number | null }
  | { kind: "unsupported" };

function seconds(value: unknown): number {
  const raw = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(raw) || raw <= 0) return 0;
  // Accept both seconds and milliseconds; the backend currently uses seconds.
  return raw > 1_000_000_000_000 ? raw / 1000 : raw;
}

function nameOf(raw: unknown): string {
  if (typeof raw === "string") return raw.trim();
  if (!raw || typeof raw !== "object") return "";
  const record = raw as Record<string, unknown>;
  for (const key of ["user_name", "display_name", "name", "email", "user_id", "id"]) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function normalizeLegacyUnit(lock: UnitLockInfo, id: string): LockHolder {
  return {
    kind: "unit",
    id,
    token: lock.token ?? "",
    userId: lock.user_id ?? "",
    userName: lock.user_name ?? "",
    expiresAt: seconds(lock.expires_at),
    supported: true,
  };
}

function normalizeGeneric(
  payload: Record<string, unknown> | null | undefined,
  kind: EditLockKind,
  id: string,
): LockHolder {
  const envelope =
    payload?.lock && typeof payload.lock === "object"
      ? (payload.lock as Record<string, unknown>)
      : payload ?? {};
  const holderRaw = envelope.holder ?? payload?.holder;
  const holderRecord =
    holderRaw && typeof holderRaw === "object"
      ? (holderRaw as Record<string, unknown>)
      : null;
  const token =
    (typeof envelope.token === "string" && envelope.token) ||
    (typeof payload?.token === "string" && payload.token) ||
    (typeof holderRecord?.token === "string" && holderRecord.token) ||
    "";
  return {
    kind,
    id,
    token,
    userId:
      (typeof envelope.user_id === "string" && envelope.user_id) ||
      (typeof holderRecord?.id === "string" && holderRecord.id) ||
      (typeof holderRecord?.user_id === "string" && holderRecord.user_id) ||
      "",
    userName:
      nameOf(holderRaw) ||
      (typeof envelope.user_name === "string" ? envelope.user_name : "") ||
      "",
    expiresAt:
      seconds(envelope.expires_at ?? envelope.expiresAt ?? payload?.expires_at) || 0,
    supported: true,
  };
}

function conflictFromError(error: ApiError, kind: EditLockKind, id: string): AcquireOutcome {
  const payload = error.payload ?? {};
  const rawLock =
    payload.lock && typeof payload.lock === "object"
      ? (payload.lock as Record<string, unknown>)
      : payload;
  const holderRaw = rawLock.holder ?? payload.holder;
  const holder = normalizeGeneric(payload, kind, id);
  return {
    kind: "blocked",
    name: nameOf(holderRaw) || holder.userName || error.message || "another member",
    expiresAt:
      seconds(rawLock.expires_at ?? payload.expires_at) || holder.expiresAt || null,
  };
}

function isMissingEndpoint(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.status === 404 || error.status === 405 || error.status === 501)
  );
}

async function acquireGeneric(
  kind: EditLockKind,
  id: string,
  force = false,
): Promise<LockHolder> {
  const payload = await request<Record<string, unknown>>(
    `/api/v1/locks/${kind}/${encodeURIComponent(id)}`,
    { method: "POST", body: JSON.stringify({ force }) },
  );
  return normalizeGeneric(payload, kind, id);
}

async function acquireLegacy(
  kind: EditLockKind,
  id: string,
  force = false,
): Promise<LockHolder> {
  if (kind === "unit") {
    const result = await api.acquireUnitLock(id, force);
    return normalizeLegacyUnit(result.lock, id);
  }
  const result = await request<Record<string, unknown>>(
    `/api/v1/pieces/${encodeURIComponent(id)}/lock`,
    { method: "POST", body: JSON.stringify({ force }) },
  );
  return normalizeGeneric(result, kind, id);
}

export async function acquireEditLock(
  kind: EditLockKind,
  id: string,
  force = false,
): Promise<AcquireOutcome> {
  try {
    const holder = await acquireGeneric(kind, id, force);
    return { kind: "held", holder };
  } catch (error) {
    if (!isMissingEndpoint(error)) {
      if (error instanceof ApiError && error.status === 409) {
        return conflictFromError(error, kind, id);
      }
      throw error;
    }
    try {
      const holder = await acquireLegacy(kind, id, force);
      return { kind: "held", holder };
    } catch (legacyError) {
      if (isMissingEndpoint(legacyError)) return { kind: "unsupported" };
      if (legacyError instanceof ApiError && legacyError.status === 409) {
        return conflictFromError(legacyError, kind, id);
      }
      throw legacyError;
    }
  }
}

export async function renewEditLock(
  kind: EditLockKind,
  id: string,
  token: string,
): Promise<LockHolder> {
  try {
    const payload = await request<Record<string, unknown>>(
      `/api/v1/locks/${kind}/${encodeURIComponent(id)}/renew`,
      { method: "POST", body: JSON.stringify({ token }) },
    );
    return normalizeGeneric(payload, kind, id);
  } catch (error) {
    if (!isMissingEndpoint(error)) throw error;
  }
  if (kind === "unit") {
    const result = await api.heartbeatUnitLock(id, token);
    return normalizeLegacyUnit(result.lock, id);
  }
  const payload = await request<Record<string, unknown>>(
    `/api/v1/pieces/${encodeURIComponent(id)}/lock/heartbeat`,
    { method: "POST", body: JSON.stringify({ token }) },
  );
  return normalizeGeneric(payload, kind, id);
}

export async function releaseEditLock(
  kind: EditLockKind,
  id: string,
  token: string,
): Promise<void> {
  if (!token && kind === "unit") return;
  try {
    await request<{ ok?: boolean }>(
      `/api/v1/locks/${kind}/${encodeURIComponent(id)}?token=${encodeURIComponent(token)}`,
      { method: "DELETE" },
    );
    return;
  } catch (error) {
    if (!isMissingEndpoint(error)) throw error;
  }
  if (kind === "unit") {
    await api.releaseUnitLock(id, token);
    return;
  }
  await request<{ ok?: boolean }>(
    `/api/v1/pieces/${encodeURIComponent(id)}/lock?token=${encodeURIComponent(token)}`,
    { method: "DELETE" },
  );
}

export function releaseEditLockBeacon(
  kind: EditLockKind,
  id: string,
  token: string,
): void {
  if (!id) return;
  const headers: Record<string, string> = {};
  const auth = getToken();
  const tenant = getTenantId();
  if (auth) headers["Authorization"] = `Bearer ${auth}`;
  if (tenant) headers["X-Tenant-Id"] = tenant;
  const legacyPath =
    kind === "unit"
      ? `/api/v1/units/${encodeURIComponent(id)}/lock`
      : `/api/v1/pieces/${encodeURIComponent(id)}/lock`;
  const query = `?token=${encodeURIComponent(token)}`;
  for (const path of [`/api/v1/locks/${kind}/${encodeURIComponent(id)}`, legacyPath]) {
    try {
      void fetch(`${API_BASE}${path}${query}`, {
        method: "DELETE",
        headers,
        keepalive: true,
      });
    } catch {
      // Best effort only; the lock also expires on its own TTL.
    }
  }
}

export function formatLockRemaining(expiresAt: number | null, now = Date.now()): string {
  if (!expiresAt) return "";
  const total = Math.max(0, Math.round(expiresAt - now / 1000));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

/** Read-only lock snapshot included by unit/piece read responses. */
export function lockStateFromRead(
  payload:
    | {
        lock?: unknown;
        lock_state?: string;
        state?: string;
        locked_by_me?: boolean;
      }
    | null
    | undefined,
  kind: EditLockKind,
  id: string,
  currentUserId = "",
): EditLockState | null {
  if (!payload) return null;
  const state = String(payload.lock_state ?? payload.state ?? "").toLowerCase();
  const rawLock =
    payload.lock && typeof payload.lock === "object"
      ? (payload.lock as Record<string, unknown>)
      : null;
  if (!rawLock || state === "free") return { status: "idle" };
  const holder = normalizeGeneric({ lock: rawLock }, kind, id);
  if (payload.locked_by_me || (currentUserId && holder.userId === currentUserId)) {
    // A lock owned by this user in another tab is not this tab's edit session.
    return { status: "idle" };
  }
  return {
    status: "blocked",
    name: holder.userName || "another member",
    expiresAt: holder.expiresAt || null,
  };
}

export function isLockConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

export type EditLockController = {
  start: () => Promise<EditLockState>;
  force: () => Promise<EditLockState>;
  retry: () => Promise<EditLockState>;
  stop: (release?: boolean) => void;
  release: () => Promise<void>;
  token: () => string | null;
};

export function createEditLockController(options: {
  kind: EditLockKind;
  id: string;
  intervalMs?: number;
  onState: (state: EditLockState) => void;
  onError?: (message: string) => void;
}): EditLockController {
  const { kind, id, onState, onError } = options;
  const intervalMs = options.intervalMs ?? LOCK_HEARTBEAT_MS;
  let holder: LockHolder | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let stopped = false;
  let heartbeatInFlight = false;

  const clearTimer = () => {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };

  const publish = (state: EditLockState): EditLockState => {
    onState(state);
    return state;
  };

  const schedule = () => {
    clearTimer();
    timer = setInterval(() => {
      const current = holder;
      if (!current || stopped || heartbeatInFlight) return;
      heartbeatInFlight = true;
      void renewEditLock(kind, id, current.token)
        .then((next) => {
          if (stopped) return;
          holder = { ...next, supported: true };
          publish({ status: "held", holder });
        })
        .catch((error: unknown) => {
          if (stopped) return;
          holder = null;
          clearTimer();
          if (isMissingEndpoint(error)) {
            publish({ status: "unsupported" });
            return;
          }
          if (isLockConflict(error)) {
            const payload = error instanceof ApiError ? error.payload ?? {} : {};
            const lockRaw =
              payload.lock && typeof payload.lock === "object"
                ? (payload.lock as Record<string, unknown>)
                : null;
            const holderRaw = payload.holder ?? lockRaw?.holder;
            const rawExpiry = lockRaw?.expires_at ?? payload.expires_at;
            if (holderRaw || rawExpiry) {
              const name = nameOf(holderRaw) || "another member";
              publish({
                status: "blocked",
                name,
                expiresAt: seconds(rawExpiry) || null,
              });
            } else {
              publish({ status: "lost" });
            }
            return;
          }
          publish({ status: "lost" });
        })
        .finally(() => {
          heartbeatInFlight = false;
        });
    }, intervalMs);
  };

  const acquire = async (force = false): Promise<EditLockState> => {
    stopped = false;
    clearTimer();
    publish({ status: "acquiring" });
    try {
      const outcome = await acquireEditLock(kind, id, force);
      if (outcome.kind === "unsupported") {
        holder = null;
        return publish({ status: "unsupported" });
      }
      if (outcome.kind === "blocked") {
        holder = null;
        return publish({
          status: "blocked",
          name: outcome.name,
          expiresAt: outcome.expiresAt,
        });
      }
      holder = outcome.holder;
      const state = publish({ status: "held", holder });
      schedule();
      return state;
    } catch (error) {
      holder = null;
      clearTimer();
      publish({ status: "idle" });
      const message =
        error instanceof Error ? error.message : "Failed to acquire the edit lock";
      onError?.(message);
      return { status: "idle" };
    }
  };

  return {
    start: () => acquire(false),
    force: () => acquire(true),
    retry: () => acquire(false),
    stop: (release = true) => {
      stopped = true;
      clearTimer();
      const current = holder;
      holder = null;
      if (release && current) releaseEditLockBeacon(kind, id, current.token);
      publish({ status: "idle" });
    },
    release: async () => {
      stopped = true;
      clearTimer();
      const current = holder;
      holder = null;
      try {
        if (current) await releaseEditLock(kind, id, current.token);
      } catch {
        if (current) releaseEditLockBeacon(kind, id, current.token);
      } finally {
        publish({ status: "idle" });
      }
    },
    token: () => holder?.token ?? null,
  };
}
