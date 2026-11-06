import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  BookMarked,
  BrainCircuit,
  ChevronDown,
  Clock3,
  Compass,
  FileText,
  FlaskConical,
  HelpCircle,
  Loader2,
  Pencil,
  Sparkles,
  Trash2,
  Wand2,
  X,
} from "lucide-react";
import clsx from "clsx";
import { ApiError, api, type ResearchRun } from "@/lib/api";
import { jobResultNumber, jobResultString, runJob } from "@/lib/jobs";
import { formatDateTime } from "@/lib/format";
import { useSession } from "@/components/auth/SessionProvider";
import { PromptDialog } from "@/components/common/Dialogs";
import { useI18n } from "@/i18n/I18nProvider";

const DEPTH_OPTIONS = [1, 2, 3];

const STATUS_KEYS = ["queued", "running", "completed", "failed"] as const;

const TOPK_OPTIONS = [3, 5, 8];

function statusClass(status: string): string {
  if (status === "completed") {
    return "bg-emerald-500/12 text-emerald-700 ring-emerald-500/25 dark:bg-emerald-400/15 dark:text-emerald-300 dark:ring-emerald-300/25";
  }
  if (status === "failed") {
    return "bg-rose-500/12 text-rose-700 ring-rose-500/25 dark:bg-rose-400/15 dark:text-rose-300 dark:ring-rose-300/25";
  }
  return "bg-indigo-500/12 text-indigo-600 ring-indigo-400/25 dark:bg-indigo-400/15 dark:text-indigo-300 dark:ring-indigo-300/25";
}

function briefExcerpt(run: ResearchRun, fallback: string, limit = 60): string {
  const text = (run.brief?.summary || run.topic || "").replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text || fallback;
  return `${text.slice(0, limit)}…`;
}

function useElapsed(active: boolean): number {
  const [seconds, setSeconds] = useState(0);
  const startedRef = useRef(0);

  useEffect(() => {
    if (!active) {
      setSeconds(0);
      return;
    }
    startedRef.current = Date.now();
    setSeconds(0);
    const timer = window.setInterval(() => {
      setSeconds(Math.floor((Date.now() - startedRef.current) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [active]);

  return seconds;
}

function CollapsibleBlock({
  title,
  icon,
  count,
  children,
  tone = "neutral",
  defaultOpen = false,
}: {
  title: string;
  icon: React.ReactNode;
  count: number;
  children: React.ReactNode;
  tone?: "neutral" | "amber" | "rose" | "indigo";
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const border =
    tone === "amber"
      ? "border-amber-300/40 dark:border-amber-300/20"
      : tone === "rose"
        ? "border-rose-300/40 dark:border-rose-300/20"
        : tone === "indigo"
          ? "border-indigo-300/40 dark:border-indigo-300/20"
          : "border-white/45 dark:border-white/10";

  return (
    <div className={clsx("rounded-2xl border bg-white/45 dark:bg-white/[0.04]", border)}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left text-xs font-semibold text-slate-600 dark:text-slate-300"
      >
        {icon}
        <span>{title}</span>
        <span className="rounded-full bg-slate-500/10 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-white/10 dark:text-slate-400">
          {count}
        </span>
        <ChevronDown
          size={14}
          className={clsx("ml-auto transition", open && "rotate-180")}
        />
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="space-y-2 px-3.5 pb-3 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
              {children}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

export default function ResearchPage() {
  const { can, roleName } = useSession();
  const { t } = useI18n();
  const writable = can("write");

  const [topic, setTopic] = useState("");
  const [depth, setDepth] = useState(2);
  const [topK, setTopK] = useState(5);

  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const elapsed = useElapsed(running);
  const [searchParams] = useSearchParams();
  const focusId = searchParams.get("id") ?? "";
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [renaming, setRenaming] = useState<ResearchRun | null>(null);
  const [dialogBusy, setDialogBusy] = useState(false);
  const [dialogError, setDialogError] = useState("");

  const [run, setRun] = useState<ResearchRun | null>(null);
  const [history, setHistory] = useState<ResearchRun[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);

  const [openEvidence, setOpenEvidence] = useState<string | null>(null);

  const [blueprintOpen, setBlueprintOpen] = useState(false);
  const [blueprintTitle, setBlueprintTitle] = useState("");
  const [blueprintMode, setBlueprintMode] = useState<"loose" | "strict">("loose");
  const [blueprintBusy, setBlueprintBusy] = useState(false);
  const [blueprintResult, setBlueprintResult] = useState<{ seriesId: string } | null>(
    null,
  );

  const renameResearch = async (topic: string) => {
    if (!renaming) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updateResearch(renaming.id, topic);
      setHistory((prev) =>
        prev.map((item) => (item.id === updated.id ? { ...item, topic: updated.topic } : item)),
      );
      setRun((prev) => (prev && prev.id === updated.id ? { ...prev, topic: updated.topic } : prev));
      setRenaming(null);
      setNotice(t("research.topicUpdated"));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("research.renameFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const data = await api.listResearch();
      setHistory(data.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("research.historyLoadFailed"));
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    if (!focusId) return;
    let cancelled = false;
    void (async () => {
      try {
        const detail = await api.getResearch(focusId);
        if (cancelled) return;
        setRun(detail);
        setNotice(t("research.loadedFromJobs", { topic: detail.topic }));
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : t("research.detailLoadFailed"));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [focusId]);

  const citationIndex = useMemo(() => {
    const map = new Map<string, ResearchRun["citations"][number]>();
    (run?.citations ?? []).forEach((item, index) => {
      map.set(`E${index + 1}`, item);
    });
    return map;
  }, [run]);

  const startResearch = async () => {
    const text = topic.trim();
    if (!text || running) return;
    if (!writable) {
      setError(t("research.readOnlyStart"));
      return;
    }
    setRunning(true);
    setProgress(0);
    setJobId(null);
    setError("");
    setNotice("");
    setBlueprintResult(null);
    const startedAt = Date.now();
    try {
      let researchId = "";
      let citations = 0;
      try {
        const job = await runJob(
          "research",
          { topic: text, depth, top_k: topK },
          {
            onProgress: setProgress,
            onJob: (created) => setJobId(created.id),
          },
        );
        researchId = jobResultString(job, "research_id");
        citations = jobResultNumber(job, "citations");
      } catch (queueErr) {
        const queueable =
          queueErr instanceof ApiError &&
          (queueErr.status === 400 || queueErr.status === 404 || queueErr.status === 422);
        if (!queueable) throw queueErr;
        const result = await api.runResearch({ topic: text, depth, top_k: topK });
        researchId = result.id;
        citations = result.citations.length;
      }
      if (!researchId) throw new Error(t("research.noResult"));
      const detail = await api.getResearch(researchId);
      setProgress(1);
      setRun(detail);
      const seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      setNotice(
        t("research.completedNotice", {
          seconds,
          count: citations || detail.citations.length,
        }),
      );
      await loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("research.failed"));
    } finally {
      setRunning(false);
      setJobId(null);
    }
  };

  const selectRun = (item: ResearchRun) => {
    setRun(item);
    setError("");
    setNotice("");
    setBlueprintResult(null);
    setOpenEvidence(null);
  };

  const removeRun = async (target: ResearchRun) => {
    if (!writable || deleting) return;
    const confirmed = window.confirm(t("research.confirmDelete", { topic: target.topic }));
    if (!confirmed) return;
    setDeleting(target.id);
    setError("");
    try {
      await api.deleteResearch(target.id);
      setHistory((prev) => prev.filter((item) => item.id !== target.id));
      setRun((prev) => (prev?.id === target.id ? null : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.deleteFailed"));
    } finally {
      setDeleting(null);
    }
  };

  const openBlueprintForm = () => {
    if (!run) return;
    setBlueprintTitle(run.topic);
    setBlueprintOpen(true);
    setBlueprintResult(null);
  };

  const submitBlueprint = async () => {
    if (!run || blueprintBusy) return;
    setBlueprintBusy(true);
    setError("");
    try {
      const result = await api.researchToBlueprint(run.id, {
        create_series: true,
        series_title: blueprintTitle.trim() || run.topic,
        mode: blueprintMode,
      });
      setBlueprintResult({ seriesId: result.series_id });
      setBlueprintOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("research.blueprintFailed"));
    } finally {
      setBlueprintBusy(false);
    }
  };

  const brief = run?.brief;

  return (
    <div className="space-y-5">
      {!writable ? (
        <div className="rounded-2xl border border-amber-300/50 bg-amber-50/70 px-4 py-2.5 text-xs text-amber-700 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-300">
          {t("research.readOnlyView", { role: roleName || t("common.readOnly") })}
        </div>
      ) : null}

      <motion.section
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="glass relative overflow-hidden rounded-[2rem] p-6 shadow-glass sm:p-8"
      >
        <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-gradient-to-br from-indigo-400/25 to-violet-400/20 blur-3xl" />
        <div className="relative space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <span className="chip">
              <BrainCircuit size={11} />
              {t("research.badge")}
            </span>
            <h1 className="text-xl font-semibold tracking-tight text-slate-800 dark:text-slate-100 sm:text-2xl">
              {t("research.heroTitle")}
            </h1>
          </div>

          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_auto_auto] sm:items-end">
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                {t("research.fieldTopic")}
              </span>
              <input
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                placeholder={t("research.topicPlaceholder")}
                className="input"
                disabled={running}
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                {t("research.fieldDepth")}
              </span>
              <select
                value={depth}
                onChange={(event) => setDepth(Number(event.target.value))}
                className="select"
                disabled={running}
              >
                {DEPTH_OPTIONS.map((value) => (
                  <option key={value} value={value}>
                    {t(`research.depth${value}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                {t("research.fieldTopK")}
              </span>
              <select
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
                className="select"
                disabled={running}
              >
                {TOPK_OPTIONS.map((value) => (
                  <option key={value} value={value}>
                    {t("research.evidenceCount", { count: value })}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={startResearch}
              disabled={running || !topic.trim() || !writable}
              className="btn btn-primary h-[42px] whitespace-nowrap"
              title={!writable ? t("common.readOnlyRole") : undefined}
            >
              {running ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {running ? t("research.runningBtn") : t("research.start")}
            </button>
          </div>

          {running ? (
            <div className="rounded-2xl border border-indigo-300/40 bg-indigo-50/60 px-4 py-3 text-xs text-indigo-700 dark:border-indigo-300/20 dark:bg-indigo-400/10 dark:text-indigo-200">
              <div className="flex items-center gap-2 font-medium">
                <Loader2 size={13} className="animate-spin" />
                {t("research.runningTitle")}
                <span className="ml-auto inline-flex items-center gap-1 tabular-nums">
                  <Clock3 size={12} />
                  {t("piece.elapsed", { seconds: elapsed })}
                </span>
              </div>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/60 dark:bg-white/10">
                <div
                  className="brand-gradient h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.max(6, Math.round(progress * 100))}%` }}
                />
              </div>
              <p className="mt-1.5 flex items-center justify-between leading-relaxed opacity-80">
                <span>
                  {jobId ? t("research.queueHint") : t("research.syncHint")}
                </span>
                <span className="tabular-nums">{Math.round(progress * 100)}%</span>
              </p>
            </div>
          ) : null}

          {error ? (
            <div className="flex items-start gap-2 rounded-2xl border border-rose-300/50 bg-rose-50/70 px-4 py-2.5 text-xs text-rose-700 dark:border-rose-300/25 dark:bg-rose-400/10 dark:text-rose-300">
              <AlertTriangle size={13} className="mt-0.5 shrink-0" />
              <span className="break-words">{error}</span>
            </div>
          ) : null}

          {notice ? (
            <div className="rounded-2xl border border-emerald-300/50 bg-emerald-50/70 px-4 py-2.5 text-xs text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-400/10 dark:text-emerald-300">
              {notice}
            </div>
          ) : null}

          {blueprintResult ? (
            <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-emerald-300/50 bg-emerald-50/70 px-4 py-2.5 text-xs text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-400/10 dark:text-emerald-300">
              <BookMarked size={13} />
              {t("research.blueprintDone")}
              <Link
                to={`/series/${blueprintResult.seriesId}`}
                className="inline-flex items-center gap-1 font-semibold underline decoration-dotted"
              >
                {t("research.goToSeries")}
                <ArrowRight size={12} />
              </Link>
            </div>
          ) : null}
        </div>
      </motion.section>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0 space-y-4">
          {run ? (
            <motion.section
              key={run.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className="glass space-y-4 rounded-3xl p-5 shadow-glass sm:p-6"
            >
              <header className="flex flex-wrap items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={clsx(
                        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ring-1",
                        statusClass(run.status),
                      )}
                    >
                      {(STATUS_KEYS as readonly string[]).includes(run.status)
                        ? t(`research.status.${run.status}`)
                        : run.status}
                    </span>
                    <span className="chip-muted">
                      {t("research.depthBadge", { depth: run.depth })}
                    </span>
                    <span className="chip-muted">
                      {t("research.evidenceBadge", { count: run.citations.length })}
                    </span>
                    {run.provider ? <span className="chip-muted">{run.provider}</span> : null}
                  </div>
                  <h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-800 dark:text-slate-100">
                    {run.topic}
                  </h2>
                  <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
                    {formatDateTime(run.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={openBlueprintForm}
                    disabled={!writable}
                    className="btn btn-quiet"
                    title={!writable ? t("common.readOnlyRole") : undefined}
                  >
                    <Wand2 size={13} />
                    {t("research.toBlueprint")}
                  </button>
                  <button
                    type="button"
                    onClick={() => removeRun(run)}
                    disabled={!writable || deleting === run.id}
                    className="btn btn-quiet text-rose-600 dark:text-rose-300"
                    title={!writable ? t("common.readOnlyRole") : undefined}
                  >
                    {deleting === run.id ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <Trash2 size={13} />
                    )}
                    {t("common.delete")}
                  </button>
                </div>
              </header>

              {run.warning ? (
                <div className="flex items-start gap-2 rounded-2xl border border-amber-300/50 bg-amber-50/70 px-3.5 py-2.5 text-xs text-amber-700 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-300">
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                  <span className="break-words">{run.warning}</span>
                </div>
              ) : null}

              {run.questions.length ? (
                <div>
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.1em] text-slate-400 dark:text-slate-500">
                    <HelpCircle size={12} />
                    {t("research.questions")}
                  </h3>
                  <ol className="flex flex-wrap gap-2">
                    {run.questions.map((question, index) => (
                      <li
                        key={`${question}-${index}`}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-white/50 bg-white/55 px-2.5 py-1.5 text-[11px] text-slate-600 dark:border-white/10 dark:bg-white/[0.06] dark:text-slate-300"
                      >
                        <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full brand-gradient text-[9px] font-semibold text-white">
                          {index + 1}
                        </span>
                        {question}
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null}

              {brief?.summary ? (
                <div>
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.1em] text-slate-400 dark:text-slate-500">
                    <Compass size={12} />
                    {t("research.summary")}
                  </h3>
                  <p className="whitespace-pre-wrap text-[13px] leading-[1.85] text-slate-700 dark:text-slate-200">
                    {brief.summary}
                  </p>
                </div>
              ) : null}

              {brief?.findings?.length ? (
                <div>
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.1em] text-slate-400 dark:text-slate-500">
                    <FlaskConical size={12} />
                    {t("research.findings")}
                  </h3>
                  <div className="space-y-2.5">
                    {brief.findings.map((finding, index) => (
                      <div
                        key={`${finding.title}-${index}`}
                        className="rounded-2xl border border-white/45 bg-white/45 p-3.5 transition hover:border-indigo-300/50 dark:border-white/10 dark:bg-white/[0.04]"
                      >
                        <p className="text-[13px] font-semibold text-slate-800 dark:text-slate-100">
                          {finding.title || t("research.findingFallback", { index: index + 1 })}
                        </p>
                        <p className="mt-1 whitespace-pre-wrap text-[12.5px] leading-[1.8] text-slate-600 dark:text-slate-300">
                          {finding.detail}
                        </p>
                        {finding.evidence.length ? (
                          <div className="mt-2 space-y-1.5">
                            <div className="flex flex-wrap items-center gap-1.5">
                              {finding.evidence.map((marker) => {
                                const key = `${index}-${marker}`;
                                const active = openEvidence === key;
                                return (
                                  <button
                                    key={key}
                                    type="button"
                                    onClick={() =>
                                      setOpenEvidence(active ? null : key)
                                    }
                                    className={clsx(
                                      "rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 transition",
                                      active
                                        ? "brand-gradient text-white ring-transparent"
                                        : "bg-indigo-500/10 text-indigo-600 ring-indigo-400/25 hover:bg-indigo-500/15 dark:bg-indigo-400/15 dark:text-indigo-300 dark:ring-indigo-300/25",
                                    )}
                                  >
                                    {marker}
                                  </button>
                                );
                              })}
                            </div>
                            {finding.evidence.map((marker) => {
                              const key = `${index}-${marker}`;
                              if (openEvidence !== key) return null;
                              const citation = citationIndex.get(marker);
                              return (
                                <div
                                  key={`${key}-panel`}
                                  className="rounded-xl border border-indigo-300/40 bg-indigo-50/60 p-2.5 text-[11px] leading-relaxed text-slate-600 dark:border-indigo-300/20 dark:bg-indigo-400/10 dark:text-slate-300"
                                >
                                  <p className="mb-1 flex flex-wrap items-center gap-1 font-semibold text-indigo-700 dark:text-indigo-200">
                                    <FileText size={11} />
                                    {citation?.source_name || t("research.evidence")}
                                    <span className="font-normal text-slate-400">
                                      {citation
                                        ? t("research.snippetNo", {
                                            index: citation.chunk_index,
                                          })
                                        : t("research.noSource")}
                                    </span>
                                  </p>
                                  <p className="max-h-40 overflow-y-auto whitespace-pre-wrap">
                                    {citation?.snippet ||
                                      citation?.text ||
                                      t("research.noCitationText")}
                                  </p>
                                </div>
                              );
                            })}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="space-y-2">
                <CollapsibleBlock
                  title={t("research.contradictions")}
                  icon={<AlertTriangle size={13} />}
                  count={brief?.contradictions?.length ?? 0}
                  tone="rose"
                  defaultOpen={!brief?.contradictions?.length}
                >
                  {brief?.contradictions?.length ? (
                    brief.contradictions.map((item, index) => (
                      <div
                        key={`${item.claim}-${index}`}
                        className="rounded-xl bg-white/60 p-2.5 dark:bg-white/[0.05]"
                      >
                        <p className="font-medium text-slate-700 dark:text-slate-200">
                          {item.claim}
                        </p>
                        <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                          {t("research.evidenceList", {
                            list: item.evidence.join(", ") || t("research.none"),
                          })}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-[11px] text-slate-500 dark:text-slate-400">
                      {t("research.contradictionsEmpty")}
                    </p>
                  )}
                </CollapsibleBlock>

                {brief?.gaps?.length ? (
                  <CollapsibleBlock
                    title={t("research.gaps")}
                    icon={<Compass size={13} />}
                    count={brief.gaps.length}
                    tone="amber"
                  >
                    <ul className="list-disc space-y-1 pl-4">
                      {brief.gaps.map((gap, index) => (
                        <li key={`${gap}-${index}`}>{gap}</li>
                      ))}
                    </ul>
                  </CollapsibleBlock>
                ) : null}

                {brief?.next_steps?.length ? (
                  <CollapsibleBlock
                    title={t("research.nextSteps")}
                    icon={<ArrowRight size={13} />}
                    count={brief.next_steps.length}
                    tone="indigo"
                  >
                    <ul className="list-disc space-y-1 pl-4">
                      {brief.next_steps.map((step, index) => (
                        <li key={`${step}-${index}`}>{step}</li>
                      ))}
                    </ul>
                  </CollapsibleBlock>
                ) : null}
              </div>

              {run.citations.length ? (
                <div>
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.1em] text-slate-400 dark:text-slate-500">
                    <FileText size={12} />
                    {t("research.sources")}
                  </h3>
                  <ul className="space-y-1.5">
                    {run.citations.map((citation, index) => (
                      <li
                        key={`${citation.chunk_id}-${index}`}
                        className="flex flex-wrap items-center gap-2 rounded-xl border border-white/45 bg-white/40 px-3 py-2 text-[11px] text-slate-600 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-300"
                      >
                        <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full brand-gradient text-[9px] font-semibold text-white">
                          {index + 1}
                        </span>
                        <span className="min-w-0 flex-1 truncate font-medium">
                          {citation.source_name || t("research.unknownSource")}
                        </span>
                        <span className="chip-muted">
                          {t("research.snippet", { index: citation.chunk_index })}
                        </span>
                        <span className="text-slate-400 dark:text-slate-500">
                          {citation.score.toFixed(2)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </motion.section>
          ) : (
            <div className="glass rounded-3xl p-8 text-center shadow-glass">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl brand-gradient text-white shadow-brand">
                <BrainCircuit size={20} />
              </div>
              <p className="mt-3 text-sm font-medium text-slate-700 dark:text-slate-200">
                {t("research.emptyTitle")}
              </p>
              <p className="mx-auto mt-1.5 max-w-md text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                {t("research.emptyDesc")}
              </p>
              <Link to="/kb" className="btn btn-quiet mx-auto mt-4">
                <FileText size={13} />
                {t("research.goKb")}
              </Link>
            </div>
          )}
        </div>

        <aside className="glass h-fit rounded-3xl p-4 shadow-glass">
          <div className="flex items-center justify-between px-1">
            <h2 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
              <Clock3 size={12} />
              {t("research.history")}
            </h2>
            <span className="text-[10px] text-slate-400 dark:text-slate-500">
              {history.length}
            </span>
          </div>
          <div className="no-scrollbar mt-2.5 max-h-[560px] space-y-1.5 overflow-y-auto pr-1">
            {historyLoading ? (
              <p className="px-1 py-3 text-[11px] text-slate-400">
                {t("common.loading")}
              </p>
            ) : history.length === 0 ? (
              <p className="px-1 py-3 text-[11px] leading-relaxed text-slate-400 dark:text-slate-500">
                {t("research.historyEmpty")}
              </p>
            ) : (
              history.map((item) => (
                <div
                  key={item.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => selectRun(item)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") selectRun(item);
                  }}
                  className={clsx(
                    "w-full cursor-pointer rounded-xl px-2.5 py-2 text-left transition",
                    run?.id === item.id
                      ? "brand-gradient text-white shadow-brand"
                      : "hover:bg-white/55 dark:hover:bg-white/10",
                  )}
                >
                  <span className="flex items-start gap-1">
                    <span
                      className={clsx(
                        "block min-w-0 flex-1 truncate text-[12px] font-medium",
                        run?.id === item.id
                          ? "text-white"
                          : "text-slate-700 dark:text-slate-200",
                      )}
                    >
                      {item.topic}
                    </span>
                    {writable ? (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setDialogError("");
                          setRenaming(item);
                        }}
                        className={clsx(
                          "shrink-0 rounded p-0.5 transition",
                          run?.id === item.id
                            ? "text-white/70 hover:text-white"
                            : "text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-300",
                        )}
                        aria-label={t("research.renameTitle")}
                      >
                        <Pencil size={11} />
                      </button>
                    ) : null}
                  </span>
                  <span
                    className={clsx(
                      "mt-0.5 block text-[10px] leading-snug",
                      run?.id === item.id
                        ? "text-white/80"
                        : "text-slate-400 dark:text-slate-500",
                    )}
                  >
                    {briefExcerpt(item, t("research.noSummary"))}
                  </span>
                  <span
                    className={clsx(
                      "mt-1 block text-[10px]",
                      run?.id === item.id
                        ? "text-white/70"
                        : "text-slate-400 dark:text-slate-500",
                    )}
                  >
                    {formatDateTime(item.created_at)}
                  </span>
                </div>
              ))
            )}
          </div>
          <button
            type="button"
            onClick={() => void loadHistory()}
            className="btn btn-quiet mt-3 w-full"
          >
            <Clock3 size={12} />
            {t("research.refreshList")}
          </button>
        </aside>
      </div>

      <AnimatePresence>
        {blueprintOpen ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 grid place-items-center bg-slate-900/30 p-4 backdrop-blur-sm"
          >
            <motion.div
              initial={{ opacity: 0, y: 12, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.98 }}
              className="glass w-full max-w-md rounded-3xl p-5 shadow-glass"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                    {t("research.toBlueprint")}
                  </h3>
                  <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                    {t("research.blueprintDesc")}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setBlueprintOpen(false)}
                  className="btn-quiet grid h-8 w-8 place-items-center rounded-full"
                >
                  <X size={14} />
                </button>
              </div>
              <label className="mt-4 block">
                <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  {t("research.seriesName")}
                </span>
                <input
                  value={blueprintTitle}
                  onChange={(event) => setBlueprintTitle(event.target.value)}
                  className="input"
                  placeholder={run?.topic ?? ""}
                />
              </label>
              <label className="mt-3 block">
                <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  {t("piece.fieldMode")}
                </span>
                <select
                  value={blueprintMode}
                  onChange={(event) =>
                    setBlueprintMode(event.target.value as "loose" | "strict")
                  }
                  className="select"
                >
                  <option value="loose">{t("piece.modeLooseOption")}</option>
                  <option value="strict">{t("piece.modeStrictCiteOption")}</option>
                </select>
              </label>
              <div className="mt-5 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setBlueprintOpen(false)}
                  className="btn btn-quiet"
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="button"
                  onClick={submitBlueprint}
                  disabled={blueprintBusy}
                  className="btn btn-primary"
                >
                  {blueprintBusy ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Wand2 size={13} />
                  )}
                  {t("research.generateBlueprint")}
                </button>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <PromptDialog
        open={Boolean(renaming)}
        title={t("research.renameTitle")}
        label={t("research.fieldTopic")}
        initial={renaming?.topic ?? ""}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={(value) => void renameResearch(value)}
        onClose={() => setRenaming(null)}
      />
    </div>
  );
}
