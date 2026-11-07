import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Building2,
  CheckCircle2,
  Crown,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  UserRound,
  Users,
  X,
} from "lucide-react";
import clsx from "clsx";
import { api, tenantId, type Member, type TenantMembership } from "@/lib/api";
import { setTenantId } from "@/lib/session";
import { useSession } from "@/components/auth/SessionProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { roleLabel } from "@/i18n/labels";

const KIND_LABEL_KEY: Record<string, string> = {
  system: "space.system",
  personal: "space.personal",
  team: "space.team",
};

export default function SpacesCard({
  onNotice,
  onError,
}: {
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { tenant, refresh } = useSession();
  const { t } = useI18n();
  const [items, setItems] = useState<TenantMembership[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"personal" | "team">("team");
  const [renamingId, setRenamingId] = useState("");
  const [renameValue, setRenameValue] = useState("");
  const [transferId, setTransferId] = useState("");
  const [transferMembers, setTransferMembers] = useState<Member[]>([]);
  const [transferUser, setTransferUser] = useState("");
  const [transferLoading, setTransferLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listTenants();
      setItems(data.tenants ?? []);
    } catch (err) {
      onError(err instanceof Error ? err.message : t("space.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [onError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const goTenant = (id: string) => {
    setTenantId(id, false);
    window.dispatchEvent(new Event("series-studio:refresh"));
    window.location.reload();
  };

  const createSpace = async () => {
    if (!name.trim()) return;
    setBusy(true);
    onError("");
    onNotice("");
    try {
      const created = await api.createTenant({ name: name.trim(), kind });
      setName("");
      await refresh();
      goTenant(created.tenant.id);
    } catch (err) {
      onError(err instanceof Error ? err.message : t("space.createFailed"));
    } finally {
      setBusy(false);
    }
  };

  const renameSpace = async (id: string) => {
    if (!renameValue.trim()) return;
    setBusy(true);
    onError("");
    onNotice("");
    try {
      await api.renameTenant(id, renameValue.trim());
      setRenamingId("");
      setRenameValue("");
      await load();
      await refresh();
      onNotice(t("space.renamed"));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("space.renameFailed"));
    } finally {
      setBusy(false);
    }
  };

  const deleteSpace = async (id: string) => {
    setBusy(true);
    onError("");
    onNotice("");
    try {
      await api.deleteTenant(id);
      await load();
      await refresh();
      onNotice(t("space.deleted"));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("space.deleteFailed"));
    } finally {
      setBusy(false);
    }
  };

  const openTransfer = async (id: string) => {
    setTransferId(id);
    setTransferUser("");
    setTransferLoading(true);
    onError("");
    try {
      const data = await api.listMembers(id);
      setTransferMembers(data.members ?? []);
    } catch (err) {
      onError(err instanceof Error ? err.message : t("members.loadFailed"));
      setTransferMembers([]);
    } finally {
      setTransferLoading(false);
    }
  };

  const doTransfer = async () => {
    if (!transferId || !transferUser) return;
    setBusy(true);
    onError("");
    onNotice("");
    try {
      await api.transferTenant(transferId, transferUser);
      setTransferId("");
      await load();
      await refresh();
      onNotice(t("space.transferSuccess"));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("space.transferFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-3xl p-5 shadow-glass"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Building2 size={15} className="text-indigo-500 dark:text-indigo-300" />
        <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
          {t("space.title")}
        </h2>
        <span className="chip-muted">{t("common.count", { count: items.length })}</span>
      </div>

      <div className="mt-3 space-y-1.5">
        {loading ? (
          <p className="text-[11px] text-slate-400">{t("common.loading")}</p>
        ) : (
          items.map((item) => {
            const info = item.tenant;
            const id = tenantId(info);
            const isCurrent = id === tenant;
            const isSystem = Boolean(info.is_system) || info.kind === "system";
            const isOwner = item.role === "owner";
            return (
              <div
                key={id}
                className={clsx(
                  "rounded-2xl border px-3 py-2.5 transition",
                  isCurrent
                    ? "border-indigo-400/40 bg-indigo-500/10 dark:border-indigo-300/30 dark:bg-indigo-400/10"
                    : "border-white/50 bg-white/45 dark:border-white/10 dark:bg-white/[0.04]",
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
                    {info.name || id}
                  </span>
                  <span className="chip-muted">
                    {KIND_LABEL_KEY[String(info.kind ?? "")]
                      ? t(KIND_LABEL_KEY[String(info.kind ?? "")])
                      : info.kind ?? t("space.team")}
                  </span>
                  {isCurrent ? (
                    <span className="rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] font-medium text-indigo-600 dark:text-indigo-300">
                      {t("space.current")}
                    </span>
                  ) : null}
                  <span className="flex items-center gap-1 text-[10px] text-slate-400">
                    <Users size={10} />
                    {info.member_count ?? 0}
                  </span>
                  <span className="flex items-center gap-1 text-[10px] text-slate-400">
                    <Crown size={10} />
                    {roleLabel(t, item.role)}
                  </span>
                  <span className="flex-1" />
                  {!isCurrent ? (
                    <button
                      type="button"
                      onClick={() => goTenant(id)}
                      className="btn-quiet px-2 py-1 text-[10.5px]"
                    >
                      {t("space.switch")}
                    </button>
                  ) : null}
                  {isOwner && !isSystem ? (
                    <>
                      <button
                        type="button"
                        onClick={() => {
                          setRenamingId(renamingId === id ? "" : id);
                          setRenameValue(info.name ?? "");
                        }}
                        className="btn-quiet px-1.5"
                        title={t("common.rename")}
                      >
                        <Pencil size={12} />
                      </button>
                      <button
                        type="button"
                        onClick={() => void openTransfer(id)}
                        className="btn-quiet px-1.5"
                        title={t("space.transfer")}
                      >
                        <UserRound size={12} />
                      </button>
                      <button
                        type="button"
                        onClick={() => void deleteSpace(id)}
                        disabled={busy}
                        className="btn-quiet px-1.5"
                        title={t("space.deleteSpace")}
                      >
                        <Trash2 size={12} />
                      </button>
                    </>
                  ) : null}
                </div>

                {renamingId === id ? (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <input
                      value={renameValue}
                      onChange={(event) => setRenameValue(event.target.value)}
                      className="input w-full sm:max-w-[220px]"
                      placeholder={t("space.namePlaceholder")}
                    />
                    <button
                      type="button"
                      onClick={() => void renameSpace(id)}
                      disabled={busy || !renameValue.trim()}
                      className="btn btn-primary px-3 py-1.5 text-[11px]"
                    >
                      {busy ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
                      {t("common.save")}
                    </button>
                    <button
                      type="button"
                      onClick={() => setRenamingId("")}
                      className="btn-quiet px-1.5"
                      aria-label={t("common.cancel")}
                    >
                      <X size={12} />
                    </button>
                  </div>
                ) : null}

                {transferId === id ? (
                  <div className="mt-2 rounded-2xl border border-white/60 bg-white/55 p-2.5 dark:border-white/10 dark:bg-white/[0.05]">
                    <span className="block text-[11px] text-slate-500 dark:text-slate-400">
                      {t("space.selectOwner")}
                    </span>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2">
                      <select
                        value={transferUser}
                        onChange={(event) => setTransferUser(event.target.value)}
                        className="select w-full py-1.5 text-[11px] sm:max-w-[240px]"
                        disabled={transferLoading}
                      >
                        <option value="">
                          {transferLoading ? t("common.loading") : t("space.selectMember")}
                        </option>
                        {transferMembers.map((member) => (
                          <option key={member.user_id} value={member.user_id}>
                            {member.user_display_name || member.user_email} ·{" "}
                            {roleLabel(t, member.role)}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => void doTransfer()}
                        disabled={busy || !transferUser}
                        className="btn btn-primary px-3 py-1.5 text-[11px]"
                      >
                        {t("space.transferConfirm")}
                      </button>
                      <button
                        type="button"
                        onClick={() => setTransferId("")}
                        className="btn-quiet px-1.5"
                        aria-label={t("common.cancel")}
                      >
                        <X size={12} />
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>

      <div className="mt-3.5 rounded-2xl border border-white/60 bg-white/55 p-3 dark:border-white/10 dark:bg-white/[0.05]">
        <span className="block text-[11px] font-medium text-slate-600 dark:text-slate-300">
          {t("space.create")}
        </span>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t("space.namePlaceholder")}
            className="input w-full sm:max-w-[220px]"
          />
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as "personal" | "team")}
            className="select w-full py-2 text-[12px] sm:w-auto"
          >
            <option value="team">{t("space.team")}</option>
            <option value="personal">{t("space.personal")}</option>
          </select>
          <button
            type="button"
            onClick={() => void createSpace()}
            disabled={busy || !name.trim()}
            className="btn btn-primary"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
            {t("space.createAndSwitch")}
          </button>
        </div>
      </div>
    </motion.section>
  );
}
