import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { KeyRound, Loader2, Pencil, Plus, Save, Trash2, X } from "lucide-react";
import clsx from "clsx";
import { api, type RoleRecord, type RoleScope } from "@/lib/api";
import { useSession } from "@/components/auth/SessionProvider";
import { useI18n } from "@/i18n/I18nProvider";
import type { RoleAction } from "@/lib/session";

const ACTIONS: { value: RoleAction; labelKey: string }[] = [
  { value: "read", labelKey: "roles.actionRead" },
  { value: "write", labelKey: "roles.actionWrite" },
  { value: "review", labelKey: "roles.actionReview" },
  { value: "manage_members", labelKey: "roles.actionMembers" },
  { value: "manage_quota", labelKey: "roles.actionQuota" },
  { value: "manage_server", labelKey: "roles.actionServer" },
];

const ACTION_LABEL_KEY: Record<string, string> = {
  read: "roles.actionRead",
  write: "roles.actionWrite",
  review: "roles.actionReview",
  manage_members: "roles.actionMembers",
  manage_quota: "roles.actionQuota",
  manage_server: "roles.actionServer",
};

type RoleForm = {
  id: string;
  name: string;
  actions: RoleAction[];
  scope: RoleScope;
  builtin: boolean;
};

const EMPTY_FORM: RoleForm = {
  id: "",
  name: "",
  actions: ["read"],
  scope: "all",
  builtin: false,
};

export default function RolesCard({
  onNotice,
  onError,
  onRolesChange,
}: {
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onRolesChange?: (roles: RoleRecord[]) => void;
}) {
  const { can, refresh } = useSession();
  const { t } = useI18n();
  const canManage = can("manage_members");

  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<RoleForm | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listRoles();
      const next = data.roles ?? [];
      setRoles(next);
      onRolesChange?.(next);
    } catch (err) {
      onError(err instanceof Error ? err.message : t("roles.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [onError, onRolesChange, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const saveRole = async () => {
    if (!form) return;
    setBusy(true);
    onError("");
    onNotice("");
    try {
      if (form.id) {
        await api.updateRole(form.id, {
          name: form.name.trim(),
          scope: form.scope,
          ...(form.builtin ? {} : { actions: form.actions }),
        });
        onNotice(t("roles.updated"));
      } else {
        await api.createRole({
          name: form.name.trim(),
          actions: form.actions,
          scope: form.scope,
        });
        onNotice(t("roles.created"));
      }
      setForm(null);
      await load();
      await refresh();
    } catch (err) {
      onError(err instanceof Error ? err.message : t("roles.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const deleteRole = async (roleId: string) => {
    onError("");
    onNotice("");
    try {
      await api.deleteRole(roleId);
      onNotice(t("roles.deleted"));
      await load();
    } catch (err) {
      onError(err instanceof Error ? err.message : t("roles.deleteFailed"));
    }
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-3xl p-5 shadow-glass"
    >
      <div className="flex flex-wrap items-center gap-2">
        <KeyRound size={15} className="text-indigo-500 dark:text-indigo-300" />
        <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
          {t("roles.title")}
        </h2>
        <span className="chip-muted">{t("common.count", { count: roles.length })}</span>
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => setForm({ ...EMPTY_FORM })}
          disabled={!canManage}
          title={canManage ? "" : t("roles.noManage")}
          className="btn btn-primary px-3 py-1.5 text-[11px]"
        >
          <Plus size={12} />
          {t("roles.new")}
        </button>
      </div>

      <div className="mt-3 space-y-1.5">
        {loading ? (
          <p className="text-[11px] text-slate-400">{t("roles.loading")}</p>
        ) : (
          roles.map((item) => (
            <div
              key={item.id}
              className="rounded-2xl border border-white/50 bg-white/45 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
                  {item.name}
                </span>
                <span className="chip-muted">{item.key}</span>
                {item.builtin ? <span className="chip">{t("roles.builtin")}</span> : null}
                <span
                  className={clsx(
                    "rounded-full px-2 py-0.5 text-[10px] font-medium",
                    item.scope === "assigned"
                      ? "bg-violet-500/12 text-violet-600 dark:text-violet-300"
                      : "bg-indigo-500/12 text-indigo-600 dark:text-indigo-300",
                  )}
                >
                  {item.scope === "assigned" ? t("roles.scopeAssigned") : t("roles.scopeAll")}
                </span>
                <span className="text-[10px] text-slate-400">
                  {item.member_count} {t("roles.memberUnit")}
                </span>
                <span className="flex-1" />
                <button
                  type="button"
                  onClick={() =>
                    setForm({
                      id: item.id,
                      name: item.name,
                      actions: [...item.actions],
                      scope: item.scope,
                      builtin: Boolean(item.builtin),
                    })
                  }
                  disabled={!canManage}
                  title={canManage ? t("roles.edit") : t("roles.noManage")}
                  className="btn-quiet px-1.5"
                >
                  <Pencil size={12} />
                </button>
                <button
                  type="button"
                  onClick={() => void deleteRole(item.id)}
                  disabled={!canManage || Boolean(item.builtin)}
                  title={item.builtin ? t("roles.builtinLocked") : t("roles.delete")}
                  className="btn-quiet px-1.5"
                >
                  <Trash2 size={12} />
                </button>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {item.actions.length === 0 ? (
                  <span className="text-[10px] text-slate-400">{t("roles.noActions")}</span>
                ) : (
                  item.actions.map((action) => (
                    <span
                      key={action}
                      className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] text-slate-600 ring-1 ring-slate-200/70 dark:bg-white/[0.06] dark:text-slate-300 dark:ring-white/10"
                    >
                      {ACTION_LABEL_KEY[action] ? t(ACTION_LABEL_KEY[action]) : action}
                    </span>
                  ))
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {form ? (
        <div className="mt-3 rounded-2xl border border-white/60 bg-white/60 p-3.5 dark:border-white/10 dark:bg-white/[0.05]">
          <div className="flex items-center gap-2">
            <span className="text-[12px] font-semibold text-slate-800 dark:text-slate-100">
              {form.id ? t("roles.editTitle") : t("roles.addTitle")}
            </span>
            <span className="flex-1" />
            <button
              type="button"
              onClick={() => setForm(null)}
              className="btn-quiet px-1.5"
              aria-label={t("common.cancel")}
            >
              <X size={12} />
            </button>
          </div>
          <div className="mt-2.5 space-y-2.5">
            <label className="block">
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                {t("roles.name")}
              </span>
              <input
                value={form.name}
                onChange={(event) =>
                  setForm((prev) => (prev ? { ...prev, name: event.target.value } : prev))
                }
                placeholder={t("roles.namePlaceholder")}
                className="input"
              />
            </label>

            <div>
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                {t("roles.actionsLabel")}
                {form.builtin ? t("roles.builtinSuffix") : ""}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {ACTIONS.map((action) => {
                  const active = form.actions.includes(action.value);
                  return (
                    <button
                      key={action.value}
                      type="button"
                      disabled={form.builtin}
                      onClick={() =>
                        setForm((prev) => {
                          if (!prev) return prev;
                          const next = prev.actions.includes(action.value)
                            ? prev.actions.filter((item) => item !== action.value)
                            : [...prev.actions, action.value];
                          return { ...prev, actions: next };
                        })
                      }
                      className={clsx(
                        "rounded-full px-2.5 py-1 text-[11px] font-medium transition",
                        active
                          ? "brand-gradient text-white shadow-[0_10px_22px_-16px_rgba(99,102,241,0.9)]"
                          : "bg-white/70 text-slate-600 ring-1 ring-slate-200/70 hover:text-indigo-600 dark:bg-white/[0.06] dark:text-slate-300 dark:ring-white/10",
                        form.builtin && "opacity-60",
                      )}
                    >
                      {t(action.labelKey)}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <span className="mb-1 block text-[11px] text-slate-500 dark:text-slate-400">
                {t("roles.scopeLabel")}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {[
                  { value: "all" as RoleScope, label: t("roles.scopeAll") },
                  { value: "assigned" as RoleScope, label: t("roles.scopeAssignedOnly") },
                ].map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() =>
                      setForm((prev) => (prev ? { ...prev, scope: option.value } : prev))
                    }
                    className={clsx(
                      "rounded-full px-2.5 py-1 text-[11px] font-medium transition",
                      form.scope === option.value
                        ? "brand-gradient text-white shadow-[0_10px_22px_-16px_rgba(99,102,241,0.9)]"
                        : "bg-white/70 text-slate-600 ring-1 ring-slate-200/70 hover:text-indigo-600 dark:bg-white/[0.06] dark:text-slate-300 dark:ring-white/10",
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={() => void saveRole()}
              disabled={busy || !form.name.trim()}
              className="btn btn-primary"
            >
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
              {t("roles.save")}
            </button>
          </div>
        </div>
      ) : null}
    </motion.section>
  );
}
