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
  type Longform,
  type LongformVersion,
} from "@/lib/api";
import { cancelJob, runJob } from "@/lib/jobs";
import { contentLength, formatChars, formatDateTime } from "@/lib/format";
import MarkdownReader from "@/components/reader/MarkdownReader";
import VersionDiffDialog from "@/components/reader/VersionDiffDialog";
import VersionPreviewDialog from "@/components/reader/VersionPreviewDialog";
import { useSession } from "@/components/auth/SessionProvider";
import { useI18n } from "@/i18n/I18nProvider";
import SharePanel, { type ShareMember } from "@/components/sharing/SharePanel";
import ShareLinksDialog from "@/components/share/ShareLinksDialog";
import ExportMenu from "@/components/export/ExportMenu";
import ImagePickerDrawer from "@/components/media/ImagePickerDrawer";
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

export default function LongformEditorPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { can, roleName, tenant } = useSession();
  const { t } = useI18n();
  const writable = can("write");

  const genreLabel = (value: string) =>
    (GENRE_VALUES as readonly string[]).includes(value)
      ? t(`longform.genre.${value}`)
      : t("longform.genre.article");

  const [longform, setLongform] = useState<Longform | null>(null);
  const [versions, setVersions] = useState<LongformVersion[]>([]);
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
        api.getLongformGrants(id),
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
      setShareError(err instanceof Error ? err.message : t("longform.shareLoadFailed"));
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
        await api.saveLongformGrants(id, entries);
        setNotice(t("longform.shareSaved"));
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

  const load = useCallback(
    async (quiet = false) => {
      if (!id) return;
      if (!quiet) setLoading(true);
      try {
        const [detail, versionData] = await Promise.all([
          api.getLongform(id),
          api.listLongformVersions(id),
        ]);
        setLongform(detail);
        setVersions(versionData.versions);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("longform.loadFailed"));
      } finally {
        setLoading(false);
      }
    },
    [id, t],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const words = useMemo(
    () => (longform?.content ? contentLength(longform.content) : 0),
    [longform],
  );

  const generateAll = async () => {
    if (!longform || busy) return;
    if (!writable) {
      setError(t("longform.readOnlyGenerate"));
      return;
    }
    setBusy("all");
    setJobProgress(0);
    setJobId(null);
    setError("");
    setNotice("");
    const startedAt = Date.now();
    try {
      let updated: Longform | null = null;
      try {
        await runJob(
          "longform_generate",
          { longform_id: longform.id },
          {
            onProgress: setJobProgress,
            onJob: (created) => setJobId(created.id),
          },
        );
        updated = await api.getLongform(longform.id);
      } catch (queueErr) {
        const queueable =
          queueErr instanceof ApiError &&
          (queueErr.status === 400 || queueErr.status === 404 || queueErr.status === 422);
        if (!queueable) throw queueErr;
        updated = await api.generateLongform(longform.id, {
          mode: (longform.last_mode as GenerationMode) || "loose",
          expected_version: longform.current_version,
        });
      }
      setLongform(updated);
      const versionData = await api.listLongformVersions(longform.id);
      setVersions(versionData.versions);
      const seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      setNotice(
        t("longform.generatedFull", {
          seconds,
          version: updated.current_version,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : t("longform.generateFailed"));
    } finally {
      setBusy("");
      setJobId(null);
    }
  };

  const generateOne = async (sectionId: string) => {
    if (!longform || busy) return;
    if (!writable) {
      setError(t("longform.readOnlyGenerateSection"));
      return;
    }
    setBusy(sectionId);
    setError("");
    setNotice("");
    const startedAt = Date.now();
    try {
      const result = await api.generateSection(longform.id, sectionId, {
        mode: (longform.last_mode as GenerationMode) || "loose",
      });
      setLongform(result.longform);
      const versionData = await api.listLongformVersions(longform.id);
      setVersions(versionData.versions);
      const seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      setNotice(t("longform.generatedSection", { seconds }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("longform.generateSectionFailed"));
    } finally {
      setBusy("");
    }
  };

  const submitRewrite = async () => {
    const text = instruction.trim();
    if (!longform || !text || busy) return;
    if (!writable) {
      setError(t("longform.readOnlyRewrite"));
      return;
    }
    setBusy("rewrite");
    setJobProgress(0);
    setJobId(null);
    setError("");
    setNotice("");
    const startedAt = Date.now();
    try {
      let updated: Longform | null = null;
      try {
        await runJob(
          "longform_rewrite",
          { longform_id: longform.id, instruction: text },
          {
            onProgress: setJobProgress,
            onJob: (created) => setJobId(created.id),
          },
        );
        updated = await api.getLongform(longform.id);
      } catch (queueErr) {
        const queueable =
          queueErr instanceof ApiError &&
          (queueErr.status === 400 || queueErr.status === 404 || queueErr.status === 422);
        if (!queueable) throw queueErr;
        updated = await api.rewriteLongform(longform.id, {
          instruction: text,
          mode: rewriteMode,
          expected_version: longform.current_version,
        });
      }
      setLongform(updated);
      const versionData = await api.listLongformVersions(longform.id);
      setVersions(versionData.versions);
      setRewriteOpen(false);
      setInstruction("");
      const seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      setNotice(
        t("longform.rewriteDone", {
          seconds,
          version: updated.current_version,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : t("longform.rewriteFailed"));
    } finally {
      setBusy("");
      setJobId(null);
    }
  };

  const cancelActive = async () => {
    if (!jobId) return;
    try {
      await cancelJob(jobId);
      setNotice(t("longform.cancelRequested"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("longform.cancelFailed"));
    }
  };

  const openVersionDiff = (version: number) => {
    setVersionDiffAnchor(version);
    setVersionDiffOpen(true);
  };

  const loadVersionPreview = async (version: number) => {
    const detail = await api.getLongformVersion(id, version);
    return {
      content: detail.version.content ?? "",
      citations: detail.version.citations ?? [],
    };
  };

  const fetchVersionDiff = async (from: number, to: number) => {
    return api.diffLongformVersions(id, from, to);
  };

  const revert = async (version: number) => {
    if (!longform || busy) return;
    if (!writable) return;
    const confirmed = window.confirm(t("longform.confirmRevert", { version }));
    if (!confirmed) return;
    setBusy(`revert-${version}`);
    setError("");
    try {
      const updated = await api.revertLongform(longform.id, version);
      setLongform(updated);
      const versionData = await api.listLongformVersions(longform.id);
      setVersions(versionData.versions);
      setNotice(t("longform.reverted", { version, current: updated.current_version }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("longform.revertFailed"));
    } finally {
      setBusy("");
    }
  };

  const remove = async () => {
    if (!longform || !writable) return;
    const confirmed = window.confirm(
      t("longform.confirmDelete", { title: longform.title }),
    );
    if (!confirmed) return;
    try {
      await api.deleteLongform(longform.id);
      navigate("/longforms");
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

  const openManual = () => {
    if (!longform) return;
    setDialogError("");
    setManualText(longform.content ?? "");
    setManualOpen(true);
  };

  const saveManual = async () => {
    if (!longform) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.saveLongformContent(longform.id, {
        content: manualText,
        note: t("longform.manualNote"),
        expected_version: longform.current_version,
      });
      setLongform(updated);
      const versionData = await api.listLongformVersions(longform.id);
      setVersions(versionData.versions);
      setManualOpen(false);
      setNotice(t("longform.savedAsVersion", { version: updated.current_version }));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("errors.saveFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const saveTitle = async (value: string) => {
    if (!longform) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updateLongform(longform.id, { title: value });
      setLongform(updated);
      setTitleEditOpen(false);
      setNotice(t("longform.titleUpdated"));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("longform.updateFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const saveTargetWords = async (value: string) => {
    if (!longform) return;
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setDialogError(t("longform.targetWordsInvalid"));
      return;
    }
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updateLongform(longform.id, {
        target_words: Math.round(parsed),
      });
      setLongform(updated);
      setTargetEditOpen(false);
      setNotice(t("longform.targetUpdated"));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("longform.updateFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const renameSection = async (value: string) => {
    if (!longform || !sectionRename) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updateLongformSection(longform.id, sectionRename.id, {
        title: value,
      });
      setLongform(updated);
      setSectionRename(null);
      setNotice(t("longform.sectionRenamed"));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("longform.renameFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const saveSectionForm = async () => {
    if (!longform || !sectionForm) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updateLongformSection(longform.id, sectionForm.id, {
        title: sectionForm.title.trim(),
        summary: sectionForm.summary,
        target_words: Number(sectionForm.targetWords) || 0,
        content: sectionForm.content,
      });
      setLongform(updated);
      setSectionForm(null);
      setNotice(t("longform.sectionSaved"));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("errors.saveFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const createSection = async () => {
    if (!longform || !sectionCreate) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const result = await api.createLongformSection(longform.id, {
        title: sectionCreate.title.trim(),
        summary: sectionCreate.summary,
        target_words: Number(sectionCreate.targetWords) || 0,
        after_id: sectionCreate.afterId,
      });
      setLongform(result.longform);
      setSectionCreate(null);
      setNotice(t("longform.sectionCreated"));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("longform.createFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const deleteSection = async () => {
    if (!longform || !sectionDelete) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.deleteLongformSection(longform.id, sectionDelete.id);
      setLongform(updated);
      setSectionDelete(null);
      setNotice(t("longform.sectionDeleted"));
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("errors.deleteFailed"));
    } finally {
      setDialogBusy(false);
    }
  };

  const moveSection = async (sectionId: string, direction: -1 | 1) => {
    if (!longform) return;
    const ids = longform.outline.map((section) => section.id);
    const index = ids.indexOf(sectionId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ids.length) return;
    const next = [...ids];
    next[index] = ids[target];
    next[target] = ids[index];
    try {
      const updated = await api.reorderLongformSections(longform.id, next);
      setLongform(updated);
      setNotice(t("longform.orderUpdated"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("longform.reorderFailed"));
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
      label: t("longform.editSection"),
      icon: <FileText size={11} />,
      onClick: () => {
        const target = longform?.outline.find((item) => item.id === sectionId);
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
      label: t("longform.addSectionBelow"),
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
      label: t("longform.moveUp"),
      icon: <ArrowUp size={11} />,
      disabled: index === 0,
      onClick: () => void moveSection(sectionId, -1),
    },
    {
      label: t("longform.moveDown"),
      icon: <ArrowDown size={11} />,
      disabled: index === (longform?.outline.length ?? 0) - 1,
      onClick: () => void moveSection(sectionId, 1),
    },
    {
      label: t("longform.deleteSection"),
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

  if (!longform) {
    return (
      <div className="glass rounded-3xl p-10 text-center shadow-glass">
        <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
          {t("longform.notFound")}
        </p>
        {error ? (
          <p className="mt-2 break-words text-xs text-rose-600 dark:text-rose-300">{error}</p>
        ) : null}
        <Link to="/longforms" className="btn btn-quiet mx-auto mt-4">
          <ArrowLeft size={13} />
          {t("longform.backToList")}
        </Link>
      </div>
    );
  }

  const modeText =
    longform.last_mode === "loose" ? t("longform.loose") : t("longform.strict");
  const progress = longform.target_words
    ? Math.min(100, Math.round((words / longform.target_words) * 100))
    : 0;

  return (
    <div className="space-y-4">
      <div className="glass rounded-3xl p-4 shadow-glass sm:p-5">
        <div className="flex flex-wrap items-start gap-3">
          <Link
            to="/longforms"
            className="btn-quiet grid h-9 w-9 shrink-0 place-items-center rounded-full"
            title={t("longform.backToListTitle")}
          >
            <ArrowLeft size={15} />
          </Link>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="chip">{genreLabel(longform.profile?.genre ?? "")}</span>
              <span
                className={clsx(
                  "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium ring-1",
                  longform.last_mode === "loose"
                    ? "bg-amber-400/20 text-amber-700 ring-amber-500/30 dark:bg-amber-300/15 dark:text-amber-300 dark:ring-amber-300/25"
                    : "bg-emerald-500/12 text-emerald-700 ring-emerald-500/25 dark:bg-emerald-400/15 dark:text-emerald-300 dark:ring-emerald-300/25",
                )}
              >
                {modeText}
              </span>
              <span className="chip-muted">v{longform.current_version}</span>
              <span className="chip-muted">
                {t("longform.sectionCount", { count: longform.outline.length })}
              </span>
            </div>
            <h1 className="mt-2 flex items-center gap-1.5 text-lg font-semibold tracking-tight text-slate-800 dark:text-slate-100 sm:text-xl">
              <span className="min-w-0 break-words">{longform.title}</span>
              {writable ? (
                <button
                  type="button"
                  onClick={() => {
                    setDialogError("");
                    setTitleEditOpen(true);
                  }}
                  className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-slate-400 transition hover:bg-white/70 hover:text-indigo-600 dark:hover:bg-white/10 dark:hover:text-indigo-300"
                  aria-label={t("longform.editTitle")}
                >
                  <Pencil size={13} />
                </button>
              ) : null}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
              <span className="tabular-nums">
                {t("longform.charsOfTarget", {
                  current: formatChars(words),
                  target: formatChars(longform.target_words),
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
                  {t("longform.editTarget")}
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
                {t("longform.updatedAt", {
                  time: formatDateTime(longform.updated_at || longform.created_at),
                })}
              </span>
            </div>
          </div>

          <div className="no-scrollbar flex w-full shrink-0 items-center gap-2 overflow-x-auto lg:w-auto">
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
              {t("longform.generateAll")}
            </button>
            <a
              href={`/read/longform/${longform.id}`}
              target="_blank"
              rel="noreferrer"
              className="btn btn-quiet whitespace-nowrap"
              title={t("longform.readerHint")}
            >
              <BookOpen size={13} />
              {t("longform.readerMode")}
            </a>
            <button
              type="button"
              onClick={() => setRewriteOpen(true)}
              disabled={Boolean(busy) || !writable}
              className="btn btn-quiet whitespace-nowrap"
              title={!writable ? t("common.readOnlyRole") : undefined}
            >
              <Wand2 size={13} />
              {t("longform.rewrite")}
            </button>
            <button
              type="button"
              onClick={() => void openShare()}
              disabled={!canShare}
              className="btn btn-quiet whitespace-nowrap"
              title={canShare ? t("longform.shareHint") : t("longform.shareNoPermission")}
            >
              <Share2 size={13} />
              {t("common.share")}
            </button>
            <button
              type="button"
              onClick={() => setShareLinksOpen(true)}
              disabled={!writable}
              className="btn btn-quiet whitespace-nowrap"
              title={writable ? t("longform.shareLinkHint") : t("common.readOnlyRole")}
            >
              <Link2 size={13} />
              {t("longform.shareLink")}
            </button>
            <button
              type="button"
              onClick={openManual}
              disabled={Boolean(busy) || !writable}
              className="btn btn-quiet whitespace-nowrap"
              title={!writable ? t("common.readOnlyRole") : t("longform.manualHint")}
            >
              <PenLine size={13} />
              {t("longform.manualEdit")}
            </button>
            <button
              type="button"
              onClick={() => setPickOpen(true)}
              disabled={Boolean(busy) || !writable}
              className="btn btn-quiet whitespace-nowrap"
              title={!writable ? t("common.readOnlyRole") : t("longform.insertImageHint")}
            >
              <ImagePlus size={13} />
              {t("longform.insertImage")}
            </button>
            <ExportMenu
              sourceType="longform"
              sourceId={longform.id}
              fallbackName={longform.title}
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
                ? t("longform.busyFull")
                : busy === "rewrite"
                  ? t("longform.busyRewrite")
                  : busy.startsWith("revert-")
                    ? t("longform.busyRevert")
                    : t("longform.busySection")}
              <span className="ml-auto inline-flex items-center gap-1 tabular-nums">
                <Clock3 size={12} />
                {t("longform.elapsed", { seconds: elapsed })}
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
            {t("longform.readOnlyView", { role: roleName || t("common.readOnly") })}
          </div>
        ) : null}
      </div>

      <div className="lg:hidden">
        <button
          type="button"
          onClick={() => setOutlineOpen((prev) => !prev)}
          className="btn btn-quiet w-full justify-between"
        >
          <span className="flex items-center gap-1.5">
            <Layers size={13} />
            {t("longform.outlineWithCount", { count: longform.outline.length })}
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
                {longform.outline.map((section, index) => (
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
                          {section.content ? t("longform.written") : t("longform.pending")}
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
                        {t("longform.generateSection")}
                      </button>
                      {writable ? (
                        <RowMenu
                          label={t("longform.sectionMenuLabel", { title: section.title })}
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
            {t("longform.addSectionEnd")}
          </button>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)_220px]">
        <aside className="glass hidden h-fit rounded-3xl p-3.5 shadow-glass lg:block">
          <h2 className="flex items-center gap-1.5 px-1 text-xs font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
            <Layers size={12} />
            {t("longform.outline")}
          </h2>
          <div className="no-scrollbar mt-2.5 max-h-[70vh] space-y-1.5 overflow-y-auto pr-1">
            {longform.outline.length === 0 ? (
              <p className="px-1 py-2 text-[11px] text-slate-400">
                {t("longform.outlineEmpty")}
              </p>
            ) : (
              longform.outline.map((section, index) => (
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
                        {section.content ? t("longform.written") : t("longform.pending")}
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
                      {t("longform.generateSection")}
                    </button>
                    {writable ? (
                      <RowMenu
                        label={t("longform.sectionMenuLabel", { title: section.title })}
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
              {t("longform.addSectionEnd")}
            </button>
          ) : null}
        </aside>

        <section className="glass min-w-0 rounded-3xl p-4 shadow-glass sm:p-6">
          <div ref={contentRef}>
            {longform.content ? (
              <MarkdownReader content={longform.content} citations={longform.citations} />
            ) : (
              <div className="py-12 text-center">
                <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl brand-gradient text-white shadow-brand">
                  <PenLine size={20} />
                </div>
                <p className="mt-3 text-sm font-medium text-slate-700 dark:text-slate-200">
                  {t("longform.contentEmpty")}
                </p>
                <p className="mx-auto mt-1.5 max-w-sm text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                  {t("longform.contentEmptyDesc")}
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
                  {t("longform.generateAll")}
                </button>
              </div>
            )}
          </div>
        </section>

        <aside className="glass h-fit rounded-3xl p-3.5 shadow-glass">
          <h2 className="flex items-center gap-1.5 px-1 text-xs font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
            <History size={12} />
            {t("longform.versions")}
          </h2>
          <div className="no-scrollbar mt-2.5 max-h-[60vh] space-y-1.5 overflow-y-auto pr-1">
            {versions.length === 0 ? (
              <p className="px-1 py-2 text-[11px] text-slate-400">
                {t("longform.versionsEmpty")}
              </p>
            ) : (
              [...versions]
                .sort((a, b) => b.version - a.version)
                .map((version) => {
                  const active = selectedVersion === version.version;
                  const current = version.version === longform.current_version;
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
                              {t("longform.current")}
                            </span>
                          ) : null}
                          {version.mode ? (
                            <span className="text-[9px] font-normal text-slate-400">
                              {version.mode === "loose"
                                ? t("longform.loose")
                                : t("longform.strict")}
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
                          {t("longform.preview")}
                        </button>
                        <button
                          type="button"
                          onClick={() => openVersionDiff(version.version)}
                          className="btn-quiet px-2 py-1 text-[10.5px]"
                        >
                          <GitCompare size={11} />
                          {t("longform.compare")}
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
                          {t("longform.revertTo")}
                        </button>
                      ) : null}
                    </div>
                  );
                })
            )}
          </div>
          <p className="mt-2 px-1 text-[10px] leading-relaxed text-slate-400 dark:text-slate-500">
            {t("longform.versionsHint")}
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
                    {t("longform.rewriteTitle")}
                  </h3>
                  <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                    {t("longform.rewriteDesc")}
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
                  {t("longform.instructionLabel")}
                </span>
                <textarea
                  value={instruction}
                  onChange={(event) => setInstruction(event.target.value)}
                  rows={4}
                  className="input resize-y"
                  placeholder={t("longform.instructionPlaceholder")}
                />
              </label>
              <label className="mt-3 block">
                <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  {t("longform.fieldMode")}
                </span>
                <select
                  value={rewriteMode}
                  onChange={(event) =>
                    setRewriteMode(event.target.value as GenerationMode)
                  }
                  className="select"
                >
                  <option value="loose">{t("longform.modeLooseOption")}</option>
                  <option value="strict">{t("longform.modeStrictCiteOption")}</option>
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
                  {t("longform.startRewrite")}
                </button>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <ShareLinksDialog
        open={shareLinksOpen}
        onClose={() => setShareLinksOpen(false)}
        resourceType="longform"
        resourceId={longform?.id ?? ""}
        title={longform?.title}
      />

      <SharePanel
        open={shareOpen}
        title={t("longform.shareTitle")}
        subtitle={longform ? longform.title : undefined}
        members={shareMembers}
        value={shareLevels}
        options={[
          { value: "read", label: t("sharing.read"), desc: t("longform.readDesc") },
          { value: "write", label: t("sharing.write"), desc: t("longform.writeDesc") },
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
        longform={longform}
        onClose={() => setPickOpen(false)}
        onInserted={(message) => {
          setNotice(message);
          void load(true);
        }}
      />

      <PromptDialog
        open={titleEditOpen}
        title={t("longform.editTitle")}
        label={t("longform.longformTitle")}
        initial={longform?.title ?? ""}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={(value) => void saveTitle(value)}
        onClose={() => setTitleEditOpen(false)}
      />

      <PromptDialog
        open={targetEditOpen}
        title={t("longform.editTargetTitle")}
        label={t("longform.fieldTargetWords")}
        initial={String(longform?.target_words ?? 0)}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={(value) => void saveTargetWords(value)}
        onClose={() => setTargetEditOpen(false)}
      />

      <PromptDialog
        open={Boolean(sectionRename)}
        title={t("longform.renameSection")}
        label={t("longform.sectionTitle")}
        initial={sectionRename?.title ?? ""}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={(value) => void renameSection(value)}
        onClose={() => setSectionRename(null)}
      />

      <Modal
        open={Boolean(sectionForm)}
        title={t("longform.editSectionTitle")}
        subtitle={t("longform.editSectionDesc")}
        onClose={() => setSectionForm(null)}
        wide
      >
        {sectionForm ? (
          <div className="space-y-3">
            <label className="block text-[11px] text-slate-500 dark:text-slate-400">
              {t("longform.fieldTitle")}
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
                {t("longform.fieldSummary")}
                <input
                  value={sectionForm.summary}
                  onChange={(event) =>
                    setSectionForm({ ...sectionForm, summary: event.target.value })
                  }
                  className="input mt-1"
                />
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                {t("longform.fieldTargetWords")}
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
              {t("longform.fieldSectionContent")}
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
                {t("longform.saveSection")}
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(sectionCreate)}
        title={t("longform.addSectionTitle")}
        onClose={() => setSectionCreate(null)}
      >
        {sectionCreate ? (
          <div className="space-y-3">
            <label className="block text-[11px] text-slate-500 dark:text-slate-400">
              {t("longform.sectionTitle")}
              <input
                autoFocus
                value={sectionCreate.title}
                onChange={(event) =>
                  setSectionCreate({ ...sectionCreate, title: event.target.value })
                }
                className="input mt-1"
                placeholder={t("longform.sectionTitlePlaceholder")}
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-[1fr_130px]">
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                {t("longform.fieldSummary")}
                <input
                  value={sectionCreate.summary}
                  onChange={(event) =>
                    setSectionCreate({ ...sectionCreate, summary: event.target.value })
                  }
                  className="input mt-1"
                />
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                {t("longform.fieldTargetWords")}
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
                ? t("longform.insertAfter")
                : t("longform.appendEnd")}
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
                {t("longform.addSectionTitle")}
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        open={Boolean(sectionDelete)}
        title={t("longform.deleteSectionTitle")}
        description={t("longform.deleteSectionDesc", {
          title: sectionDelete?.title ?? "",
        })}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={() => void deleteSection()}
        onClose={() => setSectionDelete(null)}
      />

      <Modal
        open={manualOpen}
        title={t("longform.manualEditTitle")}
        subtitle={t("longform.manualEditDesc", {
          version: longform?.current_version ?? 0,
        })}
        onClose={() => setManualOpen(false)}
        wide
      >
        <div className="space-y-3">
          <textarea
            value={manualText}
            onChange={(event) => setManualText(event.target.value)}
            rows={16}
            className="input w-full font-mono text-[12px] leading-relaxed"
            placeholder={t("longform.manualPlaceholder")}
          />
          <div className="flex items-center justify-between gap-2 text-[10.5px] text-slate-400 dark:text-slate-500">
            <span>{t("longform.charCount", { count: manualText.length })}</span>
            {dialogError ? (
              <span className="text-rose-600 dark:text-rose-300">{dialogError}</span>
            ) : null}
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setManualOpen(false)}
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
              {t("longform.saveAsVersion")}
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
          (longform?.current_version ||
            versions.reduce((max, item) => Math.max(max, item.version), 1))
        }
        fetchDiff={fetchVersionDiff}
        onClose={() => setVersionDiffOpen(false)}
      />
    </div>
  );
}
