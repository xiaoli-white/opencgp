import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  Ban,
  CheckCircle2,
  Clock3,
  ListChecks,
  Loader2,
  RefreshCw,
  Trash2,
  XCircle,
} from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import { ConfirmDialog } from "@/components/common/Dialogs";
import {
  cancelJob,
  isTerminal,
  listJobs,
  streamJob,
  type Job,
  type JobEvent,
} from "@/lib/jobs";
import { formatDateTime } from "@/lib/format";
import { useSession } from "@/components/auth/SessionProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { jobKindLabel, jobStatusLabel } from "@/i18n/labels";

type FilterKey = "all" | "active" | "done" | "failed";

const FILTERS: FilterKey[] = ["all", "active", "done", "failed"];

const FILTER_LABEL: Record<FilterKey, string> = {
  all: "common.all",
  active: "jobs.tabActive",
  done: "jobs.tabDone",
  failed: "jobs.tabFailed",
};

function statusTone(status: string): string {
  if (status === "succeeded")
    return "bg-emerald-500/12 text-emerald-700 ring-emerald-500/25 dark:bg-emerald-400/15 dark:text-emerald-300 dark:ring-emerald-300/25";
  if (status === "failed")
    return "bg-rose-500/12 text-rose-700 ring-rose-500/25 dark:bg-rose-400/15 dark:text-rose-300 dark:ring-rose-300/25";
  if (status === "canceled")
    return "bg-slate-500/12 text-slate-600 ring-slate-400/25 dark:bg-slate-400/15 dark:text-slate-300 dark:ring-slate-300/25";
  if (status === "running")
    return "bg-indigo-500/12 text-indigo-600 ring-indigo-400/25 dark:bg-indigo-400/15 dark:text-indigo-300 dark:ring-indigo-300/25";
  return "bg-amber-500/12 text-amber-700 ring-amber-500/25 dark:bg-amber-400/15 dark:text-amber-300 dark:ring-amber-300/25";
}

function statusIcon(status: string) {
  if (status === "succeeded") return <CheckCircle2 size={12} />;
  if (status === "failed") return <XCircle size={12} />;
  if (status === "canceled") return <Ban size={12} />;
  if (status === "running") return <Loader2 size={12} className="animate-spin" />;
  return <Clock3 size={12} />;
}

function formatDuration(job: Job): string {
  const start = job.started_at || job.created_at;
  const end = job.finished_at || (job.status === "queued" ? start : Date.now() / 1000);
  const seconds = Math.max(0, Math.round(end - start));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

function resultLink(job: Job): { href: string; labelKey: string } | null {
  const result = job.result ?? {};
  const payload = job.payload ?? {};
  const pick = (key: string) => {
    const value = result[key] ?? payload[key];
    return typeof value === "string" ? value : "";
  };
  if (job.kind === "research") {
    const id = pick("research_id");
    return id
      ? { href: `/research?id=${encodeURIComponent(id)}`, labelKey: "jobs.viewResearch" }
      : null;
  }
  if (job.kind === "piece_create" || job.kind === "piece_generate" || job.kind === "piece_rewrite") {
    const id = pick("piece_id");
    return id
      ? { href: `/pieces/${encodeURIComponent(id)}`, labelKey: "jobs.openEditor" }
      : null;
  }
  if (job.kind === "unit_generate" || job.kind === "blueprint_generate") {
    const id = pick("series_id");
    return id
      ? { href: `/series/${encodeURIComponent(id)}`, labelKey: "jobs.openSeries" }
      : null;
  }
  return null;
}

function matchesFilter(job: Job, filter: FilterKey): boolean {
  if (filter === "active") return !isTerminal(job.status);
  if (filter === "done") return job.status === "succeeded";
  if (filter === "failed") return job.status === "failed" || job.status === "canceled";
  return true;
}

export default function JobsPage() {
  const { can } = useSession();
  const { t } = useI18n();
  const writable = can("write");

  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [canceling, setCanceling] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [pageVisible, setPageVisible] = useState(
    () => typeof document === "undefined" || !document.hidden,
  );
  const timerRef = useRef<number | null>(null);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await listJobs({ limit: 40 });
      setJobs(data.jobs ?? []);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("jobs.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const hasActive = useMemo(() => jobs.some((job) => !isTerminal(job.status)), [jobs]);
  const activeIds = useMemo(
    () => jobs.filter((job) => !isTerminal(job.status)).map((job) => job.id),
    [jobs],
  );
  const activeKey = activeIds.join(",");

  useEffect(() => {
    const handleVisibility = () => setPageVisible(!document.hidden);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  const applyJobEvent = useCallback((event: JobEvent) => {
    setJobs((prev) =>
      prev.map((job) =>
        job.id === event.id
          ? {
              ...job,
              status: event.status,
              progress:
                typeof event.progress === "number" ? event.progress : job.progress,
              error: event.error ?? job.error,
              result: event.result ?? job.result,
            }
          : job,
      ),
    );
  }, []);

  useEffect(() => {
    if (!pageVisible || !activeIds.length) return;
    const controllers = activeIds.map((jobId) => {
      const controller = new AbortController();
      void streamJob(jobId, {
        onEvent: applyJobEvent,
        signal: controller.signal,
      })
        .then((job) => {
          if (isTerminal(job.status)) {
            setJobs((prev) =>
              prev.map((item) => (item.id === job.id ? { ...item, ...job } : item)),
            );
            void load(true);
          }
        })
        .catch(() => {});
      return controller;
    });
    return () => {
      controllers.forEach((controller) => controller.abort());
    };
  }, [activeKey, pageVisible, applyJobEvent, load]);

  useEffect(() => {
    if (!hasActive) {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    timerRef.current = window.setInterval(() => {
      void load(true);
    }, 5000);
    return () => {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [hasActive, load]);

  const counters = useMemo(() => {
    const active = jobs.filter((job) => !isTerminal(job.status)).length;
    const failed = jobs.filter((job) => job.status === "failed" || job.status === "canceled").length;
    return { active, done: jobs.filter((job) => job.status === "succeeded").length, failed };
  }, [jobs]);

  const visible = useMemo(() => jobs.filter((job) => matchesFilter(job, filter)), [jobs, filter]);

  const handleCancel = async (job: Job) => {
    if (canceling) return;
    setCanceling(job.id);
    setError("");
    try {
      await cancelJob(job.id);
      setNotice(t("jobs.cancelRequested", { kind: jobKindLabel(t, job.kind) }));
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("jobs.cancelFailed"));
    } finally {
      setCanceling(null);
    }
  };

  const [removing, setRemoving] = useState<Job | null>(null);

  const handleRemove = async () => {
    if (!removing) return;
    setCanceling(removing.id);
    setError("");
    try {
      await api.deleteJob(removing.id);
      setNotice(t("jobs.deleted"));
      setRemoving(null);
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.deleteFailed"));
    } finally {
      setCanceling(null);
    }
  };

  return (
    <div className="space-y-5">
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="glass rounded-3xl p-5 shadow-glass sm:p-6"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <span className="chip-muted inline-flex items-center gap-1.5">
              <ListChecks size={12} />
              {t("jobs.badge")}
            </span>
            <h1 className="mt-2.5 text-xl font-semibold tracking-tight text-slate-900 dark:text-slate-50 sm:text-2xl">
              {t("jobs.title")}
            </h1>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              {t("jobs.subtitle")}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            className="btn btn-quiet"
            disabled={loading}
          >
            <RefreshCw size={13} className={clsx(loading && "animate-spin")} />
            {t("common.refresh")}
          </button>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2 sm:gap-3">
          {[
            {
              label: t("jobs.counterActive"),
              value: counters.active,
              tone: "text-indigo-600 dark:text-indigo-300",
            },
            {
              label: t("jobs.counterDone"),
              value: counters.done,
              tone: "text-emerald-600 dark:text-emerald-300",
            },
            {
              label: t("jobs.counterFailed"),
              value: counters.failed,
              tone: "text-rose-600 dark:text-rose-300",
            },
          ].map((item) => (
            <div
              key={item.label}
              className="rounded-2xl border border-white/45 bg-white/55 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.05]"
            >
              <div className="text-[11px] text-slate-500 dark:text-slate-400">{item.label}</div>
              <div className={clsx("text-lg font-semibold tabular-nums", item.tone)}>
                {item.value}
              </div>
            </div>
          ))}
        </div>

        <div className="no-scrollbar mt-4 flex gap-1.5 overflow-x-auto">
          {FILTERS.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={clsx(
                "shrink-0 whitespace-nowrap rounded-full px-3.5 py-1.5 text-xs font-medium transition",
                filter === key
                  ? "brand-gradient text-white shadow-brand"
                  : "border border-white/50 bg-white/55 text-slate-600 hover:text-indigo-600 dark:border-white/10 dark:bg-white/[0.06] dark:text-slate-300 dark:hover:text-indigo-200",
              )}
            >
              {t(FILTER_LABEL[key])}
            </button>
          ))}
        </div>

        {error ? (
          <div className="mt-3 flex items-start gap-2 rounded-2xl border border-rose-300/50 bg-rose-50/70 px-4 py-2.5 text-xs text-rose-700 dark:border-rose-300/25 dark:bg-rose-400/10 dark:text-rose-300">
            <AlertTriangle size={13} className="mt-0.5 shrink-0" />
            <span className="break-words">{error}</span>
          </div>
        ) : null}

        {notice ? (
          <div className="mt-3 rounded-2xl border border-emerald-300/50 bg-emerald-50/70 px-4 py-2.5 text-xs text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-400/10 dark:text-emerald-300">
            {notice}
          </div>
        ) : null}
      </motion.section>

      <div className="space-y-3">
        {loading && !jobs.length ? (
          <div className="glass flex items-center gap-2 rounded-3xl px-5 py-8 text-sm text-slate-500 shadow-glass dark:text-slate-400">
            <Loader2 size={15} className="animate-spin" />
            {t("jobs.loading")}
          </div>
        ) : null}

        {!loading && !visible.length ? (
          <div className="glass rounded-3xl px-5 py-10 text-center shadow-glass">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-indigo-500/10 text-indigo-600 dark:bg-indigo-400/15 dark:text-indigo-300">
              <ListChecks size={20} />
            </div>
            <p className="mt-3 text-sm font-medium text-slate-700 dark:text-slate-200">
              {t("jobs.emptyTitle")}
            </p>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {t("jobs.emptyDesc")}
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              <Link to="/research" className="btn btn-primary whitespace-nowrap">
                {t("jobs.goResearch")}
                <ArrowRight size={13} />
              </Link>
              <Link to="/pieces" className="btn btn-ghost whitespace-nowrap">
                {t("jobs.goPieces")}
              </Link>
            </div>
          </div>
        ) : null}

        {visible.map((job) => {
          const link = resultLink(job);
          const running = job.status === "running" || job.status === "queued";
          const percent = Math.round(Math.min(1, Math.max(0, job.progress || 0)) * 100);
          return (
            <motion.div
              key={job.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
              className="glass rounded-2xl p-4 shadow-glass sm:p-5"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                      {jobKindLabel(t, job.kind)}
                    </span>
                    <span
                      className={clsx(
                        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1",
                        statusTone(job.status),
                      )}
                    >
                      {statusIcon(job.status)}
                      {jobStatusLabel(t, job.status)}
                    </span>
                    <span className="text-[11px] text-slate-400 dark:text-slate-500">
                      {formatDateTime(job.created_at)} ·{" "}
                      {t("jobs.duration", { duration: formatDuration(job) })}
                    </span>
                  </div>
                  <p className="mt-1 truncate font-mono text-[11px] text-slate-400 dark:text-slate-500">
                    {job.id}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {link && job.status === "succeeded" ? (
                    <Link to={link.href} className="btn btn-quiet whitespace-nowrap">
                      {t(link.labelKey)}
                      <ArrowRight size={12} />
                    </Link>
                  ) : null}
                  {running && writable ? (
                    <button
                      type="button"
                      onClick={() => void handleCancel(job)}
                      disabled={canceling === job.id}
                      className="btn btn-quiet"
                    >
                      {canceling === job.id ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Ban size={12} />
                      )}
                      {t("common.cancel")}
                    </button>
                  ) : null}
                  {!running && isTerminal(job.status) ? (
                    <button
                      type="button"
                      onClick={() => setRemoving(job)}
                      className="btn-quiet px-2 py-1 text-[11px] text-rose-600 dark:text-rose-300"
                      title={t("jobs.deleteTitle")}
                    >
                      <Trash2 size={12} />
                      {t("common.delete")}
                    </button>
                  ) : null}
                </div>
              </div>

              {running ? (
                <div className="mt-3">
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200/70 dark:bg-white/10">
                    <div
                      className="brand-gradient h-full rounded-full transition-all duration-500"
                      style={{ width: `${Math.max(percent, job.status === "queued" ? 4 : 8)}%` }}
                    />
                  </div>
                  <div className="mt-1 flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
                    <span>
                      {job.status === "queued" ? t("jobs.queuedHint") : t("jobs.executing")}
                    </span>
                    <span className="flex items-center gap-2">
                      {pageVisible ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-medium text-emerald-600 dark:text-emerald-300">
                          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
                          SSE
                        </span>
                      ) : null}
                      <span className="tabular-nums">{percent}%</span>
                    </span>
                  </div>
                </div>
              ) : null}

              {job.status === "failed" && job.error ? (
                <div className="mt-3">
                  <button
                    type="button"
                    onClick={() => setExpanded(expanded === job.id ? null : job.id)}
                    className="inline-flex items-center gap-1 text-[11px] font-medium text-rose-600 dark:text-rose-300"
                  >
                    <AlertTriangle size={11} />
                    {expanded === job.id ? t("jobs.hideError") : t("jobs.showError")}
                  </button>
                  <AnimatePresence initial={false}>
                    {expanded === job.id ? (
                      <motion.pre
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        className="mt-2 overflow-x-auto whitespace-pre-wrap break-words rounded-xl border border-rose-300/40 bg-rose-50/60 p-3 text-[11px] leading-relaxed text-rose-700 dark:border-rose-300/20 dark:bg-rose-400/10 dark:text-rose-300"
                      >
                        {job.error}
                      </motion.pre>
                    ) : null}
                  </AnimatePresence>
                </div>
              ) : null}

              {job.status === "succeeded" && job.result ? (
                <p className="mt-2 truncate text-[11px] text-slate-500 dark:text-slate-400">
                  {Object.entries(job.result)
                    .filter(([, value]) => typeof value === "string" || typeof value === "number")
                    .slice(0, 4)
                    .map(([key, value]) => `${key}=${String(value)}`)
                    .join(" · ")}
                </p>
              ) : null}
            </motion.div>
          );
        })}
      </div>

      <ConfirmDialog
        open={Boolean(removing)}
        title={t("jobs.deleteTitle")}
        description={t("jobs.deleteDesc", { id: removing?.id ?? "" })}
        busy={Boolean(removing && canceling === removing.id)}
        onConfirm={() => void handleRemove()}
        onClose={() => setRemoving(null)}
      />
    </div>
  );
}
