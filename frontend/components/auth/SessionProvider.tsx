"use client";

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
  type MeResponse,
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
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getMe();
      setMe(data);
      const current = tenantId(data.tenant);
      if (current && current !== getTenantId()) {
        persistTenant(current, false);
      }
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => subscribeSession(() => void refresh()), [refresh]);

  const switchTenant = useCallback(
    (tenant: string) => {
      if (!tenant || tenant === getTenantId()) return;
      persistTenant(tenant);
      window.dispatchEvent(new Event("course-studio:refresh"));
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      setMe(null);
    }
    clearSession();
    setMe(null);
    window.dispatchEvent(new Event("course-studio:refresh"));
  }, []);

  const value = useMemo<SessionValue>(() => {
    const role = me?.role ?? null;
    return {
      me,
      loading,
      role,
      tenant: tenantId(me?.tenant),
      tenantName: tenantName(me?.tenant),
      tenants: (me?.tenants ?? []).map((item) => ({
        id: tenantId(item.tenant),
        name: tenantName(item.tenant),
        role: item.role,
      })),
      authMode: me?.auth_mode ?? "disabled",
      can: (action: RoleAction) => (role ? roleCan(role, action) : true),
      switchTenant,
      refresh,
      logout,
    };
  }, [me, loading, switchTenant, refresh, logout]);

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
