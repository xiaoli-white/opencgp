import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import clsx from "clsx";
import {
  ArrowRight,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Layers,
  ScrollText,
} from "lucide-react";
import {
  api,
  type Citation,
  type CourseProgress,
  type GenerationMode,
  type Lesson,
} from "@/lib/api";
import { contentLength, modeLabel } from "@/lib/format";
import MarkdownReader from "@/components/reader/MarkdownReader";
import StatusBadge, { statusDotClass } from "@/components/course/StatusBadge";

type LessonMeta = {
  citations: Citation[];
  mode: GenerationMode | "";
};

type CourseReaderProps = {
  lessons: Lesson[];
  progress: CourseProgress | null;
  onOpenLesson: (lessonId: string) => void;
  onGoReader: () => void;
};

export default function CourseReader({
  lessons,
  progress,
  onOpenLesson,
  onGoReader,
}: CourseReaderProps) {
  const readable = useMemo(
    () =>
      lessons
        .filter((lesson) => Boolean(lesson.content))
        .sort((a, b) => a.order_index - b.order_index),
    [lessons],
  );

  const [metaMap, setMetaMap] = useState<Record<string, LessonMeta>>({});
  const [activeId, setActiveId] = useState<string>(readable[0]?.id ?? "");
  const [ratio, setRatio] = useState(0);
  const visibleRef = useRef<Set<string>>(new Set());

  const metaKey = readable
    .map((lesson) => `${lesson.id}:${lesson.current_version}`)
    .join("|");

  useEffect(() => {
    if (readable.length === 0) {
      setMetaMap({});
      return;
    }
    let cancelled = false;
    Promise.all(
      readable.map(async (lesson) => {
        try {
          const data = await api.listVersions(lesson.id);
          const current =
            data.versions.find(
              (version) => version.version === lesson.current_version,
            ) ?? data.versions[0];
          const meta: LessonMeta = {
            citations: current?.citations ?? [],
            mode: current?.mode ?? lesson.last_mode ?? "",
          };
          return [lesson.id, meta] as const;
        } catch {
          const fallback: LessonMeta = {
            citations: [],
            mode: lesson.last_mode ?? "",
          };
          return [lesson.id, fallback] as const;
        }
      }),
    ).then((entries) => {
      if (!cancelled) setMetaMap(Object.fromEntries(entries));
    });
    return () => {
      cancelled = true;
    };
  }, [metaKey, readable]);

  useEffect(() => {
    if (readable.length > 0 && !readable.some((l) => l.id === activeId)) {
      setActiveId(readable[0].id);
    }
  }, [readable, activeId]);

  useEffect(() => {
    const onScroll = () => {
      const height =
        document.documentElement.scrollHeight - window.innerHeight;
      if (height <= 0) {
        setRatio(0);
        return;
      }
      setRatio(Math.min(1, Math.max(0, window.scrollY / height)));
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  useEffect(() => {
    if (readable.length === 0) return;
    const visible = visibleRef.current;
    visible.clear();
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const id = entry.target.getAttribute("data-lesson-id");
          if (!id) return;
          if (entry.isIntersecting) {
            visible.add(id);
          } else {
            visible.delete(id);
          }
        });
        const first = readable.find((lesson) => visible.has(lesson.id));
        if (first) setActiveId(first.id);
      },
      { rootMargin: "-100px 0px -55% 0px", threshold: 0 },
    );
    readable.forEach((lesson) => {
      const element = document.getElementById(`lesson-${lesson.id}`);
      if (element) observer.observe(element);
    });
    return () => observer.disconnect();
  }, [metaKey, readable]);

  const jumpTo = (lessonId: string) => {
    const element = document.getElementById(`lesson-${lessonId}`);
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "start" });
      setActiveId(lessonId);
    }
  };

  if (readable.length === 0) {
    return (
      <div className="glass rounded-3xl p-10 text-center shadow-glass">
        <div className="brand-gradient mx-auto grid h-12 w-12 place-items-center rounded-2xl text-white shadow-brand">
          <ScrollText size={20} />
        </div>
        <p className="mt-4 text-sm font-medium text-slate-700 dark:text-slate-200">
          还没有可连续阅读的正文
        </p>
        <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          连续阅读会把所有已有正文的讲次按顺序串起来。先去阅读视图生成至少一讲正文。
        </p>
        <button type="button" onClick={onGoReader} className="btn btn-primary mt-4">
          <BookOpen size={14} />
          去阅读视图生成
        </button>
      </div>
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[230px_minmax(0,1fr)]">
      <aside className="glass hidden max-h-[calc(100vh-7rem)] flex-col rounded-3xl p-3.5 shadow-glass lg:sticky lg:top-24 lg:flex">
        <div className="px-1">
          <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
            <Layers size={11} />
            连续阅读
          </p>
          <p className="mt-0.5 text-[13px] font-medium text-slate-700 dark:text-slate-200">
            {readable.length} 讲 ·{" "}
            {progress ? `已通过 ${progress.approved}/${progress.total}` : "阅读中"}
          </p>
        </div>

        <div className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-200/80 dark:bg-white/10">
          <motion.div
            animate={{ width: `${Math.round(ratio * 100)}%` }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="brand-gradient h-full rounded-full"
          />
        </div>

        <nav className="no-scrollbar mt-3 flex-1 space-y-0.5 overflow-y-auto pr-0.5">
          {readable.map((lesson) => {
            const active = lesson.id === activeId;
            return (
              <button
                key={lesson.id}
                type="button"
                onClick={() => jumpTo(lesson.id)}
                className={clsx(
                  "flex w-full items-start gap-2 rounded-xl px-2 py-1.5 text-left transition",
                  active
                    ? "bg-indigo-500/12 dark:bg-indigo-400/15"
                    : "hover:bg-white/60 dark:hover:bg-white/[0.06]",
                )}
              >
                <span
                  className={clsx(
                    "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                    statusDotClass(lesson.status),
                  )}
                />
                <span className="min-w-0 flex-1">
                  <span
                    className={clsx(
                      "block truncate text-[12px] font-medium",
                      active
                        ? "text-indigo-700 dark:text-indigo-200"
                        : "text-slate-600 dark:text-slate-300",
                    )}
                  >
                    {lesson.order_index}. {lesson.title}
                  </span>
                  <span className="mt-0.5 block text-[10px] text-slate-400 dark:text-slate-500">
                    {contentLength(lesson.content)} 字
                  </span>
                </span>
              </button>
            );
          })}
        </nav>

        <p className="mt-2 border-t border-slate-200/70 px-1 pt-2 text-[10px] leading-relaxed text-slate-400 dark:border-white/10 dark:text-slate-500">
          滚动进度 {Math.round(ratio * 100)}%
        </p>
      </aside>

      <div className="min-w-0 space-y-5">
        {readable.map((lesson, index) => {
          const meta = metaMap[lesson.id];
          const citations = meta?.citations ?? [];
          const mode = meta?.mode ?? lesson.last_mode ?? "";
          const previous = readable[index - 1];
          const next = readable[index + 1];
          return (
            <motion.section
              key={lesson.id}
              id={`lesson-${lesson.id}`}
              data-lesson-id={lesson.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              className="glass scroll-mt-24 rounded-3xl p-5 shadow-glass sm:p-8"
            >
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200/70 pb-4 dark:border-white/10">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400 dark:text-slate-500">
                    <span>第 {lesson.order_index} 讲</span>
                    <span>·</span>
                    <span>v{lesson.current_version}</span>
                    <StatusBadge status={lesson.status} />
                    <span
                      className={clsx(
                        "rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                        mode === "loose"
                          ? "bg-amber-400/20 text-amber-700 ring-1 ring-amber-400/30 dark:bg-amber-300/12 dark:text-amber-300 dark:ring-amber-300/20"
                          : "bg-indigo-500/12 text-indigo-600 ring-1 ring-indigo-400/20 dark:bg-indigo-400/14 dark:text-indigo-300 dark:ring-indigo-300/20",
                      )}
                    >
                      {modeLabel(mode)}模式
                    </span>
                  </div>
                  <h2 className="mt-1 text-xl font-semibold tracking-tight text-slate-900 dark:text-white sm:text-[22px]">
                    {lesson.title}
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => onOpenLesson(lesson.id)}
                  className="btn-quiet"
                >
                  单独阅读
                  <ArrowRight size={11} />
                </button>
              </div>

              {lesson.learning_objectives.length > 0 ? (
                <ul className="mt-4 flex flex-wrap gap-1.5">
                  {lesson.learning_objectives.map((objective) => (
                    <li key={objective} className="chip-muted">
                      {objective}
                    </li>
                  ))}
                </ul>
              ) : null}

              <div className="mt-5">
                <MarkdownReader
                  content={lesson.content}
                  citations={citations}
                  mode={mode}
                />
              </div>

              <div className="mt-7 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200/70 pt-4 dark:border-white/10">
                <span className="flex items-center gap-1.5 text-[10.5px] text-slate-400 dark:text-slate-500">
                  <Clock3 size={11} />
                  {contentLength(lesson.content)} 字 · {citations.length} 条引用
                </span>
                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => previous && jumpTo(previous.id)}
                    disabled={!previous}
                    className="btn btn-ghost !px-3 !py-1.5 text-[11px] disabled:opacity-40"
                  >
                    <ChevronLeft size={12} />
                    上一讲
                  </button>
                  <button
                    type="button"
                    onClick={() => next && jumpTo(next.id)}
                    disabled={!next}
                    className="btn btn-ghost !px-3 !py-1.5 text-[11px] disabled:opacity-40"
                  >
                    下一讲
                    <ChevronRight size={12} />
                  </button>
                  <button
                    type="button"
                    onClick={() => onOpenLesson(lesson.id)}
                    className="btn btn-primary !px-3 !py-1.5 text-[11px]"
                  >
                    <BookOpen size={12} />
                    回到该讲单独阅读
                  </button>
                </div>
              </div>
            </motion.section>
          );
        })}
      </div>
    </div>
  );
}
