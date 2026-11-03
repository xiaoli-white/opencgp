import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Member } from "@/lib/api";
import { useSession } from "@/components/auth/SessionProvider";
import SharePanel, { type ShareMember, type ShareOption } from "@/components/sharing/SharePanel";

const OPTIONS: ShareOption[] = [
  { value: "read", label: "可读", desc: "可查看讲义与蓝图" },
  { value: "write", label: "可写", desc: "可生成、审核与修改" },
];

export default function CourseGrantsPanel({
  courseId,
  open,
  onClose,
  onNotice,
}: {
  courseId: string;
  open: boolean;
  onClose: () => void;
  onNotice?: (message: string) => void;
}) {
  const { tenant } = useSession();
  const [members, setMembers] = useState<Member[]>([]);
  const [levels, setLevels] = useState<Record<string, string | null>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!courseId) return;
    setLoading(true);
    setError("");
    try {
      const [memberList, grantList] = await Promise.all([
        tenant ? api.listMembers(tenant) : Promise.resolve({ count: 0, members: [] }),
        api.getCourseGrants(courseId),
      ]);
      setMembers(memberList.members ?? []);
      const next: Record<string, string | null> = {};
      for (const item of memberList.members ?? []) next[item.user_id] = null;
      for (const grant of grantList.grants ?? []) {
        next[grant.user_id] = grant.level === "write" ? "write" : "read";
      }
      setLevels(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [courseId, tenant]);

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
        note: member.user_display_name || member.user_email ? "空间成员" : undefined,
      })),
    [members],
  );

  const save = useCallback(
    async (entries: { user_id: string; level: string }[]) => {
      setSaving(true);
      setError("");
      try {
        await api.saveCourseGrants(
          courseId,
          entries.map((item) => ({
            user_id: item.user_id,
            level: item.level === "write" ? ("write" as const) : ("read" as const),
          })),
        );
        onNotice?.("可见范围已保存");
        onClose();
      } catch (err) {
        setError(err instanceof Error ? err.message : "保存失败");
      } finally {
        setSaving(false);
      }
    },
    [courseId, onClose, onNotice],
  );

  return (
    <SharePanel
      open={open}
      title="课程可见范围"
      subtitle="按成员设置本课程权限"
      note="角色范围为「全部课程」的成员不受此限制；此处仅对范围为「指定课程」的角色生效。"
      members={shareMembers}
      value={levels}
      options={OPTIONS}
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
