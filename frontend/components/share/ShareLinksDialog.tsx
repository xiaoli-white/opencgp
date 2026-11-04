import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  Ban,
  Check,
  Copy,
  ExternalLink,
  Link2,
  Loader2,
  Plus,
} from "lucide-react";
import clsx from "clsx";
import { api, type ShareLink, type ShareResourceType } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { ConfirmDialog, Modal } from "@/components/common/Dialogs";
import { useI18n } from "@/i18n/I18nProvider";

type Props = {
  open: boolean;
  onClose: () => void;
  resourceType: ShareResourceType;
  resourceId: string;
  title?: string;
};

type LinkStatus = "valid" | "revoked" | "expired";

const DAY_OPTIONS = ["1", "7", "30", "0"] as const;

function statusOf(link: ShareLink): LinkStatus {
  if (link.revoked) return "revoked";
  if (link.expires_at && link.expires_at * 1000 < Date.now()) return "expired";
  return "valid";
}

function absoluteUrl(url: string): string {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  if (typeof window === "undefined") return url;
  return `${window.location.origin}${url.startsWith("/") ? "" : "/"}${url}`;
}

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    void 0;
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    area.style.left = "-1000px";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.focus();
    area.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}

export default function ShareLinksDialog({
  open,
  onClose,
  resourceType,
  resourceId,
  title,
}: Props) {
  const { t } = useI18n();
  const [links, setLinks] = useState<ShareLink[]>([]);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState<string>("7");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [copiedId, setCopiedId] = useState("");
  const [revokeTarget, setRevokeTarget] = useState<ShareLink | null>(null);
  const [revoking, setRevoking] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.listShareLinks({
        resource_type: resourceType,
        resource_id: resourceId,
      });
      setLinks(data.links ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("share.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [resourceType, resourceId, t]);

  useEffect(() => {
    if (!open) return;
    setCopiedId("");
    setRevokeTarget(null);
    void load();
  }, [open, load]);

  const create = async () => {
    setCreating(true);
    setError("");
    try {
      const link = await api.createShareLink({
        resource_type: resourceType,
        resource_id: resourceId,
        expires_in_days: Number(days),
      });
      setLinks((prev) => [link, ...prev.filter((item) => item.id !== link.id)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("share.createFailed"));
    } finally {
      setCreating(false);
    }
  };

  const copy = async (link: ShareLink) => {
    const ok = await copyToClipboard(absoluteUrl(link.url));
    if (!ok) return;
    setCopiedId(link.id);
    window.setTimeout(() => {
      setCopiedId((prev) => (prev === link.id ? "" : prev));
    }, 1600);
  };

  const revoke = async () => {
    if (!revokeTarget) return;
    setRevoking(true);
    setError("");
    try {
      await api.deleteShareLink(revokeTarget.id);
      setRevokeTarget(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("share.revokeFailed"));
    } finally {
      setRevoking(false);
    }
  };

  const statusLabel = (status: LinkStatus) =>
    status === "revoked"
      ? t("share.statusRevoked")
      : status === "expired"
        ? t("share.statusExpired")
        : t("share.statusValid");

  const expiryLabel = (link: ShareLink) =>
    link.expires_at
      ? t("share.expiresAt", { time: formatDateTime(link.expires_at) })
      : t("share.permanent");

  return (
    <>
      <Modal
        open={open}
        wide
        title={t("share.dialogTitle")}
        subtitle={title ? `${title} · ${t("share.note")}` : t("share.note")}
        onClose={onClose}
      >
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/60 bg-white/55 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]">
            <label className="flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
              {t("share.validity")}
              <select
                value={days}
                onChange={(event) => setDays(event.target.value)}
                className="select py-1 text-[11px]"
              >
                {DAY_OPTIONS.map((value) => (
                  <option key={value} value={value}>
                    {value === "0"
                      ? t("share.optionPermanent")
                      : t(`share.option${value}`)}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void create()}
              disabled={creating || loading}
              className="btn btn-primary ml-auto"
            >
              {creating ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Plus size={13} />
              )}
              {creating ? t("share.generating") : t("share.generate")}
            </button>
          </div>

          {error ? (
            <div className="flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              <span className="min-w-0 flex-1 break-words">{error}</span>
            </div>
          ) : null}

          {loading ? (
            <p className="flex items-center gap-2 px-1 text-[11px] text-slate-400">
              <Loader2 size={12} className="animate-spin" />
              {t("share.loading")}
            </p>
          ) : links.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-white/70 bg-white/40 px-3 py-4 text-center text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-400">
              {t("share.empty")}
            </p>
          ) : (
            <div className="space-y-2">
              <AnimatePresence initial={false}>
                {links.map((link) => {
                  const status = statusOf(link);
                  const full = absoluteUrl(link.url);
                  return (
                    <motion.div
                      key={link.id}
                      layout
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -6 }}
                      transition={{ duration: 0.16 }}
                      className="rounded-2xl border border-white/60 bg-white/55 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]"
                    >
                      <div className="flex items-start gap-2">
                        <Link2
                          size={13}
                          className="mt-0.5 shrink-0 text-indigo-500 dark:text-indigo-300"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex min-w-0 items-center gap-2">
                            <span
                              className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-slate-700 dark:text-slate-200"
                              title={full}
                            >
                              {full}
                            </span>
                            <span
                              className={clsx(
                                "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium",
                                status === "valid"
                                  ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                                  : status === "revoked"
                                    ? "bg-slate-500/15 text-slate-600 dark:text-slate-300"
                                    : "bg-amber-500/15 text-amber-700 dark:text-amber-300",
                              )}
                            >
                              {statusLabel(status)}
                            </span>
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-slate-400 dark:text-slate-500">
                            <span>
                              {t("share.createdAt", {
                                time: formatDateTime(link.created_at),
                              })}
                            </span>
                            <span>{expiryLabel(link)}</span>
                            <span>{t("share.views", { count: link.view_count })}</span>
                          </div>
                        </div>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => void copy(link)}
                          className="btn btn-quiet px-2 py-1 text-[11px]"
                        >
                          {copiedId === link.id ? <Check size={12} /> : <Copy size={12} />}
                          {copiedId === link.id ? t("share.copied") : t("share.copy")}
                        </button>
                        <a
                          href={link.url || full}
                          target="_blank"
                          rel="noreferrer"
                          className="btn btn-quiet px-2 py-1 text-[11px]"
                        >
                          <ExternalLink size={12} />
                          {t("share.open")}
                        </a>
                        <button
                          type="button"
                          onClick={() => setRevokeTarget(link)}
                          disabled={status === "revoked"}
                          className="btn btn-quiet px-2 py-1 text-[11px] text-rose-600 disabled:opacity-40 dark:text-rose-300"
                        >
                          <Ban size={12} />
                          {t("share.revoke")}
                        </button>
                      </div>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
            </div>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(revokeTarget)}
        title={t("share.revokeTitle")}
        description={t("share.revokeDesc")}
        confirmLabel={t("share.revoke")}
        busy={revoking}
        onConfirm={() => void revoke()}
        onClose={() => {
          if (!revoking) setRevokeTarget(null);
        }}
      />
    </>
  );
}
