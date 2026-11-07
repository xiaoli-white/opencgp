import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  BookOpen,
  Copy,
  Download,
  Loader2,
  Lock,
  Pencil,
  Plus,
  Share2,
  Trash2,
  Upload,
  Wand2,
  X,
} from "lucide-react";
import clsx from "clsx";
import {
  ApiError,
  api,
  type Member,
  type ProfileShareLevel,
  type ProfileSpec,
  type ProfileValidationIssue,
  type WorkProfile,
} from "@/lib/api";
import { useSession } from "@/components/auth/SessionProvider";
import { ConfirmDialog, PromptDialog } from "@/components/common/Dialogs";
import ProfileEditor from "@/components/profiles/ProfileEditor";
import SharePanel, { type ShareMember } from "@/components/sharing/SharePanel";
import { useI18n } from "@/i18n/I18nProvider";
import {
  policyLabel,
  profileDescriptionLabel,
  profileNameLabel,
  profileUnitNameLabel,
  validatorLabel,
} from "@/i18n/labels";

function scopeKey(profile: WorkProfile): string {
  if (profile.is_builtin) return "profiles.scopeBuiltin";
  const scope = profile.scope ?? "user";
  if (scope === "global") return "profiles.scopeGlobal";
  if (scope === "tenant") return "profiles.scopeTenant";
  return "profiles.scopeUser";
}

function ProfileCard({
  profile,
  t,
  onEdit,
  onDuplicate,
  onDelete,
  onShare,
  onExport,
  exporting,
  canWrite,
}: {
  profile: WorkProfile;
  t: (path: string, vars?: Record<string, string | number>) => string;
  onEdit: (profile: WorkProfile) => void;
  onDuplicate: (profile: WorkProfile) => void;
  onDelete: (profile: WorkProfile) => void;
  onShare: (profile: WorkProfile) => void;
  onExport: (profile: WorkProfile) => void;
  exporting: boolean;
  canWrite: boolean;
}) {
  const unitName = profile.spec?.unit?.name
    ? profileUnitNameLabel(t, profile, profile.spec.unit.name)
    : "-";
  const words = profile.spec?.unit?.default_words ?? 0;
  const validators = profile.spec?.validation?.validators ?? [];
  const policy = profile.spec?.grounding?.citation_policy ?? "optional";
  const editable = Boolean(profile.can_edit) && canWrite;
  const showOwner = !profile.is_builtin && !profile.is_owner && Boolean(profile.owner_name);

  return (
    <div
      data-profile-id={profile.id}
      data-scope={profile.scope ?? "user"}
      data-can-edit={profile.can_edit ? "true" : "false"}
      className="flex min-w-0 flex-col rounded-2xl border border-white/60 bg-white/55 p-3 shadow-[0_10px_30px_-24px_rgba(15,23,42,0.45)] transition hover:border-indigo-300/60 dark:border-white/10 dark:bg-white/[0.04]"
    >
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        <p className="min-w-0 break-words text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
          {profileNameLabel(t, profile)}
        </p>
        <span className="chip-muted shrink-0" data-scope-badge="true">
          {t(scopeKey(profile))}
        </span>
        {profile.is_shared && !profile.is_owner && profile.scope !== "tenant" && profile.scope !== "global" ? (
          <span className="chip shrink-0">{t("profiles.sharedBadge")}</span>
        ) : null}
      </div>
      {profile.description ? (
        <p className="mt-1 line-clamp-2 break-words text-[10.5px] leading-relaxed text-slate-400 dark:text-slate-500">
          {profileDescriptionLabel(t, profile)}
        </p>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-1">
        <span className="chip-muted">
          <BookOpen size={10} />
          {unitName}
        </span>
        <span className="chip-muted">{t("profiles.words", { count: words })}</span>
        <span className="chip-muted">{policyLabel(t, policy)}</span>
        {validators.length > 0 ? (
          validators.map((item) => (
            <span key={item} className="chip-muted text-[9.5px]">
              {validatorLabel(t, item)}
            </span>
          ))
        ) : (
          <span className="chip-muted">-</span>
        )}
      </div>
      <p className="mt-1.5 break-words text-[10px] text-slate-400 dark:text-slate-500">
        {t("profiles.summary", {
          unit: unitName,
          count: words,
          policy: policyLabel(t, policy),
          validators:
            validators.length > 0
              ? validators.map((item) => validatorLabel(t, item)).join(", ")
              : "-",
        })}
      </p>
      {showOwner ? (
        <p className="mt-0.5 break-words text-[10px] text-slate-400 dark:text-slate-500">
          {t("profiles.ownerLabel", { name: profile.owner_name ?? "" })}
        </p>
      ) : null}
      <div className="mt-auto flex flex-wrap items-center gap-1 pt-2.5">
        {editable ? (
          <button
            type="button"
            onClick={() => onEdit(profile)}
            className="btn btn-quiet px-2 py-1 text-[10.5px]"
            data-action="edit"
          >
            <Pencil size={11} />
            {t("profiles.edit")}
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => onDuplicate(profile)}
          disabled={!canWrite}
          className="btn btn-quiet px-2 py-1 text-[10.5px]"
          data-action="duplicate"
        >
          <Copy size={11} />
          {t("profiles.duplicate")}
        </button>
        {editable ? (
          <>
            <button
              type="button"
              onClick={() => onShare(profile)}
              className="btn btn-quiet px-2 py-1 text-[10.5px]"
              data-action="share"
            >
              <Share2 size={11} />
              {t("profiles.share")}
            </button>
            <button
              type="button"
              onClick={() => onDelete(profile)}
              className="btn btn-quiet px-2 py-1 text-[10.5px] text-rose-600 hover:text-rose-700 dark:text-rose-300"
              data-action="delete"
            >
              <Trash2 size={11} />
              {t("profiles.delete")}
            </button>
          </>
        ) : null}
        <button
          type="button"
          onClick={() => onExport(profile)}
          disabled={exporting}
          className="btn btn-quiet px-2 py-1 text-[10.5px]"
          data-action="export"
        >
          {exporting ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            <Download size={11} />
          )}
          {t("profiles.export")}
        </button>
      </div>
    </div>
  );
}

export default function ProfilesCard({
  canWrite,
  onNotice,
  onError,
}: {
  canWrite: boolean;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { t } = useI18n();
  const { tenant } = useSession();
  const [profiles, setProfiles] = useState<WorkProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorProfile, setEditorProfile] = useState<WorkProfile | null>(null);
  const [duplicateSource, setDuplicateSource] = useState<WorkProfile | null>(null);
  const [duplicateName, setDuplicateName] = useState("");
  const [duplicateError, setDuplicateError] = useState("");
  const [duplicating, setDuplicating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<WorkProfile | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [shareTarget, setShareTarget] = useState<WorkProfile | null>(null);
  const [shareMembers, setShareMembers] = useState<Member[]>([]);
  const [shareLevels, setShareLevels] = useState<Record<string, string | null>>({});
  const [shareLoading, setShareLoading] = useState(false);
  const [shareSaving, setShareSaving] = useState(false);
  const [shareError, setShareError] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importFileName, setImportFileName] = useState("");
  const [importBusy, setImportBusy] = useState(false);
  const [importError, setImportError] = useState("");
  const [importIssues, setImportIssues] = useState<ProfileValidationIssue[]>([]);
  const [exportingId, setExportingId] = useState("");
  const importFileRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listWorkProfiles();
      setProfiles(data.profiles ?? []);
    } catch (err) {
      onError(err instanceof Error ? err.message : t("profiles.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [onError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const handler = () => void load();
    window.addEventListener("series-studio:refresh", handler);
    return () => window.removeEventListener("series-studio:refresh", handler);
  }, [load]);

  const builtin = useMemo(() => profiles.filter((item) => item.is_builtin), [profiles]);
  const spaceScoped = useMemo(
    () =>
      profiles.filter(
        (item) => !item.is_builtin && (item.scope === "tenant" || item.scope === "global"),
      ),
    [profiles],
  );
  const mine = useMemo(
    () =>
      profiles.filter(
        (item) =>
          !item.is_builtin &&
          item.is_owner &&
          item.scope !== "tenant" &&
          item.scope !== "global",
      ),
    [profiles],
  );
  const shared = useMemo(
    () =>
      profiles.filter(
        (item) =>
          !item.is_builtin &&
          !item.is_owner &&
          item.scope !== "tenant" &&
          item.scope !== "global",
      ),
    [profiles],
  );

  const openCreate = () => {
    setEditorProfile(null);
    setEditorOpen(true);
  };

  const openDuplicate = (profile: WorkProfile) => {
    setDuplicateError("");
    setDuplicateName(
      t("profiles.duplicateSuffix", { name: profileNameLabel(t, profile) }),
    );
    setDuplicateSource(profile);
  };

  const confirmDuplicate = async (name: string) => {
    if (!duplicateSource) return;
    setDuplicating(true);
    setDuplicateError("");
    try {
      const created = await api.duplicateWorkProfile(duplicateSource.id, {
        name: name.trim() || undefined,
      });
      setDuplicateSource(null);
      onNotice(t("profiles.duplicated"));
      await load();
      setEditorProfile(created);
      setEditorOpen(true);
    } catch (err) {
      setDuplicateError(err instanceof Error ? err.message : t("profiles.duplicateFailed"));
    } finally {
      setDuplicating(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await api.deleteWorkProfile(deleteTarget.id);
      setDeleteTarget(null);
      onNotice(t("profiles.deleted"));
      await load();
    } catch (err) {
      if (err instanceof ApiError) {
        setDeleteError(err.message);
      } else {
        setDeleteError(err instanceof Error ? err.message : t("profiles.deleteFailed"));
      }
    } finally {
      setDeleting(false);
    }
  };

  const handleExport = async (profile: WorkProfile) => {
    setExportingId(profile.id);
    try {
      const result = await api.exportWorkProfile(profile.id);
      const href = URL.createObjectURL(result.blob);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = result.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(href);
      onNotice(t("profiles.exported", { name: result.filename }));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("profiles.exportFailed"));
    } finally {
      setExportingId("");
    }
  };

  const resetImport = () => {
    setImportText("");
    setImportFileName("");
    setImportError("");
    setImportIssues([]);
    if (importFileRef.current) importFileRef.current.value = "";
  };

  const toggleImport = () => {
    setImportOpen((prev) => {
      if (prev) resetImport();
      return !prev;
    });
  };

  const readImportFile = async (file: File | null) => {
    if (!file) return;
    setImportError("");
    setImportIssues([]);
    try {
      const text = await file.text();
      setImportText(text);
      setImportFileName(file.name);
    } catch (err) {
      setImportError(err instanceof Error ? err.message : t("profiles.importFailed"));
    }
  };

  const runImport = async () => {
    setImportError("");
    setImportIssues([]);
    const raw = importText.trim();
    if (!raw) {
      setImportError(t("profiles.importEmpty"));
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      setImportIssues([
        {
          path: "",
          message: t("profiles.importInvalidJson", {
            message: err instanceof Error ? err.message : "",
          }),
        },
      ]);
      return;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      setImportIssues([
        { path: "", message: t("profiles.importInvalidJson", { message: "not an object" }) },
      ]);
      return;
    }
    const envelope = parsed as Record<string, unknown>;
    const data =
      envelope.data && typeof envelope.data === "object" && !Array.isArray(envelope.data)
        ? (envelope.data as Record<string, unknown>)
        : envelope;
    const specValue = data.spec;
    if (!specValue || typeof specValue !== "object" || Array.isArray(specValue)) {
      setImportIssues([{ path: "spec", message: t("profiles.importMissingSpec") }]);
      return;
    }
    setImportBusy(true);
    try {
      const result = await api.validateWorkProfile(specValue as ProfileSpec);
      if (!result.ok) {
        setImportIssues(result.errors ?? []);
        return;
      }
      await api.importWorkProfile(data);
      onNotice(t("profiles.importDone"));
      resetImport();
      setImportOpen(false);
      await load();
    } catch (err) {
      setImportError(err instanceof Error ? err.message : t("profiles.importFailed"));
    } finally {
      setImportBusy(false);
    }
  };

  const openShare = async (profile: WorkProfile) => {
    setShareTarget(profile);
    setShareError("");
    setShareLoading(true);
    try {
      const [members, shares] = await Promise.all([
        tenant ? api.listMembers(tenant) : Promise.resolve({ count: 0, members: [] }),
        api.getProfileShares(profile.id),
      ]);
      setShareMembers(members.members ?? []);
      const levels: Record<string, string | null> = {};
      for (const member of members.members ?? []) levels[member.user_id] = null;
      for (const share of shares.shares ?? []) levels[share.user_id] = share.level;
      setShareLevels(levels);
    } catch (err) {
      setShareError(err instanceof Error ? err.message : t("profiles.shareLoadFailed"));
    } finally {
      setShareLoading(false);
    }
  };

  const shareMemberList = useMemo<ShareMember[]>(
    () =>
      shareMembers.map((member) => ({
        user_id: member.user_id,
        user_email: member.user_email,
        user_display_name: member.user_display_name,
        avatar_url: member.avatar_url,
        note: t("profiles.memberNote"),
      })),
    [shareMembers, t],
  );

  const shareOptions = useMemo(
    () => [
      { value: "read", label: t("profiles.shareRead"), desc: t("profiles.shareReadDesc") },
      { value: "use", label: t("profiles.shareUse"), desc: t("profiles.shareUseDesc") },
      {
        value: "manage",
        label: t("profiles.shareManage"),
        desc: t("profiles.shareManageDesc"),
      },
    ],
    [t],
  );

  const saveShares = async (entries: { user_id: string; level: string }[]) => {
    if (!shareTarget) return;
    setShareSaving(true);
    setShareError("");
    try {
      await api.saveProfileShares(
        shareTarget.id,
        entries.map((entry) => ({
          user_id: entry.user_id,
          level: entry.level as ProfileShareLevel,
        })),
      );
      setShareTarget(null);
      onNotice(t("profiles.shareSaved"));
      await load();
    } catch (err) {
      setShareError(err instanceof Error ? err.message : t("profiles.shareFailed"));
    } finally {
      setShareSaving(false);
    }
  };

  const groupTitle = (title: string, count: number) => (
    <div className="flex items-center gap-1.5">
      <h3 className="text-[11.5px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {title}
      </h3>
      <span className="chip-muted">{count}</span>
    </div>
  );

  const renderGroup = (title: string, items: WorkProfile[], emptyKey: string) => (
    <div>
      {groupTitle(title, items.length)}
      <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((profile) => (
          <ProfileCard
            key={profile.id}
            profile={profile}
            t={t}
            canWrite={canWrite}
            exporting={exportingId === profile.id}
            onEdit={(item) => {
              setEditorProfile(item);
              setEditorOpen(true);
            }}
            onDuplicate={openDuplicate}
            onDelete={(item) => {
              setDeleteError("");
              setDeleteTarget(item);
            }}
            onShare={(item) => void openShare(item)}
            onExport={(item) => void handleExport(item)}
          />
        ))}
      </div>
      {items.length === 0 ? (
        <p className="mt-2 flex items-center justify-center gap-1.5 rounded-xl border border-white/50 bg-white/40 px-3 py-3 text-center text-[10.5px] text-slate-400 dark:border-white/10 dark:bg-white/[0.04]">
          <Lock size={11} />
          {t(emptyKey)}
        </p>
      ) : null}
    </div>
  );

  return (
    <section id="creation-profiles" className="glass min-w-0 rounded-3xl p-5 shadow-glass">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-slate-800 dark:text-slate-100">
          <Wand2 size={15} className="text-indigo-500" />
          {t("profiles.title")}
          <span className="chip-muted">{t("common.count", { count: profiles.length })}</span>
        </h2>
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={toggleImport}
            className={clsx("btn btn-ghost px-3 py-1.5 text-[11px]", importOpen && "text-indigo-600 dark:text-indigo-300")}
            data-action="import"
            aria-expanded={importOpen}
          >
            <Upload size={12} />
            {t("profiles.import")}
          </button>
          <button
            type="button"
            onClick={openCreate}
            disabled={!canWrite}
            title={!canWrite ? t("common.readOnlyRole") : undefined}
            className="btn btn-primary px-3 py-1.5 text-[11px]"
          >
            <Plus size={12} />
            {t("profiles.newProfile")}
          </button>
        </div>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
        {t("profiles.hint")}
      </p>

      {importOpen ? (
        <div
          className="mt-3 min-w-0 rounded-2xl border border-indigo-400/30 bg-indigo-500/[0.06] p-3 dark:border-indigo-400/25 dark:bg-indigo-500/10"
          data-import-panel="true"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-[11.5px] font-semibold text-slate-700 dark:text-slate-200">
                {t("profiles.import")}
              </p>
              <p className="mt-0.5 break-words text-[10.5px] leading-relaxed text-slate-500 dark:text-slate-400">
                {t("profiles.importHint")}
              </p>
            </div>
            <button
              type="button"
              onClick={toggleImport}
              className="btn-quiet grid h-6 w-6 shrink-0 place-items-center rounded-full"
              aria-label={t("common.close")}
            >
              <X size={12} />
            </button>
          </div>

          <div className="mt-2 flex min-w-0 flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => importFileRef.current?.click()}
              className="btn btn-quiet px-2.5 py-1 text-[10.5px]"
            >
              <Upload size={11} />
              {t("profiles.importFile")}
            </button>
            <input
              ref={importFileRef}
              type="file"
              accept=".json,application/json"
              className="hidden"
              data-field="import.file"
              onChange={(event) => void readImportFile(event.target.files?.[0] ?? null)}
            />
            <span className="min-w-0 break-all text-[10px] text-slate-400 dark:text-slate-500">
              {importFileName || t("profiles.importPaste")}
            </span>
          </div>

          <textarea
            rows={5}
            value={importText}
            onChange={(event) => {
              setImportText(event.target.value);
              setImportIssues([]);
              setImportError("");
            }}
            className="input mt-2 min-w-0 font-mono text-[10.5px]"
            placeholder={t("profiles.importPlaceholder")}
            data-field="import.text"
          />

          {importIssues.length > 0 ? (
            <div
              className="mt-2 min-w-0 rounded-xl border border-rose-400/40 bg-rose-500/10 px-2.5 py-2 text-[10.5px] leading-relaxed text-rose-700 dark:text-rose-300"
              data-import-errors="true"
            >
              <p className="font-medium">
                {t("profiles.validationIssues", { count: importIssues.length })}
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {importIssues.map((item, index) => (
                  <li key={`${item.path}-${index}`} className="break-words font-mono text-[10px]">
                    {item.path || "spec"}: {item.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {importError ? (
            <p className="mt-2 break-words rounded-xl border border-rose-400/40 bg-rose-500/10 px-2.5 py-2 text-[10.5px] text-rose-700 dark:text-rose-300">
              {importError}
            </p>
          ) : null}

          <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
            <button type="button" onClick={toggleImport} className="btn btn-quiet px-2.5 py-1 text-[10.5px]">
              {t("common.cancel")}
            </button>
            <button
              type="button"
              onClick={() => void runImport()}
              disabled={importBusy}
              className="btn btn-primary px-2.5 py-1 text-[10.5px]"
              data-action="import-submit"
            >
              {importBusy ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
              {importBusy ? t("profiles.importRunning") : t("profiles.importValidate")}
            </button>
          </div>
        </div>
      ) : null}

      {loading ? (
        <div className="mt-4 flex items-center gap-2 text-[11px] text-slate-400">
          <Loader2 size={12} className="animate-spin" />
          {t("profiles.loading")}
        </div>
      ) : (
        <div className="mt-4 space-y-5">
          {renderGroup(t("profiles.builtinGroup"), builtin, "profiles.emptyBuiltin")}
          {renderGroup(t("profiles.mineGroup"), mine, "profiles.emptyMine")}
          {spaceScoped.length > 0
            ? renderGroup(t("profiles.spaceGroup"), spaceScoped, "profiles.emptySpace")
            : null}
          {renderGroup(t("profiles.sharedGroup"), shared, "profiles.emptyShared")}

          {profiles.length === 0 ? (
            <p className="flex items-center justify-center gap-2 rounded-2xl border border-white/50 bg-white/40 px-3 py-6 text-center text-[11px] text-slate-400 dark:border-white/10 dark:bg-white/[0.04]">
              <AlertCircle size={12} />
              {t("profiles.empty")}
            </p>
          ) : null}
        </div>
      )}

      <ProfileEditor
        open={editorOpen}
        profile={editorProfile}
        onClose={() => setEditorOpen(false)}
        onSaved={(saved) => {
          setEditorProfile(saved);
          void load();
        }}
      />

      <PromptDialog
        open={Boolean(duplicateSource)}
        title={t("profiles.duplicateTitle")}
        label={t("profiles.duplicateLabel")}
        initial={duplicateName}
        confirmLabel={t("profiles.duplicate")}
        busy={duplicating}
        error={duplicateError}
        onConfirm={(value) => void confirmDuplicate(value)}
        onClose={() => {
          if (!duplicating) setDuplicateSource(null);
        }}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={t("profiles.deleteTitle")}
        description={
          deleteTarget
            ? t("profiles.deleteDesc", {
                name: profileNameLabel(t, deleteTarget),
              })
            : undefined
        }
        confirmLabel={t("common.delete")}
        busy={deleting}
        error={deleteError}
        onConfirm={() => void confirmDelete()}
        onClose={() => {
          if (!deleting) setDeleteTarget(null);
        }}
      />

      <SharePanel
        open={Boolean(shareTarget)}
        title={
          shareTarget
            ? t("profiles.sharesTitle", {
                name: profileNameLabel(t, shareTarget),
              })
            : ""
        }
        subtitle={t("profiles.sharesSubtitle")}
        note={t("profiles.sharesNote")}
        members={shareMemberList}
        value={shareLevels}
        options={shareOptions}
        loading={shareLoading}
        saving={shareSaving}
        error={shareError}
        onClose={() => {
          if (!shareSaving) setShareTarget(null);
        }}
        onChange={(userId, level) =>
          setShareLevels((prev) => ({ ...prev, [userId]: level }))
        }
        onSave={saveShares}
      />
    </section>
  );
}
