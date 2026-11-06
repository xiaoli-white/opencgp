import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Member } from "@/lib/api";
import { useSession } from "@/components/auth/SessionProvider";
import SharePanel, { type ShareMember, type ShareOption } from "@/components/sharing/SharePanel";
import { useI18n } from "@/i18n/I18nProvider";

export default function SeriesGrantsPanel({
  seriesId,
  open,
  onClose,
  onNotice,
}: {
  seriesId: string;
  open: boolean;
  onClose: () => void;
  onNotice?: (message: string) => void;
}) {
  const { tenant } = useSession();
  const { t } = useI18n();
  const options = useMemo<ShareOption[]>(
    () => [
      { value: "read", label: t("sharing.read"), desc: t("sharing.readDesc") },
      { value: "write", label: t("sharing.write"), desc: t("sharing.writeDesc") },
    ],
    [t],
  );
  const [members, setMembers] = useState<Member[]>([]);
  const [levels, setLevels] = useState<Record<string, string | null>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!seriesId) return;
    setLoading(true);
    setError("");
    try {
      const [memberList, grantList] = await Promise.all([
        tenant ? api.listMembers(tenant) : Promise.resolve({ count: 0, members: [] }),
        api.getSeriesGrants(seriesId),
      ]);
      setMembers(memberList.members ?? []);
      const next: Record<string, string | null> = {};
      for (const item of memberList.members ?? []) next[item.user_id] = null;
      for (const grant of grantList.grants ?? []) {
        next[grant.user_id] = grant.level === "write" ? "write" : "read";
      }
      setLevels(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("sharing.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [seriesId, tenant, t]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const shareMembers = useMemo<ShareMember[]>(
    () =>
      members.map((member) => ({
        user_id: member.user_id,
        user_email: member.user_email,
        user_display_name: member.user_display_name,
        avatar_url: member.avatar_url,
        note:
          member.user_display_name || member.user_email
            ? t("sharing.memberNote")
            : undefined,
      })),
    [members, t],
  );

  const save = useCallback(
    async (entries: { user_id: string; level: string }[]) => {
      setSaving(true);
      setError("");
      try {
        await api.saveSeriesGrants(
          seriesId,
          entries.map((item) => ({
            user_id: item.user_id,
            level: item.level === "write" ? ("write" as const) : ("read" as const),
          })),
        );
        onNotice?.(t("sharing.saved"));
        onClose();
      } catch (err) {
        setError(err instanceof Error ? err.message : t("sharing.saveFailed"));
      } finally {
        setSaving(false);
      }
    },
    [seriesId, onClose, onNotice, t],
  );

  return (
    <SharePanel
      open={open}
      title={t("sharing.seriesTitle")}
      subtitle={t("sharing.seriesSubtitle")}
      note={t("sharing.seriesNote")}
      members={shareMembers}
      value={levels}
      options={options}
      loading={loading}
      saving={saving}
      error={error}
      onClose={onClose}
      onChange={(userId, level) =>
        setLevels((prev) => ({ ...prev, [userId]: level }))
      }
      onSave={save}
    />
  );
}
