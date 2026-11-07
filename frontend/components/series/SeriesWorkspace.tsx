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
  Link2,
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
  Wand2,
  X,
} from "lucide-react";
import clsx from "clsx";
import {
  ApiError,
  api,
  type SeriesDetail,
  type SeriesProgress,
  type GenerationMode,
  type UnitVersion,
} from "@/lib/api";
import {
  createEditLockController,
  lockStateFromRead,
  releaseEditLockBeacon,
  type EditLockController,
  type EditLockState,
} from "@/lib/editLock";
import { contentLength, formatRelative } from "@/lib/format";
import {
  difficultyLabel,
  profileNameLabel,
  roleLabel,
  unitNameLabel,
  unitStatusLabel,
  modeLabel,
  languageLabel,
} from "@/i18n/labels";
import { useI18n } from "@/i18n/I18nProvider";
import MarkdownReader from "@/components/reader/MarkdownReader";
import SeriesReader from "@/components/reader/SeriesReader";
import VersionPanel from "@/components/reader/VersionPanel";
import ChatPanel from "@/components/chat/ChatPanel";
import ModePicker from "@/components/series/ModePicker";
import BlueprintBoard from "@/components/blueprint/BlueprintBoard";
import ReviewControls from "@/components/series/ReviewControls";
import CodeCheckPanel from "@/components/series/CodeCheckPanel";
import SeriesGrantsPanel from "@/components/series/SeriesGrantsPanel";
import ShareLinksDialog from "@/components/share/ShareLinksDialog";
import StatusBadge from "@/components/series/StatusBadge";
import EditLockChip from "@/components/series/EditLockChip";
import SeriesGenerateAllPanel from "@/components/series/SeriesGenerateAllPanel";
import ExportMenu from "@/components/export/ExportMenu";
import SeriesEditDialog from "@/components/series/SeriesEditDialog";
import ThreadsPanel from "@/components/series/ThreadsPanel";
import { useWorkProfiles } from "@/components/profiles/ProfileSelect";
import {
  ConfirmDialog,
  PromptDialog,
  RowMenu,
} from "@/components/common/Dialogs";
import ConflictDialog, {
  type VersionConflict,
} from "@/components/series/ConflictDialog";
import { useSession } from "@/components/auth/SessionProvider";

type WorkspaceView = "reader" | "blueprint" | "continuous";

const VIEWS: { value: WorkspaceView; key: string; icon: typeof BookOpen }[] = [
  { value: "reader", key: "viewReader", icon: BookOpen },
  { value: "blueprint", key: "viewBlueprint", icon: Network },
  { value: "continuous", key: "viewContinuous", icon: ScrollText },
];

export default function SeriesWorkspace({ seriesId }: { seriesId: string }) {
  const { can, roleKey, roleName, me } = useSession();
  const { t } = useI18n();
  const canWrite = can("write");
  const canManage = can("manage_members");
  const readOnly = !canWrite;
  const [detail, setDetail] = useState<SeriesDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [versions, setVersions] = useState<UnitVersion[]>([]);
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
  const [shareLinksOpen, setShareLinksOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [versionTick, setVersionTick] = useState(0);
  const [view, setView] = useState<WorkspaceView>("reader");
  const [progress, setProgress] = useState<SeriesProgress | null>(null);
  const [blueprintTick, setBlueprintTick] = useState(0);
  const [lockState, setLockState] = useState<EditLockState>({
    status: "idle",
  });
  const [editingUnitId, setEditingUnitId] = useState<string | null>(null);
  const [unitDraft, setUnitDraft] = useState("");
  const [savingUnit, setSavingUnit] = useState(false);
  const [conflict, setConflict] = useState<VersionConflict | null>(null);
  const [conflictBusy, setConflictBusy] = useState(false);
  const [seriesEditOpen, setSeriesEditOpen] = useState(false);
  const [seriesDeleteOpen, setSeriesDeleteOpen] = useState(false);
  const [seriesBusy, setSeriesBusy] = useState(false);
  const [seriesDialogError, setSeriesDialogError] = useState("");
  const [unitRename, setUnitRename] = useState<{ id: string; title: string } | null>(
    null,
  );
  const [unitDelete, setUnitDelete] = useState<{ id: string; title: string } | null>(
    null,
  );
  const [unitBusy, setUnitBusy] = useState(false);
  const [unitDialogError, setUnitDialogError] = useState("");
  const { profiles } = useWorkProfiles();
  const navigate = useNavigate();
  const lockController = useRef<EditLockController | null>(null);
  const editingUnitRef = useRef<string | null>(null);

  useEffect(() => {
    editingUnitRef.current = editingUnitId;
  }, [editingUnitId]);

  const lockBlocked =
    canWrite && (lockState.status === "blocked" || lockState.status === "lost");
  const lockReason =
    lockState.status === "blocked"
      ? t("series.lockEditing", { name: lockState.name })
      : t("series.lockLost");
  const guard = readOnly
    ? { disabled: true, title: t("series.guardReadOnly") }
    : lockBlocked
      ? { disabled: true, title: lockReason }
      : {};

  const loadSeries = useCallback(
    async (preferred?: string | null) => {
      const data = await api.getSeries(seriesId);
      setDetail(data);
      setActiveId((prev) => {
        const candidate = preferred ?? prev;
        if (candidate && data.units.some((unit) => unit.id === candidate)) {
          return candidate;
        }
        return data.units[0]?.id ?? null;
      });
      return data;
    },
    [seriesId],
  );

  const refreshProgress = useCallback(async () => {
    try {
      const data = await api.getProgress(seriesId);
      setProgress(data);
    } catch {
      setProgress(null);
    }
  }, [seriesId]);

  const refreshWorkspace = useCallback(async () => {
    await loadSeries(activeId);
    await refreshProgress();
    setVersionTick((tick) => tick + 1);
    setBlueprintTick((tick) => tick + 1);
  }, [activeId, loadSeries, refreshProgress]);

  useEffect(() => {
    void refreshProgress();
  }, [refreshProgress, versionTick, blueprintTick]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError("");
    api
      .getSeries(seriesId)
      .then((data) => {
        if (cancelled) return;
        setDetail(data);
        setActiveId(data.units[0]?.id ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : t("series.errors.load"));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [seriesId]);

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

  const activeUnit = useMemo(
    () => detail?.units.find((unit) => unit.id === activeId) ?? null,
    [detail, activeId],
  );

  useEffect(() => {
    if (!activeId || editingUnitId) return;
    let alive = true;
    api
      .getUnit(activeId)
      .then((unit) => {
        if (!alive || editingUnitRef.current || lockController.current) return;
        const next = lockStateFromRead(
          unit,
          "unit",
          activeId,
          me?.user?.id ?? "",
        );
        if (next) setLockState(next);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [activeId, editingUnitId, me?.user?.id]);

  const currentVersionRecord = useMemo(
    () =>
      activeUnit
        ? versions.find(
            (version) => version.version === activeUnit.current_version,
          )
        : undefined,
    [versions, activeUnit],
  );

  const currentCitations = useMemo(
    () => currentVersionRecord?.citations ?? [],
    [currentVersionRecord],
  );

  const currentMode = useMemo<GenerationMode | "">(
    () =>
      currentVersionRecord?.mode || activeUnit?.last_mode || "",
    [currentVersionRecord, activeUnit],
  );

  useEffect(() => {
    const handleUnload = () => {
      const controller = lockController.current;
      const token = controller?.token();
      const unitId = editingUnitRef.current;
      if (controller && token && unitId) {
        releaseEditLockBeacon("unit", unitId, token);
      }
    };
    window.addEventListener("beforeunload", handleUnload);
    return () => {
      window.removeEventListener("beforeunload", handleUnload);
      const controller = lockController.current;
      lockController.current = null;
      controller?.stop(true);
    };
  }, []);

  useEffect(() => {
    const controller = lockController.current;
    if (controller) {
      lockController.current = null;
      controller.stop(true);
    }
    setEditingUnitId(null);
    setUnitDraft("");
    setLockState({ status: "idle" });
  }, [activeId]);

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
    if (!activeUnit || generating) return;
    if (lockBlocked) {
      setError(lockReason);
      return;
    }
    const baseline = expectedVersion ?? activeUnit.current_version;
    setGenerating(true);
    setError("");
    try {
      const result = await api.generateUnit(activeUnit.id, {
        topic: topic.trim() || undefined,
        top_k: topK,
        mode: generateMode,
        expected_version: baseline,
      });
      await loadSeries(activeUnit.id);
      setVersionTick((tick) => tick + 1);
      setGenerateOpen(false);
      setTopic("");
      setNotice(
        result.mode === "loose"
          ? t("series.notices.generatedLoose", { version: result.version })
          : result.grounded
            ? t("series.notices.generatedGrounded", {
                version: result.version,
                count: result.citations.length,
              })
            : t("series.notices.generatedUngrounded", { version: result.version }),
      );
      window.dispatchEvent(new Event("series-studio:refresh"));
    } catch (err) {
      const info = err instanceof ApiError ? err.conflict() : null;
      if (info && info.current_version !== undefined) {
        const current = info.current_version;
        setConflict({
          expectedVersion: baseline,
          currentVersion: current,
          label: t("series.conflictContent"),
          retry: () => runGenerate(current),
        });
      } else {
        setError(err instanceof Error ? err.message : t("series.errors.generate"));
      }
    } finally {
      setGenerating(false);
    }
  };

  const handleRevert = async (version: number, expectedVersion?: number) => {
    if (!activeUnit) return;
    if (lockBlocked) {
      setError(lockReason);
      return;
    }
    const baseline = expectedVersion ?? activeUnit.current_version;
    setReverting(version);
    setError("");
    try {
      await api.revertUnit(
        activeUnit.id,
        version,
        `revert to v${version}`,
        baseline,
      );
      await loadSeries(activeUnit.id);
      setVersionTick((tick) => tick + 1);
      setNotice(t("series.notices.reverted", { version }));
    } catch (err) {
      const info = err instanceof ApiError ? err.conflict() : null;
      if (info && info.current_version !== undefined) {
        const current = info.current_version;
        setConflict({
          expectedVersion: baseline,
          currentVersion: current,
          label: t("series.conflictRevert"),
          retry: () => handleRevert(version, current),
        });
      } else {
        setError(err instanceof Error ? err.message : t("series.errors.revert"));
      }
    } finally {
      setReverting(null);
    }
  };

  const beginUnitEdit = async () => {
    if (!activeUnit || !canWrite || generating || savingUnit) return;
    setError("");
    setConflict(null);
    const previous = lockController.current;
    if (previous) previous.stop(true);
    const controller = createEditLockController({
      kind: "unit",
      id: activeUnit.id,
      onState: setLockState,
      onError: setError,
    });
    lockController.current = controller;
    const state = await controller.start();
    if (lockController.current !== controller) return;
    if (state.status === "held" || state.status === "unsupported") {
      setEditingUnitId(activeUnit.id);
      setUnitDraft(activeUnit.content ?? "");
    }
  };

  const cancelUnitEdit = async () => {
    const controller = lockController.current;
    lockController.current = null;
    void controller?.release();
    setEditingUnitId(null);
    setUnitDraft("");
    setLockState({ status: "idle" });
  };

  const saveUnitEdit = async () => {
    if (!activeUnit || editingUnitId !== activeUnit.id || savingUnit) return;
    setSavingUnit(true);
    setError("");
    try {
      await api.updateUnit(activeUnit.id, { content: unitDraft });
      await loadSeries(activeUnit.id);
      setVersionTick((tick) => tick + 1);
      await refreshProgress();
      const controller = lockController.current;
      lockController.current = null;
      await controller?.release();
      setEditingUnitId(null);
      setUnitDraft("");
      setLockState({ status: "idle" });
      setNotice(t("common.save"));
      window.dispatchEvent(new Event("series-studio:refresh"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.saveFailed"));
    } finally {
      setSavingUnit(false);
    }
  };

  const dismissLock = () => {
    const controller = lockController.current;
    lockController.current = null;
    controller?.stop(false);
    setLockState({ status: "idle" });
  };

  const retryLock = () => {
    void lockController.current?.retry();
  };

  const takeOverLock = () => {
    void lockController.current?.force();
  };

  useEffect(() => {
    if (!editingUnitId) return;
    if (lockState.status !== "blocked" && lockState.status !== "lost") return;
    setEditingUnitId(null);
    setUnitDraft("");
    if (lockState.status === "blocked") {
      setError(t("series.lockEditing", { name: lockState.name }));
    } else {
      setError(t("series.lockLost"));
    }
  }, [editingUnitId, lockState, t]);

  const handleCreateUnit = async (event: React.FormEvent) => {
    event.preventDefault();
    const title = newTitle.trim();
    if (!title || creating) return;
    setCreating(true);
    setError("");
    try {
      const result = await api.createUnit(seriesId, {
        title,
        order_index: (detail?.units.length ?? 0) + 1,
      });
      await loadSeries(result.unit.id);
      setNewTitle("");
      setFormOpen(false);
      setNotice(t("series.notices.unitCreated", { title: result.unit.title }));
      await refreshProgress();
      window.dispatchEvent(new Event("series-studio:refresh"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("series.errors.createUnit"));
    } finally {
      setCreating(false);
    }
  };

  const handleChatApplied = async () => {
    if (activeUnit) {
      await loadSeries(activeUnit.id);
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

  const handleOpenUnit = useCallback((unitId: string) => {
    if (unitId) setActiveId(unitId);
    setView("reader");
    setGenerateOpen(false);
  }, []);

  const handleUnitsChanged = useCallback(async () => {
    await loadSeries(activeId);
    await refreshProgress();
  }, [activeId, loadSeries, refreshProgress]);

  const handleSeriesDelete = async () => {
    setSeriesBusy(true);
    setSeriesDialogError("");
    try {
      await api.deleteSeries(seriesId);
      window.dispatchEvent(new Event("series-studio:refresh"));
      navigate("/");
    } catch (err) {
      setSeriesDialogError(err instanceof Error ? err.message : t("series.errors.delete"));
    } finally {
      setSeriesBusy(false);
    }
  };

  const handleUnitRename = async (title: string) => {
    if (!unitRename) return;
    setUnitBusy(true);
    setUnitDialogError("");
    try {
      await api.updateUnit(unitRename.id, { title });
      setUnitRename(null);
      setNotice(t("series.notices.unitRenamed"));
      await handleUnitsChanged();
    } catch (err) {
      setUnitDialogError(err instanceof Error ? err.message : t("series.errors.rename"));
    } finally {
      setUnitBusy(false);
    }
  };

  const handleUnitDelete = async () => {
    if (!unitDelete) return;
    setUnitBusy(true);
    setUnitDialogError("");
    try {
      await api.deleteUnit(unitDelete.id);
      setUnitDelete(null);
      setNotice(t("series.notices.unitDeleted"));
      if (activeId === unitDelete.id) setActiveId(null);
      await handleUnitsChanged();
    } catch (err) {
      setUnitDialogError(err instanceof Error ? err.message : t("series.errors.delete"));
    } finally {
      setUnitBusy(false);
    }
  };

  const moveUnit = async (unitId: string, direction: -1 | 1) => {
    if (!detail) return;
    const ids = detail.units.map((unit) => unit.id);
    const index = ids.indexOf(unitId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ids.length) return;
    const next = [...ids];
    next[index] = ids[target];
    next[target] = ids[index];
    try {
      await api.reorderUnits(seriesId, next);
      setNotice(t("series.notices.orderUpdated"));
      await handleUnitsChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("series.errors.order"));
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
          {t("series.loadErrorTitle")}
        </p>
        <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          {loadError || t("series.loadErrorBody")}
        </p>
        <Link to="/" className="btn btn-ghost mt-5">
          <ArrowLeft size={14} />
          {t("series.backToSeries")}
        </Link>
      </div>
    );
  }

  const series = detail.series;
  const currentProfile = profiles.find((item) => item.id === series.profile_id);

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
              {t("series.allSeries")}
            </Link>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 dark:text-white sm:text-[26px]">
              {series.title}
            </h1>
            {series.subtitle ? (
              <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                {series.subtitle}
              </p>
            ) : null}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="chip">
                <BookOpen size={11} />
                {t("series.unitCount", { count: detail.unit_count })}
              </span>
              <span className="chip-muted">
                {difficultyLabel(t, series.difficulty)}
              </span>
              {series.audience ? (
                <span className="chip-muted">
                  {t("series.audienceChip", { name: series.audience })}
                </span>
              ) : null}
              <span className="chip-muted">
                {languageLabel(t, series.language)}
              </span>
              {series.profile_id ? (
                <Link
                  to="/settings#creation-profiles"
                  className="chip transition hover:text-indigo-600 dark:hover:text-indigo-200"
                  title={t("profiles.seriesChipHint")}
                >
                  <Wand2 size={11} />
                  {t("profiles.seriesChip", {
                    name:
                      profileNameLabel(t, currentProfile) || series.profile_id,
                  })}
                </Link>
              ) : null}
            </div>
          </div>
          <div className="no-scrollbar -mx-1 flex items-center gap-2 overflow-x-auto px-1">
            <ExportMenu
              sourceType="series"
              sourceId={series.id}
              fallbackName={series.title}
            />
            <a
              href={`/read/series/${series.id}`}
              target="_blank"
              rel="noreferrer"
              className="btn btn-ghost shrink-0"
              title={t("series.readModeTitle")}
            >
              <BookOpen size={13} />
              {t("series.readMode")}
            </a>
            {canWrite ? (
              <button
                type="button"
                onClick={() => setSeriesEditOpen(true)}
                className="btn btn-ghost shrink-0"
              >
                <Pencil size={13} />
                {t("series.edit")}
              </button>
            ) : null}
            {canWrite ? (
              <button
                type="button"
                onClick={() => {
                  setSeriesDialogError("");
                  setSeriesDeleteOpen(true);
                }}
                className="btn btn-ghost shrink-0 text-rose-600 hover:text-rose-700 dark:text-rose-300"
              >
                <Trash2 size={13} />
                {t("series.deleteSeries")}
              </button>
            ) : null}
            {can("manage_members") ? (
              <button
                type="button"
                onClick={() => setGrantsOpen(true)}
                className="btn btn-ghost shrink-0"
              >
                <Lock size={13} />
                {t("series.grants")}
              </button>
            ) : null}
            {canWrite ? (
              <button
                type="button"
                onClick={() => setShareLinksOpen(true)}
                className="btn btn-ghost shrink-0"
              >
                <Link2 size={13} />
                {t("share.dialogTitle")}
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => setOutlineOpen(true)}
              className="btn btn-ghost shrink-0 lg:hidden"
            >
              <List size={14} />
              {t("series.outline")}
            </button>
            <button
              type="button"
              {...guard}
              onClick={() => setChatOpen(true)}
              disabled={readOnly || lockBlocked || !activeUnit}
              className="btn btn-primary hidden shrink-0 sm:inline-flex"
            >
              <MessageSquare size={14} />
              {t("series.askEdit")}
            </button>
          </div>
        </div>
      </div>

      {readOnly ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-2 text-[11px] text-amber-700 dark:text-amber-300">
          {t("series.readOnlyBanner", {
            role: roleLabel(t, roleKey, roleName) || t("common.readOnly"),
          })}
        </div>
      ) : null}

      <SeriesGenerateAllPanel
        seriesId={seriesId}
        units={detail.units}
        canWrite={canWrite}
        onRefresh={refreshWorkspace}
        onNotice={setNotice}
        onOpenUnit={handleOpenUnit}
      />

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
                {t(`series.${item.key}`)}
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {progress ? (
            <span className="chip-muted">
              {t("series.progress.approved", {
                approved: progress.approved,
                total: progress.total,
                pending: progress.pending_review,
              })}
            </span>
          ) : null}
          <span className="chip-muted">
            {progress?.blueprint_ready
              ? t("series.progress.blueprintReady", {
                  version: progress.blueprint_version,
                })
              : t("series.progress.blueprintMissing")}
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
            aria-label={t("series.closeError")}
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
                {t("series.outlineTitle")}
              </p>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
                {t("series.unitCount", { count: detail.unit_count })}
              </p>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setFormOpen((value) => !value)}
                className="grid h-9 w-9 place-items-center rounded-full bg-indigo-500/10 text-indigo-600 transition hover:bg-indigo-500/20 dark:text-indigo-300"
                aria-label={t("series.addUnit")}
              >
                <Plus size={15} />
              </button>
              <button
                type="button"
                onClick={() => setOutlineOpen(false)}
                className="grid h-9 w-9 place-items-center rounded-full text-slate-400 transition hover:bg-white/70 hover:text-slate-600 dark:hover:bg-white/10 lg:hidden"
                aria-label={t("series.closeOutline")}
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
                onSubmit={handleCreateUnit}
                className="overflow-hidden"
              >
                <div className="mt-2.5 space-y-2 rounded-2xl border border-white/60 bg-white/50 p-2.5 dark:border-white/10 dark:bg-white/[0.04]">
                  <input
                    autoFocus
                    value={newTitle}
                    onChange={(event) => setNewTitle(event.target.value)}
                    placeholder={t("series.unitTitlePlaceholder")}
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
                      {t("common.cancel")}
                    </button>
                    <button
                      type="submit"
                      disabled={creating || !newTitle.trim()}
                      className="btn btn-primary px-3 py-1.5 text-[11px]"
                    >
                      {creating ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Plus size={12} />
                      )}
                      {t("series.add")}
                    </button>
                  </div>
                </div>
              </motion.form>
            )}
          </AnimatePresence>

          <div className="no-scrollbar mt-3 flex-1 space-y-1 overflow-y-auto pr-0.5">
            {detail.units.length === 0 ? (
              <p className="px-2 py-4 text-[11px] leading-relaxed text-slate-400 dark:text-slate-500">
                {t("series.emptyUnits")}
              </p>
            ) : (
              detail.units.map((unit, unitIndex) => {
                const active = unit.id === activeId;
                return (
                  <div
                    key={unit.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => {
                      setActiveId(unit.id);
                      setGenerateOpen(false);
                      setOutlineOpen(false);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        setActiveId(unit.id);
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
                      {unit.order_index}
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
                        {unit.title}
                      </span>
                      <span className="mt-0.5 block truncate text-[10px] text-slate-400 dark:text-slate-500">
                        {unit.content
                          ? `v${unit.current_version}`
                          : t("series.toGenerate")}{" "}
                        · {unitStatusLabel(t, unit.status)}
                      </span>
                    </span>
                    {canWrite ? (
                      <RowMenu
                        items={[
                          {
                            label: t("common.rename"),
                            icon: <Pencil size={11} />,
                            onClick: () => {
                              setUnitDialogError("");
                              setUnitRename({ id: unit.id, title: unit.title });
                            },
                          },
                          {
                            label: t("series.moveUp"),
                            icon: <ArrowUp size={11} />,
                            disabled: unitIndex === 0,
                            onClick: () => void moveUnit(unit.id, -1),
                          },
                          {
                            label: t("series.moveDown"),
                            icon: <ArrowDown size={11} />,
                            disabled: unitIndex === detail.units.length - 1,
                            onClick: () => void moveUnit(unit.id, 1),
                          },
                          {
                            label: t("series.deleteUnit"),
                            icon: <Trash2 size={11} />,
                            danger: true,
                            onClick: () => {
                              setUnitDialogError("");
                              setUnitDelete({ id: unit.id, title: unit.title });
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
          {activeUnit ? (
            <article className="glass rounded-3xl p-4 shadow-glass sm:p-8">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200/70 pb-5 dark:border-white/10">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400 dark:text-slate-500">
                    <span>
                      {t("series.unitNo", { index: activeUnit.order_index })}
                    </span>
                    <span>·</span>
                    <StatusBadge status={activeUnit.status} />
                    <span>·</span>
                    <span>v{activeUnit.current_version}</span>
                    {activeUnit.content ? (
                      <span
                        className={clsx(
                          "rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                          currentMode === "loose"
                            ? "bg-amber-400/20 text-amber-700 ring-1 ring-amber-400/30 dark:bg-amber-300/12 dark:text-amber-300 dark:ring-amber-300/20"
                            : "bg-indigo-500/12 text-indigo-600 ring-1 ring-indigo-400/20 dark:bg-indigo-400/14 dark:text-indigo-300 dark:ring-indigo-300/20",
                        )}
                      >
                        {t("series.modeSuffix", {
                          mode: modeLabel(t, currentMode),
                        })}
                      </span>
                    ) : null}
                  </div>
                  <h2 className="mt-1 text-xl font-semibold tracking-tight text-slate-900 dark:text-white sm:text-[22px]">
                    {activeUnit.title}
                  </h2>
                </div>
                <div className="no-scrollbar -mx-1 flex items-center gap-2 overflow-x-auto px-1 pb-0.5">
                  {canWrite ? (
                    <button
                      type="button"
                      data-testid="unit-edit"
                      onClick={() => void beginUnitEdit()}
                      disabled={
                        generating ||
                        savingUnit ||
                        editingUnitId === activeUnit.id ||
                        lockState.status === "acquiring"
                      }
                      className="btn btn-ghost"
                    >
                      {lockState.status === "acquiring" ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Pencil size={14} />
                      )}
                      {editingUnitId === activeUnit.id
                        ? t("unit.editing")
                        : t("unit.edit")}
                    </button>
                  ) : null}
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
                    {activeUnit.content
                      ? t("series.regenerate")
                      : t("series.generate")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setVersionsOpen(true)}
                    className="btn btn-ghost xl:hidden"
                  >
                    <History size={14} />
                    {t("series.versions")}
                  </button>
                  {canWrite ? (
                    <RowMenu
                      label={t("series.unitActions")}
                      items={[
                        {
                          label: t("series.renameUnitTitle"),
                          icon: <Pencil size={11} />,
                          onClick: () => {
                            setUnitDialogError("");
                            setUnitRename({
                              id: activeUnit.id,
                              title: activeUnit.title,
                            });
                          },
                        },
                        {
                          label: t("series.moveUp"),
                          icon: <ArrowUp size={11} />,
                          disabled:
                            detail.units.findIndex(
                              (unit) => unit.id === activeUnit.id,
                            ) <= 0,
                          onClick: () => void moveUnit(activeUnit.id, -1),
                        },
                        {
                          label: t("series.moveDown"),
                          icon: <ArrowDown size={11} />,
                          disabled:
                            detail.units.findIndex(
                              (unit) => unit.id === activeUnit.id,
                            ) ===
                            detail.units.length - 1,
                          onClick: () => void moveUnit(activeUnit.id, 1),
                        },
                        {
                          label: t("series.deleteUnit"),
                          icon: <Trash2 size={11} />,
                          danger: true,
                          onClick: () => {
                            setUnitDialogError("");
                            setUnitDelete({
                              id: activeUnit.id,
                              title: activeUnit.title,
                            });
                          },
                        },
                      ]}
                    />
                  ) : null}
                </div>
              </div>

              <div className="mt-3">
                <EditLockChip
                  state={lockState}
                  canTakeOver={canManage}
                  busy={lockState.status === "acquiring"}
                  onReadOnly={dismissLock}
                  onRetry={retryLock}
                  onTakeOver={takeOverLock}
                />
              </div>

              <CodeCheckPanel unitId={activeUnit.id} disabled={!canWrite} />
              <ReviewControls
                unit={activeUnit}
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
          {t("series.readOnlyBannerSpace")}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-[11px] font-medium text-indigo-600 dark:text-indigo-300">
                          {generateMode === "loose"
                            ? t("series.generateLooseHint")
                            : t("series.generateStrictHint")}
                        </p>
                        <span className="chip-muted">{t("series.writeMode")}</span>
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
                          placeholder={t("series.topicPlaceholder")}
                          className="input"
                        />
                        <select
                          value={topK}
                          onChange={(event) => setTopK(Number(event.target.value))}
                          className="select"
                        >
                          {[3, 5, 8, 12].map((value) => (
                            <option key={value} value={value}>
                              {t("series.evidenceCount", { count: value })}
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
                          {t("series.startGenerate")}
                        </button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {generating && (
                <div className="mt-4 flex items-center gap-2 rounded-2xl border border-indigo-200/50 bg-white/50 px-4 py-3 text-xs text-slate-500 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-400">
                  <Loader2 size={14} className="animate-spin text-indigo-500" />
                  {t("series.generatingHint")}
                </div>
              )}

              {activeUnit.learning_objectives.length > 0 && (
                <div className="mt-5 rounded-2xl border border-indigo-200/50 bg-indigo-500/5 p-4 dark:border-indigo-400/20 dark:bg-indigo-400/5">
                  <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-indigo-500 dark:text-indigo-300">
                    <Target size={12} />
                    {t("series.objectives")}
                  </p>
                  <ul className="mt-2 space-y-1 text-[13px] leading-relaxed text-slate-600 dark:text-slate-300">
                    {activeUnit.learning_objectives.map((objective) => (
                      <li key={objective} className="flex items-start gap-1.5">
                        <Check size={12} className="mt-1 shrink-0 text-indigo-400" />
                        <span>{objective}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {activeUnit.prerequisites.length > 0 && (
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <span className="text-[10px] uppercase tracking-[0.14em] text-slate-400">
                    {t("series.prerequisites")}
                  </span>
                  {activeUnit.prerequisites.map((item) => (
                    <span key={item} className="chip-muted">
                      {item}
                    </span>
                  ))}
                </div>
              )}

              <div className="relative mt-6">
                {editingUnitId === activeUnit.id ? (
                  <div data-testid="unit-editor-panel" className="space-y-3">
                    <textarea
                      data-testid="unit-editor"
                      value={unitDraft}
                      onChange={(event) => setUnitDraft(event.target.value)}
                      rows={18}
                      className="input min-h-[22rem] w-full font-mono text-[12px] leading-relaxed"
                      placeholder={t("piece.manualPlaceholder")}
                    />
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-[10.5px] text-slate-400 dark:text-slate-500">
                        {t("piece.charCount", { count: unitDraft.length })}
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          data-testid="unit-cancel"
                          onClick={() => void cancelUnitEdit()}
                          disabled={savingUnit}
                          className="btn btn-quiet"
                        >
                          {t("common.cancel")}
                        </button>
                        <button
                          type="button"
                          data-testid="unit-save"
                          onClick={() => void saveUnitEdit()}
                          disabled={savingUnit}
                          className="btn btn-primary"
                        >
                          {savingUnit ? (
                            <Loader2 size={13} className="animate-spin" />
                          ) : null}
                          {t("common.saveChanges")}
                        </button>
                      </div>
                    </div>
                  </div>
                ) : activeUnit.content ? (
                  <MarkdownReader
                    content={activeUnit.content}
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
                      {t("series.emptyContentTitle")}
                    </p>
                    <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                      {t("series.emptyContentBody")}
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
                        {t("series.generate")}
                      </button>
                      <Link to="/kb" className="btn btn-ghost">
                        {t("series.uploadFirst")}
                      </Link>
                    </div>
                  </div>
                )}
              </div>

              <div className="mt-8 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200/70 pt-4 text-[11px] text-slate-400 dark:border-white/10 dark:text-slate-500">
                <span>
                  {t("series.citationsChars", {
                    citations: currentCitations.length,
                    chars: contentLength(activeUnit.content),
                  })}
                </span>
                <span>
                  {t("series.updatedAt", {
                    time: formatRelative(activeUnit.updated_at),
                  })}
                </span>
              </div>
            </article>
          ) : (
            <div className="glass rounded-3xl p-10 text-center shadow-glass">
              <div className="brand-gradient mx-auto grid h-12 w-12 place-items-center rounded-2xl text-white shadow-brand">
                <BookOpen size={20} />
              </div>
              <p className="mt-4 text-sm font-medium text-slate-700 dark:text-slate-200">
                {t("series.noUnitsTitle")}
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                {t("series.noUnitsBody")}
              </p>
              <button
                type="button"
                onClick={() => setFormOpen(true)}
                className="btn btn-primary mt-4"
              >
                <Plus size={14} />
                {t("series.addFirstUnit")}
              </button>
            </div>
          )}
          <div className="mt-4">
            <ThreadsPanel
              seriesId={seriesId}
              canWrite={canWrite}
              onNotice={setNotice}
              onError={setError}
            />
          </div>
        </div>

        <div className="hidden xl:block">
          <VersionPanel
            versions={versions}
            currentVersion={activeUnit?.current_version ?? 0}
            loading={versionsLoading}
            busyVersion={reverting}
            onRevert={handleRevert}
            unitId={activeUnit?.id}
            className="sticky top-24 h-[calc(100vh-7rem)]"
          />
        </div>
      </div>
      ) : null}

      {view === "blueprint" ? (
        <BlueprintBoard
          seriesId={seriesId}
          units={detail.units}
          reloadKey={blueprintTick}
          onOpenUnit={handleOpenUnit}
          onUnitsChanged={handleUnitsChanged}
          onNotice={setNotice}
          onError={setError}
          onProgressRefresh={() => void refreshProgress()}
          onVersionConflict={setConflict}
        />
      ) : null}

      {view === "continuous" ? (
        <SeriesReader
          units={detail.units}
          progress={progress}
          onOpenUnit={handleOpenUnit}
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
                currentVersion={activeUnit?.current_version ?? 0}
                loading={versionsLoading}
                busyVersion={reverting}
                onRevert={handleRevert}
                unitId={activeUnit?.id}
                className="h-full"
              />
              <button
                type="button"
                onClick={() => setVersionsOpen(false)}
                className="absolute -top-1 right-0 grid h-8 w-8 place-items-center rounded-full bg-white/85 text-slate-500 shadow-sm dark:bg-slate-800/85 dark:text-slate-300"
                aria-label={t("series.closeVersions")}
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

      {view === "reader" && activeUnit ? (
        <button
          type="button"
          onClick={() => setChatOpen(true)}
          disabled={readOnly || lockBlocked}
          title={
            readOnly
              ? t("series.guardReadOnly")
              : lockBlocked
                ? lockReason
                : t("series.askEdit")
          }
          aria-label={t("series.askEdit")}
          className="fab brand-gradient grid h-14 w-14 place-items-center rounded-full text-white shadow-brand transition active:scale-95 disabled:opacity-45 sm:hidden"
        >
          <MessageSquare size={20} />
        </button>
      ) : null}

      <ChatPanel
        open={chatOpen}
        unitId={activeUnit?.id ?? null}
        unitTitle={activeUnit?.title ?? ""}
        currentVersion={activeUnit?.current_version ?? 0}
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

      <SeriesGrantsPanel
        seriesId={seriesId}
        open={grantsOpen}
        onClose={() => setGrantsOpen(false)}
      />

      <ShareLinksDialog
        open={shareLinksOpen}
        onClose={() => setShareLinksOpen(false)}
        resourceType="series"
        resourceId={seriesId}
        title={series.title}
      />

      <SeriesEditDialog
        open={seriesEditOpen}
        series={series}
        onClose={() => setSeriesEditOpen(false)}
        onSaved={(updated) => {
          setDetail((prev) => (prev ? { ...prev, series: updated } : prev));
          setNotice(t("series.notices.seriesUpdated"));
        }}
      />

      <ConfirmDialog
        open={seriesDeleteOpen}
        title={t("series.deleteSeriesTitle")}
        description={t("series.deleteSeriesDesc", { title: series.title })}
        requireText={series.title}
        busy={seriesBusy}
        error={seriesDialogError}
        onConfirm={() => void handleSeriesDelete()}
        onClose={() => setSeriesDeleteOpen(false)}
      />

      <PromptDialog
        open={Boolean(unitRename)}
        title={t("series.renameUnitTitle")}
        label={t("series.unitTitleLabel")}
        initial={unitRename?.title ?? ""}
        busy={unitBusy}
        error={unitDialogError}
        onConfirm={(value) => void handleUnitRename(value)}
        onClose={() => setUnitRename(null)}
      />

      <ConfirmDialog
        open={Boolean(unitDelete)}
        title={t("series.deleteUnitTitle")}
        description={t("series.deleteUnitDesc", {
          title: unitDelete?.title ?? "",
        })}
        busy={unitBusy}
        error={unitDialogError}
        onConfirm={() => void handleUnitDelete()}
        onClose={() => setUnitDelete(null)}
      />
    </motion.div>
  );
}
