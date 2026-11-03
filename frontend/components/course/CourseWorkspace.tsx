import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  ArrowLeft,
  ArrowDown,
  ArrowUp,
  BookOpen,
  Check,
  ChevronRight,
  History,
  Loader2,
  List,
  Lock,
  MessageSquare,
  Network,
  Pencil,
  Plus,
  ScrollText,
  Sparkles,
  Target,
  Trash2,
  X,
} from "lucide-react";
import clsx from "clsx";
import {
  ApiError,
  api,
  type CourseDetail,
  type CourseProgress,
  type GenerationMode,
  type LessonVersion,
} from "@/lib/api";
import {
  createLessonLockController,
  releaseLessonLockBeacon,
  type LessonLockController,
  type LessonLockState,
} from "@/lib/lock";
import {
  contentLength,
  difficultyLabel,
  formatRelative,
  modeLabel,
  statusLabel,
} from "@/lib/format";
import MarkdownReader from "@/components/reader/MarkdownReader";
import CourseReader from "@/components/reader/CourseReader";
import VersionPanel from "@/components/reader/VersionPanel";
import ChatPanel from "@/components/chat/ChatPanel";
import ModePicker from "@/components/course/ModePicker";
import BlueprintBoard from "@/components/blueprint/BlueprintBoard";
import ReviewControls from "@/components/course/ReviewControls";
import CourseGrantsPanel from "@/components/course/CourseGrantsPanel";
import StatusBadge from "@/components/course/StatusBadge";
import LessonLockBanner from "@/components/course/LessonLockBanner";
import CourseEditDialog from "@/components/course/CourseEditDialog";
import ThreadsPanel from "@/components/course/ThreadsPanel";
import {
  ConfirmDialog,
  PromptDialog,
  RowMenu,
} from "@/components/common/Dialogs";
import ConflictDialog, {
  type VersionConflict,
} from "@/components/course/ConflictDialog";
import { useSession } from "@/components/auth/SessionProvider";

type WorkspaceView = "reader" | "blueprint" | "continuous";

const VIEWS: { value: WorkspaceView; label: string; icon: typeof BookOpen }[] = [
  { value: "reader", label: "阅读", icon: BookOpen },
  { value: "blueprint", label: "蓝图", icon: Network },
  { value: "continuous", label: "连续阅读", icon: ScrollText },
];

export default function CourseWorkspace({ courseId }: { courseId: string }) {
  const { can, roleName } = useSession();
  const canWrite = can("write");
  const canManage = can("manage_members");
  const readOnly = !canWrite;
  const [detail, setDetail] = useState<CourseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [versions, setVersions] = useState<LessonVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [reverting, setReverting] = useState<number | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [topic, setTopic] = useState("");
  const [topK, setTopK] = useState(5);
  const [generateMode, setGenerateMode] = useState<GenerationMode>("strict");
  const [chatOpen, setChatOpen] = useState(false);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const [pendingSelection, setPendingSelection] = useState<string | null>(null);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [grantsOpen, setGrantsOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [versionTick, setVersionTick] = useState(0);
  const [view, setView] = useState<WorkspaceView>("reader");
  const [progress, setProgress] = useState<CourseProgress | null>(null);
  const [blueprintTick, setBlueprintTick] = useState(0);
  const [lockState, setLockState] = useState<LessonLockState>({
    status: "idle",
  });
  const [conflict, setConflict] = useState<VersionConflict | null>(null);
  const [conflictBusy, setConflictBusy] = useState(false);
  const [courseEditOpen, setCourseEditOpen] = useState(false);
  const [courseDeleteOpen, setCourseDeleteOpen] = useState(false);
  const [courseBusy, setCourseBusy] = useState(false);
  const [courseDialogError, setCourseDialogError] = useState("");
  const [lessonRename, setLessonRename] = useState<{ id: string; title: string } | null>(
    null,
  );
  const [lessonDelete, setLessonDelete] = useState<{ id: string; title: string } | null>(
    null,
  );
  const [lessonBusy, setLessonBusy] = useState(false);
  const [lessonDialogError, setLessonDialogError] = useState("");
  const navigate = useNavigate();
  const lockController = useRef<LessonLockController | null>(null);

  const lockBlocked =
    canWrite && (lockState.status === "blocked" || lockState.status === "lost");
  const lockReason =
    lockState.status === "blocked"
      ? `${lockState.name} 正在编辑这一讲`
      : "编辑锁已失效";
  const guard = readOnly
    ? { disabled: true, title: "当前角色只读" }
    : lockBlocked
      ? { disabled: true, title: lockReason }
      : {};

  const loadCourse = useCallback(
    async (preferred?: string | null) => {
      const data = await api.getCourse(courseId);
      setDetail(data);
      setActiveId((prev) => {
        const candidate = preferred ?? prev;
        if (candidate && data.lessons.some((lesson) => lesson.id === candidate)) {
          return candidate;
        }
        return data.lessons[0]?.id ?? null;
      });
      return data;
    },
    [courseId],
  );

  const refreshProgress = useCallback(async () => {
    try {
      const data = await api.getProgress(courseId);
      setProgress(data);
    } catch {
      setProgress(null);
    }
  }, [courseId]);

  const refreshWorkspace = useCallback(async () => {
    await loadCourse(activeId);
    await refreshProgress();
    setVersionTick((tick) => tick + 1);
    setBlueprintTick((tick) => tick + 1);
  }, [activeId, loadCourse, refreshProgress]);

  useEffect(() => {
    void refreshProgress();
  }, [refreshProgress, versionTick, blueprintTick]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError("");
    api
      .getCourse(courseId)
      .then((data) => {
        if (cancelled) return;
        setDetail(data);
        setActiveId(data.lessons[0]?.id ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "课程加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [courseId]);

  useEffect(() => {
    if (!activeId) {
      setVersions([]);
      return;
    }
    let cancelled = false;
    setVersionsLoading(true);
    api
      .listVersions(activeId)
      .then((data) => {
        if (!cancelled) setVersions(data.versions);
      })
      .catch(() => {
        if (!cancelled) setVersions([]);
      })
      .finally(() => {
        if (!cancelled) setVersionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId, versionTick]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 4200);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    setPendingSelection(null);
  }, [activeId]);

  const activeLesson = useMemo(
    () => detail?.lessons.find((lesson) => lesson.id === activeId) ?? null,
    [detail, activeId],
  );

  const currentVersionRecord = useMemo(
    () =>
      activeLesson
        ? versions.find(
            (version) => version.version === activeLesson.current_version,
          )
        : undefined,
    [versions, activeLesson],
  );

  const currentCitations = useMemo(
    () => currentVersionRecord?.citations ?? [],
    [currentVersionRecord],
  );

  const currentMode = useMemo<GenerationMode | "">(
    () =>
      currentVersionRecord?.mode || activeLesson?.last_mode || "",
    [currentVersionRecord, activeLesson],
  );

  useEffect(() => {
    if (!activeId || !canWrite) {
      setLockState({ status: "idle" });
      return;
    }
    const controller = createLessonLockController({
      lessonId: activeId,
      onState: setLockState,
    });
    lockController.current = controller;
    void controller.start();
    const handleUnload = () => {
      const token = controller.token();
      if (token) releaseLessonLockBeacon(activeId, token);
    };
    window.addEventListener("beforeunload", handleUnload);
    return () => {
      window.removeEventListener("beforeunload", handleUnload);
      controller.stop(true);
      if (lockController.current === controller) lockController.current = null;
    };
  }, [activeId, canWrite]);

  const handleLoadLatest = useCallback(() => {
    setConflict(null);
    void refreshWorkspace();
  }, [refreshWorkspace]);

  const handleRetryConflict = async () => {
    const current = conflict;
    if (!current) return;
    setConflict(null);
    setConflictBusy(true);
    try {
      await current.retry();
    } finally {
      setConflictBusy(false);
    }
  };

  const runGenerate = async (expectedVersion?: number) => {
    if (!activeLesson || generating) return;
    if (lockBlocked) {
      setError(lockReason);
      return;
    }
    const baseline = expectedVersion ?? activeLesson.current_version;
    setGenerating(true);
    setError("");
    try {
      const result = await api.generateLesson(activeLesson.id, {
        topic: topic.trim() || undefined,
        top_k: topK,
        mode: generateMode,
        expected_version: baseline,
      });
      await loadCourse(activeLesson.id);
      setVersionTick((tick) => tick + 1);
      setGenerateOpen(false);
      setTopic("");
      setNotice(
        result.mode === "loose"
          ? `已按非严格模式生成 v${result.version} · 正文标注由大模型编写`
          : result.grounded
            ? `已生成 v${result.version} · 引用 ${result.citations.length} 条证据`
            : `v${result.version} 已写入：知识库暂缺证据，正文为资料不足提示`,
      );
      window.dispatchEvent(new Event("course-studio:refresh"));
    } catch (err) {
      const info = err instanceof ApiError ? err.conflict() : null;
      if (info && info.current_version !== undefined) {
        const current = info.current_version;
        setConflict({
          expectedVersion: baseline,
          currentVersion: current,
          label: "本讲正文",
          retry: () => runGenerate(current),
        });
      } else {
        setError(err instanceof Error ? err.message : "生成失败");
      }
    } finally {
      setGenerating(false);
    }
  };

  const handleRevert = async (version: number, expectedVersion?: number) => {
    if (!activeLesson) return;
    if (lockBlocked) {
      setError(lockReason);
      return;
    }
    const baseline = expectedVersion ?? activeLesson.current_version;
    setReverting(version);
    setError("");
    try {
      await api.revertLesson(
        activeLesson.id,
        version,
        `revert to v${version}`,
        baseline,
      );
      await loadCourse(activeLesson.id);
      setVersionTick((tick) => tick + 1);
      setNotice(`已回滚：基于 v${version} 生成新版本，历史仍可追溯`);
    } catch (err) {
      const info = err instanceof ApiError ? err.conflict() : null;
      if (info && info.current_version !== undefined) {
        const current = info.current_version;
        setConflict({
          expectedVersion: baseline,
          currentVersion: current,
          label: "版本回滚",
          retry: () => handleRevert(version, current),
        });
      } else {
        setError(err instanceof Error ? err.message : "回滚失败");
      }
    } finally {
      setReverting(null);
    }
  };

  const handleCreateLesson = async (event: React.FormEvent) => {
    event.preventDefault();
    const title = newTitle.trim();
    if (!title || creating) return;
    setCreating(true);
    setError("");
    try {
      const result = await api.createLesson(courseId, {
        title,
        order_index: (detail?.lessons.length ?? 0) + 1,
      });
      await loadCourse(result.lesson.id);
      setNewTitle("");
      setFormOpen(false);
      setNotice(`已创建《${result.lesson.title}》`);
      await refreshProgress();
      window.dispatchEvent(new Event("course-studio:refresh"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建讲次失败");
    } finally {
      setCreating(false);
    }
  };

  const handleChatApplied = async () => {
    if (activeLesson) {
      await loadCourse(activeLesson.id);
    }
    setVersionTick((tick) => tick + 1);
  };

  const handleAskSelection = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setPendingSelection(trimmed);
    setChatOpen(true);
  }, []);

  const handleCloseChat = useCallback(() => {
    setChatOpen(false);
    setPendingSelection(null);
  }, []);

  const handleOpenLesson = useCallback((lessonId: string) => {
    if (lessonId) setActiveId(lessonId);
    setView("reader");
    setGenerateOpen(false);
  }, []);

  const handleLessonsChanged = useCallback(async () => {
    await loadCourse(activeId);
    await refreshProgress();
  }, [activeId, loadCourse, refreshProgress]);

  const handleCourseDelete = async () => {
    setCourseBusy(true);
    setCourseDialogError("");
    try {
      await api.deleteCourse(courseId);
      window.dispatchEvent(new Event("course-studio:refresh"));
      navigate("/");
    } catch (err) {
      setCourseDialogError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setCourseBusy(false);
    }
  };

  const handleLessonRename = async (title: string) => {
    if (!lessonRename) return;
    setLessonBusy(true);
    setLessonDialogError("");
    try {
      await api.updateLesson(lessonRename.id, { title });
      setLessonRename(null);
      setNotice("讲次已重命名");
      await handleLessonsChanged();
    } catch (err) {
      setLessonDialogError(err instanceof Error ? err.message : "重命名失败");
    } finally {
      setLessonBusy(false);
    }
  };

  const handleLessonDelete = async () => {
    if (!lessonDelete) return;
    setLessonBusy(true);
    setLessonDialogError("");
    try {
      await api.deleteLesson(lessonDelete.id);
      setLessonDelete(null);
      setNotice("讲次已删除");
      if (activeId === lessonDelete.id) setActiveId(null);
      await handleLessonsChanged();
    } catch (err) {
      setLessonDialogError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setLessonBusy(false);
    }
  };

  const moveLesson = async (lessonId: string, direction: -1 | 1) => {
    if (!detail) return;
    const ids = detail.lessons.map((lesson) => lesson.id);
    const index = ids.indexOf(lessonId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ids.length) return;
    const next = [...ids];
    next[index] = ids[target];
    next[target] = ids[index];
    try {
      await api.reorderLessons(courseId, next);
      setNotice("讲次顺序已更新");
      await handleLessonsChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "排序失败");
    }
  };

  if (loading) {
    return (
      <div className="space-y-5">
        <div className="glass h-32 animate-pulse rounded-3xl" />
        <div className="grid gap-5 lg:grid-cols-[250px_minmax(0,1fr)] xl:grid-cols-[250px_minmax(0,1fr)_320px]">
          <div className="glass h-72 animate-pulse rounded-3xl" />
          <div className="glass h-[28rem] animate-pulse rounded-3xl" />
        </div>
      </div>
    );
  }

  if (loadError || !detail) {
    return (
      <div className="glass mx-auto max-w-lg rounded-3xl p-8 text-center shadow-glass">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-rose-500/10 text-rose-500">
          <AlertCircle size={20} />
        </div>
        <p className="mt-4 text-sm font-medium text-slate-700 dark:text-slate-200">
          课程无法加载
        </p>
        <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          {loadError || "课程不存在，或后端服务未启动。"}
        </p>
        <Link to="/" className="btn btn-ghost mt-5">
          <ArrowLeft size={14} />
          返回课程列表
        </Link>
      </div>
    );
  }

  const course = detail.course;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="space-y-5"
    >
      <div className="glass rounded-3xl p-5 shadow-glass sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <Link
              to="/"
              className="inline-flex items-center gap-1 text-[11px] text-slate-400 transition hover:text-indigo-600 dark:hover:text-indigo-300"
            >
              <ArrowLeft size={12} />
              全部课程
            </Link>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 dark:text-white sm:text-[26px]">
              {course.title}
            </h1>
            {course.subtitle ? (
              <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                {course.subtitle}
              </p>
            ) : null}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="chip">
                <BookOpen size={11} />
                {detail.lesson_count} 讲
              </span>
              <span className="chip-muted">{difficultyLabel(course.difficulty)}</span>
              {course.audience ? (
                <span className="chip-muted">受众 · {course.audience}</span>
              ) : null}
              <span className="chip-muted">
                {course.language === "zh" ? "中文" : course.language}
              </span>
            </div>
          </div>
          <div className="no-scrollbar -mx-1 flex items-center gap-2 overflow-x-auto px-1">
            {canWrite ? (
              <button
                type="button"
                onClick={() => setCourseEditOpen(true)}
                className="btn btn-ghost shrink-0"
              >
                <Pencil size={13} />
                编辑
              </button>
            ) : null}
            {canWrite ? (
              <button
                type="button"
                onClick={() => {
                  setCourseDialogError("");
                  setCourseDeleteOpen(true);
                }}
                className="btn btn-ghost shrink-0 text-rose-600 hover:text-rose-700 dark:text-rose-300"
              >
                <Trash2 size={13} />
                删除课程
              </button>
            ) : null}
            {can("manage_members") ? (
              <button
                type="button"
                onClick={() => setGrantsOpen(true)}
                className="btn btn-ghost shrink-0"
              >
                <Lock size={13} />
                可见范围
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => setOutlineOpen(true)}
              className="btn btn-ghost shrink-0 lg:hidden"
            >
              <List size={14} />
              大纲
            </button>
            <button
              type="button"
              {...guard}
              onClick={() => setChatOpen(true)}
              disabled={readOnly || lockBlocked || !activeLesson}
              className="btn btn-primary hidden shrink-0 sm:inline-flex"
            >
              <MessageSquare size={14} />
              追问 / 修改
            </button>
          </div>
        </div>
      </div>

      {readOnly ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-2 text-[11px] text-amber-700 dark:text-amber-300">
          你以 {roleName || "只读"} 身份访问，仅可读取，写入类操作已禁用。
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="no-scrollbar inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-full border border-slate-200/70 bg-white/50 p-0.5 shadow-[0_10px_26px_-24px_rgba(99,102,241,0.9)] backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.05]">
          {VIEWS.map((item) => {
            const active = view === item.value;
            const Icon = item.icon;
            return (
              <button
                key={item.value}
                type="button"
                onClick={() => setView(item.value)}
                className={clsx(
                  "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-medium transition",
                  active
                    ? "brand-gradient text-white shadow-[0_10px_22px_-14px_rgba(99,102,241,0.9)]"
                    : "text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-200",
                )}
              >
                <Icon size={12} />
                {item.label}
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {progress ? (
            <span className="chip-muted">
              已通过 {progress.approved}/{progress.total} · 待审{" "}
              {progress.pending_review}
            </span>
          ) : null}
          <span className="chip-muted">
            蓝图 {progress?.blueprint_ready ? `v${progress.blueprint_version}` : "未生成"}
          </span>
        </div>
      </div>

      {error ? (
        <div className="flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-xs leading-relaxed text-rose-700 dark:text-rose-300">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span className="flex-1">{error}</span>
          <button
            type="button"
            onClick={() => setError("")}
            className="text-rose-400 transition hover:text-rose-600"
            aria-label="关闭错误提示"
          >
            <X size={13} />
          </button>
        </div>
      ) : null}

      {view === "reader" ? (
      <div className="grid gap-5 lg:grid-cols-[250px_minmax(0,1fr)] xl:grid-cols-[250px_minmax(0,1fr)_320px]">
        <AnimatePresence>
          {outlineOpen && (
            <motion.div
              className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-sm lg:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setOutlineOpen(false)}
            />
          )}
        </AnimatePresence>
        <aside
          className={clsx(
            "glass no-scrollbar flex-col rounded-3xl p-3.5 shadow-glass",
            "max-lg:fixed max-lg:inset-y-0 max-lg:left-0 max-lg:z-50 max-lg:m-3 max-lg:w-[min(300px,calc(100vw-1.5rem))] max-lg:max-h-none max-lg:overflow-y-auto",
            "hidden lg:sticky lg:top-24 lg:flex lg:max-h-[calc(100vh-7rem)]",
            outlineOpen ? "max-lg:flex" : "",
          )}
        >
          <div className="flex items-center justify-between px-1">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                课程大纲
              </p>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
                {detail.lesson_count} 讲
              </p>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setFormOpen((value) => !value)}
                className="grid h-9 w-9 place-items-center rounded-full bg-indigo-500/10 text-indigo-600 transition hover:bg-indigo-500/20 dark:text-indigo-300"
                aria-label="新增讲次"
              >
                <Plus size={15} />
              </button>
              <button
                type="button"
                onClick={() => setOutlineOpen(false)}
                className="grid h-9 w-9 place-items-center rounded-full text-slate-400 transition hover:bg-white/70 hover:text-slate-600 dark:hover:bg-white/10 lg:hidden"
                aria-label="关闭大纲"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          <AnimatePresence initial={false}>
            {formOpen && (
              <motion.form
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
                onSubmit={handleCreateLesson}
                className="overflow-hidden"
              >
                <div className="mt-2.5 space-y-2 rounded-2xl border border-white/60 bg-white/50 p-2.5 dark:border-white/10 dark:bg-white/[0.04]">
                  <input
                    autoFocus
                    value={newTitle}
                    onChange={(event) => setNewTitle(event.target.value)}
                    placeholder="讲次标题，如：什么是向量检索"
                    className="input text-[13px]"
                  />
                  <div className="flex justify-end gap-1">
                    <button
                      type="button"
                      onClick={() => {
                        setFormOpen(false);
                        setNewTitle("");
                      }}
                      className="btn-quiet"
                    >
                      取消
                    </button>
                    <button
                      type="submit"
                      disabled={creating || !newTitle.trim()}
                      className="btn btn-primary px-3 py-1.5 text-[11px]"
                    >
                      {creating ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                      添加
                    </button>
                  </div>
                </div>
              </motion.form>
            )}
          </AnimatePresence>

          <div className="no-scrollbar mt-3 flex-1 space-y-1 overflow-y-auto pr-0.5">
            {detail.lessons.length === 0 ? (
              <p className="px-2 py-4 text-[11px] leading-relaxed text-slate-400 dark:text-slate-500">
                还没有讲次，先添加一讲再生成正文。
              </p>
            ) : (
              detail.lessons.map((lesson, lessonIndex) => {
                const active = lesson.id === activeId;
                return (
                  <div
                    key={lesson.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => {
                      setActiveId(lesson.id);
                      setGenerateOpen(false);
                      setOutlineOpen(false);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        setActiveId(lesson.id);
                        setGenerateOpen(false);
                        setOutlineOpen(false);
                      }
                    }}
                    className={clsx(
                      "group flex w-full items-center gap-2 rounded-xl px-2 py-2 text-left transition",
                      active
                        ? "bg-indigo-500/12 dark:bg-indigo-400/15"
                        : "hover:bg-white/60 dark:hover:bg-white/[0.06]",
                    )}
                  >
                    <span
                      className={clsx(
                        "grid h-6 w-6 shrink-0 place-items-center rounded-lg text-[11px] font-semibold",
                        active
                          ? "brand-gradient text-white"
                          : "bg-slate-200/70 text-slate-500 dark:bg-white/10 dark:text-slate-300",
                      )}
                    >
                      {lesson.order_index}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span
                        className={clsx(
                          "block truncate text-[13px] font-medium",
                          active
                            ? "text-indigo-700 dark:text-indigo-200"
                            : "text-slate-600 dark:text-slate-300",
                        )}
                      >
                        {lesson.title}
                      </span>
                      <span className="mt-0.5 block truncate text-[10px] text-slate-400 dark:text-slate-500">
                        {lesson.content ? `v${lesson.current_version}` : "待生成"} ·{" "}
                        {statusLabel(lesson.status)}
                      </span>
                    </span>
                    {canWrite ? (
                      <RowMenu
                        items={[
                          {
                            label: "重命名",
                            icon: <Pencil size={11} />,
                            onClick: () => {
                              setLessonDialogError("");
                              setLessonRename({ id: lesson.id, title: lesson.title });
                            },
                          },
                          {
                            label: "上移",
                            icon: <ArrowUp size={11} />,
                            disabled: lessonIndex === 0,
                            onClick: () => void moveLesson(lesson.id, -1),
                          },
                          {
                            label: "下移",
                            icon: <ArrowDown size={11} />,
                            disabled: lessonIndex === detail.lessons.length - 1,
                            onClick: () => void moveLesson(lesson.id, 1),
                          },
                          {
                            label: "删除讲次",
                            icon: <Trash2 size={11} />,
                            danger: true,
                            onClick: () => {
                              setLessonDialogError("");
                              setLessonDelete({ id: lesson.id, title: lesson.title });
                            },
                          },
                        ]}
                      />
                    ) : (
                      <ChevronRight
                        size={13}
                        className={clsx(
                          "shrink-0 transition",
                          active
                            ? "text-indigo-500 dark:text-indigo-300"
                            : "text-slate-300 group-hover:text-indigo-400 dark:text-slate-600",
                        )}
                      />
                    )}
                  </div>
                );
              })
            )}
          </div>
        </aside>

        <div className="min-w-0 space-y-4">
          {activeLesson ? (
            <article className="glass rounded-3xl p-4 shadow-glass sm:p-8">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200/70 pb-5 dark:border-white/10">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400 dark:text-slate-500">
                    <span>第 {activeLesson.order_index} 讲</span>
                    <span>·</span>
                    <StatusBadge status={activeLesson.status} />
                    <span>·</span>
                    <span>v{activeLesson.current_version}</span>
                    {activeLesson.content ? (
                      <span
                        className={clsx(
                          "rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                          currentMode === "loose"
                            ? "bg-amber-400/20 text-amber-700 ring-1 ring-amber-400/30 dark:bg-amber-300/12 dark:text-amber-300 dark:ring-amber-300/20"
                            : "bg-indigo-500/12 text-indigo-600 ring-1 ring-indigo-400/20 dark:bg-indigo-400/14 dark:text-indigo-300 dark:ring-indigo-300/20",
                        )}
                      >
                        {modeLabel(currentMode)}模式
                      </span>
                    ) : null}
                  </div>
                  <h2 className="mt-1 text-xl font-semibold tracking-tight text-slate-900 dark:text-white sm:text-[22px]">
                    {activeLesson.title}
                  </h2>
                </div>
                <div className="no-scrollbar -mx-1 flex items-center gap-2 overflow-x-auto px-1 pb-0.5">
                  <button
                    type="button"
                    {...guard}
                    onClick={() => setGenerateOpen((value) => !value)}
                    disabled={readOnly || lockBlocked || generating}
                    className="btn btn-primary"
                  >
                    {generating ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Sparkles size={14} />
                    )}
                    {activeLesson.content ? "重新生成" : "生成正文"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setVersionsOpen(true)}
                    className="btn btn-ghost xl:hidden"
                  >
                    <History size={14} />
                    版本
                  </button>
                  {canWrite ? (
                    <RowMenu
                      label="讲次操作"
                      items={[
                        {
                          label: "重命名讲次",
                          icon: <Pencil size={11} />,
                          onClick: () => {
                            setLessonDialogError("");
                            setLessonRename({
                              id: activeLesson.id,
                              title: activeLesson.title,
                            });
                          },
                        },
                        {
                          label: "上移",
                          icon: <ArrowUp size={11} />,
                          disabled:
                            detail.lessons.findIndex(
                              (lesson) => lesson.id === activeLesson.id,
                            ) <= 0,
                          onClick: () => void moveLesson(activeLesson.id, -1),
                        },
                        {
                          label: "下移",
                          icon: <ArrowDown size={11} />,
                          disabled:
                            detail.lessons.findIndex(
                              (lesson) => lesson.id === activeLesson.id,
                            ) ===
                            detail.lessons.length - 1,
                          onClick: () => void moveLesson(activeLesson.id, 1),
                        },
                        {
                          label: "删除讲次",
                          icon: <Trash2 size={11} />,
                          danger: true,
                          onClick: () => {
                            setLessonDialogError("");
                            setLessonDelete({
                              id: activeLesson.id,
                              title: activeLesson.title,
                            });
                          },
                        },
                      ]}
                    />
                  ) : null}
                </div>
              </div>

              <LessonLockBanner
                state={lockState}
                canTakeOver={canManage}
                readOnly={readOnly}
                busy={lockState.status === "acquiring"}
                onRefresh={() => void refreshWorkspace()}
                onTakeOver={() => void lockController.current?.force()}
                onReacquire={() => void lockController.current?.retry()}
              />

              <ReviewControls
                lesson={activeLesson}
                progress={progress}
                onReviewed={refreshWorkspace}
                onNotice={setNotice}
                onError={setError}
                locked={lockBlocked}
                lockedReason={lockReason}
              />

              <AnimatePresence initial={false}>
                {generateOpen && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.22 }}
                    className="overflow-hidden"
                  >
                    <div className="mt-4 rounded-2xl border border-indigo-200/60 bg-indigo-500/5 p-4 dark:border-indigo-400/20 dark:bg-indigo-400/5">
                      {readOnly ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-2 text-[11px] text-amber-700 dark:text-amber-300">
          你以 只读 身份访问该空间，可浏览与阅读，写入类操作已禁用。
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-[11px] font-medium text-indigo-600 dark:text-indigo-300">
                          {generateMode === "loose"
                            ? "非严格模式：先检索证据，允许模型自由写作，正文标注由大模型编写"
                            : "严格模式：先检索知识库证据，再逐段带 [En] 引用写作"}
                        </p>
                        <span className="chip-muted">写作模式</span>
                      </div>
                      <div className="mt-3">
                        <ModePicker
                          value={generateMode}
                          onChange={setGenerateMode}
                          disabled={generating}
                        />
                      </div>
                      <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_120px_auto]">
                        <input
                          value={topic}
                          onChange={(event) => setTopic(event.target.value)}
                          placeholder="本节主题（留空则用讲次标题）"
                          className="input"
                        />
                        <select
                          value={topK}
                          onChange={(event) => setTopK(Number(event.target.value))}
                          className="select"
                        >
                          {[3, 5, 8, 12].map((value) => (
                            <option key={value} value={value}>
                              证据 {value} 条
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          {...guard}
                          onClick={() => void runGenerate()}
                          disabled={readOnly || lockBlocked || generating}
                          className="btn btn-primary"
                        >
                          {generating ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Sparkles size={14} />
                          )}
                          开始生成
                        </button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {generating && (
                <div className="mt-4 flex items-center gap-2 rounded-2xl border border-indigo-200/50 bg-white/50 px-4 py-3 text-xs text-slate-500 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-400">
                  <Loader2 size={14} className="animate-spin text-indigo-500" />
                  正在检索证据、组织段落并写入新版本…
                </div>
              )}

              {activeLesson.learning_objectives.length > 0 && (
                <div className="mt-5 rounded-2xl border border-indigo-200/50 bg-indigo-500/5 p-4 dark:border-indigo-400/20 dark:bg-indigo-400/5">
                  <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-indigo-500 dark:text-indigo-300">
                    <Target size={12} />
                    本节目标
                  </p>
                  <ul className="mt-2 space-y-1 text-[13px] leading-relaxed text-slate-600 dark:text-slate-300">
                    {activeLesson.learning_objectives.map((objective) => (
                      <li key={objective} className="flex items-start gap-1.5">
                        <Check size={12} className="mt-1 shrink-0 text-indigo-400" />
                        <span>{objective}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {activeLesson.prerequisites.length > 0 && (
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <span className="text-[10px] uppercase tracking-[0.14em] text-slate-400">
                    前置
                  </span>
                  {activeLesson.prerequisites.map((item) => (
                    <span key={item} className="chip-muted">
                      {item}
                    </span>
                  ))}
                </div>
              )}

              <div className="relative mt-6">
                {activeLesson.content ? (
                  <MarkdownReader
                    content={activeLesson.content}
                    citations={currentCitations}
                    mode={currentMode}
                    onAskSelection={handleAskSelection}
                  />
                ) : (
                  <div className="rounded-2xl border border-dashed border-slate-300/70 px-6 py-10 text-center dark:border-white/15">
                    <div className="brand-gradient mx-auto grid h-12 w-12 place-items-center rounded-2xl text-white shadow-brand">
                      <Sparkles size={20} />
                    </div>
                    <p className="mt-4 text-sm font-medium text-slate-700 dark:text-slate-200">
                      这一讲还没有正文
                    </p>
                    <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                      严格模式没有证据就明确提示资料不足；非严格模式允许模型自由写作，但正文会标注「由大模型编写」。
                    </p>
                    <div className="mt-4 flex flex-wrap justify-center gap-2">
                      <button
                        type="button"
                        {...guard}
                        onClick={() => setGenerateOpen(true)}
                        disabled={readOnly || lockBlocked}
                        className="btn btn-primary"
                      >
                        <Sparkles size={14} />
                        生成正文
                      </button>
                      <Link to="/kb" className="btn btn-ghost">
                        先上传资料
                      </Link>
                    </div>
                  </div>
                )}
                {lockBlocked ? (
                  <div className="pointer-events-none absolute inset-0 rounded-2xl bg-white/30 dark:bg-slate-950/35">
                    <div className="sticky top-3 mx-auto mt-3 w-fit rounded-full border border-amber-400/40 bg-amber-50/90 px-3 py-1 text-[11px] font-medium text-amber-800 shadow-sm backdrop-blur-sm dark:border-amber-300/25 dark:bg-amber-400/15 dark:text-amber-200">
                      {lockReason} · 正文只读
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="mt-8 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200/70 pt-4 text-[11px] text-slate-400 dark:border-white/10 dark:text-slate-500">
                <span>
                  {currentCitations.length} 条引用 · {contentLength(activeLesson.content)} 字
                </span>
                <span>更新于 {formatRelative(activeLesson.updated_at)}</span>
              </div>
            </article>
          ) : (
            <div className="glass rounded-3xl p-10 text-center shadow-glass">
              <div className="brand-gradient mx-auto grid h-12 w-12 place-items-center rounded-2xl text-white shadow-brand">
                <BookOpen size={20} />
              </div>
              <p className="mt-4 text-sm font-medium text-slate-700 dark:text-slate-200">
                这门课还没有讲次
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                在左侧大纲里添加第一讲，然后生成正文。
              </p>
              <button
                type="button"
                onClick={() => setFormOpen(true)}
                className="btn btn-primary mt-4"
              >
                <Plus size={14} />
                添加第一讲
              </button>
            </div>
          )}
          <div className="mt-4">
            <ThreadsPanel
              courseId={courseId}
              canWrite={canWrite}
              onNotice={setNotice}
              onError={setError}
            />
          </div>
        </div>

        <div className="hidden xl:block">
          <VersionPanel
            versions={versions}
            currentVersion={activeLesson?.current_version ?? 0}
            loading={versionsLoading}
            busyVersion={reverting}
            onRevert={handleRevert}
            className="sticky top-24 h-[calc(100vh-7rem)]"
          />
        </div>
      </div>
      ) : null}

      {view === "blueprint" ? (
        <BlueprintBoard
          courseId={courseId}
          lessons={detail.lessons}
          reloadKey={blueprintTick}
          onOpenLesson={handleOpenLesson}
          onLessonsChanged={handleLessonsChanged}
          onNotice={setNotice}
          onError={setError}
          onProgressRefresh={() => void refreshProgress()}
          onVersionConflict={setConflict}
        />
      ) : null}

      {view === "continuous" ? (
        <CourseReader
          lessons={detail.lessons}
          progress={progress}
          onOpenLesson={handleOpenLesson}
          onGoReader={() => setView("reader")}
        />
      ) : null}

      <AnimatePresence>
        {versionsOpen && (
          <motion.div
            className="fixed inset-0 z-50 xl:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div
              className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
              onClick={() => setVersionsOpen(false)}
            />
            <motion.div
              initial={{ y: 40, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 30, opacity: 0 }}
              transition={{ type: "spring", stiffness: 300, damping: 32 }}
              className="absolute inset-x-3 bottom-3 top-20"
            >
              <VersionPanel
                versions={versions}
                currentVersion={activeLesson?.current_version ?? 0}
                loading={versionsLoading}
                busyVersion={reverting}
                onRevert={handleRevert}
                className="h-full"
              />
              <button
                type="button"
                onClick={() => setVersionsOpen(false)}
                className="absolute -top-1 right-0 grid h-8 w-8 place-items-center rounded-full bg-white/85 text-slate-500 shadow-sm dark:bg-slate-800/85 dark:text-slate-300"
                aria-label="关闭版本面板"
              >
                <X size={15} />
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {notice && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            className="glass fixed bottom-6 left-1/2 z-40 flex max-w-[92vw] -translate-x-1/2 items-center gap-2 rounded-2xl px-4 py-2.5 text-xs text-slate-700 shadow-glass dark:text-slate-200"
          >
            <Check size={14} className="text-emerald-500" />
            {notice}
          </motion.div>
        )}
      </AnimatePresence>

      {view === "reader" && activeLesson ? (
        <button
          type="button"
          onClick={() => setChatOpen(true)}
          disabled={readOnly || lockBlocked}
          title={readOnly ? "当前角色只读" : lockBlocked ? lockReason : "追问 / 修改"}
          aria-label="追问 / 修改"
          className="fab brand-gradient grid h-14 w-14 place-items-center rounded-full text-white shadow-brand transition active:scale-95 disabled:opacity-45 sm:hidden"
        >
          <MessageSquare size={20} />
        </button>
      ) : null}

      <ChatPanel
        open={chatOpen}
        lessonId={activeLesson?.id ?? null}
        lessonTitle={activeLesson?.title ?? ""}
        currentVersion={activeLesson?.current_version ?? 0}
        initialSelection={pendingSelection ?? undefined}
        onSelectionConsumed={() => setPendingSelection(null)}
        onClose={handleCloseChat}
        onApplied={handleChatApplied}
        onNotice={setNotice}
        onVersionConflict={setConflict}
      />

      <ConflictDialog
        conflict={conflict}
        busy={conflictBusy}
        onLoadLatest={handleLoadLatest}
        onRetry={() => void handleRetryConflict()}
        onClose={() => {
          if (!conflictBusy) setConflict(null);
        }}
      />

      <CourseGrantsPanel
        courseId={courseId}
        open={grantsOpen}
        onClose={() => setGrantsOpen(false)}
      />

      <CourseEditDialog
        open={courseEditOpen}
        course={course}
        onClose={() => setCourseEditOpen(false)}
        onSaved={(updated) => {
          setDetail((prev) => (prev ? { ...prev, course: updated } : prev));
          setNotice("课程信息已更新");
        }}
      />

      <ConfirmDialog
        open={courseDeleteOpen}
        title="删除课程"
        description={`将删除「${course.title}」及其全部讲次、版本、对话线与蓝图，且不可恢复。`}
        requireText={course.title}
        busy={courseBusy}
        error={courseDialogError}
        onConfirm={() => void handleCourseDelete()}
        onClose={() => setCourseDeleteOpen(false)}
      />

      <PromptDialog
        open={Boolean(lessonRename)}
        title="重命名讲次"
        label="讲次标题"
        initial={lessonRename?.title ?? ""}
        busy={lessonBusy}
        error={lessonDialogError}
        onConfirm={(value) => void handleLessonRename(value)}
        onClose={() => setLessonRename(null)}
      />

      <ConfirmDialog
        open={Boolean(lessonDelete)}
        title="删除讲次"
        description={`将删除「${lessonDelete?.title ?? ""}」及其全部版本与对话线，且不可恢复。`}
        busy={lessonBusy}
        error={lessonDialogError}
        onConfirm={() => void handleLessonDelete()}
        onClose={() => setLessonDelete(null)}
      />
    </motion.div>
  );
}
