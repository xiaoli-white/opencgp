import { Link } from "react-router-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  BookOpen,
  BrainCircuit,
  IdCard,
  Image as ImageIcon,
  LayoutGrid,
  Library,
  ListChecks,
  LogOut,
  Menu,
  PenLine,
  Server,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import clsx from "clsx";
import { useCallback, useEffect, useState } from "react";
import { API_BASE, api, type Series } from "@/lib/api";
import { difficultyLabel } from "@/lib/format";
import { ROLE_LABEL, type Role } from "@/lib/session";
import ThemeToggle from "@/components/ThemeToggle";
import LocaleToggle from "@/components/i18n/LocaleToggle";
import { useSession } from "@/components/auth/SessionProvider";
import { useI18n } from "@/i18n/I18nProvider";

type NavItem = {
  href: string;
  labelKey: string;
  icon: typeof LayoutGrid;
  exact: boolean;
  requireServer?: boolean;
  requireWrite?: boolean;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/", labelKey: "nav.workspace", icon: LayoutGrid, exact: true },
  { href: "/kb", labelKey: "nav.kb", icon: Library, exact: false },
  {
    href: "/research",
    labelKey: "nav.research",
    icon: BrainCircuit,
    exact: false,
    requireWrite: true,
  },
  { href: "/pieces", labelKey: "nav.piece", icon: PenLine, exact: false },
  { href: "/jobs", labelKey: "nav.jobs", icon: ListChecks, exact: false },
  { href: "/media", labelKey: "nav.media", icon: ImageIcon, exact: false },
  { href: "/settings", labelKey: "nav.settings", icon: IdCard, exact: true },
  {
    href: "/settings/server",
    labelKey: "nav.server",
    icon: Server,
    exact: true,
    requireServer: true,
  },
];

const ROLE_LABEL_EN: Record<Role, string> = {
  owner: "Owner",
  admin: "Admin",
  editor: "Editor",
  viewer: "Read-only",
};

const DIFFICULTY_EN: Record<string, string> = {
  beginner: "Beginner",
  elementary: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
  expert: "Expert",
};

type Status = "checking" | "online" | "degraded" | "offline";

type SidebarProps = {
  series: Series[];
  pathname: string;
  status: Status;
  onNavigate?: () => void;
};

function SidebarBody({ series, pathname, status, onNavigate }: SidebarProps) {
  const { me, role, roleName, tenant, tenantName, tenants, avatarUrl, switchTenant, logout, can } =
    useSession();
  const { t, tm } = useI18n();

  const displayName = me?.user.display_name || me?.user.email || t("nav.localUser");
  const initial = displayName.slice(0, 1).toUpperCase();
  const roleText = role
    ? tm({
        zh: ROLE_LABEL[role] ?? roleName ?? role,
        en: ROLE_LABEL_EN[role] ?? roleName ?? role,
      })
    : roleName || t("common.readOnly");

  const roleLabel = (value: Role | string) =>
    value in ROLE_LABEL
      ? tm({
          zh: ROLE_LABEL[value as Role],
          en: ROLE_LABEL_EN[value as Role] ?? value,
        })
      : value;

  const statusText =
    status === "online"
      ? t("nav.statusOnline")
      : status === "degraded"
        ? t("nav.statusDegraded")
        : status === "checking"
          ? t("nav.statusChecking")
          : t("nav.statusOffline");

  const statusColor =
    status === "online"
      ? "bg-emerald-500"
      : status === "degraded"
        ? "bg-amber-500"
        : status === "checking"
          ? "bg-slate-400"
          : "bg-rose-500";

  return (
    <div className="glass flex h-full min-h-0 flex-col rounded-3xl p-4 shadow-glass">
      <Link
        to="/"
        onClick={onNavigate}
        className="group flex items-center gap-3 rounded-2xl px-2 py-2"
      >
        <span className="brand-gradient grid h-10 w-10 shrink-0 place-items-center rounded-2xl text-white shadow-brand">
          <BookOpen size={18} />
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold tracking-tight text-slate-800 dark:text-slate-100">
            {t("nav.brand")}
          </span>
          <span className="block whitespace-nowrap text-[10px] tracking-tight text-slate-500 dark:text-slate-400">
            {t("nav.tagline")}
          </span>
        </span>
      </Link>

      <nav className="mt-4 space-y-1">
        {NAV_ITEMS.filter(
          (item) =>
            (!item.requireServer || can("manage_server")) &&
            (!item.requireWrite || can("write")),
        ).map((item) => {
          const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              to={item.href}
              onClick={onNavigate}
              className={clsx(
                "flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm transition",
                active
                  ? "brand-gradient text-white shadow-brand"
                  : "text-slate-600 hover:bg-white/55 hover:text-indigo-600 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-indigo-200",
              )}
            >
              <Icon size={16} />
              <span className="font-medium">{t(item.labelKey)}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-6 flex items-center justify-between px-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
          {t("nav.mySeries")}
        </span>
        <span className="text-[10px] text-slate-400 dark:text-slate-500">
          {series.length}
        </span>
      </div>

      <div className="no-scrollbar mt-2 flex-1 space-y-1 overflow-y-auto pr-1">
        {series.length === 0 ? (
          <p className="px-2 py-3 text-[11px] leading-relaxed text-slate-400 dark:text-slate-500">
            {t("nav.noSeries")}
          </p>
        ) : (
          series.map((series) => {
            const active = pathname === `/series/${series.id}`;
            return (
              <Link
                key={series.id}
                to={`/series/${series.id}`}
                onClick={onNavigate}
                className={clsx(
                  "group flex items-start gap-2 rounded-xl px-2.5 py-2 transition",
                  active
                    ? "bg-indigo-500/12 text-indigo-700 dark:bg-indigo-400/15 dark:text-indigo-200"
                    : "text-slate-600 hover:bg-white/55 dark:text-slate-300 dark:hover:bg-white/10",
                )}
              >
                <Sparkles
                  size={13}
                  className={clsx(
                    "mt-0.5 shrink-0",
                    active
                      ? "text-indigo-500 dark:text-indigo-300"
                      : "text-slate-300 group-hover:text-indigo-400 dark:text-slate-600",
                  )}
                />
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-medium">
                    {series.title}
                  </span>
                  <span className="mt-0.5 block truncate text-[10px] text-slate-400 dark:text-slate-500">
                    {tm({
                      zh: difficultyLabel(series.difficulty),
                      en: DIFFICULTY_EN[series.difficulty] ?? difficultyLabel(series.difficulty),
                    })}
                    {series.audience ? ` · ${series.audience}` : ""}
                  </span>
                </span>
              </Link>
            );
          })
        )}
      </div>

      <div className="mt-3 rounded-2xl border border-white/50 bg-white/40 p-3 dark:border-white/10 dark:bg-white/[0.04]">
        <div className="flex items-center gap-2.5">
          {avatarUrl ? (
            <img
              src={`${API_BASE}${avatarUrl}`}
              alt={t("account.avatarAlt")}
              className="h-8 w-8 shrink-0 rounded-full object-cover ring-2 ring-white/60 dark:ring-white/10"
            />
          ) : (
            <span className="brand-gradient grid h-8 w-8 shrink-0 place-items-center rounded-full text-[12px] font-semibold text-white">
              {initial}
            </span>
          )}
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12px] font-medium text-slate-800 dark:text-slate-100">
              {displayName}
            </span>
            <span className="mt-0.5 flex items-center gap-1">
              <span className="chip-muted">
                <ShieldCheck size={10} />
                {roleText}
              </span>
            </span>
          </span>
          {me ? (
            <button
              type="button"
              onClick={() => void logout()}
              aria-label={t("nav.logout")}
              title={t("nav.logout")}
              className="btn-quiet px-1.5"
            >
              <LogOut size={13} />
            </button>
          ) : null}
        </div>

        <label className="mt-2.5 block">
          <span className="mb-1 block text-[10px] uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
            {t("nav.tenant")}
          </span>
          <select
            value={tenant}
            onChange={(event) => switchTenant(event.target.value)}
            className="select w-full py-1.5 text-[11px]"
          >
            {(tenants.length > 0
              ? tenants
              : [
                  {
                    id: tenant || "default",
                    name: tenantName || t("nav.defaultSpace"),
                    role: role ?? "viewer",
                  },
                ]
            ).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {roleLabel(item.role)}
              </option>
            ))}
          </select>
        </label>

        <div className="mt-2.5 flex items-center gap-2 border-t border-white/50 pt-2 text-[11px] text-slate-500 dark:border-white/10 dark:text-slate-400">
          <span className={clsx("h-1.5 w-1.5 rounded-full", statusColor)} />
          <Activity size={12} />
          <span>{statusText}</span>
        </div>
        <p className="mt-1 truncate text-[10px] text-slate-400 dark:text-slate-500">
          {t("nav.footer")}
        </p>
      </div>
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = useLocation().pathname;
  const navigate = useNavigate();
  const { authMode } = useSession();
  const { t } = useI18n();
  const [series, setSeries] = useState<Series[]>([]);
  const [status, setStatus] = useState<Status>("checking");
  const [drawer, setDrawer] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await api.listSeries();
      setSeries(data.series);
    } catch {
      setSeries([]);
    }
    try {
      const health = await api.health();
      setStatus(health.status === "ok" ? "online" : "degraded");
    } catch {
      setStatus("offline");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh, pathname]);

  useEffect(() => {
    const handler = () => {
      refresh();
    };
    window.addEventListener("series-studio:refresh", handler);
    return () => window.removeEventListener("series-studio:refresh", handler);
  }, [refresh]);

  useEffect(() => {
    setDrawer(false);
  }, [pathname]);

  useEffect(() => {
    const handler = () => {
      if (authMode === "required") navigate("/login");
    };
    window.addEventListener("series-studio:auth-required", handler);
    return () =>
      window.removeEventListener("series-studio:auth-required", handler);
  }, [authMode, navigate]);


  useEffect(() => {
    document.body.style.overflow = drawer ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [drawer]);

  const activeSeries = series.find(
    (series) => pathname === `/series/${series.id}`,
  );

  const title =
    pathname === "/"
      ? t("nav.workspace")
      : pathname === "/kb"
        ? t("nav.kb")
        : pathname === "/research"
          ? t("nav.research")
          : pathname.startsWith("/pieces")
            ? t("nav.piece")
            : pathname === "/jobs"
              ? t("nav.jobs")
              : pathname === "/media"
                ? t("nav.media")
                : pathname === "/settings"
                  ? t("nav.settings")
                  : pathname === "/settings/server"
                    ? t("nav.server")
                    : activeSeries?.title ?? t("nav.series");

  if (pathname === "/login") {
    return <main className="min-h-screen px-4 py-6">{children}</main>;
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[1680px]">
      <aside className="hidden w-[292px] shrink-0 px-4 py-4 lg:block">
        <div className="sticky top-4 h-[calc(100vh-2rem)]">
          <SidebarBody series={series} pathname={pathname} status={status} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 px-4 pt-4">
          <div className="glass flex items-center gap-3 rounded-2xl px-3 py-2.5 shadow-glass sm:px-4">
            <button
              type="button"
              onClick={() => setDrawer(true)}
              className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-slate-500 transition hover:bg-white/60 hover:text-indigo-600 dark:text-slate-300 dark:hover:bg-white/10 lg:hidden"
              aria-label={t("nav.openNav")}
            >
              <Menu size={18} />
            </button>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold tracking-tight text-slate-800 dark:text-slate-100">
                {title}
              </p>
            </div>
            <LocaleToggle />
            <ThemeToggle />
          </div>
        </header>

        <main className="app-main min-w-0 flex-1 px-4 pb-14 pt-6">{children}</main>
      </div>

      <AnimatePresence>
        {drawer && (
          <motion.div
            className="fixed inset-0 z-50 lg:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div
              className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
              onClick={() => setDrawer(false)}
            />
            <motion.div
              initial={{ x: -320 }}
              animate={{ x: 0 }}
              exit={{ x: -320 }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              className="absolute inset-y-0 left-0 w-[300px] p-3"
            >
              <div className="relative h-full">
                <SidebarBody
                  series={series}
                  pathname={pathname}
                  status={status}
                  onNavigate={() => setDrawer(false)}
                />
                <button
                  type="button"
                  onClick={() => setDrawer(false)}
                  className="absolute -right-1 top-2 grid h-10 w-10 place-items-center rounded-full bg-white/80 text-slate-500 shadow-sm dark:bg-slate-800/80 dark:text-slate-300"
                  aria-label={t("nav.closeNav")}
                >
                  <X size={15} />
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
