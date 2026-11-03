import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  api,
  tenantId,
  tenantName,
  type AuthMode,
  type Capabilities,
  type MeResponse,
  type RoleScope,
} from "@/lib/api";
import {
  clearSession,
  getTenantId,
  roleCan,
  setTenantId as persistTenant,
  subscribeSession,
  type Role,
  type RoleAction,
} from "@/lib/session";

export type TenantOption = {
  id: string;
  name: string;
  role: Role;
};

type SessionValue = {
  me: MeResponse | null;
  loading: boolean;
  role: Role | null;
  roleKey: string;
  roleName: string;
  actions: RoleAction[];
  scope: RoleScope;
  visibleCourseIds: string[] | "all";
  tenant: string;
  tenantName: string;
  tenants: TenantOption[];
  authMode: AuthMode;
  can: (action: RoleAction) => boolean;
  switchTenant: (tenant: string) => void;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getMe();
      setMe(data);
      const current = tenantId(data.tenant);
      if (current && current !== getTenantId()) {
        persistTenant(current, false);
      }
      try {
        setCaps(await api.getCapabilities());
      } catch {
        setCaps(null);
      }
    } catch {
      setMe(null);
      setCaps(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => subscribeSession(() => void refresh()), [refresh]);

  const switchTenant = useCallback((tenant: string) => {
    if (!tenant || tenant === getTenantId()) return;
    persistTenant(tenant);
    window.dispatchEvent(new Event("course-studio:refresh"));
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      setMe(null);
    }
    clearSession();
    setMe(null);
    setCaps(null);
    window.dispatchEvent(new Event("course-studio:refresh"));
  }, []);

  const value = useMemo<SessionValue>(() => {
    const role = me?.role ?? null;
    const actions: RoleAction[] =
      caps?.role?.actions ?? me?.actions ?? [];
    const roleName =
      caps?.role?.name || me?.role_name || (role === "owner" ? "所有者" : "");
    return {
      me,
      loading,
      role,
      roleKey: caps?.role?.key || me?.role_key || role || "",
      roleName,
      actions,
      scope: caps?.role?.scope ?? me?.scope ?? "all",
      visibleCourseIds: caps?.visible_course_ids ?? "all",
      tenant: tenantId(me?.tenant),
      tenantName: tenantName(me?.tenant),
      tenants: (me?.tenants ?? []).map((item) => ({
        id: tenantId(item.tenant),
        name: tenantName(item.tenant),
        role: item.role,
      })),
      authMode: me?.auth_mode ?? "disabled",
      can: (action: RoleAction) => {
        if (actions.length > 0) return actions.includes(action);
        return role ? roleCan(role, action) : true;
      },
      switchTenant,
      refresh,
      logout,
    };
  }, [me, caps, loading, switchTenant, refresh, logout]);

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (ctx) return ctx;
  return {
    me: null,
    loading: false,
    role: null,
    roleKey: "",
    roleName: "",
    actions: [],
    scope: "all",
    visibleCourseIds: "all",
    tenant: "",
    tenantName: "",
    tenants: [],
    authMode: "disabled",
    can: () => true,
    switchTenant: () => {},
    refresh: async () => {},
    logout: async () => {},
  };
}
