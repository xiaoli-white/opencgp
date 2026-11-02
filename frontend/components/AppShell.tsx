"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  BookOpen,
  LayoutGrid,
  Library,
  Menu,
  Plus,
  Sparkles,
  X,
} from "lucide-react";
import clsx from "clsx";
import { useCallback, useEffect, useState } from "react";
import { api, type Course } from "@/lib/api";
import { difficultyLabel } from "@/lib/format";
import ThemeToggle from "@/components/ThemeToggle";

const NAV_ITEMS = [
  { href: "/", label: "课程工作台", icon: LayoutGrid },
  { href: "/kb", label: "知识库", icon: Library },
];

type Status = "checking" | "online" | "degraded" | "offline";

type SidebarProps = {
  courses: Course[];
  pathname: string;
  status: Status;
  onNavigate?: () => void;
};

function SidebarBody({ courses, pathname, status, onNavigate }: SidebarProps) {
  const statusText =
    status === "online"
      ? "后端已连接"
      : status === "degraded"
        ? "后端降级运行"
        : status === "checking"
          ? "正在连接后端"
          : "后端未连接";

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
        href="/"
        onClick={onNavigate}
        className="group flex items-center gap-3 rounded-2xl px-2 py-2"
      >
        <span className="brand-gradient grid h-10 w-10 shrink-0 place-items-center rounded-2xl text-white shadow-brand">
          <BookOpen size={18} />
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold tracking-tight text-slate-800 dark:text-slate-100">
            AI 课程工作室
          </span>
          <span className="block truncate text-[11px] text-slate-500 dark:text-slate-400">
            对话即作者，课程即活文档
          </span>
        </span>
      </Link>

      <nav className="mt-4 space-y-1">
        {NAV_ITEMS.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={clsx(
                "flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm transition",
                active
                  ? "brand-gradient text-white shadow-brand"
                  : "text-slate-600 hover:bg-white/55 hover:text-indigo-600 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-indigo-200",
              )}
            >
              <Icon size={16} />
              <span className="font-medium">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-6 flex items-center justify-between px-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
          我的课程
        </span>
        <span className="text-[10px] text-slate-400 dark:text-slate-500">
          {courses.length}
        </span>
      </div>

      <div className="no-scrollbar mt-2 flex-1 space-y-1 overflow-y-auto pr-1">
        {courses.length === 0 ? (
          <p className="px-2 py-3 text-[11px] leading-relaxed text-slate-400 dark:text-slate-500">
            还没有课程，去工作台新建一门。
          </p>
        ) : (
          courses.map((course) => {
            const active = pathname === `/courses/${course.id}`;
            return (
              <Link
                key={course.id}
                href={`/courses/${course.id}`}
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
                    {course.title}
                  </span>
                  <span className="mt-0.5 block truncate text-[10px] text-slate-400 dark:text-slate-500">
                    {difficultyLabel(course.difficulty)}
                    {course.audience ? ` · ${course.audience}` : ""}
                  </span>
                </span>
              </Link>
            );
          })
        )}
      </div>

      <div className="mt-3 rounded-2xl border border-white/50 bg-white/40 p-3 dark:border-white/10 dark:bg-white/[0.04]">
        <div className="flex items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
          <span className={clsx("h-1.5 w-1.5 rounded-full", statusColor)} />
          <Activity size={12} />
          <span>{statusText}</span>
        </div>
        <p className="mt-1 truncate text-[10px] text-slate-400 dark:text-slate-500">
          证据驱动写作 · 版本可回滚
        </p>
      </div>
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [courses, setCourses] = useState<Course[]>([]);
  const [status, setStatus] = useState<Status>("checking");
  const [drawer, setDrawer] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await api.listCourses();
      setCourses(data.courses);
    } catch {
      setCourses([]);
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
    window.addEventListener("course-studio:refresh", handler);
    return () => window.removeEventListener("course-studio:refresh", handler);
  }, [refresh]);

  useEffect(() => {
    setDrawer(false);
  }, [pathname]);

  useEffect(() => {
    document.body.style.overflow = drawer ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [drawer]);

  const activeCourse = courses.find(
    (course) => pathname === `/courses/${course.id}`,
  );

  const title = pathname === "/" ? "课程工作台" : pathname === "/kb" ? "知识库" : activeCourse?.title ?? "课程";
  const subtitle =
    pathname === "/"
      ? "从主题到成体系课程，逐讲生成、随时追问"
      : pathname === "/kb"
        ? "上传资料，作为写作与追问的证据底座"
        : activeCourse?.subtitle || "大纲 · 阅读 · 追问 · 版本";

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[1680px]">
      <aside className="hidden w-[292px] shrink-0 px-4 py-4 lg:block">
        <div className="sticky top-4 h-[calc(100vh-2rem)]">
          <SidebarBody courses={courses} pathname={pathname} status={status} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 px-4 pt-4">
          <div className="glass flex items-center gap-3 rounded-2xl px-3 py-2.5 shadow-glass sm:px-4">
            <button
              type="button"
              onClick={() => setDrawer(true)}
              className="grid h-9 w-9 place-items-center rounded-full text-slate-500 transition hover:bg-white/60 hover:text-indigo-600 dark:text-slate-300 dark:hover:bg-white/10 lg:hidden"
              aria-label="打开导航"
            >
              <Menu size={18} />
            </button>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold tracking-tight text-slate-800 dark:text-slate-100">
                {title}
              </p>
              <p className="hidden truncate text-[11px] text-slate-500 dark:text-slate-400 sm:block">
                {subtitle}
              </p>
            </div>
            <Link href="/" className="btn-quiet hidden sm:inline-flex">
              <Plus size={14} />
              新课程
            </Link>
            <Link href="/kb" className="btn-quiet hidden md:inline-flex">
              <Library size={14} />
              知识库
            </Link>
            <ThemeToggle />
          </div>
        </header>

        <main className="min-w-0 flex-1 px-4 pb-14 pt-4 sm:px-6">{children}</main>
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
                  courses={courses}
                  pathname={pathname}
                  status={status}
                  onNavigate={() => setDrawer(false)}
                />
                <button
                  type="button"
                  onClick={() => setDrawer(false)}
                  className="absolute -right-1 top-2 grid h-8 w-8 place-items-center rounded-full bg-white/80 text-slate-500 shadow-sm dark:bg-slate-800/80 dark:text-slate-300"
                  aria-label="关闭导航"
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
