import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import clsx from "clsx";
import {
  ArrowRight,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Layers,
  List,
  ScrollText,
  X,
} from "lucide-react";
import {
  api,
  type Citation,
  type SeriesProgress,
  type GenerationMode,
  type Unit,
} from "@/lib/api";
import { contentLength } from "@/lib/format";
import { modeLabel } from "@/i18n/labels";
import { useI18n } from "@/i18n/I18nProvider";
import MarkdownReader from "@/components/reader/MarkdownReader";
import StatusBadge, { statusDotClass } from "@/components/series/StatusBadge";

type UnitMeta = {
  citations: Citation[];
  mode: GenerationMode | "";
};

type SeriesReaderProps = {
  units: Unit[];
  progress: SeriesProgress | null;
  onOpenUnit: (unitId: string) => void;
  onGoReader: () => void;
};

export default function SeriesReader({
  units,
  progress,
  onOpenUnit,
  onGoReader,
}: SeriesReaderProps) {
  const { t } = useI18n();
  const readable = useMemo(
    () =>
      units
        .filter((unit) => Boolean(unit.content))
        .sort((a, b) => a.order_index - b.order_index),
    [units],
  );

  const [tocOpen, setTocOpen] = useState(false);
  const [metaMap, setMetaMap] = useState<Record<string, UnitMeta>>({});
  const [activeId, setActiveId] = useState<string>(readable[0]?.id ?? "");
  const [ratio, setRatio] = useState(0);
  const visibleRef = useRef<Set<string>>(new Set());

  const metaKey = readable
    .map((unit) => `${unit.id}:${unit.current_version}`)
    .join("|");

  useEffect(() => {
    if (readable.length === 0) {
      setMetaMap({});
      return;
    }
    let cancelled = false;
    Promise.all(
      readable.map(async (unit) => {
        try {
          const data = await api.listVersions(unit.id);
          const current =
            data.versions.find(
              (version) => version.version === unit.current_version,
            ) ?? data.versions[0];
          const meta: UnitMeta = {
            citations: current?.citations ?? [],
            mode: current?.mode ?? unit.last_mode ?? "",
          };
          return [unit.id, meta] as const;
        } catch {
          const fallback: UnitMeta = {
            citations: [],
            mode: unit.last_mode ?? "",
          };
          return [unit.id, fallback] as const;
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
          const id = entry.target.getAttribute("data-unit-id");
          if (!id) return;
          if (entry.isIntersecting) {
            visible.add(id);
          } else {
            visible.delete(id);
          }
        });
        const first = readable.find((unit) => visible.has(unit.id));
        if (first) setActiveId(first.id);
      },
      { rootMargin: "-100px 0px -55% 0px", threshold: 0 },
    );
    readable.forEach((unit) => {
      const element = document.getElementById(`unit-${unit.id}`);
      if (element) observer.observe(element);
    });
    return () => observer.disconnect();
  }, [metaKey, readable]);

  const jumpTo = (unitId: string) => {
    const element = document.getElementById(`unit-${unitId}`);
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "start" });
      setActiveId(unitId);
    }
  };

  if (readable.length === 0) {
    return (
      <div className="glass rounded-3xl p-10 text-center shadow-glass">
        <div className="brand-gradient mx-auto grid h-12 w-12 place-items-center rounded-2xl text-white shadow-brand">
          <ScrollText size={20} />
        </div>
        <p className="mt-4 text-sm font-medium text-slate-700 dark:text-slate-200">
          {t("reader.emptyTitle")}
        </p>
        <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          {t("reader.emptyBody")}
        </p>
        <button type="button" onClick={onGoReader} className="btn btn-primary mt-4">
          <BookOpen size={14} />
          {t("reader.goGenerate")}
        </button>
      </div>
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[230px_minmax(0,1fr)]">
      <div className="flex items-center justify-between gap-2 lg:hidden">
        <span className="chip-muted">
          <ScrollText size={11} />
          {t("reader.continuousBadge", { count: readable.length })}
        </span>
        <button
          type="button"
          onClick={() => setTocOpen(true)}
          className="btn btn-ghost shrink-0"
        >
          <List size={14} />
          {t("reader.toc")}
        </button>
      </div>
      <AnimatePresence>
        {tocOpen && (
          <motion.div
            className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-sm lg:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setTocOpen(false)}
          />
        )}
      </AnimatePresence>
      <aside
        className={clsx(
          "glass no-scrollbar flex-col rounded-3xl p-3.5 shadow-glass lg:sticky lg:top-24 lg:flex lg:max-h-[calc(100vh-7rem)]",
          "max-lg:fixed max-lg:inset-y-0 max-lg:left-0 max-lg:z-50 max-lg:m-3 max-lg:w-[min(300px,calc(100vw-1.5rem))] max-lg:max-h-none max-lg:overflow-y-auto",
          tocOpen ? "flex" : "hidden",
        )}
      >
        <div className="flex items-start justify-between gap-2 px-1">
          <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
            <Layers size={11} />
            {t("reader.continuous")}
          </p>
          <p className="mt-0.5 text-[13px] font-medium text-slate-700 dark:text-slate-200">
            {t("reader.tocSummary", {
              count: readable.length,
              progress: progress
                ? t("reader.approvedProgress", {
                    approved: progress.approved,
                    total: progress.total,
                  })
                : t("reader.reading"),
            })}
          </p>
          </div>
          <button
            type="button"
            onClick={() => setTocOpen(false)}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-slate-400 transition hover:bg-white/70 hover:text-slate-600 dark:hover:bg-white/10 lg:hidden"
            aria-label={t("reader.closeToc")}
          >
            <X size={16} />
          </button>
        </div>

        <div className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-200/80 dark:bg-white/10">
          <motion.div
            animate={{ width: `${Math.round(ratio * 100)}%` }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="brand-gradient h-full rounded-full"
          />
        </div>

        <nav className="no-scrollbar mt-3 flex-1 space-y-0.5 overflow-y-auto pr-0.5">
          {readable.map((unit) => {
            const active = unit.id === activeId;
            return (
              <button
                key={unit.id}
                type="button"
                onClick={() => {
                  jumpTo(unit.id);
                  setTocOpen(false);
                }}
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
                    statusDotClass(unit.status),
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
                    {unit.order_index}. {unit.title}
                  </span>
                  <span className="mt-0.5 block text-[10px] text-slate-400 dark:text-slate-500">
                    {t("reader.chars", {
                      count: contentLength(unit.content),
                    })}
                  </span>
                </span>
              </button>
            );
          })}
        </nav>

        <p className="mt-2 border-t border-slate-200/70 px-1 pt-2 text-[10px] leading-relaxed text-slate-400 dark:border-white/10 dark:text-slate-500">
          {t("reader.scrollProgress", { percent: Math.round(ratio * 100) })}
        </p>
      </aside>

      <div className="min-w-0 space-y-5">
        {readable.map((unit, index) => {
          const meta = metaMap[unit.id];
          const citations = meta?.citations ?? [];
          const mode = meta?.mode ?? unit.last_mode ?? "";
          const previous = readable[index - 1];
          const next = readable[index + 1];
          return (
            <motion.section
              key={unit.id}
              id={`unit-${unit.id}`}
              data-unit-id={unit.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              className="glass scroll-mt-24 rounded-3xl p-4 shadow-glass sm:p-8"
            >
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200/70 pb-4 dark:border-white/10">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400 dark:text-slate-500">
                    <span>
                      {t("reader.unitNo", { index: unit.order_index })}
                    </span>
                    <span>·</span>
                    <span>v{unit.current_version}</span>
                    <StatusBadge status={unit.status} />
                    <span
                      className={clsx(
                        "rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                        mode === "loose"
                          ? "bg-amber-400/20 text-amber-700 ring-1 ring-amber-400/30 dark:bg-amber-300/12 dark:text-amber-300 dark:ring-amber-300/20"
                          : "bg-indigo-500/12 text-indigo-600 ring-1 ring-indigo-400/20 dark:bg-indigo-400/14 dark:text-indigo-300 dark:ring-indigo-300/20",
                      )}
                    >
                      {t("reader.modeSuffix", { mode: modeLabel(t, mode) })}
                    </span>
                  </div>
                  <h2 className="mt-1 text-xl font-semibold tracking-tight text-slate-900 dark:text-white sm:text-[22px]">
                    {unit.title}
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => onOpenUnit(unit.id)}
                  className="btn-quiet"
                >
                  {t("reader.readAlone")}
                  <ArrowRight size={11} />
                </button>
              </div>

              {unit.learning_objectives.length > 0 ? (
                <ul className="mt-4 flex flex-wrap gap-1.5">
                  {unit.learning_objectives.map((objective) => (
                    <li key={objective} className="chip-muted">
                      {objective}
                    </li>
                  ))}
                </ul>
              ) : null}

              <div className="mt-5">
                <MarkdownReader
                  content={unit.content}
                  citations={citations}
                  mode={mode}
                />
              </div>

              <div className="mt-7 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200/70 pt-4 dark:border-white/10">
                <span className="flex items-center gap-1.5 text-[10.5px] text-slate-400 dark:text-slate-500">
                  <Clock3 size={11} />
                  {t("reader.chars", { count: contentLength(unit.content) })}
                </span>
                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => previous && jumpTo(previous.id)}
                    disabled={!previous}
                    className="btn btn-ghost !px-3 !py-1.5 text-[11px] disabled:opacity-40"
                  >
                    <ChevronLeft size={12} />
                    {t("reader.prevUnit")}
                  </button>
                  <button
                    type="button"
                    onClick={() => next && jumpTo(next.id)}
                    disabled={!next}
                    className="btn btn-ghost !px-3 !py-1.5 text-[11px] disabled:opacity-40"
                  >
                    {t("reader.nextUnit")}
                    <ChevronRight size={12} />
                  </button>
                  <button
                    type="button"
                    onClick={() => onOpenUnit(unit.id)}
                    className="btn btn-primary !px-3 !py-1.5 text-[11px]"
                  >
                    <BookOpen size={12} />
                    {t("reader.backToUnit")}
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
