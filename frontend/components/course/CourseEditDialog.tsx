import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { api, type Course } from "@/lib/api";
import { Modal } from "@/components/common/Dialogs";

const DIFFICULTIES: { value: string; label: string }[] = [
  { value: "beginner", label: "入门" },
  { value: "intermediate", label: "进阶" },
  { value: "advanced", label: "高级" },
];

const LANGUAGES: { value: string; label: string }[] = [
  { value: "zh", label: "中文" },
  { value: "en", label: "English" },
];

export default function CourseEditDialog({
  open,
  course,
  onClose,
  onSaved,
}: {
  open: boolean;
  course: Course | null;
  onClose: () => void;
  onSaved: (course: Course) => void;
}) {
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [audience, setAudience] = useState("");
  const [difficulty, setDifficulty] = useState("beginner");
  const [language, setLanguage] = useState("zh");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || !course) return;
    setTitle(course.title);
    setSubtitle(course.subtitle ?? "");
    setAudience(course.audience ?? "");
    setDifficulty(course.difficulty || "beginner");
    setLanguage(course.language || "zh");
    setError("");
  }, [open, course]);

  const submit = async () => {
    if (!course) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api.updateCourse(course.id, {
        title: title.trim(),
        subtitle: subtitle.trim(),
        audience: audience.trim(),
        difficulty,
        language,
      });
      onSaved(updated);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title="编辑课程信息"
      subtitle="标题、简介与受众等元信息会同步显示在课程页与首页卡片。"
      onClose={onClose}
    >
      <div className="space-y-3">
        <label className="block text-[11px] text-slate-500 dark:text-slate-400">
          课程标题
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className="input mt-1"
            placeholder="例如：向量检索入门"
          />
        </label>
        <label className="block text-[11px] text-slate-500 dark:text-slate-400">
          副标题
          <input
            value={subtitle}
            onChange={(event) => setSubtitle(event.target.value)}
            className="input mt-1"
            placeholder="一句话说明这门课"
          />
        </label>
        <label className="block text-[11px] text-slate-500 dark:text-slate-400">
          目标受众
          <input
            value={audience}
            onChange={(event) => setAudience(event.target.value)}
            className="input mt-1"
            placeholder="例如：后端工程师"
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-[11px] text-slate-500 dark:text-slate-400">
            难度
            <select
              value={difficulty}
              onChange={(event) => setDifficulty(event.target.value)}
              className="select mt-1"
            >
              {DIFFICULTIES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-[11px] text-slate-500 dark:text-slate-400">
            语言
            <select
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              className="select mt-1"
            >
              {LANGUAGES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {error ? (
          <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
            {error}
          </p>
        ) : null}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="btn btn-quiet">
            取消
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || !title.trim()}
            className="btn btn-primary"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : null}
            保存修改
          </button>
        </div>
      </div>
    </Modal>
  );
}
