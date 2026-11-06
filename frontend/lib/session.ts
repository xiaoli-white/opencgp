export type Role = "owner" | "admin" | "editor" | "viewer";

export type RoleAction =
  | "read"
  | "write"
  | "review"
  | "manage_members"
  | "manage_quota"
  | "manage_server";

export const SESSION_EVENT = "series-studio:session";
export const AUTH_REQUIRED_EVENT = "series-studio:auth-required";

const TOKEN_KEY = "cs_token";
const TENANT_KEY = "cs_tenant";

const RANK: Record<Role, number> = {
  owner: 4,
  admin: 3,
  editor: 2,
  viewer: 1,
};

const NEEDED: Record<RoleAction, number> = {
  read: 1,
  write: 2,
  review: 2,
  manage_members: 3,
  manage_quota: 3,
  manage_server: 4,
};

export const ROLE_LABEL: Record<Role, string> = {
  owner: "所有者",
  admin: "管理员",
  editor: "编辑",
  viewer: "只读",
};

export function isRole(value: unknown): value is Role {
  return (
    value === "owner" ||
    value === "admin" ||
    value === "editor" ||
    value === "viewer"
  );
}

export function roleCan(role: string | null | undefined, action: RoleAction): boolean {
  if (!isRole(role)) return false;
  return RANK[role] >= NEEDED[action];
}

function read(key: string): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function write(key: string, value: string) {
  if (typeof window === "undefined") return;
  try {
    if (value) window.localStorage.setItem(key, value);
    else window.localStorage.removeItem(key);
  } catch {
    return;
  }
}

export function notifySession() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(SESSION_EVENT));
}

export function getToken(): string {
  return read(TOKEN_KEY);
}

export function setToken(token: string) {
  write(TOKEN_KEY, token);
  notifySession();
}

export function getTenantId(): string {
  return read(TENANT_KEY);
}

export function setTenantId(tenantId: string, notify = true) {
  write(TENANT_KEY, tenantId);
  if (notify) notifySession();
}

export function clearSession() {
  write(TOKEN_KEY, "");
  write(TENANT_KEY, "");
  notifySession();
}

export function subscribeSession(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = () => callback();
  window.addEventListener(SESSION_EVENT, handler);
  return () => window.removeEventListener(SESSION_EVENT, handler);
}
