import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import clsx from "clsx";
import WebEvidenceNotice from "@/components/reader/WebEvidenceNotice";
import {
  AlertTriangle,
  BookMarked,
  Check,
  CheckCheck,
  CheckCircle2,
  ClipboardCheck,
  History,
  Layers,
  Loader2,
  Lock,
  Network,
  Pencil,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Waypoints,
  X,
} from "lucide-react";
import {
  ApiError,
  api,
  evidenceGateError,
  type ApplyBlueprintResult,
  type Blueprint,
  type BlueprintApplyPlan,
  type BlueprintValidationError,
  type BlueprintVersionSummary,
  type EvidenceGatePayload,
  type GenerationMode,
  type GlossaryTerm,
  type Unit,
} from "@/lib/api";
import { getJob, isTerminal, listJobs } from "@/lib/jobs";
import { formatRelative } from "@/lib/format";
import { useSession } from "@/components/auth/SessionProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { modeLabel, pluralLabel } from "@/i18n/labels";
import ModePicker from "@/components/series/ModePicker";
import type { VersionConflict } from "@/components/series/ConflictDialog";
import LearningPathTimeline from "@/components/blueprint/LearningPathTimeline";
import GlossaryGrid from "@/components/blueprint/GlossaryGrid";
import BlueprintEditor from "@/components/blueprint/BlueprintEditor";
import {
  createEditLockController,
  type EditLockController,
  type EditLockState,
} from "@/lib/editLock";

type BlueprintBoardProps = {
  seriesId: string;
  units: Unit[];
  reloadKey: number;
  onOpenUnit: (unitId: string) => void;
  onUnitsChanged: () => Promise<void>;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onProgressRefresh: () => void;
  onUnitsApplied?: (unitIds: string[]) => void;
  onVersionConflict?: (conflict: VersionConflict) => void;
  onDirtyChange?: (dirty: boolean) => void;
};

function pause(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function readApiValidationErrors(error: unknown): {
  errors: BlueprintValidationError[];
  message: string;
} {
  if (!(error instanceof ApiError)) {
    return {
      errors: [],
      message: error instanceof Error ? error.message : "",
    };
  }
  const detail = error.payload?.detail;
  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    const raw = record.errors;
    if (Array.isArray(raw)) {
      const errors = raw
        .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
        .map((item) => ({
          path: String(item.path ?? ""),
          code: String(item.code ?? "invalid"),
          message: String(item.message ?? ""),
        }));
      return {
        errors,
        message: String(record.message ?? error.message),
      };
    }
    if (typeof record.message === "string") {
      return { errors: [], message: record.message };
    }
  }
  return { errors: [], message: error.message };
}

function cloneBlueprint(blueprint: Blueprint): Blueprint {
  return JSON.parse(JSON.stringify(blueprint)) as Blueprint;
}

export default function BlueprintBoard({
  seriesId,
  units,
  reloadKey,
  onOpenUnit,
  onUnitsChanged,
  onNotice,
  onError,
  onProgressRefresh,
  onUnitsApplied,
  onVersionConflict,
  onDirtyChange,
}: BlueprintBoardProps) {
  const { can } = useSession();
  const { t } = useI18n();
  const readOnly = !can("write");
  const [blueprint, setBlueprint] = useState<Blueprint | null>(null);
  const [appliedVersion, setAppliedVersion] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [mode, setMode] = useState<GenerationMode>("strict");
  const [focus, setFocus] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generationJobId, setGenerationJobId] = useState<string | null>(null);
  const [generationProgress, setGenerationProgress] = useState(0);
  const [generationStatus, setGenerationStatus] = useState("");
  const [generationError, setGenerationError] = useState("");
  const [gateError, setGateError] = useState<EvidenceGatePayload | null>(null);
  const [regenerateOpen, setRegenerateOpen] = useState(false);
  const [conflict, setConflict] = useState("");
  const [applying, setApplying] = useState(false);
  const [applyResult, setApplyResult] = useState<ApplyBlueprintResult | null>(null);
  const [applyError, setApplyError] = useState("");
  const [highlightUnitIds, setHighlightUnitIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [editingGlossary, setEditingGlossary] = useState(false);
  const [savingGlossary, setSavingGlossary] = useState(false);
  const [editingBlueprint, setEditingBlueprint] = useState(false);
  const [draft, setDraft] = useState<Blueprint | null>(null);
  const [validationErrors, setValidationErrors] = useState<
    BlueprintValidationError[]
  >([]);
  const [savingBlueprint, setSavingBlueprint] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saveSummary, setSaveSummary] = useState("");
  const [lockState, setLockState] = useState<EditLockState>({ status: "idle" });
  const [versions, setVersions] = useState<BlueprintVersionSummary[]>([]);
  const [versionToRestore, setVersionToRestore] = useState<number | null>(null);
  const [restoringVersion, setRestoringVersion] = useState(false);
  const [applyPlan, setApplyPlan] = useState<BlueprintApplyPlan | null>(null);
  const [previewingApply, setPreviewingApply] = useState(false);
  const lockController = useRef<EditLockController | null>(null);
  const pollToken = useRef(0);

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      setLoadError("");
      try {
        const data = await api.getBlueprint(seriesId);
        setBlueprint(data.exists ? data.blueprint : null);
        setAppliedVersion(
          typeof data.applied_version === "number" ? data.applied_version : null,
        );
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : t("blueprint.loadFailed"));
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [seriesId, t],
  );

  const loadVersions = useCallback(async () => {
    try {
      const payload = await api.listBlueprintVersions(seriesId);
      setVersions(payload.versions ?? []);
    } catch {
      setVersions([]);
    }
  }, [seriesId]);

  useEffect(() => {
    void load(reloadKey > 0);
    void loadVersions();
  }, [load, loadVersions, reloadKey]);

  useEffect(() => {
    const controller = createEditLockController({
      kind: "blueprint",
      id: seriesId,
      onState: setLockState,
      onError: (message) => onError(message),
    });
    lockController.current = controller;
    return () => {
      controller.stop(true);
      lockController.current = null;
    };
  }, [onError, seriesId]);

  const dirty = useMemo(() => {
    if (!draft || !blueprint) return false;
    return JSON.stringify(draft) !== JSON.stringify(blueprint);
  }, [blueprint, draft]);

  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  useEffect(() => {
    onDirtyChange?.(editingBlueprint && dirty);
  }, [dirty, editingBlueprint, onDirtyChange]);

  useEffect(() => {
    return () => onDirtyChange?.(false);
  }, [onDirtyChange]);

  useEffect(() => {
    return () => {
      pollToken.current += 1;
    };
  }, []);

  // Inline validation: the backend reuses the blueprint sanitizer's
  // placeholder detector, so the editor does not keep a second copy of those
  // rules.  Debounced to avoid a request per keystroke.
  useEffect(() => {
    if (!editingBlueprint || !draft) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void api
        .validateBlueprint(seriesId, draft)
        .then((result) => {
          if (!cancelled) setValidationErrors(result.errors ?? []);
        })
        .catch(() => {
          if (!cancelled) setValidationErrors([]);
        });
    }, 450);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [draft, editingBlueprint, seriesId]);

  const unitTitleMap = useMemo(() => {
    const map = new Map<string, string>();
    units.forEach((unit) => map.set(unit.id, unit.title));
    return map;
  }, [units]);

  const blueprintVersion = blueprint?.version ?? null;
  // "Apply" stays disabled while the units already match the current
  // blueprint version, so a no-op apply cannot be clicked again.
  const applyUpToDate =
    blueprintVersion !== null && appliedVersion === blueprintVersion;

  const boundCount = useMemo(
    () => blueprint?.outline.filter((node) => node.unit_id).length ?? 0,
    [blueprint],
  );

  const watchGenerationJob = useCallback(
    async (jobId: string) => {
      const token = ++pollToken.current;
      setGenerationError("");
      while (pollToken.current === token) {
        let job;
        try {
          job = await getJob(jobId);
        } catch (err) {
          if (pollToken.current !== token) return;
          const reason =
            err instanceof Error ? err.message : t("blueprint.generateFailed");
          setGenerating(false);
          setGenerationJobId(null);
          setGenerationError(reason);
          onError(reason);
          return;
        }
        if (pollToken.current !== token) return;
        setGenerationStatus(job.status);
        setGenerationProgress(job.progress ?? 0);
        if (isTerminal(job.status)) {
          setGenerating(false);
          setGenerationJobId(null);
          if (job.status === "succeeded") {
            await load(true);
            setRegenerateOpen(false);
            setGateError(null);
            onNotice(
              t("blueprint.generationSucceeded", {
                version: Number(job.result?.version ?? 0),
              }),
            );
            onProgressRefresh();
          } else {
            const structured = job.result?.error;
            if (
              structured &&
              typeof structured === "object" &&
              typeof (structured as Record<string, unknown>).code === "string"
            ) {
              setGateError(structured as unknown as EvidenceGatePayload);
            } else {
              setGateError(null);
            }
            const reason = job.error || t("blueprint.generateFailed");
            setGenerationError(reason);
            onError(reason);
          }
          return;
        }
        await pause(1200);
      }
    },
    [load, onError, onNotice, onProgressRefresh, t],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await listJobs({ kind: "blueprint_generate", limit: 20 });
        const active = (data.jobs ?? []).find(
          (job) =>
            !isTerminal(job.status) &&
            String(
              (job.payload as Record<string, unknown> | undefined)?.series_id ??
                "",
            ) === seriesId,
        );
        if (!cancelled && active) {
          setGenerating(true);
          setGenerationJobId(active.id);
          setGenerationProgress(active.progress ?? 0);
          setGenerationStatus(active.status);
          void watchGenerationJob(active.id);
        }
      } catch {
        return;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [seriesId, watchGenerationJob]);

  const runGenerate = useCallback(
    async (overrideMode?: GenerationMode) => {
      const useMode = overrideMode ?? mode;
      setGenerating(true);
      setConflict("");
      setGenerationError("");
      setGateError(null);
      setGenerationProgress(0);
      onError("");
      try {
        const envelope = await api.enqueueBlueprintGeneration(seriesId, {
          mode: useMode,
          focus: focus.trim(),
        });
        setGenerationJobId(envelope.job_id);
        setGenerationProgress(envelope.job.progress ?? 0);
        setGenerationStatus(envelope.job.status || "queued");
        if (envelope.duplicate) {
          onNotice(t("blueprint.generationAlreadyRunning"));
        }
        setRegenerateOpen(false);
        void watchGenerationJob(envelope.job_id);
      } catch (err) {
        setGenerating(false);
        setGenerationJobId(null);
        const structured = evidenceGateError(err);
        if (structured) {
          setGateError(structured);
          setGenerationError(structured.message);
        } else if (err instanceof ApiError && err.status === 409) {
          setConflict(err.message);
        } else {
          onError(err instanceof Error ? err.message : t("blueprint.generateFailed"));
        }
      }
    },
    [mode, focus, seriesId, onError, onNotice, t, watchGenerationJob],
  );

  const enterBlueprintEdit = async () => {
    setSaveError("");
    setSaveSummary("");
    const state = await lockController.current?.start();
    if (!state || state.status !== "held") {
      if (state?.status === "blocked") {
        setSaveError(
          t("blueprint.editor.lockedByOther", { name: state.name || "—" }),
        );
      }
      return;
    }
    if (!blueprint) return;
    setDraft(cloneBlueprint(blueprint));
    setValidationErrors([]);
    setEditingBlueprint(true);
  };

  const leaveBlueprintEdit = async (discard: boolean) => {
    if (dirty && !discard) {
      if (!window.confirm(t("blueprint.editor.discardConfirm"))) return;
    }
    setEditingBlueprint(false);
    setDraft(null);
    setValidationErrors([]);
    setSaveError("");
    setEditingGlossary(false);
    await lockController.current?.release();
  };

  const handleSaveBlueprint = async () => {
    if (!draft || !blueprint || savingBlueprint) return;
    setSavingBlueprint(true);
    setSaveError("");
    onError("");
    try {
      const validation = await api.validateBlueprint(seriesId, draft);
      if (!validation.ok) {
        setValidationErrors(validation.errors ?? []);
        setSaveError(validation.message || t("blueprint.editor.invalid"));
        return;
      }
      const saved = await api.saveBlueprint(
        seriesId,
        draft,
        blueprint.version,
        t("blueprint.editor.saveNote"),
      );
      setBlueprint(saved);
      setEditingBlueprint(false);
      setDraft(null);
      setValidationErrors([]);
      setSaveSummary(
        t("blueprint.editor.savedSummary", {
          version: saved.version,
          stages: saved.learning_path.length,
          nodes: saved.outline.length,
          terms: saved.glossary.length,
        }),
      );
      onNotice(
        t("blueprint.editor.savedNotice", {
          version: saved.version,
          stages: saved.learning_path.length,
          nodes: saved.outline.length,
        }),
      );
      lockController.current?.stop(true);
      await loadVersions();
      onProgressRefresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setSaveError(t("blueprint.editor.versionConflict"));
        return;
      }
      const parsed = readApiValidationErrors(err);
      setValidationErrors(parsed.errors);
      const message = parsed.message || t("blueprint.editor.saveFailed");
      setSaveError(message);
      onError(message);
    } finally {
      setSavingBlueprint(false);
    }
  };

  const handleRestoreVersion = async () => {
    if (!versionToRestore || !blueprint || restoringVersion) return;
    if (
      !window.confirm(
        t("blueprint.editor.confirmRestore", { version: versionToRestore }),
      )
    ) {
      return;
    }
    setRestoringVersion(true);
    setSaveError("");
    try {
      const restored = await api.restoreBlueprintVersion(
        seriesId,
        versionToRestore,
        blueprint.version,
      );
      setBlueprint(restored);
      setSaveSummary(
        t("blueprint.editor.restoredSummary", { version: restored.version }),
      );
      await load(true);
      await loadVersions();
      onProgressRefresh();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : t("blueprint.editor.restoreFailed");
      setSaveError(message);
      onError(message);
    } finally {
      setRestoringVersion(false);
    }
  };

  const handlePreviewApply = async () => {
    if (previewingApply || applying) return;
    setPreviewingApply(true);
    setApplyError("");
    setApplyResult(null);
    onError("");
    try {
      const plan = await api.previewBlueprintApply(seriesId);
      setApplyPlan(plan);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : t("blueprint.applyFailed");
      setApplyError(message);
      onError(message);
    } finally {
      setPreviewingApply(false);
    }
  };

  const handleApply = async () => {
    if (!applyPlan || applying) return;
    setApplying(true);
    setApplyResult(null);
    setApplyError("");
    onError("");
    try {
      const result = await api.applyBlueprint(seriesId, {
        confirm_removals: applyPlan.removed.length > 0,
        expected_version: blueprint?.version ?? null,
        plan_token: applyPlan.token,
      });
      setApplyResult(result);
      setApplyPlan(null);
      setBlueprint(result.blueprint);
      setHighlightUnitIds(new Set(result.affected_unit_ids));
      await load(true);
      await loadVersions();
      await onUnitsChanged();
      onProgressRefresh();
      onUnitsApplied?.(result.affected_unit_ids);
      onNotice(
        `${result.status === "partial" ? t("blueprint.applyPartialTitle") : t("blueprint.applySuccessTitle")} · ${t("blueprint.applySummaryCounts", { created: result.created_count, updated: result.updated_count, unchanged: result.unchanged_count })}`,
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const detail = err.payload?.detail;
        if (detail && typeof detail === "object") {
          const record = detail as Record<string, unknown>;
          if (record.code === "apply_requires_confirmation" && record.plan) {
            setApplyPlan(record.plan as unknown as BlueprintApplyPlan);
            setApplyError(t("blueprint.applyConfirmRequired"));
            return;
          }
        }
      }
      const message =
        err instanceof Error ? err.message : t("blueprint.applyFailed");
      setApplyError(message);
      onError(message);
    } finally {
      setApplying(false);
    }
  };

  const handleSaveGlossary = async (terms: GlossaryTerm[]) => {
    setSavingGlossary(true);
    onError("");
    try {
      const payload = await api.saveGlossary(seriesId, terms);
      setBlueprint((prev) =>
        prev ? { ...prev, glossary: payload.glossary } : prev,
      );
      setDraft((prev) =>
        prev ? { ...prev, glossary: payload.glossary } : prev,
      );
      setEditingGlossary(false);
      onNotice(pluralLabel(t, "blueprint.glossarySaved", payload.count));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("blueprint.glossarySaveFailed"));
    } finally {
      setSavingGlossary(false);
    }
  };

  const affectedTitles = applyResult
    ? [...applyResult.created_units, ...applyResult.updated_units].map(
        (unit) => unit.title,
      )
    : [];

  const generationBanner = gateError ? (
    <div
      role="alert"
      data-testid="evidence-gate-error"
      data-code={gateError.code}
      data-searched={gateError.chunks_searched}
      data-best={gateError.best_score}
      data-threshold={gateError.threshold}
      className="rounded-2xl border border-rose-400/50 bg-rose-500/10 px-3.5 py-3 text-[11.5px] leading-relaxed text-rose-700 dark:border-rose-300/25 dark:bg-rose-400/10 dark:text-rose-200"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle size={14} className="mt-0.5 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{t("blueprint.gateTitle")}</p>
          <p className="mt-1" data-testid="evidence-gate-reason">
            {t("blueprint.gateReason", {
              topic: gateError.topic || "—",
              searched: gateError.chunks_searched,
              best: Number(gateError.best_score ?? 0).toFixed(3),
              threshold: Number(gateError.threshold ?? 0).toFixed(3),
              usable: gateError.usable_passages,
              required: gateError.min_passages,
            })}
          </p>
          {(gateError.off_topic_passages ?? 0) > 0 ? (
            <p className="mt-1" data-testid="evidence-gate-off-topic">
              {t("blueprint.gateOffTopic", {
                count: gateError.off_topic_passages ?? 0,
                sources:
                  (
                    (gateError.off_topic_local_sources ?? []).length > 0
                      ? gateError.off_topic_local_sources
                      : gateError.off_topic_sources
                  )?.join(", ") || "—",
              })}
            </p>
          ) : null}
          {(gateError.topic_terms ?? []).length > 0 ? (
            <p className="mt-1 opacity-80" data-testid="evidence-gate-topic-terms">
              {t("blueprint.gateTopicTerms", {
                terms: (gateError.topic_terms ?? []).join(", "),
              })}
            </p>
          ) : null}
          <p className="mt-1 opacity-80" data-testid="evidence-gate-next-step">
            {t("blueprint.gateNextStep")}
          </p>
          <p className="mt-1 font-mono text-[10.5px] opacity-70">
            {t("blueprint.gateCode", { code: gateError.code })}
          </p>
          <WebEvidenceNotice gate={gateError} />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Link to="/kb" className="btn btn-primary btn-xs">
              {t("blueprint.gateOpenKb")}
            </Link>
            <button
              type="button"
              className="btn btn-ghost btn-xs"
              onClick={() => void runGenerate()}
            >
              {t("blueprint.gateRetry")}
            </button>
          </div>
        </div>
        <button
          type="button"
          onClick={() => {
            setGateError(null);
            setGenerationError("");
          }}
          className="grid h-6 w-6 shrink-0 place-items-center rounded-full opacity-70 transition hover:bg-black/5 hover:opacity-100 dark:hover:bg-white/10"
          aria-label={t("blueprint.dismissNotice")}
        >
          <X size={12} />
        </button>
      </div>
    </div>
  ) : generating || generationError ? (
      <div
        role="status"
        data-testid="blueprint-generation-status"
        data-status={generationStatus}
        data-progress={Math.round(generationProgress * 100)}
        data-job-id={generationJobId ?? ""}
        className={clsx(
          "flex items-start gap-2 rounded-2xl border px-3.5 py-2.5 text-[11.5px] leading-relaxed",
          generationError
            ? "border-rose-400/40 bg-rose-500/10 text-rose-700 dark:border-rose-300/25 dark:bg-rose-400/10 dark:text-rose-300"
            : "border-indigo-400/40 bg-indigo-500/10 text-indigo-700 dark:border-indigo-300/25 dark:bg-indigo-400/10 dark:text-indigo-200",
        )}
      >
        {generating ? (
          <Loader2 size={14} className="mt-0.5 shrink-0 animate-spin" />
        ) : (
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <p className="font-medium">
            {generating
              ? generationJobId
                ? t("blueprint.generationRunning", {
                    progress: Math.round(generationProgress * 100),
                  })
                : t("blueprint.generationQueued")
              : t("blueprint.generationFailed", { reason: generationError })}
          </p>
          {generating && generationJobId ? (
            <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-indigo-500/15">
              <div
                className="h-full rounded-full bg-indigo-500 transition-all"
                style={{ width: `${Math.max(4, Math.round(generationProgress * 100))}%` }}
              />
            </div>
          ) : null}
          <p className="mt-1 opacity-80">
            {t("blueprint.generationJobHint")}
            {" · "}
            <Link to="/jobs" className="underline underline-offset-2">
              {t("blueprint.generationJobLink")}
            </Link>
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            pollToken.current += 1;
            setGenerating(false);
            setGenerationJobId(null);
            setGenerationError("");
          }}
          className="grid h-6 w-6 shrink-0 place-items-center rounded-full opacity-70 transition hover:bg-black/5 hover:opacity-100 dark:hover:bg-white/10"
          aria-label={t("blueprint.dismissNotice")}
        >
          <X size={12} />
        </button>
      </div>
    ) : null;

  const applyBanner = applying ? (
    <div
      role="status"
      data-testid="blueprint-apply-progress"
      className="flex items-start gap-2 rounded-2xl border border-indigo-400/40 bg-indigo-500/10 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-indigo-700 dark:border-indigo-300/25 dark:bg-indigo-400/10 dark:text-indigo-200"
    >
      <Loader2 size={14} className="mt-0.5 shrink-0 animate-spin" />
      <span>{t("blueprint.applying")}</span>
    </div>
  ) : applyError ? (
    <div
      role="alert"
      data-testid="blueprint-apply-error"
      className="flex items-start gap-2 rounded-2xl border border-rose-400/40 bg-rose-500/10 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-rose-700 dark:border-rose-300/25 dark:bg-rose-400/10 dark:text-rose-300"
    >
      <AlertTriangle size={14} className="mt-0.5 shrink-0" />
      <span className="min-w-0 flex-1">
        {t("blueprint.applyFailedReason", { reason: applyError })}
      </span>
      <button
        type="button"
        onClick={() => setApplyError("")}
        className="grid h-6 w-6 shrink-0 place-items-center rounded-full opacity-70 transition hover:bg-black/5 hover:opacity-100 dark:hover:bg-white/10"
        aria-label={t("blueprint.dismissNotice")}
      >
        <X size={12} />
      </button>
    </div>
  ) : applyResult ? (
    <div
      role="status"
      data-testid="blueprint-apply-summary"
      data-status={applyResult.status}
      data-created={applyResult.created_count}
      data-updated={applyResult.updated_count}
      data-unchanged={applyResult.unchanged_count}
      data-stages={applyResult.stage_count}
      data-nodes={applyResult.node_count}
      data-affected={applyResult.affected_unit_ids.length}
      className={clsx(
        "flex items-start gap-2 rounded-2xl border px-3.5 py-2.5 text-[11.5px] leading-relaxed",
        applyResult.status === "partial"
          ? "border-amber-400/40 bg-amber-400/15 text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-200"
          : "border-emerald-400/40 bg-emerald-500/10 text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-400/10 dark:text-emerald-300",
      )}
    >
      {applyResult.status === "partial" ? (
        <AlertTriangle size={14} className="mt-0.5 shrink-0" />
      ) : (
        <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-semibold">
            {applyResult.status === "partial"
              ? t("blueprint.applyPartialTitle")
              : t("blueprint.applySuccessTitle")}
          </p>
          <span className="chip-muted">
            {applyResult.status === "partial"
              ? t("blueprint.applySummaryStatusPartial")
              : t("blueprint.applySummaryStatusSucceeded")}
          </span>
        </div>
        <p className="mt-1" data-testid="blueprint-apply-counts">
          {t("blueprint.applySummaryCounts", {
            created: applyResult.created_count,
            updated: applyResult.updated_count,
            unchanged: applyResult.unchanged_count,
          })}
        </p>
        <p>
          {t("blueprint.applySummaryLanding", {
            stages: applyResult.stage_count,
            nodes: applyResult.node_count,
          })}
        </p>
        <p>
          {affectedTitles.length > 0
            ? t("blueprint.applyAffectedUnits", {
                units: affectedTitles.slice(0, 6).join(", "),
              })
            : t("blueprint.applyNoAffectedUnits")}
        </p>
        {applyResult.failures.length > 0 ? (
          <ul className="mt-1 list-disc pl-4">
            {applyResult.failures.slice(0, 5).map((failure) => (
              <li key={failure.node_id || failure.title}>
                {t("blueprint.applyPartialReason", {
                  reason: `${failure.title || failure.node_id}: ${failure.reason}`,
                })}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <button
        type="button"
        onClick={() => setApplyResult(null)}
        className="grid h-6 w-6 shrink-0 place-items-center rounded-full opacity-70 transition hover:bg-black/5 hover:opacity-100 dark:hover:bg-white/10"
        aria-label={t("blueprint.dismissNotice")}
      >
        <X size={12} />
      </button>
    </div>
  ) : null;


  const applyPlanPanel = applyPlan ? (
    <div
      role="dialog"
      aria-modal="false"
      data-testid="blueprint-apply-diff"
      className="rounded-2xl border border-indigo-400/40 bg-indigo-500/5 p-3.5 text-[11.5px] leading-relaxed text-slate-700 dark:border-indigo-300/25 dark:bg-indigo-400/5 dark:text-slate-200"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold text-indigo-700 dark:text-indigo-200">
          {t("blueprint.applyDiffTitle")}
        </p>
        <span className="chip-muted">
          {t("blueprint.applyDiffVersion", {
            version: applyPlan.blueprint_version,
          })}
        </span>
      </div>
      <p className="mt-1 text-[10.5px] text-slate-500 dark:text-slate-400">
        {t("blueprint.applyDiffHint")}
      </p>

      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <DiffGroup
          label={t("blueprint.applyDiffCreated", {
            count: applyPlan.created.length,
          })}
          items={applyPlan.created.map((item) => item.title)}
          empty={t("blueprint.applyDiffNothing")}
        />
        <DiffGroup
          label={t("blueprint.applyDiffRenamed", {
            count: applyPlan.renamed.length,
          })}
          items={applyPlan.renamed.map((item) => `${item.from} → ${item.to}`)}
          empty={t("blueprint.applyDiffNothing")}
        />
        <DiffGroup
          label={t("blueprint.applyDiffUpdated", {
            count: applyPlan.updated.length,
          })}
          items={applyPlan.updated.map((item) => item.title)}
          empty={t("blueprint.applyDiffNothing")}
        />
        <DiffGroup
          label={t("blueprint.applyDiffRemoved", {
            count: applyPlan.removed.length,
          })}
          items={applyPlan.removed.map((item) => item.title)}
          empty={t("blueprint.applyDiffNothing")}
        />
      </div>

      {applyPlan.kept_unlinked.length > 0 ? (
        <p className="mt-2 text-[10.5px] text-slate-500 dark:text-slate-400">
          {t("blueprint.applyDiffKept", {
            count: applyPlan.kept_unlinked.length,
          })}
        </p>
      ) : null}

      {(() => {
        const preserved = [...applyPlan.renamed, ...applyPlan.updated].filter(
          (item) => item.has_content,
        ).length;
        return preserved > 0 ? (
          <p className="mt-2 text-[10.5px] text-emerald-700 dark:text-emerald-300">
            {t("blueprint.applyDiffContentPreserved", { count: preserved })}
          </p>
        ) : null;
      })()}

      {applyPlan.removed.length > 0 ? (
        <div className="mt-2 rounded-xl border border-amber-400/40 bg-amber-400/10 px-2.5 py-2 text-[10.5px] text-amber-800 dark:border-amber-300/25 dark:text-amber-200">
          <p className="font-medium">{t("blueprint.applyDiffRemovalWarning")}</p>
          {applyPlan.content_loss.length > 0 ? (
            <p data-testid="blueprint-apply-content-loss" className="mt-1">
              {t("blueprint.applyDiffContentLoss", {
                units: applyPlan.content_loss
                  .map((item) => `${item.title} (${item.content_chars})`)
                  .join(", "),
              })}
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          data-testid="blueprint-apply-confirm"
          onClick={() => void handleApply()}
          disabled={applying}
          className="btn btn-primary"
        >
          {applying ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Check size={14} />
          )}
          {applying
            ? t("blueprint.applying")
            : applyPlan.removed.length > 0
              ? t("blueprint.applyConfirmRemovals")
              : t("blueprint.applyConfirm")}
        </button>
        <button
          type="button"
          onClick={() => setApplyPlan(null)}
          disabled={applying}
          className="btn btn-ghost"
        >
          <X size={14} />
          {t("blueprint.applyDiffCancel")}
        </button>
      </div>
    </div>
  ) : null;

  const generatePanel = (
    <div className="rounded-2xl border border-indigo-200/60 bg-indigo-500/5 p-4 dark:border-indigo-400/20 dark:bg-indigo-400/5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] font-medium text-indigo-600 dark:text-indigo-300">
          {mode === "loose" ? t("blueprint.looseHint") : t("blueprint.strictHint")}
        </p>
        <span className="chip-muted">{t("blueprint.planningMode")}</span>
      </div>
      <div className="mt-3">
        <ModePicker value={mode} onChange={setMode} disabled={generating} />
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto]">
        <input
          value={focus}
          onChange={(event) => setFocus(event.target.value)}
          placeholder={t("blueprint.focusPlaceholder")}
          className="input"
        />
        <button
          type="button"
          onClick={() => void runGenerate()}
          disabled={readOnly || generating}
          title={readOnly ? t("common.readOnlyRole") : ""}
          className="btn btn-primary"
        >
          {generating ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Sparkles size={14} />
          )}
          {t("blueprint.generate")}
        </button>
      </div>
    </div>
  );

  const conflictBar = conflict ? (
    <div className="flex flex-wrap items-start gap-2 rounded-2xl border border-amber-400/40 bg-amber-400/15 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-200">
      <AlertTriangle size={14} className="mt-0.5 shrink-0" />
      <span className="min-w-0 flex-1 whitespace-pre-line">{conflict}</span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => {
            setMode("loose");
            void runGenerate("loose");
          }}
          disabled={generating}
          className="btn btn-ghost !px-2.5 !py-1 text-[10.5px]"
        >
          {generating ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            <RefreshCw size={11} />
          )}
          {t("blueprint.retryLoose")}
        </button>
        <button
          type="button"
          onClick={() => setConflict("")}
          className="grid h-6 w-6 place-items-center rounded-full text-amber-600/70 transition hover:bg-amber-500/15 hover:text-amber-700 dark:text-amber-300/70"
          aria-label={t("blueprint.dismissNotice")}
        >
          <X size={12} />
        </button>
      </div>
    </div>
  ) : null;

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="glass h-40 animate-pulse rounded-3xl" />
        <div className="glass h-72 animate-pulse rounded-3xl" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="glass rounded-3xl p-8 text-center shadow-glass">
        <div className="mx-auto grid h-11 w-11 place-items-center rounded-2xl bg-rose-500/10 text-rose-500">
          <AlertTriangle size={18} />
        </div>
        <p className="mt-3 text-sm font-medium text-slate-700 dark:text-slate-200">
          {t("blueprint.loadErrorTitle")}
        </p>
        <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          {loadError}
        </p>
        <button type="button" onClick={() => void load()} className="btn btn-ghost mt-4">
          <RefreshCw size={13} />
          {t("common.retry")}
        </button>
      </div>
    );
  }

  if (!blueprint) {
    return (
      <div className="space-y-4">
        {generationBanner}
        <div className="glass rounded-3xl p-6 shadow-glass sm:p-8">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="brand-gradient grid h-9 w-9 place-items-center rounded-2xl text-white shadow-brand">
                  <Waypoints size={16} />
                </span>
                <div>
                  <p className="text-[15px] font-semibold tracking-tight text-slate-800 dark:text-slate-100">
                    {t("blueprint.emptyTitle")}
                  </p>
                  <p className="text-[11px] text-slate-400 dark:text-slate-500">
                    {t("blueprint.emptyDesc")}
                  </p>
                </div>
              </div>
              <p className="mt-3 max-w-xl text-[12.5px] leading-relaxed text-slate-500 dark:text-slate-400">
                {t("blueprint.emptyBody")}
              </p>
            </div>
            <span className="chip-muted">
              {pluralLabel(t, "blueprint.existingUnits", units.length)}
            </span>
          </div>

          <div className="mt-5 space-y-3">
            {conflictBar}
            {generatePanel}
          </div>
        </div>
      </div>
    );
  }

  const loose = blueprint.mode === "loose";

  if (editingBlueprint && draft) {
    return (
      <div className="space-y-4">
        {lockState.status === "blocked" ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-2xl border border-amber-400/40 bg-amber-400/15 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-amber-800 dark:border-amber-300/25 dark:text-amber-200"
          >
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>
              {t("blueprint.editor.lockedByOther", { name: lockState.name })}
            </span>
          </div>
        ) : null}
        <BlueprintEditor
          draft={draft}
          onChange={setDraft}
          errors={validationErrors}
          saving={savingBlueprint}
          saveError={saveError}
          onChangeGlossary={() => setEditingGlossary((value) => !value)}
          onSave={() => void handleSaveBlueprint()}
          onCancel={() => void leaveBlueprintEdit(false)}
        />
        {editingGlossary ? (
          <div className="glass rounded-3xl p-4 shadow-glass sm:p-5">
            <div className="flex items-center justify-between gap-2 px-1">
              <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
                <BookMarked size={12} />
                {t("blueprint.glossary")}
              </p>
              <span className="chip-muted">
                {pluralLabel(t, "blueprint.termCount", draft.glossary.length)}
              </span>
            </div>
            <div className="mt-3">
              <GlossaryGrid
                glossary={draft.glossary}
                editing
                saving={savingGlossary}
                onSave={(terms) => void handleSaveGlossary(terms)}
                onCancel={() => setEditingGlossary(false)}
              />
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {generationBanner}
      {applyBanner}
      {saveSummary ? (
        <div
          role="status"
          data-testid="blueprint-save-summary"
          className="flex items-start gap-2 rounded-2xl border border-emerald-400/40 bg-emerald-500/10 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-400/10 dark:text-emerald-300"
        >
          <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
          <span className="min-w-0 flex-1">{saveSummary}</span>
          <button
            type="button"
            onClick={() => setSaveSummary("")}
            className="grid h-6 w-6 shrink-0 place-items-center rounded-full opacity-70 transition hover:bg-black/5 hover:opacity-100 dark:hover:bg-white/10"
            aria-label={t("blueprint.dismissNotice")}
          >
            <X size={12} />
          </button>
        </div>
      ) : null}
      {lockState.status === "blocked" ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-2xl border border-amber-400/40 bg-amber-400/15 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-amber-800 dark:border-amber-300/25 dark:text-amber-200"
        >
          <Lock size={14} className="mt-0.5 shrink-0" />
          <span>
            {t("blueprint.editor.lockedByOther", { name: lockState.name })}
          </span>
        </div>
      ) : null}
      <div className="glass rounded-3xl p-5 shadow-glass sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="chip">
                <Network size={11} />
                {t("blueprint.title")}
              </span>
              <span
                className={clsx(
                  "rounded-full px-2 py-0.5 text-[10px] font-medium ring-1",
                  loose
                    ? "bg-amber-400/20 text-amber-700 ring-amber-400/30 dark:bg-amber-300/12 dark:text-amber-300 dark:ring-amber-300/20"
                    : "bg-indigo-500/12 text-indigo-600 ring-indigo-400/25 dark:bg-indigo-400/14 dark:text-indigo-300 dark:ring-indigo-300/25",
                )}
              >
                {t("blueprint.modeSuffix", { mode: modeLabel(t, blueprint.mode) })}
              </span>
              <span
                className={clsx(
                  "rounded-full px-2 py-0.5 text-[10px] font-medium ring-1",
                  blueprint.grounded
                    ? "bg-emerald-500/12 text-emerald-700 ring-emerald-500/25 dark:bg-emerald-400/15 dark:text-emerald-300 dark:ring-emerald-300/25"
                    : "bg-slate-400/15 text-slate-600 ring-slate-400/25 dark:bg-white/10 dark:text-slate-300 dark:ring-white/15",
                )}
              >
                {blueprint.grounded ? t("blueprint.grounded") : t("blueprint.noEvidence")}
              </span>
              {typeof blueprint.evidence_count === "number" ? (
                <span
                  className="chip-muted"
                  data-testid="blueprint-evidence-count"
                >
                  {t("blueprint.evidenceCount", {
                    count: blueprint.evidence_count,
                  })}
                </span>
              ) : null}
              <span className="chip-muted">
                {t("common.versionTag", { version: blueprint.version })}
              </span>
              {blueprint.provider ? (
                <span className="chip-muted">{blueprint.provider}</span>
              ) : null}
              <span className="chip-muted">
                {t("blueprint.updated", { time: formatRelative(blueprint.updated_at) })}
              </span>
            </div>
            <WebEvidenceNotice gate={blueprint.gate} />
            <div className="mt-3 text-[13px] leading-relaxed text-slate-600 dark:text-slate-300 [&_p+p]:mt-2 [&_p]:leading-relaxed [&_strong]:font-semibold [&_strong]:text-slate-800 dark:[&_strong]:text-slate-100 [&_ul]:mt-2 [&_ul]:list-disc [&_ul]:pl-5">
              {blueprint.overview ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {blueprint.overview}
                </ReactMarkdown>
              ) : (
                <p className="text-slate-400 dark:text-slate-500">
                  {t("blueprint.noOverview")}
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
          {[
            {
              icon: Layers,
              labelKey: "blueprint.learningStages",
              label: t("blueprint.learningStages"),
              value: blueprint.learning_path.length,
            },
            {
              icon: Waypoints,
              labelKey: "blueprint.outlineNodes",
              label: t("blueprint.outlineNodes"),
              value: blueprint.outline.length,
            },
            {
              icon: ClipboardCheck,
              labelKey: "blueprint.linkedUnits",
              label: t("blueprint.linkedUnits"),
              value: boundCount,
            },
            {
              icon: BookMarked,
              labelKey: "blueprint.terms",
              label: t("blueprint.terms"),
              value: blueprint.glossary.length,
            },
          ].map((item) => (
            <div
              key={item.labelKey}
              className="rounded-2xl border border-slate-200/70 bg-white/50 px-3 py-2 dark:border-white/10 dark:bg-white/[0.04]"
            >
              <p className="flex items-center gap-1 text-[10px] uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
                <item.icon size={11} />
                {item.label}
              </p>
              <p className="mt-0.5 text-[17px] font-semibold text-slate-800 dark:text-slate-100">
                {item.value}
              </p>
            </div>
          ))}
        </div>

        {blueprint.warning || loose || !blueprint.grounded ? (
          <div className="mt-3 flex items-start gap-2 rounded-2xl border border-amber-400/40 bg-amber-400/12 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-200">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>
              {blueprint.warning
                ? blueprint.warning
                : loose
                  ? t("blueprint.warningLoose")
                  : t("blueprint.warningNoEvidence")}
            </span>
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-200/70 pt-3.5 dark:border-white/10">
          <button
            type="button"
            data-testid="blueprint-edit-button"
            onClick={() => void enterBlueprintEdit()}
            disabled={readOnly || lockState.status === "acquiring"}
            title={readOnly ? t("common.readOnlyRole") : ""}
            className="btn btn-ghost"
          >
            {lockState.status === "acquiring" ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Pencil size={14} />
            )}
            {t("blueprint.editBlueprint")}
          </button>
          <button
            type="button"
            onClick={() => void handlePreviewApply()}
            disabled={readOnly || applying || previewingApply || applyUpToDate}
            title={
              readOnly
                ? t("common.readOnlyRole")
                : applyUpToDate && blueprintVersion !== null
                  ? t("blueprint.applyUpToDate", { version: blueprintVersion })
                  : ""
            }
            className="btn btn-primary"
          >
            {applying || previewingApply ? (
              <Loader2 size={14} className="animate-spin" />
            ) : applyUpToDate ? (
              <CheckCheck size={14} />
            ) : (
              <Check size={14} />
            )}
            {applyUpToDate && blueprintVersion !== null
              ? t("blueprint.appliedVersion", { version: blueprintVersion })
              : t("blueprint.applyToSeries")}
          </button>
          <button
            type="button"
            onClick={() => setRegenerateOpen((value) => !value)}
            disabled={readOnly || generating}
            title={readOnly ? t("common.readOnlyRole") : ""}
            className="btn btn-ghost"
          >
            {generating ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
            {t("blueprint.regenerate")}
          </button>
          <button
            type="button"
            onClick={() => setEditingGlossary((value) => !value)}
            disabled={readOnly}
            title={readOnly ? t("common.readOnlyRole") : ""}
            className="btn btn-ghost"
          >
            <Pencil size={14} />
            {editingGlossary ? t("blueprint.exitEditing") : t("blueprint.editGlossary")}
          </button>
          <span className="ml-auto text-[10.5px] text-slate-400 dark:text-slate-500">
            {t("blueprint.applyHint")}
          </span>
        </div>

        {versions.length > 0 ? (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200/70 bg-white/40 px-3 py-2 text-[11px] dark:border-white/10 dark:bg-white/[0.03]">
            <History size={13} className="shrink-0 text-slate-400" />
            <span className="text-slate-500 dark:text-slate-400">
              {t("blueprint.versionHistory")}
            </span>
            <select
              value={versionToRestore ?? blueprint.version}
              onChange={(event) =>
                setVersionToRestore(Number(event.target.value))
              }
              className="input min-w-0 max-w-full flex-1 !py-1 text-[11px] sm:!w-auto sm:flex-none"
            >
              {versions.map((version) => (
                <option key={version.version} value={version.version}>
                  {t("blueprint.versionOption", {
                    version: version.version,
                    source:
                      version.change_source === "manual" ||
                      version.change_source === "restore"
                        ? t("blueprint.versionManual")
                        : t("blueprint.versionGenerated"),
                  })}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => void handleRestoreVersion()}
              disabled={
                readOnly ||
                restoringVersion ||
                !versionToRestore ||
                versionToRestore === blueprint.version
              }
              className="btn btn-ghost shrink-0"
            >
              {restoringVersion ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <RotateCcw size={13} />
              )}
              {t("blueprint.restoreVersion")}
            </button>
          </div>
        ) : null}

        {applyPlanPanel}

        <AnimatePresence initial={false}>
          {(regenerateOpen || conflict) && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.22 }}
              className="overflow-hidden"
            >
              <div className="mt-3 space-y-2.5">
                {conflictBar}
                {regenerateOpen ? generatePanel : null}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div className="glass rounded-3xl p-4 shadow-glass sm:p-5">
          <div className="flex items-center justify-between px-1">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
              <Waypoints size={12} />
              {t("blueprint.learningPath")}
            </p>
            <span className="chip-muted">
              {pluralLabel(t, "blueprint.stageCount", blueprint.learning_path.length)}
              <span className="px-1">·</span>
              {pluralLabel(t, "blueprint.nodeCount", blueprint.outline.length)}
            </span>
          </div>
          <div className="mt-3">
            <LearningPathTimeline
              blueprint={blueprint}
              highlightedUnitIds={highlightUnitIds}
              onOpenUnit={onOpenUnit}
            />
          </div>
        </div>

        <div className="glass rounded-3xl p-4 shadow-glass sm:p-5">
          <div className="flex items-center justify-between px-1">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
              <BookMarked size={12} />
              {t("blueprint.glossary")}
            </p>
            <span className="chip-muted">
              {pluralLabel(t, "blueprint.termCount", blueprint.glossary.length)}
            </span>
          </div>
          <div className="mt-3">
            <GlossaryGrid
              glossary={blueprint.glossary}
              editing={editingGlossary}
              saving={savingGlossary}
              onSave={(terms) => void handleSaveGlossary(terms)}
              onCancel={() => setEditingGlossary(false)}
            />
          </div>
          {!editingGlossary && blueprint.glossary.length > 0 ? (
            <p className="mt-2 px-1 text-[10px] text-slate-400 dark:text-slate-500">
              {pluralLabel(t, "blueprint.totalTermsRelated", blueprint.glossary.length)}
              <span className="px-1">·</span>
              {t("blueprint.relatedUnits", {
                units:
                  Array.from(
                    new Set(
                      blueprint.glossary.flatMap((term) =>
                        term.node_ids
                          .map((nodeId) => {
                            const node = blueprint.outline.find(
                              (item) => item.id === nodeId,
                            );
                            return node?.unit_id
                              ? unitTitleMap.get(node.unit_id) ?? ""
                              : "";
                          })
                          .filter(Boolean),
                      ),
                    ),
                  )
                    .slice(0, 3)
                    .join(", ") || t("common.none"),
              })}
            </p>
          ) : null}
        </div>
      </div>

      <div className="flex justify-center">
        <button
          type="button"
          onClick={() => onOpenUnit(units[0]?.id ?? "")}
          disabled={!units[0]?.id}
          className="btn-quiet"
        >
          {t("blueprint.backToReader")}
        </button>
      </div>
    </div>
  );
}

function DiffGroup({
  label,
  items,
  empty,
}: {
  label: string;
  items: string[];
  empty: string;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-200/60 bg-white/50 px-2.5 py-2 dark:border-white/10 dark:bg-white/[0.03]">
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-400 dark:text-slate-500">
        {label}
      </p>
      {items.length > 0 ? (
        <ul className="mt-1 space-y-0.5 break-words">
          {items.slice(0, 8).map((item, index) => (
            <li key={`${item}-${index}`} className="min-w-0 break-words text-[11px]">
              {item}
            </li>
          ))}
          {items.length > 8 ? (
            <li className="text-[10px] text-slate-400">+{items.length - 8}</li>
          ) : null}
        </ul>
      ) : (
        <p className="mt-1 text-[10.5px] text-slate-400 dark:text-slate-500">
          {empty}
        </p>
      )}
    </div>
  );
}
