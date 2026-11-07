import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertCircle,
  Camera,
  CheckCircle2,
  KeyRound,
  Loader2,
  Save,
  UserRound,
} from "lucide-react";
import clsx from "clsx";
import { API_BASE, api } from "@/lib/api";
import { useSession } from "@/components/auth/SessionProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { roleLabel } from "@/i18n/labels";

const MAX_AVATAR_BYTES = 2 * 1024 * 1024;

export default function AccountCard({
  canWrite,
  onNotice,
  onError,
}: {
  canWrite: boolean;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { me, avatarUrl, refresh, roleName, roleKey } = useSession();
  const { t } = useI18n();
  const fileRef = useRef<HTMLInputElement | null>(null);

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwNotice, setPwNotice] = useState("");
  const [pwError, setPwError] = useState("");

  useEffect(() => {
    setDisplayName(me?.user.display_name ?? "");
    setEmail(me?.user.email ?? "");
  }, [me?.user.display_name, me?.user.email]);

  const initial = (displayName || email || "?").slice(0, 1).toUpperCase();
  const roleText =
    roleLabel(t, roleKey || me?.role || "", roleName) || t("common.readOnly");

  const pickAvatar = () => {
    if (!canWrite) return;
    fileRef.current?.click();
  };

  const uploadAvatar = async (file: File) => {
    if (file.size > MAX_AVATAR_BYTES) {
      onError(t("account.avatarTooLarge"));
      return;
    }
    setUploading(true);
    onError("");
    onNotice("");
    try {
      await api.uploadAvatar(file);
      await refresh();
      onNotice(t("account.avatarUpdated"));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("account.avatarFailed"));
    } finally {
      setUploading(false);
    }
  };

  const saveProfile = async () => {
    const nextName = displayName.trim();
    const nextEmail = email.trim();
    const payload: { display_name?: string; email?: string } = {};
    if (nextName !== (me?.user.display_name ?? "")) payload.display_name = nextName;
    if (nextEmail !== (me?.user.email ?? "")) {
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(nextEmail)) {
        onNotice("");
        onError(t("account.emailInvalid"));
        return;
      }
      payload.email = nextEmail;
    }
    if (!Object.keys(payload).length) {
      onError("");
      onNotice(t("account.noChanges"));
      return;
    }
    setSaving(true);
    onError("");
    onNotice("");
    try {
      await api.updateProfile(payload);
      await refresh();
      onNotice(t("account.updated"));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("account.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const changePassword = async () => {
    setPwError("");
    setPwNotice("");
    if (newPassword.length < 8) {
      setPwError(t("account.passwordTooShort"));
      return;
    }
    if (newPassword !== confirmPassword) {
      setPwError(t("account.passwordMismatch"));
      return;
    }
    setPwBusy(true);
    try {
      await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPwNotice(t("account.passwordUpdated"));
    } catch (err) {
      setPwError(err instanceof Error ? err.message : t("account.passwordFailed"));
    } finally {
      setPwBusy(false);
    }
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-3xl p-5 shadow-glass"
    >
      <div className="flex items-center gap-2">
        <UserRound size={15} className="text-indigo-500 dark:text-indigo-300" />
        <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
          {t("account.title")}
        </h2>
        <span className="chip-muted">{roleText}</span>
      </div>

      <div className="mt-4 flex flex-wrap items-start gap-4">
        <div className="flex flex-col items-center gap-2">
          <button
            type="button"
            onClick={pickAvatar}
            disabled={!canWrite || uploading}
            title={canWrite ? t("account.uploadAvatar") : t("common.readOnlyRole")}
            className="group relative grid h-20 w-20 shrink-0 place-items-center overflow-hidden rounded-full ring-2 ring-white/60 transition hover:ring-indigo-400/60 dark:ring-white/10"
          >
            {avatarUrl ? (
              <img
                src={`${API_BASE}${avatarUrl}`}
                alt={t("account.avatarAlt")}
                className="h-full w-full object-cover"
              />
            ) : (
              <span className="brand-gradient grid h-full w-full place-items-center text-xl font-semibold text-white">
                {initial}
              </span>
            )}
            <span
              className={clsx(
                "absolute inset-0 grid place-items-center bg-slate-900/45 text-white transition",
                uploading ? "opacity-100" : "opacity-0 group-hover:opacity-100",
              )}
            >
              {uploading ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Camera size={16} />
              )}
            </span>
          </button>
          <span className="text-[10px] text-slate-400 dark:text-slate-500">
            png / jpg / webp · ≤2MB
          </span>
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void uploadAvatar(file);
            }}
          />
        </div>

        <div className="min-w-0 flex-1 space-y-2.5">
          <label className="block">
            <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
              {t("account.displayName")}
            </span>
            <input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              disabled={!canWrite}
              placeholder={t("account.displayNamePlaceholder")}
              className="input"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
              {t("account.email")}
            </span>
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={!canWrite}
              placeholder="you@example.com"
              className="input"
            />
          </label>
          <button
            type="button"
            onClick={() => void saveProfile()}
            disabled={!canWrite || saving}
            title={canWrite ? "" : t("common.readOnlyRole")}
            className="btn btn-primary"
          >
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            {t("account.saveAccount")}
          </button>
        </div>
      </div>

      <div className="mt-5 border-t border-white/50 pt-4 dark:border-white/10">
        <div className="flex items-center gap-2">
          <KeyRound size={14} className="text-indigo-500 dark:text-indigo-300" />
          <span className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
            {t("account.changePassword")}
          </span>
        </div>

        <div className="mt-2.5 grid gap-2.5 sm:grid-cols-3">
          <label className="block">
            <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
              {t("account.currentPassword")}
            </span>
            <input
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              disabled={!canWrite}
              autoComplete="current-password"
              className="input"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
              {t("account.newPassword")}
            </span>
            <input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              disabled={!canWrite}
              autoComplete="new-password"
              placeholder={t("auth.passwordHint")}
              className="input"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
              {t("account.confirmPassword")}
            </span>
            <input
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              disabled={!canWrite}
              autoComplete="new-password"
              className="input"
            />
          </label>
        </div>

        {pwError ? (
          <p className="mt-2 flex items-start gap-1.5 text-[11px] text-rose-600 dark:text-rose-300">
            <AlertCircle size={12} className="mt-0.5 shrink-0" />
            {pwError}
          </p>
        ) : null}
        {pwNotice ? (
          <p className="mt-2 flex items-start gap-1.5 text-[11px] text-emerald-600 dark:text-emerald-300">
            <CheckCircle2 size={12} className="mt-0.5 shrink-0" />
            {pwNotice}
          </p>
        ) : null}

        <button
          type="button"
          onClick={() => void changePassword()}
          disabled={!canWrite || pwBusy || !currentPassword || !newPassword}
          title={canWrite ? "" : t("common.readOnlyRole")}
          className="btn btn-ghost mt-3"
        >
          {pwBusy ? <Loader2 size={13} className="animate-spin" /> : <KeyRound size={13} />}
          {t("account.updatePassword")}
        </button>
      </div>
    </motion.section>
  );
}
