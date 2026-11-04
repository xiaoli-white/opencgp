import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  BookOpen,
  Copy,
  Loader2,
  Lock,
  Pencil,
  Plus,
  Share2,
  Trash2,
  Wand2,
} from "lucide-react";
import clsx from "clsx";
import {
  ApiError,
  api,
  type Member,
  type ProfileShareLevel,
  type WorkProfile,
} from "@/lib/api";
import { useSession } from "@/components/auth/SessionProvider";
import { ConfirmDialog, PromptDialog } from "@/components/common/Dialogs";
import ProfileEditor from "@/components/profiles/ProfileEditor";
import SharePanel, { type ShareMember } from "@/components/sharing/SharePanel";
import { useI18n } from "@/i18n/I18nProvider";

function policyKey(policy: string | undefined): string {
  if (policy === "required") return "profiles.citeRequired";
  if (policy === "forbidden") return "profiles.citeForbidden";
  return "profiles.citeOptional";
}

function ProfileCard({
  profile,
  t,
  onEdit,
  onDuplicate,
  onDelete,
  onShare,
  canWrite,
}: {
  profile: WorkProfile;
  t: (path: string, vars?: Record<string, string | number>) => string;
  onEdit: (profile: WorkProfile) => void;
  onDuplicate: (profile: WorkProfile) => void;
  onDelete: (profile: WorkProfile) => void;
  onShare: (profile: WorkProfile) => void;
  canWrite: boolean;
}) {
  const unitName = profile.spec?.unit?.name ?? "-";
  const words = profile.spec?.unit?.default_words ?? 0;
  const validators = profile.spec?.validation?.validators ?? [];
  const policy = profile.spec?.grounding?.citation_policy ?? "optional";
  const owner = !profile.is_builtin && !profile.is_owner;

  return (
    <div
      data-profile-id={profile.id}
      className="flex min-w-0 flex-col rounded-2xl border border-white/60 bg-white/55 p-3 shadow-[0_10px_30px_-24px_rgba(15,23,42,0.45)] transition hover:border-indigo-300/60 dark:border-white/10 dark:bg-white/[0.04]"
    >
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        <p className="min-w-0 break-words text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
          {profile.name}
        </p>
        {profile.is_builtin ? (
          <span className="chip-muted shrink-0">{t("profiles.builtinBadge")}</span>
        ) : null}
        {profile.is_shared && !owner ? (
          <span className="chip shrink-0">{t("profiles.sharedBadge")}</span>
        ) : null}
        {owner ? <span className="chip-muted shrink-0">{t("profiles.readonlyBadge")}</span> : null}
      </div>
      {profile.description ? (
        <p className="mt-1 line-clamp-2 break-words text-[10.5px] leading-relaxed text-slate-400 dark:text-slate-500">
          {profile.description}
        </p>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-1">
        <span className="chip-muted">
          <BookOpen size={10} />
          {unitName}
        </span>
        <span className="chip-muted">{t("profiles.words", { count: words })}</span>
        <span className="chip-muted">{t(policyKey(policy))}</span>
        {validators.length > 0 ? (
          validators.map((item) => (
            <span key={item} className="chip-muted font-mono text-[9.5px]">
              {item}
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
          policy: t(policyKey(policy)),
          validators: validators.length > 0 ? validators.join(", ") : "-",
        })}
      </p>
      {owner && profile.owner_name ? (
        <p className="mt-0.5 break-words text-[10px] text-slate-400 dark:text-slate-500">
          {t("profiles.ownerLabel", { name: profile.owner_name })}
        </p>
      ) : null}
      <div className="mt-auto flex flex-wrap items-center gap-1 pt-2.5">
        {!profile.is_builtin && profile.is_owner ? (
          <button
            type="button"
            onClick={() => onEdit(profile)}
            disabled={!canWrite}
            className="btn btn-quiet px-2 py-1 text-[10.5px]"
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
        >
          <Copy size={11} />
          {t("profiles.duplicate")}
        </button>
        {!profile.is_builtin && profile.is_owner ? (
          <>
            <button
              type="button"
              onClick={() => onShare(profile)}
              disabled={!canWrite}
              className="btn btn-quiet px-2 py-1 text-[10.5px]"
            >
              <Share2 size={11} />
              {t("profiles.share")}
            </button>
            <button
              type="button"
              onClick={() => onDelete(profile)}
              disabled={!canWrite}
              className="btn btn-quiet px-2 py-1 text-[10.5px] text-rose-600 hover:text-rose-700 dark:text-rose-300"
            >
              <Trash2 size={11} />
              {t("profiles.delete")}
            </button>
          </>
        ) : null}
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
    window.addEventListener("course-studio:refresh", handler);
    return () => window.removeEventListener("course-studio:refresh", handler);
  }, [load]);

  const builtin = useMemo(() => profiles.filter((item) => item.is_builtin), [profiles]);
  const mine = useMemo(
    () => profiles.filter((item) => !item.is_builtin && item.is_owner),
    [profiles],
  );
  const shared = useMemo(
    () => profiles.filter((item) => !item.is_builtin && !item.is_owner),
    [profiles],
  );

  const openCreate = () => {
    setEditorProfile(null);
    setEditorOpen(true);
  };

  const openDuplicate = (profile: WorkProfile) => {
    setDuplicateError("");
    setDuplicateName(t("profiles.duplicateSuffix", { name: profile.name }));
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

  return (
    <section id="creation-profiles" className="glass rounded-3xl p-5 shadow-glass">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-slate-800 dark:text-slate-100">
          <Wand2 size={15} className="text-indigo-500" />
          {t("profiles.title")}
          <span className="chip-muted">{t("common.count", { count: profiles.length })}</span>
        </h2>
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
      <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
        {t("profiles.hint")}
      </p>

      {loading ? (
        <div className="mt-4 flex items-center gap-2 text-[11px] text-slate-400">
          <Loader2 size={12} className="animate-spin" />
          {t("profiles.loading")}
        </div>
      ) : (
        <div className="mt-4 space-y-5">
          <div>
            {groupTitle(t("profiles.builtinGroup"), builtin.length)}
            <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {builtin.map((profile) => (
                <ProfileCard
                  key={profile.id}
                  profile={profile}
                  t={t}
                  canWrite={canWrite}
                  onEdit={() => undefined}
                  onDuplicate={openDuplicate}
                  onDelete={() => undefined}
                  onShare={() => undefined}
                />
              ))}
            </div>
            {builtin.length === 0 ? (
              <p className="mt-2 rounded-xl border border-white/50 bg-white/40 px-3 py-3 text-center text-[10.5px] text-slate-400 dark:border-white/10 dark:bg-white/[0.04]">
                {t("profiles.emptyBuiltin")}
              </p>
            ) : null}
          </div>

          <div>
            {groupTitle(t("profiles.mineGroup"), mine.length)}
            <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {mine.map((profile) => (
                <ProfileCard
                  key={profile.id}
                  profile={profile}
                  t={t}
                  canWrite={canWrite}
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
                />
              ))}
            </div>
            {mine.length === 0 ? (
              <p className="mt-2 rounded-xl border border-white/50 bg-white/40 px-3 py-3 text-center text-[10.5px] text-slate-400 dark:border-white/10 dark:bg-white/[0.04]">
                {t("profiles.emptyMine")}
              </p>
            ) : null}
          </div>

          <div>
            {groupTitle(t("profiles.sharedGroup"), shared.length)}
            <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {shared.map((profile) => (
                <ProfileCard
                  key={profile.id}
                  profile={profile}
                  t={t}
                  canWrite={canWrite}
                  onEdit={() => undefined}
                  onDuplicate={openDuplicate}
                  onDelete={() => undefined}
                  onShare={() => undefined}
                />
              ))}
            </div>
            {shared.length === 0 ? (
              <p className="mt-2 flex items-center justify-center gap-1.5 rounded-xl border border-white/50 bg-white/40 px-3 py-3 text-center text-[10.5px] text-slate-400 dark:border-white/10 dark:bg-white/[0.04]">
                <Lock size={11} />
                {t("profiles.emptyShared")}
              </p>
            ) : null}
          </div>

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
          deleteTarget ? t("profiles.deleteDesc", { name: deleteTarget.name }) : undefined
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
        title={shareTarget ? t("profiles.sharesTitle", { name: shareTarget.name }) : ""}
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
