import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, Loader2, Lock, Save, X } from "lucide-react";
import { api, type Member } from "@/lib/api";
import { useSession } from "@/components/auth/SessionProvider";

type Level = "none" | "read" | "write";

const LEVELS: { value: Level; label: string }[] = [
  { value: "none", label: "无权限" },
  { value: "read", label: "可读" },
  { value: "write", label: "可写" },
];

export default function CourseGrantsPanel({
  courseId,
  open,
  onClose,
}: {
  courseId: string;
  open: boolean;
  onClose: () => void;
}) {
  const { tenant } = useSession();
  const [members, setMembers] = useState<Member[]>([]);
  const [levels, setLevels] = useState<Record<string, Level>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

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
      const next: Record<string, Level> = {};
      for (const item of memberList.members ?? []) next[item.user_id] = "none";
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

  const payload = useMemo(
    () =>
      Object.entries(levels)
        .filter(([, level]) => level !== "none")
        .map(([user_id, level]) => ({ user_id, level: level as "read" | "write" })),
    [levels],
  );

  const save = useCallback(async () => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await api.saveCourseGrants(courseId, payload);
      setNotice("可见范围已保存");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }, [courseId, payload]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-40 flex justify-end bg-slate-900/25 backdrop-blur-[2px]"
          onClick={onClose}
        >
          <motion.aside
            initial={{ x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            onClick={(event) => event.stopPropagation()}
            className="glass no-scrollbar h-full w-full max-w-md overflow-y-auto p-5 shadow-glass"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Lock size={15} className="text-indigo-500 dark:text-indigo-300" />
                <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
                  课程可见范围
                </h2>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="btn-quiet px-1.5"
                aria-label="关闭"
              >
                <X size={14} />
              </button>
            </div>

            <p className="mt-2 rounded-2xl border border-white/50 bg-white/45 px-3 py-2 text-[10.5px] leading-relaxed text-slate-500 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-400">
              角色范围为「全部课程」的成员不受此限制；此处仅对范围为「指定课程」的角色生效。
            </p>

            {error ? (
              <div className="mt-3 flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
                <AlertCircle size={13} className="mt-0.5 shrink-0" />
                <span className="flex-1">{error}</span>
              </div>
            ) : null}
            {notice ? (
              <div className="mt-3 rounded-2xl border border-emerald-400/30 bg-emerald-500/10 px-3 py-2 text-[11px] text-emerald-700 dark:text-emerald-300">
                {notice}
              </div>
            ) : null}

            <div className="mt-3 space-y-1.5">
              {loading ? (
                <p className="text-[11px] text-slate-400">加载中…</p>
              ) : members.length === 0 ? (
                <p className="text-[11px] text-slate-400">暂无成员。</p>
              ) : (
                members.map((member) => (
                  <div
                    key={member.user_id}
                    className="flex items-center gap-2 rounded-2xl border border-white/50 bg-white/45 px-3 py-2 dark:border-white/10 dark:bg-white/[0.04]"
                  >
                    <span className="brand-gradient grid h-7 w-7 shrink-0 place-items-center rounded-full text-[11px] font-semibold text-white">
                      {(member.user_display_name || member.user_email || "?")
                        .slice(0, 1)
                        .toUpperCase()}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12px] font-medium text-slate-800 dark:text-slate-100">
                        {member.user_display_name || member.user_email}
                      </span>
                      <span className="block truncate text-[10px] text-slate-400">
                        {member.user_email} · {member.role}
                      </span>
                    </span>
                    <select
                      value={levels[member.user_id] ?? "none"}
                      onChange={(event) =>
                        setLevels((prev) => ({
                          ...prev,
                          [member.user_id]: event.target.value as Level,
                        }))
                      }
                      className="select py-1 text-[11px]"
                    >
                      {LEVELS.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </div>
                ))
              )}
            </div>

            <div className="mt-4 flex items-center justify-between gap-2">
              <span className="text-[10px] text-slate-400">已授权 {payload.length} 人</span>
              <button
                type="button"
                onClick={() => void save()}
                disabled={saving || loading}
                className="btn btn-primary"
              >
                {saving ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Save size={13} />
                )}
                保存
              </button>
            </div>
          </motion.aside>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
