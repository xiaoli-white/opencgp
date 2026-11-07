import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  BookOpen,
  ChevronDown,
  Clock3,
  Eye,
  FileText,
  GitCompare,
  History,
  Layers,
  ImagePlus,
  Link2,
  Loader2,
  PenLine,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Share2,
  Sparkles,
  Trash2,
  Wand2,
  X,
} from "lucide-react";
import clsx from "clsx";
import {
  ApiError,
  api,
  type GenerationMode,
  type Piece,
  type PieceVersion,
} from "@/lib/api";
import { cancelJob, runJob } from "@/lib/jobs";
import {
  createEditLockController,
  lockStateFromRead,
  type EditLockController,
  type EditLockState,
} from "@/lib/editLock";
import { contentLength, formatChars, formatDateTime } from "@/lib/format";
import MarkdownReader from "@/components/reader/MarkdownReader";
import VersionDiffDialog from "@/components/reader/VersionDiffDialog";
import VersionPreviewDialog from "@/components/reader/VersionPreviewDialog";
import { useSession } from "@/components/auth/SessionProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { genreLabel, policyLabel, roleLabel } from "@/i18n/labels";
import SharePanel, { type ShareMember } from "@/components/sharing/SharePanel";
import ShareLinksDialog from "@/components/share/ShareLinksDialog";
import ExportMenu from "@/components/export/ExportMenu";
import ImagePickerDrawer from "@/components/media/ImagePickerDrawer";
import EditLockChip from "@/components/series/EditLockChip";
import {
  ConfirmDialog,
  Modal,
  PromptDialog,
  RowMenu,
} from "@/components/common/Dialogs";

const GENRE_VALUES = ["article", "report", "essay", "tutorial", "custom"] as const;

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

export default function PieceEditorPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { can, roleKey, roleName, tenant, me } = useSession();
  const { t } = useI18n();
  const writable = can("write");

  const [piece, setPiece] = useState<Piece | null>(null);
  const [versions, setVersions] = useState<PieceVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [busy, setBusy] = useState("");
  const [jobProgress, setJobProgress] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const elapsed = useElapsed(Boolean(busy));

  const [outlineOpen, setOutlineOpen] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [previewVersion, setPreviewVersion] = useState<number | null>(null);
  const [versionDiffOpen, setVersionDiffOpen] = useState(false);
  const [versionDiffAnchor, setVersionDiffAnchor] = useState<number | null>(null);
  const [rewriteOpen, setRewriteOpen] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [rewriteMode, setRewriteMode] = useState<GenerationMode>("loose");

  const [shareOpen, setShareOpen] = useState(false);
  const [shareLinksOpen, setShareLinksOpen] = useState(false);
  const [shareMembers, setShareMembers] = useState<ShareMember[]>([]);
  const [shareLevels, setShareLevels] = useState<Record<string, string | null>>({});
  const [shareLoading, setShareLoading] = useState(false);
  const [shareSaving, setShareSaving] = useState(false);
  const [shareError, setShareError] = useState("");
  const [pickOpen, setPickOpen] = useState(false);

  const [titleEditOpen, setTitleEditOpen] = useState(false);
  const [targetEditOpen, setTargetEditOpen] = useState(false);
  const [briefEditOpen, setBriefEditOpen] = useState(false);
  const [briefDraft, setBriefDraft] = useState("");
  const [sectionRename, setSectionRename] = useState<{ id: string; title: string } | null>(
    null,
  );
  const [sectionForm, setSectionForm] = useState<{
    id: string;
    title: string;
    summary: string;
    targetWords: number;
    content: string;
  } | null>(null);
  const [sectionCreate, setSectionCreate] = useState<{
    afterId: string | null;
    title: string;
    summary: string;
    targetWords: number;
  } | null>(null);
  const [sectionDelete, setSectionDelete] = useState<{ id: string; title: string } | null>(
    null,
  );
  const [manualOpen, setManualOpen] = useState(false);
  const [manualText, setManualText] = useState("");
  const [editLockState, setEditLockState] = useState<EditLockState>({
    status: "idle",
  });
  const [dialogBusy, setDialogBusy] = useState(false);
  const [dialogError, setDialogError] = useState("");

  const canShare = can("manage_members");

  const openShare = useCallback(async () => {
    if (!id) return;
    setShareOpen(true);
    setShareLoading(true);
    setShareError("");
    try {
      const [memberList, grantList] = await Promise.all([
        tenant ? api.listMembers(tenant) : Promise.resolve({ count: 0, members: [] }),
        api.getPieceGrants(id),
      ]);
      setShareMembers(
        (memberList.members ?? []).map((member) => ({
          user_id: member.user_id,
          user_email: member.user_email,
          user_display_name: member.user_display_name,
          avatar_url: member.avatar_url,
          note: t("sharing.memberNote"),
        })),
      );
      const next: Record<string, string | null> = {};
      for (const member of memberList.members ?? []) next[member.user_id] = null;
      for (const grant of grantList.grants ?? []) {
        next[grant.user_id] = grant.level === "write" ? "write" : "read";
      }
      setShareLevels(next);
    } catch (err) {
      setShareError(err instanceof Error ? err.message : t("piece.shareLoadFailed"));
    } finally {
      setShareLoading(false);
    }
  }, [id, tenant, t]);

  const saveShare = useCallback(
    async (entries: { user_id: string; level: string }[]) => {
      if (!id) return;
      setShareSaving(true);
      setShareError("");
      try {
        await api.savePieceGrants(id, entries);
        setNotice(t("piece.shareSaved"));
        setShareOpen(false);
      } catch (err) {
        setShareError(err instanceof Error ? err.message : t("errors.saveFailed"));
      } finally {
        setShareSaving(false);
      }
    },
    [id, t],
  );

  const contentRef = useRef<HTMLDivElement | null>(null);
  const pieceLock = useRef<EditLockController | null>(null);

  useEffect(() => {
    setEditLockState({ status: "idle" });
    setManualOpen(false);
    return () => {
      const controller = pieceLock.current;
      pieceLock.current = null;
      controller?.stop(true);
    };
  }, [id]);

  const load = useCallback(
    async (quiet = false) => {
      if (!id) return;
      if (!quiet) setLoading(true);
      try {
        const [detail, versionData] = await Promise.all([
          api.getPiece(id),
          api.listPieceVersions(id),
        ]);
        setPiece(detail);
        setVersions(versionData.versions);
        const readLock = lockStateFromRead(
          detail,
          "piece",
          detail.id,
          me?.user?.id ?? "",
        );
        if (readLock) setEditLockState(readLock);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("piece.loadFailed"));
      } finally {
        setLoading(false);
      }
    },
    [id, me?.user?.id, t],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const words = useMemo(
    () => (piece?.content ? contentLength(piece.content) : 0),
    [piece],
  );

  const generateAll = async () => {
    if (!piece || busy) return;
    if (!writable) {
      setError(t("piece.readOnlyGenerate"));
      return;
    }
    setBusy("all");
    setJobProgress(0);
    setJobId(null);
    setError("");
    setNotice("");
    const startedAt = Date.now();
    try {
      let updated: Piece | null = null;
      try {
        await runJob(
          "piece_generate",
          { piece_id: piece.id },
          {
            onProgress: setJobProgress,
            onJob: (created) => setJobId(created.id),
          },
        );
        updated = await api.getPiece(piece.id);
      } catch (queueErr) {
        const queueable =
          queueErr instanceof ApiError &&
          (queueErr.status === 400 || queueErr.status === 404 || queueErr.status === 422);
        if (!queueable) throw queueErr;
        updated = await api.generatePiece(piece.id, {
          mode: (piece.last_mode as GenerationMode) || "loose",
          expected_version: piece.current_version,
        });
      }
      setPiece(updated);
      const versionData = await api.listPieceVersions(piece.id);
      setVersions(versionData.versions);
      const seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      setNotice(
        t("piece.generatedFull", {
          seconds,
          version: updated.current_version,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : t("piece.generateFailed"));
    } finally {
      setBusy("");
      setJobId(null);
    }
  };

  const generateOne = async (sectionId: string) => {
    if (!piece || busy) return;
    if (!writable) {
      setError(t("piece.readOnlyGenerateSection"));
      return;
    }
    setBusy(sectionId);
    setError("");
    setNotice("");
    const startedAt = Date.now();
    try {
      const result = await api.generateSection(piece.id, sectionId, {
        mode: (piece.last_mode as GenerationMode) || "loose",
      });
      setPiece(result.piece);
      const versionData = await api.listPieceVersions(piece.id);
      setVersions(versionData.versions);
      const seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      setNotice(t("piece.generatedSection", { seconds }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("piece.generateSectionFailed"));
    } finally {
      setBusy("");
    }
  };

  const submitRewrite = async () => {
    const text = instruction.trim();
    if (!piece || !text || busy) return;
    if (!writable) {
      setError(t("piece.readOnlyRewrite"));
      return;
    }
    setBusy("rewrite");
    setJobProgress(0);
    setJobId(null);
    setError("");
    setNotice("");
    const startedAt = Date.now();
    try {
      let updated: Piece | null = null;
      try {
        await runJob(
          "piece_rewrite",
          { piece_id: piece.id, instruction: text },
          {
            onProgress: setJobProgress,
            onJob: (created) => setJobId(created.id),
          },
        );
        updated = await api.getPiece(piece.id);
      } catch (queueErr) {
        const queueable =
          queueErr instanceof ApiError &&
          (queueErr.status === 400 || queueErr.status === 404 || queueErr.status === 422);
        if (!queueable) throw queueErr;
        updated = await api.rewritePiece(piece.id, {
          instruction: text,
          mode: rewriteMode,
          expected_version: piece.current_version,
        });
      }
      setPiece(updated);
      const versionData = await api.listPieceVersions(piece.id);
      setVersions(versionData.versions);
      setRewriteOpen(false);
      setInstruction("");
      const seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      setNotice(
        t("piece.rewriteDone", {
          seconds,
          version: updated.current_version,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : t("piece.rewriteFailed"));
    } finally {
      setBusy("");
      setJobId(null);
    }
  };

  const cancelActive = async () => {
    if (!jobId) return;
    try {
      await cancelJob(jobId);
      setNotice(t("piece.cancelRequested"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("piece.cancelFailed"));
    }
  };

  const openVersionDiff = (version: number) => {
    setVersionDiffAnchor(version);
    setVersionDiffOpen(true);
  };

  const loadVersionPreview = async (version: number) => {
    const detail = await api.getPieceVersion(id, version);
    return {
      content: detail.version.content ?? "",
      citations: detail.version.citations ?? [],
    };
  };

  const fetchVersionDiff = async (from: number, to: number) => {
    return api.diffPieceVersions(id, from, to);
  };

  const revert = async (version: number) => {
    if (!piece || busy) return;
    if (!writable) return;
    const confirmed = window.confirm(t("piece.confirmRevert", { version }));
    if (!confirmed) return;
    setBusy(`revert-${version}`);
    setError("");
    try {
      const updated = await api.revertPiece(piece.id, version);
      setPiece(updated);
      const versionData = await api.listPieceVersions(piece.id);
      setVersions(versionData.versions);
      setNotice(t("piece.reverted", { version, current: updated.current_version }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("piece.revertFailed"));
    } finally {
      setBusy("");
    }
  };

  const remove = async () => {
    if (!piece || !writable) return;
    const confirmed = window.confirm(
      t("piece.confirmDelete", { title: piece.title }),
    );
    if (!confirmed) return;
    try {
      await api.deletePiece(piece.id);
      navigate("/pieces");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.deleteFailed"));
    }
  };

  const scrollToSection = (title: string) => {
    const root = contentRef.current;
    if (!root || !title) return;
    const headings = Array.from(root.querySelectorAll("h1,h2,h3,h4"));
    const target = headings.find((node) =>
      (node.textContent ?? "").includes(title.slice(0, 12)),
    );
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      root.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    setOutlineOpen(false);
  };

  const openManual = async () => {
    if (!piece || !writable) return;
    setDialogError("");
    const previous = pieceLock.current;
    if (previous) previous.stop(true);
    const controller = createEditLockController({
      kind: "piece",
      id: piece.id,
      onState: setEditLockState,
      onError: setError,
    });
    pieceLock.current = controller;
    const state = await controller.start();
    if (pieceLock.current !== controller) return;
    if (state.status === "held" || state.status === "unsupported") {
      setManualText(piece.content ?? "");
      setManualOpen(true);
    }
  };

  const closeManual = async () => {
    const controller = pieceLock.current;
    pieceLock.current = null;
    setManualOpen(false);
    setEditLockState({ status: "idle" });
    await controller?.release();
  };

  const saveManual = async () => {
    if (!piece) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.savePieceContent(piece.id, {
        content: manualText,
        note: t("piece.manualNote"),
        expected_version: piece.current_version,
      });
      setPiece(updated);
      const versionData = await api.listPieceVersions(piece.id);
      setVersions(versionData.versions);
      const controller = pieceLock.current;
      pieceLock.current = null;
      setManualOpen(false);
      setEditLockState({ status: "idle" });
      await controller?.release();
      setNotice(t("piece.savedAsVersion", { version: updated.current_version }));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("errors.saveFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const saveTitle = async (value: string) => {
    if (!piece) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updatePiece(piece.id, { title: value });
      setPiece(updated);
      setTitleEditOpen(false);
      setNotice(t("piece.titleUpdated"));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("piece.updateFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const saveBrief = async () => {
    if (!piece) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updatePiece(piece.id, { brief: briefDraft.trim() });
      setPiece(updated);
      setBriefEditOpen(false);
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("piece.updateFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const saveTargetWords = async (value: string) => {
    if (!piece) return;
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setDialogError(t("piece.targetWordsInvalid"));
      return;
    }
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updatePiece(piece.id, {
        target_words: Math.round(parsed),
      });
      setPiece(updated);
      setTargetEditOpen(false);
      setNotice(t("piece.targetUpdated"));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("piece.updateFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const renameSection = async (value: string) => {
    if (!piece || !sectionRename) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updatePieceSection(piece.id, sectionRename.id, {
        title: value,
      });
      setPiece(updated);
      setSectionRename(null);
      setNotice(t("piece.sectionRenamed"));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("piece.renameFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const saveSectionForm = async () => {
    if (!piece || !sectionForm) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updatePieceSection(piece.id, sectionForm.id, {
        title: sectionForm.title.trim(),
        summary: sectionForm.summary,
        target_words: Number(sectionForm.targetWords) || 0,
        content: sectionForm.content,
      });
      setPiece(updated);
      setSectionForm(null);
      setNotice(t("piece.sectionSaved"));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("errors.saveFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const createSection = async () => {
    if (!piece || !sectionCreate) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const result = await api.createPieceSection(piece.id, {
        title: sectionCreate.title.trim(),
        summary: sectionCreate.summary,
        target_words: Number(sectionCreate.targetWords) || 0,
        after_id: sectionCreate.afterId,
      });
      setPiece(result.piece);
      setSectionCreate(null);
      setNotice(t("piece.sectionCreated"));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("piece.createFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const deleteSection = async () => {
    if (!piece || !sectionDelete) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.deletePieceSection(piece.id, sectionDelete.id);
      setPiece(updated);
      setSectionDelete(null);
      setNotice(t("piece.sectionDeleted"));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("errors.deleteFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const moveSection = async (sectionId: string, direction: -1 | 1) => {
    if (!piece) return;
    const ids = piece.outline.map((section) => section.id);
    const index = ids.indexOf(sectionId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ids.length) return;
    const next = [...ids];
    next[index] = ids[target];
    next[target] = ids[index];
    try {
      const updated = await api.reorderPieceSections(piece.id, next);
      setPiece(updated);
      setNotice(t("piece.orderUpdated"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("piece.reorderFailed"));
    }
  };

  const sectionMenuItems = (sectionId: string, sectionTitle: string, index: number) => [
    {
      label: t("common.rename"),
      icon: <Pencil size={11} />,
      onClick: () => {
        setDialogError("");
        setSectionRename({ id: sectionId, title: sectionTitle });
      },
    },
    {
      label: t("piece.editSection"),
      icon: <FileText size={11} />,
      onClick: () => {
        const target = piece?.outline.find((item) => item.id === sectionId);
        if (!target) return;
        setDialogError("");
        setSectionForm({
          id: target.id,
          title: target.title,
          summary: target.summary ?? "",
          targetWords: target.target_words ?? 0,
          content: target.content ?? "",
        });
      },
    },
    {
      label: t("piece.addSectionBelow"),
      icon: <Plus size={11} />,
      onClick: () => {
        setDialogError("");
        setSectionCreate({
          afterId: sectionId,
          title: "",
          summary: "",
          targetWords: 400,
        });
      },
    },
    {
      label: t("piece.moveUp"),
      icon: <ArrowUp size={11} />,
      disabled: index === 0,
      onClick: () => void moveSection(sectionId, -1),
    },
    {
      label: t("piece.moveDown"),
      icon: <ArrowDown size={11} />,
      disabled: index === (piece?.outline.length ?? 0) - 1,
      onClick: () => void moveSection(sectionId, 1),
    },
    {
      label: t("piece.deleteSection"),
      icon: <Trash2 size={11} />,
      danger: true,
      onClick: () => {
        setDialogError("");
        setSectionDelete({ id: sectionId, title: sectionTitle });
      },
    },
  ];

  if (loading) {    return (
      <div className="glass grid place-items-center rounded-3xl p-16 shadow-glass">
        <Loader2 size={20} className="animate-spin text-indigo-500" />
      </div>
    );
  }

  if (!piece) {
    return (
      <div className="glass rounded-3xl p-10 text-center shadow-glass">
        <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
          {t("piece.notFound")}
        </p>
        {error ? (
          <p className="mt-2 break-words text-xs text-rose-600 dark:text-rose-300">{error}</p>
        ) : null}
        <Link to="/pieces" className="btn btn-quiet mx-auto mt-4">
          <ArrowLeft size={13} />
          {t("piece.backToList")}
        </Link>
      </div>
    );
  }

  const modeText =
    piece.last_mode === "loose" ? t("piece.loose") : t("piece.strict");
  const progress = piece.target_words
    ? Math.min(100, Math.round((words / piece.target_words) * 100))
    : 0;

  return (
    <div className="space-y-4">
      <div className="glass rounded-3xl p-4 shadow-glass sm:p-5">
        <div className="flex flex-wrap items-start gap-3">
          <Link
            to="/pieces"
            className="btn-quiet grid h-9 w-9 shrink-0 place-items-center rounded-full"
            title={t("piece.backToListTitle")}
          >
            <ArrowLeft size={15} />
          </Link>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="chip">{genreLabel(t, piece.profile?.genre ?? "")}</span>
              <span
                className={clsx(
                  "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium ring-1",
                  piece.last_mode === "loose"
                    ? "bg-amber-400/20 text-amber-700 ring-amber-500/30 dark:bg-amber-300/15 dark:text-amber-300 dark:ring-amber-300/25"
                    : "bg-emerald-500/12 text-emerald-700 ring-emerald-500/25 dark:bg-emerald-400/15 dark:text-emerald-300 dark:ring-emerald-300/25",
                )}
              >
                {modeText}
              </span>
              <span className="chip-muted">v{piece.current_version}</span>
              <span className="chip-muted">
                {t("piece.sectionCount", { count: piece.outline.length })}
              </span>
              <EditLockChip
                state={editLockState}
                onReadOnly={() => {
                  pieceLock.current?.stop(false);
                  pieceLock.current = null;
                  setEditLockState({ status: "idle" });
                }}
                onRetry={() => void pieceLock.current?.retry()}
              />
            </div>
            <h1 className="mt-2 flex items-center gap-1.5 text-lg font-semibold tracking-tight text-slate-800 dark:text-slate-100 sm:text-xl">
              <span className="min-w-0 break-words">{piece.title}</span>
              {writable ? (
                <button
                  type="button"
                  onClick={() => {
                    setDialogError("");
                    setTitleEditOpen(true);
                  }}
                  className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-slate-400 transition hover:bg-white/70 hover:text-indigo-600 dark:hover:bg-white/10 dark:hover:text-indigo-300"
                  aria-label={t("piece.editTitle")}
                >
                  <Pencil size={13} />
                </button>
              ) : null}
            </h1>
            {piece.brief ? (
              <p className="mt-1.5 max-w-2xl whitespace-pre-wrap break-words text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
                <span className="font-medium text-slate-600 dark:text-slate-300">
                  {t("piece.briefLabel")}:{" "}
                </span>
                <span className="line-clamp-3">{piece.brief}</span>
              </p>
            ) : null}
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
              <span className="tabular-nums">
                {t("piece.charsOfTarget", {
                  current: formatChars(words),
                  target: formatChars(piece.target_words),
                })}
              </span>
              {writable ? (
                <button
                  type="button"
                  onClick={() => {
                    setDialogError("");
                    setTargetEditOpen(true);
                  }}
                  className="rounded-full px-1.5 py-0.5 text-[10px] text-indigo-600 transition hover:bg-indigo-500/10 dark:text-indigo-300"
                >
                  {t("piece.editTarget")}
                </button>
              ) : null}
              {writable ? (
                <button
                  type="button"
                  onClick={() => {
                    setDialogError("");
                    setBriefDraft(piece.brief ?? "");
                    setBriefEditOpen(true);
                  }}
                  className="rounded-full px-1.5 py-0.5 text-[10px] text-indigo-600 transition hover:bg-indigo-500/10 dark:text-indigo-300"
                >
                  {t("piece.briefLabel")}
                </button>
              ) : null}
              <span className="h-1.5 w-28 overflow-hidden rounded-full bg-slate-500/15 dark:bg-white/10">
                <span
                  className="block h-full brand-gradient transition-all"
                  style={{ width: `${progress}%` }}
                />
              </span>
              <span>{progress}%</span>
              <span className="text-slate-400 dark:text-slate-500">
                {t("piece.updatedAt", {
                  time: formatDateTime(piece.updated_at || piece.created_at),
                })}
              </span>
            </div>
          </div>

          <div className="flex w-full min-w-0 flex-wrap items-center gap-2 lg:w-auto">
            <button
              type="button"
              onClick={generateAll}
              disabled={Boolean(busy) || !writable}
              className="btn btn-primary whitespace-nowrap"
              title={!writable ? t("common.readOnlyRole") : undefined}
            >
              {busy === "all" ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Play size={13} />
              )}
              {t("piece.generateAll")}
            </button>
            <a
              href={`/read/piece/${piece.id}`}
              target="_blank"
              rel="noreferrer"
              className="btn btn-quiet whitespace-nowrap"
              title={t("piece.readerHint")}
            >
              <BookOpen size={13} />
              {t("piece.readerMode")}
            </a>
            <button
              type="button"
              onClick={() => setRewriteOpen(true)}
              disabled={Boolean(busy) || !writable}
              className="btn btn-quiet whitespace-nowrap"
              title={!writable ? t("common.readOnlyRole") : undefined}
            >
              <Wand2 size={13} />
              {t("piece.rewrite")}
            </button>
            <button
              type="button"
              onClick={() => void openShare()}
              disabled={!canShare}
              className="btn btn-quiet whitespace-nowrap"
              title={canShare ? t("piece.shareHint") : t("piece.shareNoPermission")}
            >
              <Share2 size={13} />
              {t("common.share")}
            </button>
            <button
              type="button"
              onClick={() => setShareLinksOpen(true)}
              disabled={!writable}
              className="btn btn-quiet whitespace-nowrap"
              title={writable ? t("piece.shareLinkHint") : t("common.readOnlyRole")}
            >
              <Link2 size={13} />
              {t("piece.shareLink")}
            </button>
            <button
              type="button"
              data-testid="piece-edit"
              onClick={() => void openManual()}
              disabled={Boolean(busy) || !writable}
              className="btn btn-quiet whitespace-nowrap"
              title={!writable ? t("common.readOnlyRole") : t("piece.manualHint")}
            >
              <PenLine size={13} />
              {t("series.edit")}
            </button>
            <button
              type="button"
              onClick={() => setPickOpen(true)}
              disabled={Boolean(busy) || !writable}
              className="btn btn-quiet whitespace-nowrap"
              title={!writable ? t("common.readOnlyRole") : t("piece.insertImageHint")}
            >
              <ImagePlus size={13} />
              {t("piece.insertImage")}
            </button>
            <ExportMenu
              sourceType="piece"
              sourceId={piece.id}
              fallbackName={piece.title}
              className="max-lg:w-full max-lg:justify-end"
            />
            <button
              type="button"
              onClick={() => void load(true)}
              disabled={Boolean(busy)}
              className="btn btn-quiet whitespace-nowrap"
            >
              <RotateCcw size={13} />
              {t("common.refresh")}
            </button>
            <button
              type="button"
              onClick={remove}
              disabled={Boolean(busy) || !writable}
              className="btn btn-quiet whitespace-nowrap text-rose-600 dark:text-rose-300"
            >
              <X size={13} />
              {t("common.delete")}
            </button>
          </div>
        </div>

        {busy ? (
          <div className="mt-3 rounded-2xl border border-indigo-300/40 bg-indigo-50/60 px-4 py-2.5 text-xs text-indigo-700 dark:border-indigo-300/20 dark:bg-indigo-400/10 dark:text-indigo-200">
            <span className="flex items-center gap-2 font-medium">
              <Loader2 size={13} className="animate-spin" />
              {busy === "all"
                ? t("piece.busyFull")
                : busy === "rewrite"
                  ? t("piece.busyRewrite")
                  : busy.startsWith("revert-")
                    ? t("piece.busyRevert")
                    : t("piece.busySection")}
              <span className="ml-auto inline-flex items-center gap-1 tabular-nums">
                <Clock3 size={12} />
                {t("piece.elapsed", { seconds: elapsed })}
              </span>
            </span>
            {busy === "all" || busy === "rewrite" ? (
              <div className="mt-2 flex items-center gap-2">
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/60 dark:bg-white/10">
                  <div
                    className="brand-gradient h-full rounded-full transition-all duration-500"
                    style={{ width: `${Math.max(6, Math.round(jobProgress * 100))}%` }}
                  />
                </div>
                <span className="tabular-nums opacity-80">{Math.round(jobProgress * 100)}%</span>
                {jobId ? (
                  <button
                    type="button"
                    onClick={() => void cancelActive()}
                    className="rounded-full border border-current/30 px-2 py-0.5 text-[11px] font-medium"
                  >
                    {t("common.cancel")}
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

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

        {!writable ? (
          <div className="mt-3 rounded-2xl border border-amber-300/50 bg-amber-50/70 px-4 py-2.5 text-xs text-amber-700 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-300">
            {t("piece.readOnlyView", {
              role: roleLabel(t, roleKey, roleName) || t("common.readOnly"),
            })}
          </div>
        ) : null}
      </div>

      <div className="xl:hidden">
        <button
          type="button"
          onClick={() => setOutlineOpen((prev) => !prev)}
          className="btn btn-quiet w-full justify-between"
        >
          <span className="flex items-center gap-1.5">
            <Layers size={13} />
            {t("piece.outlineWithCount", { count: piece.outline.length })}
          </span>
          <ChevronDown size={14} className={clsx("transition", outlineOpen && "rotate-180")} />
        </button>
        <AnimatePresence initial={false}>
          {outlineOpen ? (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="glass mt-2 space-y-1.5 rounded-3xl p-3 shadow-glass">
                {piece.outline.map((section, index) => (
                  <div
                    key={section.id}
                    className="rounded-xl border border-white/45 bg-white/45 p-2.5 dark:border-white/10 dark:bg-white/[0.04]"
                  >
                    <button
                      type="button"
                      onClick={() => scrollToSection(section.title)}
                      className="block w-full text-left"
                    >
                      <span className="flex items-center gap-1.5 text-[12px] font-medium text-slate-700 dark:text-slate-200">
                        <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full brand-gradient text-[9px] font-semibold text-white">
                          {index + 1}
                        </span>
                        {section.title}
                      </span>
                      <span className="mt-1 flex items-center gap-1.5 text-[10px] text-slate-400 dark:text-slate-500">
                        <span>
                          {t("common.words", { count: section.target_words })}
                        </span>
                        <span>·</span>
                        <span>
                          {section.content ? t("piece.written") : t("piece.pending")}
                        </span>
                      </span>
                    </button>
                    <div className="mt-1.5 flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => void generateOne(section.id)}
                        disabled={Boolean(busy) || !writable}
                        className="btn-quiet flex-1 text-[11px]"
                      >
                        {busy === section.id ? (
                          <Loader2 size={11} className="animate-spin" />
                        ) : (
                          <Sparkles size={11} />
                        )}
                        {t("piece.generateSection")}
                      </button>
                      {writable ? (
                        <RowMenu
                          label={t("piece.sectionMenuLabel", { title: section.title })}
                          items={sectionMenuItems(section.id, section.title, index)}
                        />
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
        {writable ? (
          <button
            type="button"
            onClick={() => {
              setDialogError("");
              setSectionCreate({
                afterId: null,
                title: "",
                summary: "",
                targetWords: 400,
              });
            }}
            className="btn-quiet mt-2 w-full text-[11px]"
          >
            <Plus size={11} />
            {t("piece.addSectionEnd")}
          </button>
        ) : null}
      </div>

      <div className="grid gap-4 xl:grid-cols-[240px_minmax(0,1fr)_220px]">
        <aside className="glass hidden h-fit rounded-3xl p-3.5 shadow-glass xl:block">
          <h2 className="flex items-center gap-1.5 px-1 text-xs font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
            <Layers size={12} />
            {t("piece.outline")}
          </h2>
          <div className="no-scrollbar mt-2.5 max-h-[70vh] space-y-1.5 overflow-y-auto pr-1">
            {piece.outline.length === 0 ? (
              <p className="px-1 py-2 text-[11px] text-slate-400">
                {t("piece.outlineEmpty")}
              </p>
            ) : (
              piece.outline.map((section, index) => (
                <div
                  key={section.id}
                  className="rounded-xl border border-white/45 bg-white/45 p-2.5 transition hover:border-indigo-300/50 dark:border-white/10 dark:bg-white/[0.04]"
                >
                  <button
                    type="button"
                    onClick={() => scrollToSection(section.title)}
                    className="block w-full text-left"
                  >
                    <span className="flex items-start gap-1.5 text-[12px] font-medium leading-snug text-slate-700 dark:text-slate-200">
                      <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full brand-gradient text-[9px] font-semibold text-white">
                        {index + 1}
                      </span>
                      <span className="min-w-0">{section.title}</span>
                    </span>
                    <span className="mt-1 flex flex-wrap items-center gap-1 text-[10px] text-slate-400 dark:text-slate-500">
                      <span>
                        {t("common.words", { count: section.target_words })}
                      </span>
                      <span
                        className={clsx(
                          "rounded-full px-1.5 py-0.5 font-medium",
                          section.content
                            ? "bg-emerald-500/12 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300"
                            : "bg-slate-500/10 text-slate-500 dark:bg-white/10 dark:text-slate-400",
                        )}
                      >
                        {section.content ? t("piece.written") : t("piece.pending")}
                      </span>
                    </span>
                  </button>
                  <div className="mt-1.5 flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => void generateOne(section.id)}
                      disabled={Boolean(busy) || !writable}
                      className="btn-quiet flex-1 text-[11px]"
                      title={!writable ? t("common.readOnlyRole") : undefined}
                    >
                      {busy === section.id ? (
                        <Loader2 size={11} className="animate-spin" />
                      ) : (
                        <Sparkles size={11} />
                      )}
                      {t("piece.generateSection")}
                    </button>
                    {writable ? (
                      <RowMenu
                        label={t("piece.sectionMenuLabel", { title: section.title })}
                        items={sectionMenuItems(section.id, section.title, index)}
                      />
                    ) : null}
                  </div>
                </div>
              ))
            )}
          </div>
          {writable ? (
            <button
              type="button"
              onClick={() => {
                setDialogError("");
                setSectionCreate({
                  afterId: null,
                  title: "",
                  summary: "",
                  targetWords: 400,
                });
              }}
              className="btn-quiet mt-1.5 w-full text-[11px]"
            >
              <Plus size={11} />
              {t("piece.addSectionEnd")}
            </button>
          ) : null}
        </aside>

        <section className="glass min-w-0 rounded-3xl p-4 shadow-glass sm:p-6">
          <div ref={contentRef}>
            {piece.content ? (
              <MarkdownReader content={piece.content} citations={piece.citations} />
            ) : (
              <div className="py-12 text-center">
                <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl brand-gradient text-white shadow-brand">
                  <PenLine size={20} />
                </div>
                <p className="mt-3 text-sm font-medium text-slate-700 dark:text-slate-200">
                  {t("piece.contentEmpty")}
                </p>
                <p className="mx-auto mt-1.5 max-w-sm text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                  {t("piece.contentEmptyDesc")}
                </p>
                <button
                  type="button"
                  onClick={generateAll}
                  disabled={Boolean(busy) || !writable}
                  className="btn btn-primary mx-auto mt-4"
                >
                  {busy === "all" ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Play size={13} />
                  )}
                  {t("piece.generateAll")}
                </button>
              </div>
            )}
          </div>
        </section>

        <aside className="glass h-fit rounded-3xl p-3.5 shadow-glass">
          <h2 className="flex items-center gap-1.5 px-1 text-xs font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
            <History size={12} />
            {t("piece.versions")}
          </h2>
          <div className="no-scrollbar mt-2.5 max-h-[60vh] space-y-1.5 overflow-y-auto pr-1">
            {versions.length === 0 ? (
              <p className="px-1 py-2 text-[11px] text-slate-400">
                {t("piece.versionsEmpty")}
              </p>
            ) : (
              [...versions]
                .sort((a, b) => b.version - a.version)
                .map((version) => {
                  const active = selectedVersion === version.version;
                  const current = version.version === piece.current_version;
                  return (
                    <div
                      key={version.id}
                      className={clsx(
                        "rounded-xl border p-2.5 transition",
                        active
                          ? "border-indigo-400/60 bg-indigo-50/70 dark:border-indigo-300/30 dark:bg-indigo-400/10"
                          : "border-white/45 bg-white/45 hover:border-indigo-300/50 dark:border-white/10 dark:bg-white/[0.04]",
                      )}
                    >
                      <button
                        type="button"
                        onClick={() =>
                          setSelectedVersion(active ? null : version.version)
                        }
                        className="block w-full text-left"
                      >
                        <span className="flex items-center gap-1.5 text-[12px] font-semibold text-slate-700 dark:text-slate-200">
                          v{version.version}
                          {current ? (
                            <span className="rounded-full bg-emerald-500/12 px-1.5 py-0.5 text-[9px] font-medium text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300">
                              {t("piece.current")}
                            </span>
                          ) : null}
                          {version.mode ? (
                            <span className="text-[9px] font-normal text-slate-400">
                              {version.mode === "loose"
                                ? t("piece.loose")
                                : t("piece.strict")}
                            </span>
                          ) : null}
                        </span>
                        <span className="mt-0.5 block text-[10px] text-slate-400 dark:text-slate-500">
                          {formatChars(version.content_length)} ·{" "}
                          {formatDateTime(version.created_at)}
                        </span>
                        {version.note ? (
                          <span className="mt-0.5 block truncate text-[10px] text-slate-500 dark:text-slate-400">
                            {version.note}
                          </span>
                        ) : null}
                      </button>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1">
                        <button
                          type="button"
                          onClick={() => setPreviewVersion(version.version)}
                          className="btn-quiet px-2 py-1 text-[10.5px]"
                        >
                          <Eye size={11} />
                          {t("piece.preview")}
                        </button>
                        <button
                          type="button"
                          onClick={() => openVersionDiff(version.version)}
                          className="btn-quiet px-2 py-1 text-[10.5px]"
                        >
                          <GitCompare size={11} />
                          {t("piece.compare")}
                        </button>
                      </div>
                      {active && !current ? (
                        <button
                          type="button"
                          onClick={() => void revert(version.version)}
                          disabled={Boolean(busy) || !writable}
                          className="btn-quiet mt-1.5 w-full text-[11px]"
                          title={!writable ? t("common.readOnlyRole") : undefined}
                        >
                          {busy === `revert-${version.version}` ? (
                            <Loader2 size={11} className="animate-spin" />
                          ) : (
                            <RotateCcw size={11} />
                          )}
                          {t("piece.revertTo")}
                        </button>
                      ) : null}
                    </div>
                  );
                })
            )}
          </div>
          <p className="mt-2 px-1 text-[10px] leading-relaxed text-slate-400 dark:text-slate-500">
            {t("piece.versionsHint")}
          </p>
        </aside>
      </div>

      <AnimatePresence>
        {rewriteOpen ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/30 p-4 backdrop-blur-sm"
          >
            <motion.div
              initial={{ opacity: 0, y: 12, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.98 }}
              className="glass my-8 w-full max-w-lg rounded-3xl p-5 shadow-glass"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="flex items-center gap-1.5 text-sm font-semibold text-slate-800 dark:text-slate-100">
                    <Wand2 size={14} className="text-indigo-500" />
                    {t("piece.rewriteTitle")}
                  </h3>
                  <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                    {t("piece.rewriteDesc")}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setRewriteOpen(false)}
                  className="btn-quiet grid h-8 w-8 place-items-center rounded-full"
                >
                  <X size={14} />
                </button>
              </div>
              <label className="mt-4 block">
                <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  {t("piece.instructionLabel")}
                </span>
                <textarea
                  value={instruction}
                  onChange={(event) => setInstruction(event.target.value)}
                  rows={4}
                  className="input resize-y"
                  placeholder={t("piece.instructionPlaceholder")}
                />
              </label>
              <label className="mt-3 block">
                <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  {t("piece.fieldMode")}
                </span>
                <select
                  value={rewriteMode}
                  onChange={(event) =>
                    setRewriteMode(event.target.value as GenerationMode)
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
                  onClick={() => setRewriteOpen(false)}
                  className="btn btn-quiet"
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="button"
                  onClick={submitRewrite}
                  disabled={Boolean(busy) || !instruction.trim()}
                  className="btn btn-primary"
                >
                  {busy === "rewrite" ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <FileText size={13} />
                  )}
                  {t("piece.startRewrite")}
                </button>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <ShareLinksDialog
        open={shareLinksOpen}
        onClose={() => setShareLinksOpen(false)}
        resourceType="piece"
        resourceId={piece?.id ?? ""}
        title={piece?.title}
      />

      <SharePanel
        open={shareOpen}
        title={t("piece.shareTitle")}
        subtitle={piece ? piece.title : undefined}
        members={shareMembers}
        value={shareLevels}
        options={[
          { value: "read", label: t("sharing.read"), desc: t("piece.readDesc") },
          { value: "write", label: t("sharing.write"), desc: t("piece.writeDesc") },
        ]}
        loading={shareLoading}
        saving={shareSaving}
        error={shareError}
        onClose={() => setShareOpen(false)}
        onChange={(userId, level) =>
          setShareLevels((prev) => ({ ...prev, [userId]: level }))
        }
        onSave={saveShare}
      />

      <ImagePickerDrawer
        open={pickOpen}
        piece={piece}
        onClose={() => setPickOpen(false)}
        onInserted={(message) => {
          setNotice(message);
          void load(true);
        }}
      />

      <PromptDialog
        open={titleEditOpen}
        title={t("piece.editTitle")}
        label={t("piece.pieceTitle")}
        initial={piece?.title ?? ""}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={(value) => void saveTitle(value)}
        onClose={() => setTitleEditOpen(false)}
      />

      <PromptDialog
        open={targetEditOpen}
        title={t("piece.editTargetTitle")}
        label={t("piece.fieldTargetWords")}
        initial={String(piece?.target_words ?? 0)}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={(value) => void saveTargetWords(value)}
        onClose={() => setTargetEditOpen(false)}
      />

      <Modal
        open={briefEditOpen}
        title={t("piece.briefLabel")}
        subtitle={t("piece.briefHint")}
        onClose={() => setBriefEditOpen(false)}
        wide
      >
        <div className="space-y-3">
          <textarea
            value={briefDraft}
            onChange={(event) => setBriefDraft(event.target.value)}
            className="input min-h-[10rem] resize-y"
            rows={6}
            placeholder={t("piece.briefPlaceholder")}
          />
          {dialogError ? (
            <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
              {dialogError}
            </p>
          ) : null}
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => setBriefEditOpen(false)}
              className="btn btn-quiet"
            >
              {t("common.cancel")}
            </button>
            <button
              type="button"
              onClick={() => void saveBrief()}
              disabled={dialogBusy}
              className="btn btn-primary"
            >
              {dialogBusy ? <Loader2 size={13} className="animate-spin" /> : null}
              {t("common.saveChanges")}
            </button>
          </div>
        </div>
      </Modal>

      <PromptDialog
        open={Boolean(sectionRename)}
        title={t("piece.renameSection")}
        label={t("piece.sectionTitle")}
        initial={sectionRename?.title ?? ""}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={(value) => void renameSection(value)}
        onClose={() => setSectionRename(null)}
      />

      <Modal
        open={Boolean(sectionForm)}
        title={t("piece.editSectionTitle")}
        subtitle={t("piece.editSectionDesc")}
        onClose={() => setSectionForm(null)}
        wide
      >
        {sectionForm ? (
          <div className="space-y-3">
            <label className="block text-[11px] text-slate-500 dark:text-slate-400">
              {t("piece.fieldTitle")}
              <input
                value={sectionForm.title}
                onChange={(event) =>
                  setSectionForm({ ...sectionForm, title: event.target.value })
                }
                className="input mt-1"
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-[1fr_130px]">
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                {t("piece.fieldSummary")}
                <input
                  value={sectionForm.summary}
                  onChange={(event) =>
                    setSectionForm({ ...sectionForm, summary: event.target.value })
                  }
                  className="input mt-1"
                />
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                {t("piece.fieldTargetWords")}
                <input
                  type="number"
                  value={sectionForm.targetWords}
                  onChange={(event) =>
                    setSectionForm({
                      ...sectionForm,
                      targetWords: Number(event.target.value),
                    })
                  }
                  className="input mt-1"
                />
              </label>
            </div>
            <label className="block text-[11px] text-slate-500 dark:text-slate-400">
              {t("piece.fieldSectionContent")}
              <textarea
                value={sectionForm.content}
                onChange={(event) =>
                  setSectionForm({ ...sectionForm, content: event.target.value })
                }
                rows={10}
                className="input mt-1 font-mono text-[12px] leading-relaxed"
              />
            </label>
            {dialogError ? (
              <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
                {dialogError}
              </p>
            ) : null}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setSectionForm(null)}
                className="btn btn-quiet"
              >
                {t("common.cancel")}
              </button>
              <button
                type="button"
                onClick={() => void saveSectionForm()}
                disabled={dialogBusy || !sectionForm.title.trim()}
                className="btn btn-primary"
              >
                {dialogBusy ? <Loader2 size={13} className="animate-spin" /> : null}
                {t("piece.saveSection")}
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(sectionCreate)}
        title={t("piece.addSectionTitle")}
        onClose={() => setSectionCreate(null)}
      >
        {sectionCreate ? (
          <div className="space-y-3">
            <label className="block text-[11px] text-slate-500 dark:text-slate-400">
              {t("piece.sectionTitle")}
              <input
                autoFocus
                value={sectionCreate.title}
                onChange={(event) =>
                  setSectionCreate({ ...sectionCreate, title: event.target.value })
                }
                className="input mt-1"
                placeholder={t("piece.sectionTitlePlaceholder")}
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-[1fr_130px]">
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                {t("piece.fieldSummary")}
                <input
                  value={sectionCreate.summary}
                  onChange={(event) =>
                    setSectionCreate({ ...sectionCreate, summary: event.target.value })
                  }
                  className="input mt-1"
                />
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                {t("piece.fieldTargetWords")}
                <input
                  type="number"
                  value={sectionCreate.targetWords}
                  onChange={(event) =>
                    setSectionCreate({
                      ...sectionCreate,
                      targetWords: Number(event.target.value),
                    })
                  }
                  className="input mt-1"
                />
              </label>
            </div>
            <p className="text-[10.5px] text-slate-400 dark:text-slate-500">
              {sectionCreate.afterId
                ? t("piece.insertAfter")
                : t("piece.appendEnd")}
            </p>
            {dialogError ? (
              <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
                {dialogError}
              </p>
            ) : null}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setSectionCreate(null)}
                className="btn btn-quiet"
              >
                {t("common.cancel")}
              </button>
              <button
                type="button"
                onClick={() => void createSection()}
                disabled={dialogBusy || !sectionCreate.title.trim()}
                className="btn btn-primary"
              >
                {dialogBusy ? <Loader2 size={13} className="animate-spin" /> : null}
                {t("piece.addSectionTitle")}
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        open={Boolean(sectionDelete)}
        title={t("piece.deleteSectionTitle")}
        description={t("piece.deleteSectionDesc", {
          title: sectionDelete?.title ?? "",
        })}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={() => void deleteSection()}
        onClose={() => setSectionDelete(null)}
      />

      <Modal
        open={manualOpen}
        title={t("piece.manualEditTitle")}
        subtitle={t("piece.manualEditDesc", {
          version: piece?.current_version ?? 0,
        })}
        onClose={() => void closeManual()}
        wide
      >
        <div className="space-y-3">
          <textarea
            value={manualText}
            onChange={(event) => setManualText(event.target.value)}
            rows={16}
            className="input w-full font-mono text-[12px] leading-relaxed"
            placeholder={t("piece.manualPlaceholder")}
          />
          <div className="flex items-center justify-between gap-2 text-[10.5px] text-slate-400 dark:text-slate-500">
            <span>{t("piece.charCount", { count: manualText.length })}</span>
            {dialogError ? (
              <span className="text-rose-600 dark:text-rose-300">{dialogError}</span>
            ) : null}
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => void closeManual()}
              className="btn btn-quiet"
            >
              {t("common.cancel")}
            </button>
            <button
              type="button"
              onClick={() => void saveManual()}
              disabled={dialogBusy}
              className="btn btn-primary"
            >
              {dialogBusy ? <Loader2 size={13} className="animate-spin" /> : null}
              {t("piece.saveAsVersion")}
            </button>
          </div>
        </div>
      </Modal>

      <VersionPreviewDialog
        open={previewVersion !== null}
        version={previewVersion}
        load={loadVersionPreview}
        onClose={() => setPreviewVersion(null)}
        onCompare={() => {
          const target = previewVersion;
          setPreviewVersion(null);
          if (target !== null) openVersionDiff(target);
        }}
      />

      <VersionDiffDialog
        open={versionDiffOpen}
        versions={versions.map((item) => item.version)}
        initialFrom={
          versionDiffAnchor !== null
            ? Math.max(1, versionDiffAnchor - 1)
            : versions.length > 1
              ? [...versions].sort((a, b) => a.version - b.version)[0].version
              : 1
        }
        initialTo={
          versionDiffAnchor ??
          (piece?.current_version ||
            versions.reduce((max, item) => Math.max(max, item.version), 1))
        }
        fetchDiff={fetchVersionDiff}
        onClose={() => setVersionDiffOpen(false)}
      />
    </div>
  );
}
