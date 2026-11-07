import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Globe2,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  Users,
} from "lucide-react";
import { ApiError, api, type ProfileScope, type WorkProfile } from "@/lib/api";
import { ConfirmDialog } from "@/components/common/Dialogs";
import ProfileEditor from "@/components/profiles/ProfileEditor";
import { useI18n } from "@/i18n/I18nProvider";
import { profileDescriptionLabel, profileNameLabel } from "@/i18n/labels";

function scopeKey(scope: string | undefined): string {
  if (scope === "global") return "profiles.scopeGlobal";
  return "profiles.scopeTenant";
}

export default function ServerProfilesCard({
  canManage,
  onNotice,
  onError,
}: {
  canManage: boolean;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { t } = useI18n();
  const [profiles, setProfiles] = useState<WorkProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorProfile, setEditorProfile] = useState<WorkProfile | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WorkProfile | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listWorkProfiles();
      setProfiles(
        (data.profiles ?? []).filter(
          (item) => item.scope === "tenant" || item.scope === "global",
        ),
      );
    } catch (err) {
      onError(err instanceof Error ? err.message : t("serverProfiles.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [onError, t]);

  useEffect(() => {
    if (!canManage) return;
    void load();
  }, [canManage, load]);

  const scopeOptions = useMemo(
    () => [
      { value: "tenant" as ProfileScope, label: t("profiles.scopeTenant") },
      { value: "global" as ProfileScope, label: t("profiles.scopeGlobal") },
    ],
    [t],
  );

  const openCreate = () => {
    setEditorProfile(null);
    setEditorOpen(true);
  };

  const openEdit = (profile: WorkProfile) => {
    setEditorProfile(profile);
    setEditorOpen(true);
  };

  const closeEditor = () => {
    setEditorOpen(false);
    setEditorProfile(null);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await api.deleteWorkProfile(deleteTarget.id);
      setDeleteTarget(null);
      onNotice(t("serverProfiles.deleted"));
      await load();
    } catch (err) {
      if (err instanceof ApiError) {
        setDeleteError(err.message);
      } else {
        setDeleteError(err instanceof Error ? err.message : t("serverProfiles.deleteFailed"));
      }
    } finally {
      setDeleting(false);
    }
  };

  if (!canManage) return null;

  return (
    <section id="server-creation-profiles" className="glass min-w-0 rounded-3xl p-5 shadow-glass">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex min-w-0 items-center gap-1.5 text-sm font-semibold text-slate-800 dark:text-slate-100">
          <Globe2 size={15} className="shrink-0 text-indigo-500" />
          <span className="min-w-0 break-words">{t("serverProfiles.title")}</span>
          <span className="chip-muted shrink-0">{profiles.length}</span>
        </h2>
        <button
          type="button"
          onClick={editorOpen && !editorProfile ? closeEditor : openCreate}
          className="btn btn-primary px-3 py-1.5 text-[11px]"
          data-action="server-profile-new"
        >
          <Plus size={12} />
          {t("serverProfiles.new")}
        </button>
      </div>
      <p className="mt-1.5 break-words text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
        {t("serverProfiles.hint")}
      </p>

      {loading ? (
        <div className="mt-4 flex items-center gap-2 text-[11px] text-slate-400">
          <Loader2 size={12} className="animate-spin" />
          {t("serverProfiles.loading")}
        </div>
      ) : profiles.length === 0 ? (
        <p className="mt-3 flex items-center justify-center gap-1.5 rounded-xl border border-white/50 bg-white/40 px-3 py-3 text-center text-[10.5px] text-slate-400 dark:border-white/10 dark:bg-white/[0.04]">
          <AlertCircle size={11} />
          {t("serverProfiles.empty")}
        </p>
      ) : (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {profiles.map((profile) => (
            <div
              key={profile.id}
              data-profile-id={profile.id}
              data-scope={profile.scope ?? "tenant"}
              data-can-edit={profile.can_edit ? "true" : "false"}
              className="flex min-w-0 flex-col rounded-2xl border border-white/60 bg-white/55 p-3 dark:border-white/10 dark:bg-white/[0.04]"
            >
              <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                <p className="min-w-0 break-words text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
                  {profileNameLabel(t, profile)}
                </p>
                <span className="chip-muted shrink-0" data-scope-badge="true">
                  {t(scopeKey(profile.scope))}
                </span>
              </div>
              <p className="mt-1 flex min-w-0 items-center gap-1 break-words text-[10.5px] text-slate-400 dark:text-slate-500">
                <Users size={10} className="shrink-0" />
                {t("serverProfiles.owner", { name: profile.owner_name || "-" })}
              </p>
              {profile.description ? (
                <p className="mt-1 line-clamp-2 break-words text-[10px] leading-relaxed text-slate-400 dark:text-slate-500">
                  {profileDescriptionLabel(t, profile)}
                </p>
              ) : null}
              {profile.can_edit ? (
                <div className="mt-auto flex flex-wrap items-center gap-1 pt-2">
                  <button
                    type="button"
                    onClick={() => openEdit(profile)}
                    className="btn btn-quiet px-2 py-1 text-[10.5px]"
                    data-action="edit"
                  >
                    <Pencil size={11} />
                    {t("serverProfiles.edit")}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setDeleteError("");
                      setDeleteTarget(profile);
                    }}
                    className="btn btn-quiet px-2 py-1 text-[10.5px] text-rose-600 hover:text-rose-700 dark:text-rose-300"
                    data-action="delete"
                  >
                    <Trash2 size={11} />
                    {t("serverProfiles.delete")}
                  </button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}

      {editorOpen ? (
        <div className="mt-3 min-w-0" data-server-editor="true">
          <ProfileEditor
            open={editorOpen}
            profile={editorProfile}
            inline
            scopeOptions={scopeOptions}
            defaultScope="tenant"
            onClose={closeEditor}
            onSaved={() => {
              onNotice(
                editorProfile ? t("serverProfiles.updated") : t("serverProfiles.created"),
              );
              closeEditor();
              void load();
            }}
          />
        </div>
      ) : null}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={t("serverProfiles.deleteTitle")}
        description={
          deleteTarget
            ? t("serverProfiles.deleteDesc", { name: deleteTarget.name })
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
    </section>
  );
}
