"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  Check,
  ChevronRight,
  History,
  Loader2,
  MessageSquare,
  Network,
  Plus,
  ScrollText,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import clsx from "clsx";
import {
  api,
  type CourseDetail,
  type CourseProgress,
  type GenerationMode,
  type LessonVersion,
} from "@/lib/api";
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
import StatusBadge from "@/components/course/StatusBadge";

type WorkspaceView = "reader" | "blueprint" | "continuous";

const VIEWS: { value: WorkspaceView; label: string; icon: typeof BookOpen }[] = [
  { value: "reader", label: "阅读", icon: BookOpen },
  { value: "blueprint", label: "蓝图", icon: Network },
  { value: "continuous", label: "连续阅读", icon: ScrollText },
];

export default function CourseWorkspace({ courseId }: { courseId: string }) {
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
  const [pendingSelection, setPendingSelection] = useState<string | null>(null);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [versionTick, setVersionTick] = useState(0);
  const [view, setView] = useState<WorkspaceView>("reader");
  const [progress, setProgress] = useState<CourseProgress | null>(null);
  const [blueprintTick, setBlueprintTick] = useState(0);

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

  const runGenerate = async () => {
    if (!activeLesson || generating) return;
    setGenerating(true);
    setError("");
    try {
      const result = await api.generateLesson(activeLesson.id, {
        topic: topic.trim() || undefined,
        top_k: topK,
        mode: generateMode,
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
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      setGenerating(false);
    }
  };

  const handleRevert = async (version: number) => {
    if (!activeLesson) return;
    setReverting(version);
    setError("");
    try {
      await api.revertLesson(activeLesson.id, version, `revert to v${version}`);
      await loadCourse(activeLesson.id);
      setVersionTick((tick) => tick + 1);
      setNotice(`已回滚：基于 v${version} 生成新版本，历史仍可追溯`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "回滚失败");
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
        <Link href="/" className="btn btn-ghost mt-5">
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
              href="/"
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
          <button
            type="button"
            onClick={() => setChatOpen(true)}
            disabled={!activeLesson}
            className="btn btn-primary"
          >
            <MessageSquare size={14} />
            追问 / 修改
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex items-center gap-0.5 rounded-full border border-slate-200/70 bg-white/50 p-0.5 shadow-[0_10px_26px_-24px_rgba(99,102,241,0.9)] backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.05]">
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
        <aside className="glass flex max-h-[calc(100vh-7rem)] flex-col rounded-3xl p-3.5 shadow-glass lg:sticky lg:top-24">
          <div className="flex items-center justify-between px-1">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                课程大纲
              </p>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
                {detail.lesson_count} 讲
              </p>
            </div>
            <button
              type="button"
              onClick={() => setFormOpen((value) => !value)}
              className="grid h-7 w-7 place-items-center rounded-full bg-indigo-500/10 text-indigo-600 transition hover:bg-indigo-500/20 dark:text-indigo-300"
              aria-label="新增讲次"
            >
              <Plus size={14} />
            </button>
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
              detail.lessons.map((lesson) => {
                const active = lesson.id === activeId;
                return (
                  <button
                    key={lesson.id}
                    type="button"
                    onClick={() => {
                      setActiveId(lesson.id);
                      setGenerateOpen(false);
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
                    <ChevronRight
                      size={13}
                      className={clsx(
                        "shrink-0 transition",
                        active
                          ? "text-indigo-500 dark:text-indigo-300"
                          : "text-slate-300 group-hover:text-indigo-400 dark:text-slate-600",
                      )}
                    />
                  </button>
                );
              })
            )}
          </div>
        </aside>

        <div className="min-w-0 space-y-4">
          {activeLesson ? (
            <article className="glass rounded-3xl p-5 shadow-glass sm:p-8">
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
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setGenerateOpen((value) => !value)}
                    disabled={generating}
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
                </div>
              </div>

              <ReviewControls
                lesson={activeLesson}
                progress={progress}
                onReviewed={refreshWorkspace}
                onNotice={setNotice}
                onError={setError}
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
                          onClick={runGenerate}
                          disabled={generating}
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

              <div className="mt-6">
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
                        onClick={() => setGenerateOpen(true)}
                        className="btn btn-primary"
                      >
                        <Sparkles size={14} />
                        生成正文
                      </button>
                      <Link href="/kb" className="btn btn-ghost">
                        先上传资料
                      </Link>
                    </div>
                  </div>
                )}
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
      />
    </motion.div>
  );
}
