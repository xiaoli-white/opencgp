import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import clsx from "clsx";
import {
  AlertTriangle,
  BookMarked,
  Check,
  ClipboardCheck,
  Layers,
  Loader2,
  Network,
  Pencil,
  RefreshCw,
  Sparkles,
  Waypoints,
  X,
} from "lucide-react";
import {
  ApiError,
  api,
  type Blueprint,
  type GenerationMode,
  type GlossaryTerm,
  type Unit,
} from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { useSession } from "@/components/auth/SessionProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { modeLabel } from "@/i18n/labels";
import ModePicker from "@/components/series/ModePicker";
import type { VersionConflict } from "@/components/series/ConflictDialog";
import LearningPathTimeline from "@/components/blueprint/LearningPathTimeline";
import GlossaryGrid from "@/components/blueprint/GlossaryGrid";

type BlueprintBoardProps = {
  seriesId: string;
  units: Unit[];
  reloadKey: number;
  onOpenUnit: (unitId: string) => void;
  onUnitsChanged: () => Promise<void>;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onProgressRefresh: () => void;
  onVersionConflict?: (conflict: VersionConflict) => void;
};

export default function BlueprintBoard({
  seriesId,
  units,
  reloadKey,
  onOpenUnit,
  onUnitsChanged,
  onNotice,
  onError,
  onProgressRefresh,
  onVersionConflict,
}: BlueprintBoardProps) {
  const { can } = useSession();
  const { t } = useI18n();
  const readOnly = !can("write");
  const [blueprint, setBlueprint] = useState<Blueprint | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [mode, setMode] = useState<GenerationMode>("strict");
  const [focus, setFocus] = useState("");
  const [topK, setTopK] = useState(5);
  const [generating, setGenerating] = useState(false);
  const [regenerateOpen, setRegenerateOpen] = useState(false);
  const [conflict, setConflict] = useState("");
  const [applying, setApplying] = useState(false);
  const [editingGlossary, setEditingGlossary] = useState(false);
  const [savingGlossary, setSavingGlossary] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const data = await api.getBlueprint(seriesId);
      setBlueprint(data.exists ? data.blueprint : null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : t("blueprint.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [seriesId]);

  useEffect(() => {
    void load();
  }, [load, reloadKey]);

  const unitTitleMap = useMemo(() => {
    const map = new Map<string, string>();
    units.forEach((unit) => map.set(unit.id, unit.title));
    return map;
  }, [units]);

  const blueprintVersion = blueprint?.version ?? null;

  const boundCount = useMemo(
    () => blueprint?.outline.filter((node) => node.unit_id).length ?? 0,
    [blueprint],
  );

  const runGenerate = useCallback(
    async (overrideMode?: GenerationMode, expectedVersion?: number) => {
      const useMode = overrideMode ?? mode;
      const baseline = expectedVersion ?? blueprintVersion;
      setGenerating(true);
      setConflict("");
      onError("");
      try {
        const result = await api.generateBlueprint(seriesId, {
          mode: useMode,
          top_k: topK,
          focus: focus.trim(),
          expected_version: baseline,
        });
        setBlueprint(result);
        setRegenerateOpen(false);
        onNotice(
          result.mode === "loose"
            ? t("blueprint.generatedLoose")
            : t("blueprint.generatedGrounded", { version: result.version }),
        );
        onProgressRefresh();
      } catch (err) {
        const info = err instanceof ApiError ? err.conflict() : null;
        if (info && info.current_version !== undefined && onVersionConflict) {
          const current = info.current_version;
          onVersionConflict({
            expectedVersion: baseline ?? 0,
            currentVersion: current,
            label: t("blueprint.label"),
            retry: () => runGenerate(useMode, current),
          });
        } else if (err instanceof ApiError && err.status === 409) {
          setConflict(err.message);
        } else {
          onError(err instanceof Error ? err.message : t("blueprint.generateFailed"));
        }
      } finally {
        setGenerating(false);
      }
    },
    [
      blueprintVersion,
      seriesId,
      focus,
      mode,
      onError,
      onNotice,
      onProgressRefresh,
      onVersionConflict,
      topK,
    ],
  );

  const handleApply = async () => {
    setApplying(true);
    onError("");
    try {
      const result = await api.applyBlueprint(seriesId);
      setBlueprint(result.blueprint);
      onNotice(
        result.created_count > 0
          ? t("blueprint.appliedCreated", { count: result.created_count })
          : t("blueprint.appliedExisting"),
      );
      await onUnitsChanged();
      onProgressRefresh();
    } catch (err) {
      onError(err instanceof Error ? err.message : t("blueprint.applyFailed"));
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
      setEditingGlossary(false);
      onNotice(t("blueprint.glossarySaved", { count: payload.count }));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("blueprint.glossarySaveFailed"));
    } finally {
      setSavingGlossary(false);
    }
  };

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
      <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_120px_auto]">
        <input
          value={focus}
          onChange={(event) => setFocus(event.target.value)}
          placeholder={t("blueprint.focusPlaceholder")}
          className="input"
        />
        <select
          value={topK}
          onChange={(event) => setTopK(Number(event.target.value))}
          className="select"
        >
          {[3, 5, 8, 12].map((value) => (
            <option key={value} value={value}>
              {t("blueprint.evidenceItems", { count: value })}
            </option>
          ))}
        </select>
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
              {t("blueprint.existingUnits", { count: units.length })}
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

  return (
    <div className="space-y-4">
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
              <span className="chip-muted">v{blueprint.version}</span>
              {blueprint.provider ? (
                <span className="chip-muted">{blueprint.provider}</span>
              ) : null}
              <span className="chip-muted">
                {t("blueprint.updated", { time: formatRelative(blueprint.updated_at) })}
              </span>
            </div>
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
            onClick={() => void handleApply()}
            disabled={readOnly || applying}
            title={readOnly ? t("common.readOnlyRole") : ""}
            className="btn btn-primary"
          >
            {applying ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Check size={14} />
            )}
            {t("blueprint.applyToSeries")}
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
              {t("blueprint.stagesNodes", {
                stages: blueprint.learning_path.length,
                nodes: blueprint.outline.length,
              })}
            </span>
          </div>
          <div className="mt-3">
            <LearningPathTimeline
              blueprint={blueprint}
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
              {t("blueprint.termCount", { count: blueprint.glossary.length })}
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
              {t("blueprint.totalTermsRelated", { count: blueprint.glossary.length })}
              {Array.from(
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
                .join(", ") || t("common.none")}
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
