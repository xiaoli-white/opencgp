import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  XCircle,
} from "lucide-react";
import clsx from "clsx";
import { ApiError, api, type Unit } from "@/lib/api";
import {
  isTerminal,
  streamJob,
  submitJob,
  type Job,
  type JobEvent,
} from "@/lib/jobs";
import { jobStatusLabel } from "@/i18n/labels";
import { useI18n } from "@/i18n/I18nProvider";
import { ConfirmDialog } from "@/components/common/Dialogs";

type RunStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";

type UnitRun = {
  unitId: string;
  title: string;
  status: RunStatus;
  jobId?: string;
  progress?: number;
  error?: string;
};

type BatchPayload = {
  job_ids?: unknown;
  jobIds?: unknown;
  jobs?: unknown;
  unit_jobs?: unknown;
  units?: unknown;
};

type SeriesGenerateAllPanelProps = {
  seriesId: string;
  units: Unit[];
  canWrite: boolean;
  onRefresh: () => void | Promise<void>;
  onNotice?: (message: string) => void;
  onOpenUnit?: (unitId: string) => void;
};

function terminal(status: string | undefined): boolean {
  return Boolean(status && isTerminal(status));
}

function asJobIds(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        if (typeof record.id === "string") return record.id;
        if (typeof record.job_id === "string") return record.job_id;
      }
      return "";
    })
    .filter(Boolean);
}

function batchJobMap(payload: BatchPayload): Map<string, string> {
  const mapping = new Map<string, string>();
  const unitJobs = payload.unit_jobs;
  if (unitJobs && typeof unitJobs === "object" && !Array.isArray(unitJobs)) {
    for (const [unitId, value] of Object.entries(
      unitJobs as Record<string, unknown>,
    )) {
      const jobId =
        typeof value === "string"
          ? value
          : value && typeof value === "object"
            ? String((value as Record<string, unknown>).id ?? "")
            : "";
      if (jobId) mapping.set(unitId, jobId);
    }
  }
  if (Array.isArray(payload.jobs)) {
    for (const item of payload.jobs) {
      if (!item || typeof item !== "object") continue;
      const record = item as Record<string, unknown>;
      const unitId = String(record.unit_id ?? record.unitId ?? "");
      const jobId = String(record.id ?? record.job_id ?? "");
      if (unitId && jobId) mapping.set(unitId, jobId);
    }
  }
  return mapping;
}

export default function SeriesGenerateAllPanel({
  seriesId,
  units,
  canWrite,
  onRefresh,
  onNotice,
  onOpenUnit,
}: SeriesGenerateAllPanelProps) {
  const { t } = useI18n();
  const [runs, setRuns] = useState<Record<string, UnitRun>>({});
  const [order, setOrder] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [batchMode, setBatchMode] = useState<"remaining" | "regenerate">("remaining");
  const [error, setError] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const controllers = useRef<Map<string, AbortController>>(new Map());

  const remaining = useMemo(
    () => units.filter((unit) => !(unit.content ?? "").trim()),
    [units],
  );

  const done = useMemo(
    () => order.filter((unitId) => terminal(runs[unitId]?.status)).length,
    [order, runs],
  );

  const failures = useMemo(
    () => order.map((unitId) => runs[unitId]).filter((run) => run?.status === "failed"),
    [order, runs],
  );

  const total = order.length;

  const abortAll = useCallback(() => {
    controllers.current.forEach((controller) => controller.abort());
    controllers.current.clear();
  }, []);

  useEffect(() => {
    return () => abortAll();
  }, [abortAll]);

  useEffect(() => {
    if (!running || order.length === 0) return;
    if (order.every((unitId) => terminal(runs[unitId]?.status))) {
      setRunning(false);
      void onRefresh();
    }
  }, [running, order, runs, onRefresh]);

  const patchRun = useCallback((unitId: string, patch: Partial<UnitRun>) => {
    setRuns((prev) => {
      const current = prev[unitId];
      if (!current) return prev;
      return { ...prev, [unitId]: { ...current, ...patch } };
    });
  }, []);

  const watchJob = useCallback(
    (jobId: string, unitId: string) => {
      const controller = new AbortController();
      controllers.current.set(jobId, controller);
      const apply = (event: JobEvent) => {
        patchRun(unitId, {
          jobId,
          status: (event.status as RunStatus) ?? "queued",
          progress: typeof event.progress === "number" ? event.progress : undefined,
          error: event.error || undefined,
        });
      };
      void streamJob(jobId, { onEvent: apply, signal: controller.signal })
        .then((job: Job) => {
          apply({
            id: job.id,
            kind: job.kind,
            status: job.status,
            progress: job.progress,
            error: job.error,
            result: job.result,
          });
        })
        .catch(() => {})
        .finally(() => {
          controllers.current.delete(jobId);
        });
    },
    [patchRun],
  );

  const enqueueFallback = useCallback(
    async (selected: Unit[]) => {
      for (const unit of selected) {
        try {
          const job = await submitJob("unit_generate", {
            unit_id: unit.id,
            topic: unit.title,
            mode: "strict",
            expected_version: unit.current_version,
          });
          patchRun(unit.id, { jobId: job.id, status: "queued", error: undefined });
          watchJob(job.id, unit.id);
        } catch (err) {
          patchRun(unit.id, {
            status: "failed",
            error: err instanceof Error ? err.message : t("errors.saveFailed"),
          });
        }
      }
    },
    [patchRun, t, watchJob],
  );

  const start = useCallback(
    async (regenerate: boolean) => {
      if (!canWrite || running) return;
      const selected = regenerate ? units : remaining;
      if (selected.length === 0) {
        onNotice?.(t("series.noUnitsBody"));
        return;
      }
      abortAll();
      setError("");
      setBatchMode(regenerate ? "regenerate" : "remaining");
      const initial: Record<string, UnitRun> = {};
      for (const unit of selected) {
        initial[unit.id] = {
          unitId: unit.id,
          title: unit.title,
          status: "queued",
          progress: 0,
        };
      }
      setRuns(initial);
      setOrder(selected.map((unit) => unit.id));
      setRunning(true);

      let batchPayload: BatchPayload | null = null;
      try {
        batchPayload = await api.generateAllSeries(seriesId, { regenerate });
      } catch (err) {
        if (!(err instanceof ApiError) || ![404, 405, 501].includes(err.status)) {
          const message =
            err instanceof Error ? err.message : t("errors.saveFailed");
          setError(message);
          for (const unit of selected) {
            patchRun(unit.id, { status: "failed", error: message });
          }
          setRunning(false);
          return;
        }
      }

      if (batchPayload) {
        const mapping = batchJobMap(batchPayload);
        const jobIds = [
          ...asJobIds(batchPayload.job_ids),
          ...asJobIds(batchPayload.jobIds),
        ];
        if (mapping.size === 0 && jobIds.length > 0) {
          selected.forEach((unit, index) => {
            const jobId = jobIds[index];
            if (jobId) mapping.set(unit.id, jobId);
          });
        }

        const handled = new Set<string>();
        if (Array.isArray(batchPayload.units)) {
          for (const item of batchPayload.units) {
            if (!item || typeof item !== "object") continue;
            const record = item as Record<string, unknown>;
            const unitId = String(record.unit_id ?? record.unitId ?? "");
            if (!unitId || !initial[unitId]) continue;
            handled.add(unitId);
            const jobId = String(record.job_id ?? record.jobId ?? "");
            if (jobId) mapping.set(unitId, jobId);
            const status = String(record.status ?? "");
            if (status === "failed") {
              patchRun(unitId, {
                status: "failed",
                error: String(record.error ?? record.reason ?? ""),
              });
            }
          }
        }

        mapping.forEach((jobId, unitId) => {
          if (!initial[unitId]) return;
          patchRun(unitId, { jobId, status: "queued" });
          watchJob(jobId, unitId);
        });

        const fallbackUnits = selected.filter(
          (unit) => !mapping.has(unit.id) && !handled.has(unit.id),
        );
        if (fallbackUnits.length === 0) return;
        await enqueueFallback(fallbackUnits);
        return;
      }

      // The batch endpoint is not available yet: enqueue each unit from the client.
      await enqueueFallback(selected);
    },
    [
      abortAll,
      canWrite,
      enqueueFallback,
      patchRun,
      remaining,
      running,
      seriesId,
      t,
      units,
      watchJob,
      onNotice,
    ],
  );

  const retry = useCallback(
    async (unitId: string) => {
      const unit = units.find((item) => item.id === unitId);
      if (!unit) return;
      setError("");
      setRunning(true);
      patchRun(unitId, { status: "queued", error: undefined, progress: 0 });
      try {
        const job = await submitJob("unit_generate", {
          unit_id: unit.id,
          topic: unit.title,
          mode: "strict",
          expected_version: unit.current_version,
        });
        patchRun(unitId, { jobId: job.id, status: "queued" });
        watchJob(job.id, unitId);
      } catch (err) {
        patchRun(unitId, {
          status: "failed",
          error: err instanceof Error ? err.message : t("errors.saveFailed"),
        });
        setRunning(false);
      }
    },
    [patchRun, t, units, watchJob],
  );

  const percent = total === 0 ? 0 : Math.round((done / total) * 100);

  return (
    <section className="glass rounded-3xl p-4 shadow-glass sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-500 dark:text-indigo-300">
            <Play size={12} />
            {t("series.progress")}
          </p>
          <div className="mt-1 flex items-baseline gap-2">
            <span
              data-testid="series-progress-count"
              className="text-lg font-semibold tabular-nums text-slate-900 dark:text-white"
            >
              {done} / {total}
            </span>
          </div>
          <div className="mt-2 h-1.5 w-56 max-w-full overflow-hidden rounded-full bg-slate-200/70 dark:bg-white/10">
            <div
              className="h-full rounded-full brand-gradient transition-all"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            data-testid="series-generate-all"
            onClick={() => void start(false)}
            disabled={!canWrite || running || remaining.length === 0}
            className="btn btn-primary"
            title={!canWrite ? t("common.readOnlyRole") : undefined}
          >
            {running && batchMode === "remaining" ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Play size={13} />
            )}
            {t("series.generateAll")}
          </button>
          <button
            type="button"
            data-testid="series-regenerate-all"
            onClick={() => setConfirmOpen(true)}
            disabled={!canWrite || running || units.length === 0}
            className="btn btn-ghost"
            title={!canWrite ? t("common.readOnlyRole") : undefined}
          >
            <RotateCcw size={13} />
            {t("series.regenerateAll")}
          </button>
        </div>
      </div>

      {error ? (
        <div className="mt-3 flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:border-rose-300/20 dark:text-rose-200">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      {order.length > 0 ? (
        <div data-testid="series-generate-progress" className="mt-3 space-y-2">
          <div className="grid gap-1.5 sm:grid-cols-2">
            {order.map((unitId) => {
              const run = runs[unitId];
              if (!run) return null;
              const status = run.status;
              return (
                <button
                  type="button"
                  key={unitId}
                  onClick={() => onOpenUnit?.(unitId)}
                  className={clsx(
                    "flex min-w-0 items-center gap-2 rounded-2xl border px-3 py-2 text-left text-[11px] transition",
                    status === "succeeded"
                      ? "border-emerald-400/35 bg-emerald-400/10 text-emerald-700 dark:text-emerald-200"
                      : status === "failed"
                        ? "border-rose-400/35 bg-rose-500/10 text-rose-700 dark:text-rose-200"
                        : status === "running"
                          ? "border-indigo-400/35 bg-indigo-500/10 text-indigo-700 dark:text-indigo-200"
                          : "border-slate-300/50 bg-white/40 text-slate-600 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-300",
                  )}
                >
                  <span className="shrink-0">
                    {status === "succeeded" ? (
                      <CheckCircle2 size={13} />
                    ) : status === "failed" ? (
                      <XCircle size={13} />
                    ) : status === "running" ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : status === "canceled" ? (
                      <XCircle size={13} />
                    ) : (
                      <Clock3 size={13} />
                    )}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{run.title}</span>
                  <span className="shrink-0 tabular-nums opacity-80">
                    {jobStatusLabel(t, status)}
                  </span>
                </button>
              );
            })}
          </div>

          {failures.length > 0 ? (
            <div className="space-y-1.5 rounded-2xl border border-rose-400/25 bg-rose-500/5 p-2.5">
              {failures.map((run) => (
                <div
                  key={run.unitId}
                  className="flex flex-wrap items-center gap-2 text-[11px] text-rose-700 dark:text-rose-200"
                >
                  <AlertTriangle size={11} className="shrink-0" />
                  <span className="min-w-0 flex-1 truncate">
                    {run.title}
                    {run.error ? ` · ${run.error}` : ""}
                  </span>
                  <button
                    type="button"
                    onClick={() => void retry(run.unitId)}
                    className="btn btn-ghost !px-2 !py-0.5 !text-[10.5px]"
                  >
                    <RefreshCw size={10} />
                    {t("common.retry")}
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <ConfirmDialog
        open={confirmOpen}
        title={t("series.regenerateAll")}
        description={t("series.generateAllConfirm")}
        confirmLabel={t("series.regenerateAll")}
        busy={running}
        onClose={() => setConfirmOpen(false)}
        onConfirm={() => {
          setConfirmOpen(false);
          void start(true);
        }}
      />
    </section>
  );
}
