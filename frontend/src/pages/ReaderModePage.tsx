import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  List,
  Loader2,
  Maximize2,
  Minimize2,
  Minus,
  Monitor,
  Moon,
  Plus,
  Sun,
  X,
} from "lucide-react";
import clsx from "clsx";
import { api, type Citation, type GenerationMode } from "@/lib/api";
import MarkdownReader from "@/components/reader/MarkdownReader";
import { useI18n } from "@/i18n/I18nProvider";
import {
  FONT_MAX,
  FONT_MIN,
  WIDTHS,
  applyReaderTheme,
  loadReaderPrefs,
  saveReaderPrefs,
  type ReaderPrefs,
} from "@/lib/readerPrefs";

type Chapter = {
  id: string;
  title: string;
  content: string;
  mode: GenerationMode | "";
  citations: Citation[];
};

const CHIP_BTN =
  "inline-flex h-8 items-center gap-1 rounded-full px-2 text-[11px] font-medium text-slate-500 transition hover:bg-white/70 hover:text-indigo-600 disabled:opacity-35 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-indigo-300";

const ICON_BTN =
  "grid h-8 w-8 place-items-center rounded-full text-slate-500 transition hover:bg-white/70 hover:text-indigo-600 disabled:opacity-35 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-indigo-300";

type TranslateFn = (path: string, vars?: Record<string, string | number>) => string;

function splitSeriesChapters(
  units: {
    id: string;
    title: string;
    content: string;
    order_index: number;
    last_mode?: GenerationMode | "";
  }[],
  t: TranslateFn,
): Chapter[] {
  return [...units]
    .filter((unit) => (unit.content ?? "").trim().length > 0)
    .sort((a, b) => a.order_index - b.order_index)
    .map((unit) => ({
      id: unit.id,
      title: unit.title || t("reader.untitledUnit"),
      content: unit.content,
      mode: unit.last_mode || "",
      citations: [],
    }));
}

export default function ReaderModePage() {
  const { t } = useI18n();
  const { kind = "series", id = "" } = useParams();
  const navigate = useNavigate();
  const isSeries = kind === "series";

  const [title, setTitle] = useState("");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [prefs, setPrefs] = useState<ReaderPrefs>(() => loadReaderPrefs());
  const [progress, setProgress] = useState(0);
  const [activeIndex, setActiveIndex] = useState(0);
  const [tocOpen, setTocOpen] = useState(false);
  const [barHidden, setBarHidden] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  const lastYRef = useRef(0);
  const suppressUntilRef = useRef(0);
  const originalDarkRef = useRef<boolean | null>(null);

  const back = useCallback(() => {
    if (window.history.length > 1) {
      navigate(-1);
      return;
    }
    navigate(isSeries ? `/series/${id}` : `/pieces/${id}`);
  }, [navigate, isSeries, id]);

  useEffect(() => {
    document.title = t("reader.docTitle");
    const previous = document.title;
    return () => {
      document.title = previous;
    };
  }, [t]);

  useEffect(() => {
    originalDarkRef.current = document.documentElement.classList.contains("dark");
    return () => {
      if (originalDarkRef.current !== null) {
        document.documentElement.classList.toggle("dark", originalDarkRef.current);
      }
    };
  }, []);

  useEffect(() => {
    applyReaderTheme(prefs.theme);
    let mq: MediaQueryList | null = null;
    const handler = () => {
      if (prefs.theme === "system") applyReaderTheme("system");
    };
    try {
      mq = window.matchMedia("(prefers-color-scheme: dark)");
      mq.addEventListener("change", handler);
    } catch {
      mq = null;
    }
    return () => mq?.removeEventListener("change", handler);
  }, [prefs.theme]);

  useEffect(() => {
    saveReaderPrefs(prefs);
  }, [prefs]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    setChapters([]);
    setActiveIndex(0);

    const load = async () => {
      if (!id) throw new Error(t("reader.missingId"));
      if (isSeries) {
        const data = await api.getSeries(id);
        if (!alive) return;
        setTitle(data.series.title);
        setChapters(splitSeriesChapters(data.units, t));
        return;
      }
      const data = await api.getPiece(id);
      if (!alive) return;
      setTitle(data.title);
      const sections = (data.outline ?? [])
        .filter((section) => (section.content ?? "").trim().length > 0)
        .map((section, index) => ({
          id: section.id || `section-${index}`,
          title: section.title || t("reader.sectionNo", { index: index + 1 }),
          content: section.content,
          mode: (data.last_mode as GenerationMode) || "",
          citations: data.citations ?? [],
        }));
      if (sections.length === 0 && (data.content ?? "").trim()) {
        sections.push({
          id: "full",
          title: data.title,
          content: data.content,
          mode: (data.last_mode as GenerationMode) || "",
          citations: data.citations ?? [],
        });
      }
      setChapters(sections);
    };

    load()
      .catch((err) => {
        if (alive)
          setError(err instanceof Error ? err.message : t("reader.loadFailed"));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [id, isSeries, t]);

  useEffect(() => {
    if (!isSeries) return;
    const pending = chapters.filter((chapter) => chapter.citations.length === 0);
    if (pending.length === 0) return;
    let alive = true;
    const run = async () => {
      for (const chapter of pending) {
        try {
          const data = await api.listVersions(chapter.id);
          const record = data.versions.find((item) => item.version === data.current_version);
          if (!alive || !record) continue;
          setChapters((prev) =>
            prev.map((item) =>
              item.id === chapter.id
                ? {
                    ...item,
                    citations: record.citations ?? [],
                    mode: item.mode || record.mode || "",
                  }
                : item,
            ),
          );
        } catch {
          continue;
        }
      }
    };
    void run();
    return () => {
      alive = false;
    };
  }, [isSeries, chapters]);

  useEffect(() => {
    const onScroll = () => {
      const doc = document.documentElement;
      const max = doc.scrollHeight - window.innerHeight;
      const ratio = max > 0 ? window.scrollY / max : 0;
      setProgress(Math.min(100, Math.max(0, Math.round(ratio * 100))));

      const y = window.scrollY;
      if (Date.now() < suppressUntilRef.current) {
        lastYRef.current = y;
        setBarHidden(false);
        return;
      }
      const delta = y - lastYRef.current;
      if (y < 72) {
        setBarHidden(false);
      } else if (delta > 6) {
        setBarHidden(true);
      } else if (delta < -6) {
        setBarHidden(false);
      }
      lastYRef.current = y;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (chapters.length === 0) return;
    const nodes = Array.from(document.querySelectorAll<HTMLElement>("[data-chapter-index]"));
    if (nodes.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const index = Number((entry.target as HTMLElement).dataset.chapterIndex ?? "0");
          if (!Number.isNaN(index)) setActiveIndex(index);
        });
      },
      { rootMargin: "-64px 0px -70% 0px", threshold: 0 },
    );
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [chapters]);

  const goto = useCallback((index: number) => {
    const target = document.querySelector<HTMLElement>(`[data-chapter-index="${index}"]`);
    suppressUntilRef.current = Date.now() + 900;
    setBarHidden(false);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveIndex(index);
  }, []);

  const toggleFullscreen = useCallback(async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await document.documentElement.requestFullscreen();
      }
    } catch {
      return;
    }
  }, []);

  useEffect(() => {
    const onChange = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const last = chapters.length - 1;
      if (event.key === "ArrowLeft" || event.key === "[") {
        event.preventDefault();
        goto(Math.max(0, activeIndex - 1));
      } else if (event.key === "ArrowRight" || event.key === "]") {
        event.preventDefault();
        goto(Math.min(last, activeIndex + 1));
      } else if (event.key === "Escape") {
        if (tocOpen) {
          setTocOpen(false);
          return;
        }
        back();
      } else if (event.key === "f") {
        void toggleFullscreen();
      } else if (event.key === "t") {
        setPrefs((prev) => ({
          ...prev,
          theme: prev.theme === "system" ? "light" : prev.theme === "light" ? "dark" : "system",
        }));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeIndex, chapters.length, goto, back, tocOpen, toggleFullscreen]);

  const stepFont = useCallback((delta: number) => {
    setPrefs((prev) => ({
      ...prev,
      fontSize: Math.min(FONT_MAX, Math.max(FONT_MIN, prev.fontSize + delta)),
    }));
  }, []);

  const cycleWidth = useCallback(() => {
    setPrefs((prev) => ({
      ...prev,
      width: WIDTHS[(WIDTHS.indexOf(prev.width) + 1) % WIDTHS.length],
    }));
  }, []);

  const cycleTheme = useCallback(() => {
    setPrefs((prev) => ({
      ...prev,
      theme: prev.theme === "system" ? "light" : prev.theme === "light" ? "dark" : "system",
    }));
  }, []);

  const themeIcon = useMemo(() => {
    if (prefs.theme === "light") return <Sun size={15} />;
    if (prefs.theme === "dark") return <Moon size={15} />;
    return <Monitor size={15} />;
  }, [prefs.theme]);

  const activeChapter = chapters[activeIndex];

  return (
    <div className="relative min-h-screen">
      <div className="fixed inset-x-0 top-0 z-50 h-[2px] bg-transparent">
        <div
          className="brand-gradient h-full transition-[width] duration-150 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      <header
        className={clsx(
          "fixed inset-x-0 top-0 z-40 transition-transform duration-300 ease-out",
          barHidden ? "-translate-y-full" : "translate-y-0",
        )}
      >
        <div className="glass border-x-0 border-t-0 px-2 shadow-[0_16px_36px_-30px_rgba(15,23,42,0.65)] sm:px-4">
          <div className="mx-auto flex h-12 w-full max-w-[1180px] items-center gap-1">
            <button type="button" onClick={back} className={clsx(CHIP_BTN, "shrink-0")} aria-label={t("reader.back")}>
              <ArrowLeft size={15} />
              <span className="hidden sm:inline">{t("reader.back")}</span>
            </button>
            <span className="mx-1 hidden h-5 w-px shrink-0 bg-slate-300/60 dark:bg-white/10 sm:block" />
            <p className="min-w-0 flex-1 truncate text-[12.5px] font-medium tracking-tight text-slate-700 dark:text-slate-200">
              {title || (loading ? t("reader.loadingTitle") : t("reader.readerMode"))}
            </p>
            <div className="flex shrink-0 items-center gap-0.5">
              <button
                type="button"
                onClick={() => setTocOpen(true)}
                className={CHIP_BTN}
                aria-label={t("reader.toc")}
              >
                <List size={15} />
                <span className="hidden sm:inline">{t("reader.toc")}</span>
              </button>
              <span className="mx-1 hidden h-5 w-px bg-slate-300/60 dark:bg-white/10 sm:block" />
              <button
                type="button"
                onClick={() => stepFont(-1)}
                disabled={prefs.fontSize <= FONT_MIN}
                className={ICON_BTN}
                aria-label={t("reader.decreaseFont")}
              >
                <Minus size={15} />
              </button>
              <span className="w-7 text-center text-[11px] tabular-nums text-slate-500 dark:text-slate-400">
                {prefs.fontSize}
              </span>
              <button
                type="button"
                onClick={() => stepFont(1)}
                disabled={prefs.fontSize >= FONT_MAX}
                className={ICON_BTN}
                aria-label={t("reader.increaseFont")}
              >
                <Plus size={15} />
              </button>
              <button
                type="button"
                onClick={cycleWidth}
                className={clsx(CHIP_BTN, "hidden md:inline-flex")}
                title={t("reader.switchWidth")}
              >
                {t("reader.lineWidth", { width: prefs.width })}
              </button>
              <button
                type="button"
                onClick={() => setPrefs((prev) => ({ ...prev, citations: !prev.citations }))}
                className={clsx(
                  CHIP_BTN,
                  "hidden md:inline-flex",
                  prefs.citations
                    ? "text-indigo-600 dark:text-indigo-300"
                    : "text-slate-400 line-through dark:text-slate-500",
                )}
                title={
                  prefs.citations
                    ? t("reader.hideCitations")
                    : t("reader.showCitations")
                }
              >
                {t("reader.citationsLabel")}
              </button>
              <button
                type="button"
                onClick={cycleTheme}
                className={ICON_BTN}
                aria-label={t("reader.themeTitle", {
                  theme: t(`reader.theme${prefs.theme[0].toUpperCase()}${prefs.theme.slice(1)}`),
                })}
                title={t("reader.themeTitle", {
                  theme: t(`reader.theme${prefs.theme[0].toUpperCase()}${prefs.theme.slice(1)}`),
                })}
              >
                {themeIcon}
              </button>
              <button
                type="button"
                onClick={() => void toggleFullscreen()}
                className={clsx(ICON_BTN, "hidden sm:grid")}
                aria-label={
                  fullscreen ? t("reader.exitFullscreen") : t("reader.fullscreen")
                }
                title={
                  fullscreen ? t("reader.exitFullscreen") : t("reader.fullscreen")
                }
              >
                {fullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
              </button>
              <span className="ml-1 hidden w-9 text-right text-[11px] tabular-nums text-slate-500 dark:text-slate-400 sm:block">
                {progress}%
              </span>
            </div>
          </div>
        </div>
      </header>

      <main
        className="mx-auto w-full px-5 pb-24 pt-24 font-sans sm:px-6"
        style={{ maxWidth: prefs.width }}
      >
        {loading ? (
          <p className="flex items-center gap-2 text-[12px] text-slate-400">
            <Loader2 size={13} className="animate-spin" />
            {t("reader.loadingContent")}
          </p>
        ) : error ? (
          <div className="glass rounded-3xl p-6 text-center shadow-glass">
            <p className="text-[13px] text-rose-600 dark:text-rose-300">{error}</p>
            <button type="button" onClick={back} className="btn btn-primary mt-4">
              <ArrowLeft size={14} />
              {t("reader.back")}
            </button>
          </div>
        ) : chapters.length === 0 ? (
          <div className="glass rounded-3xl p-8 text-center shadow-glass">
            <p className="text-[13px] text-slate-500 dark:text-slate-400">
              {t("reader.emptyWork")}
            </p>
            <button type="button" onClick={back} className="btn btn-quiet mt-4">
              <ArrowLeft size={14} />
              {t("reader.back")}
            </button>
          </div>
        ) : (
          <>
            {chapters.map((chapter, index) => (
              <section
                key={`${chapter.id}-${index}`}
                data-chapter-index={index}
                className="scroll-mt-16 pt-1 first:pt-0"
              >
                <p className="text-[10.5px] font-medium uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">
                  {t("reader.chapterMeta", {
                    index: index + 1,
                    total: chapters.length,
                  })}
                </p>
                <h1 className="mt-2 text-xl font-semibold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
                  {chapter.title}
                </h1>
                <div
                  className="reader-surface mt-6"
                  style={{ ["--rm-font-size" as string]: `${prefs.fontSize}px` }}
                >
                  <MarkdownReader
                    content={chapter.content}
                    citations={chapter.citations}
                    mode={chapter.mode}
                    enableAsk={false}
                    showCitations={prefs.citations}
                  />
                </div>
                {index < chapters.length - 1 ? (
                  <div className="mt-14 flex items-center justify-center gap-3">
                    <span className="h-px w-16 bg-slate-300/60 dark:bg-white/10" />
                    <span className="h-1.5 w-1.5 rounded-full bg-indigo-400/60" />
                    <span className="h-px w-16 bg-slate-300/60 dark:bg-white/10" />
                  </div>
                ) : null}
              </section>
            ))}

            <nav className="mt-16 flex items-center justify-between gap-3 border-t border-slate-200/70 pt-6 dark:border-white/10">
              <button
                type="button"
                onClick={() => goto(Math.max(0, activeIndex - 1))}
                disabled={activeIndex <= 0}
                className="btn btn-quiet max-w-[46%] justify-start whitespace-nowrap"
              >
                <ChevronLeft size={14} />
                <span className="truncate">{t("reader.prevChapter")}</span>
              </button>
              <span className="hidden min-w-0 flex-1 truncate text-center text-[11px] text-slate-400 dark:text-slate-500 sm:block">
                {activeChapter
                  ? t("reader.chapterProgress", {
                      index: activeIndex + 1,
                      total: chapters.length,
                      title: activeChapter.title,
                    })
                  : ""}
              </span>
              <button
                type="button"
                onClick={() => goto(Math.min(chapters.length - 1, activeIndex + 1))}
                disabled={activeIndex >= chapters.length - 1}
                className="btn btn-quiet max-w-[46%] justify-end whitespace-nowrap"
              >
                <span className="truncate">{t("reader.nextChapter")}</span>
                <ChevronRight size={14} />
              </button>
            </nav>

            <p className="mt-6 text-center text-[10.5px] text-slate-400 dark:text-slate-500">
              {t("reader.keyboardHint")}
            </p>
          </>
        )}
      </main>

      <AnimatePresence>
        {tocOpen ? (
          <motion.div
            className="fixed inset-0 z-50"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div
              className="absolute inset-0 bg-slate-900/35 backdrop-blur-sm"
              onClick={() => setTocOpen(false)}
            />
            <motion.aside
              initial={{ x: 340 }}
              animate={{ x: 0 }}
              exit={{ x: 340 }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              className="absolute inset-y-0 right-0 w-[320px] max-w-[86vw] p-3"
            >
              <div className="glass flex h-full flex-col rounded-3xl p-4 shadow-glass">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                      {t("reader.toc")}
                    </p>
                    <p className="mt-0.5 text-[12px] font-medium text-slate-700 dark:text-slate-200">
                      {t("reader.tocProgress", {
                        count: chapters.length,
                        percent: progress,
                      })}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setTocOpen(false)}
                    className={ICON_BTN}
                    aria-label={t("reader.closeToc")}
                  >
                    <X size={15} />
                  </button>
                </div>
                <div className="no-scrollbar mt-3 flex-1 space-y-1 overflow-y-auto pr-1">
                  {chapters.map((chapter, index) => {
                    const active = index === activeIndex;
                    return (
                      <button
                        key={`${chapter.id}-toc-${index}`}
                        type="button"
                        onClick={() => {
                          goto(index);
                          setTocOpen(false);
                        }}
                        className={clsx(
                          "flex w-full items-start gap-2 rounded-xl px-2.5 py-2 text-left transition",
                          active
                            ? "bg-indigo-500/12 text-indigo-700 dark:bg-indigo-400/15 dark:text-indigo-200"
                            : "text-slate-600 hover:bg-white/55 dark:text-slate-300 dark:hover:bg-white/10",
                        )}
                      >
                        <span
                          className={clsx(
                            "mt-0.5 w-5 shrink-0 text-right text-[10px] tabular-nums",
                            active ? "text-indigo-500 dark:text-indigo-300" : "text-slate-400 dark:text-slate-500",
                          )}
                        >
                          {index + 1}
                        </span>
                        <span className="min-w-0 flex-1 text-[12.5px] leading-snug">{chapter.title}</span>
                        {active ? (
                          <ArrowRight size={12} className="mt-0.5 shrink-0 text-indigo-500 dark:text-indigo-300" />
                        ) : null}
                      </button>
                    );
                  })}
                </div>
                <div className="mt-3 space-y-2 border-t border-white/50 pt-3 dark:border-white/10">
                  <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
                    <span>{t("reader.fontSize")}</span>
                    <span className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => stepFont(-1)}
                        disabled={prefs.fontSize <= FONT_MIN}
                        className={ICON_BTN}
                        aria-label={t("reader.decreaseFont")}
                      >
                        <Minus size={14} />
                      </button>
                      <span className="w-6 text-center tabular-nums">{prefs.fontSize}</span>
                      <button
                        type="button"
                        onClick={() => stepFont(1)}
                        disabled={prefs.fontSize >= FONT_MAX}
                        className={ICON_BTN}
                        aria-label={t("reader.increaseFont")}
                      >
                        <Plus size={14} />
                      </button>
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
                    <span>{t("reader.lineWidthLabel")}</span>
                    <button type="button" onClick={cycleWidth} className={CHIP_BTN}>
                      {prefs.width}px
                    </button>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
                    <span>{t("reader.theme")}</span>
                    <button type="button" onClick={cycleTheme} className={CHIP_BTN}>
                      {themeIcon}
                      {t(`reader.theme${prefs.theme[0].toUpperCase()}${prefs.theme.slice(1)}`)}
                    </button>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
                    <span>{t("reader.citationsToggle")}</span>
                    <button
                      type="button"
                      onClick={() => setPrefs((prev) => ({ ...prev, citations: !prev.citations }))}
                      className={clsx(
                        CHIP_BTN,
                        prefs.citations ? "text-indigo-600 dark:text-indigo-300" : "text-slate-400",
                      )}
                    >
                      {prefs.citations ? t("reader.show") : t("reader.hide")}
                    </button>
                  </div>
                </div>
              </div>
            </motion.aside>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
