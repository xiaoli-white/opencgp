import { useMemo } from "react";
import clsx from "clsx";
import {
  ArrowDown,
  ArrowUp,
  Loader2,
  Plus,
  Save,
  Trash2,
  X,
} from "lucide-react";
import type {
  Blueprint,
  BlueprintValidationError,
  LearningStage,
  OutlineNode,
} from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";

export const EDIT_LIMITS = {
  title: 80,
  stageTitle: 60,
  goal: 500,
  summary: 4000,
  objective: 160,
  overview: 20000,
} as const;

function uid(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random()
    .toString(36)
    .slice(2, 6)}`;
}

function replaceAt<T>(items: T[], index: number, value: T): T[] {
  return items.map((item, position) => (position === index ? value : item));
}

function move<T>(items: T[], from: number, to: number): T[] {
  if (to < 0 || to >= items.length || from === to) return items;
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export type BlueprintEditorProps = {
  draft: Blueprint;
  onChange: (next: Blueprint) => void;
  errors: BlueprintValidationError[];
  saving: boolean;
  saveError: string;
  onChangeGlossary: () => void;
  onSave: () => void;
  onCancel: () => void;
};

export default function BlueprintEditor({
  draft,
  onChange,
  errors,
  saving,
  saveError,
  onChangeGlossary,
  onSave,
  onCancel,
}: BlueprintEditorProps) {
  const { t } = useI18n();

  const errorMap = useMemo(() => {
    const map = new Map<string, BlueprintValidationError>();
    errors.forEach((error) => {
      if (!map.has(error.path)) map.set(error.path, error);
    });
    return map;
  }, [errors]);

  const stageIds = useMemo(
    () => new Set(draft.learning_path.map((stage) => stage.id)),
    [draft.learning_path],
  );

  const errorFor = (path: string) => errorMap.get(path);

  const updateStage = (index: number, patch: Partial<LearningStage>) => {
    onChange({
      ...draft,
      learning_path: replaceAt(draft.learning_path, index, {
        ...draft.learning_path[index],
        ...patch,
      }),
    });
  };

  const updateNode = (index: number, patch: Partial<OutlineNode>) => {
    onChange({
      ...draft,
      outline: replaceAt(draft.outline, index, {
        ...draft.outline[index],
        ...patch,
      }),
    });
  };

  const addStage = () => {
    const stage: LearningStage = {
      id: uid("stage"),
      title: t("blueprint.editor.newStageTitle", {
        index: draft.learning_path.length + 1,
      }),
      goal: "",
      node_ids: [],
      estimated_minutes: 0,
    };
    onChange({ ...draft, learning_path: [...draft.learning_path, stage] });
  };

  const removeStage = (index: number) => {
    const stage = draft.learning_path[index];
    const stageNodes = draft.outline.filter((node) => node.stage_id === stage.id);
    if (
      stageNodes.length > 0 &&
      !window.confirm(
        t("blueprint.editor.confirmRemoveStage", { count: stageNodes.length }),
      )
    ) {
      return;
    }
    const remaining = draft.learning_path.filter((_, position) => position !== index);
    const fallback = remaining[0]?.id ?? "";
    onChange({
      ...draft,
      learning_path: remaining,
      outline: draft.outline
        .filter((node) => node.stage_id !== stage.id)
        .map((node) =>
          node.stage_id === stage.id && fallback
            ? { ...node, stage_id: fallback }
            : node,
        ),
    });
  };

  const addNode = (stageId: string) => {
    const node: OutlineNode = {
      id: uid("node"),
      stage_id: stageId,
      title: t("blueprint.editor.newNodeTitle", {
        index: draft.outline.length + 1,
      }),
      summary: "",
      objectives: [""],
      prerequisites: [],
      estimated_minutes: 0,
      unit_id: null,
      status: "planned",
    };
    onChange({ ...draft, outline: [...draft.outline, node] });
  };

  const removeNode = (index: number) => {
    const node = draft.outline[index];
    const message = node.unit_id
      ? t("blueprint.editor.confirmRemoveLinkedNode", { title: node.title })
      : t("blueprint.editor.confirmRemoveNode");
    if (!window.confirm(message)) return;
    onChange({
      ...draft,
      outline: draft.outline.filter((_, position) => position !== index),
    });
  };

  const moveNodeWithinStage = (nodeIndex: number, direction: -1 | 1) => {
    const node = draft.outline[nodeIndex];
    const siblings = draft.outline
      .map((item, index) => ({ item, index }))
      .filter((entry) => entry.item.stage_id === node.stage_id);
    const position = siblings.findIndex((entry) => entry.index === nodeIndex);
    const target = siblings[position + direction];
    if (!target) return;
    onChange({
      ...draft,
      outline: move(draft.outline, nodeIndex, target.index),
    });
  };

  const fieldError = (path: string) => errorFor(path)?.message ?? "";

  return (
    <div className="space-y-4" data-testid="blueprint-editor">
      <div className="glass rounded-3xl p-4 shadow-glass sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-slate-800 dark:text-slate-100">
              {t("blueprint.editor.title")}
            </p>
            <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
              {t("blueprint.editor.hint")}
            </p>
          </div>
          <button
            type="button"
            onClick={onChangeGlossary}
            className="btn btn-ghost shrink-0"
          >
            {t("blueprint.editGlossary")}
          </button>
        </div>

        <label className="mt-4 block text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
          {t("blueprint.editor.overviewLabel")}
        </label>
        <textarea
          value={draft.overview}
          data-testid="blueprint-overview-input"
          onChange={(event) => onChange({ ...draft, overview: event.target.value })}
          rows={7}
          maxLength={EDIT_LIMITS.overview}
          className={clsx(
            "input mt-1.5 min-h-[140px] w-full resize-y font-normal normal-case tracking-normal",
            fieldError("overview") && "ring-2 ring-rose-400",
          )}
        />
        <FieldNote
          error={fieldError("overview")}
          hint={t("blueprint.editor.chars", {
            count: draft.overview.length,
            limit: EDIT_LIMITS.overview,
          })}
        />
        <p className="mt-1 text-[10.5px] leading-relaxed text-slate-400 dark:text-slate-500">
          {t("blueprint.editor.proseHint")}
        </p>
      </div>

      <div className="glass rounded-3xl p-4 shadow-glass sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[13px] font-semibold text-slate-800 dark:text-slate-100">
            {t("blueprint.editor.stagesTitle", {
              count: draft.learning_path.length,
            })}
          </p>
          <button type="button" onClick={addStage} className="btn btn-ghost shrink-0">
            <Plus size={13} />
            {t("blueprint.editor.addStage")}
          </button>
        </div>

        <div className="mt-3 space-y-3">
          {draft.learning_path.map((stage, stageIndex) => {
            const nodes = draft.outline
              .map((node, nodeIndex) => ({ node, nodeIndex }))
              .filter((entry) => entry.node.stage_id === stage.id);
            return (
              <div
                key={stage.id}
                data-testid={`blueprint-stage-${stageIndex}`}
                className="rounded-2xl border border-slate-200/70 bg-white/40 p-3 dark:border-white/10 dark:bg-white/[0.03] sm:p-4"
              >
                <div className="flex flex-wrap items-start gap-2">
                  <span className="brand-gradient mt-1 grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-semibold text-white">
                    {stageIndex + 1}
                  </span>
                  <div className="min-w-0 flex-1 space-y-2">
                    <div>
                      <input
                        value={stage.title}
                        data-testid={`blueprint-stage-title-${stageIndex}`}
                        onChange={(event) =>
                          updateStage(stageIndex, { title: event.target.value })
                        }
                        maxLength={EDIT_LIMITS.stageTitle}
                        aria-label={t("blueprint.editor.stageTitleLabel")}
                        className={clsx(
                          "input w-full",
                          fieldError(`learning_path[${stageIndex}].title`) &&
                            "ring-2 ring-rose-400",
                        )}
                      />
                      <FieldNote
                        error={fieldError(`learning_path[${stageIndex}].title`)}
                        hint={t("blueprint.editor.chars", {
                          count: stage.title.length,
                          limit: EDIT_LIMITS.stageTitle,
                        })}
                      />
                    </div>
                    <div>
                      <textarea
                        value={stage.goal}
                        rows={2}
                        maxLength={EDIT_LIMITS.goal}
                        placeholder={t("blueprint.editor.stageGoalPlaceholder")}
                        onChange={(event) =>
                          updateStage(stageIndex, { goal: event.target.value })
                        }
                        className={clsx(
                          "input w-full resize-y",
                          fieldError(`learning_path[${stageIndex}].goal`) &&
                            "ring-2 ring-rose-400",
                        )}
                      />
                      <FieldNote
                        error={fieldError(`learning_path[${stageIndex}].goal`)}
                      />
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <IconButton
                      label={t("blueprint.editor.moveUp")}
                      disabled={stageIndex === 0}
                      onClick={() =>
                        onChange({
                          ...draft,
                          learning_path: move(
                            draft.learning_path,
                            stageIndex,
                            stageIndex - 1,
                          ),
                        })
                      }
                      icon={<ArrowUp size={12} />}
                    />
                    <IconButton
                      label={t("blueprint.editor.moveDown")}
                      disabled={stageIndex === draft.learning_path.length - 1}
                      onClick={() =>
                        onChange({
                          ...draft,
                          learning_path: move(
                            draft.learning_path,
                            stageIndex,
                            stageIndex + 1,
                          ),
                        })
                      }
                      icon={<ArrowDown size={12} />}
                    />
                    <IconButton
                      label={t("blueprint.editor.removeStage")}
                      danger
                      onClick={() => removeStage(stageIndex)}
                      icon={<Trash2 size={12} />}
                    />
                  </div>
                </div>

                <div className="mt-3 space-y-2 border-t border-slate-200/60 pt-3 dark:border-white/10">
                  {nodes.map(({ node, nodeIndex }, indexInStage) => (
                    <div
                      key={node.id}
                      data-testid={`blueprint-node-editor-${nodeIndex}`}
                      className="rounded-xl border border-slate-200/70 bg-white/60 p-2.5 dark:border-white/10 dark:bg-white/[0.04]"
                    >
                      <div className="flex flex-wrap items-start gap-1.5">
                        <input
                          value={node.title}
                          data-testid={`blueprint-node-title-${nodeIndex}`}
                          onChange={(event) =>
                            updateNode(nodeIndex, { title: event.target.value })
                          }
                          maxLength={EDIT_LIMITS.title}
                          aria-label={t("blueprint.editor.nodeTitleLabel")}
                          className={clsx(
                            "input min-w-0 flex-1",
                            fieldError(`outline[${nodeIndex}].title`) &&
                              "ring-2 ring-rose-400",
                          )}
                        />
                        <div className="flex shrink-0 items-center gap-1">
                          <IconButton
                            label={t("blueprint.editor.moveUp")}
                            disabled={indexInStage === 0}
                            onClick={() => moveNodeWithinStage(nodeIndex, -1)}
                            icon={<ArrowUp size={12} />}
                          />
                          <IconButton
                            label={t("blueprint.editor.moveDown")}
                            disabled={indexInStage === nodes.length - 1}
                            onClick={() => moveNodeWithinStage(nodeIndex, 1)}
                            icon={<ArrowDown size={12} />}
                          />
                          <IconButton
                            label={t("blueprint.editor.removeNode")}
                            danger
                            onClick={() => removeNode(nodeIndex)}
                            icon={<Trash2 size={12} />}
                          />
                        </div>
                      </div>
                      <FieldNote
                        error={fieldError(`outline[${nodeIndex}].title`)}
                        hint={t("blueprint.editor.chars", {
                          count: node.title.length,
                          limit: EDIT_LIMITS.title,
                        })}
                      />
                      <textarea
                        value={node.summary}
                        rows={3}
                        maxLength={EDIT_LIMITS.summary}
                        placeholder={t("blueprint.editor.summaryPlaceholder")}
                        onChange={(event) =>
                          updateNode(nodeIndex, { summary: event.target.value })
                        }
                        className={clsx(
                          "input mt-1.5 w-full resize-y",
                          fieldError(`outline[${nodeIndex}].summary`) &&
                            "ring-2 ring-rose-400",
                        )}
                      />
                      <FieldNote
                        error={fieldError(`outline[${nodeIndex}].summary`)}
                      />
                      <textarea
                        value={node.objectives.join("\n")}
                        rows={3}
                        placeholder={t("blueprint.editor.objectivesPlaceholder")}
                        onChange={(event) =>
                          updateNode(nodeIndex, {
                            objectives: event.target.value.split("\n"),
                          })
                        }
                        className={clsx(
                          "input mt-1.5 w-full resize-y font-mono text-[11.5px]",
                          fieldError(`outline[${nodeIndex}].objectives`) &&
                            "ring-2 ring-rose-400",
                        )}
                      />
                      <FieldNote
                        error={fieldError(`outline[${nodeIndex}].objectives`)}
                        hint={t("blueprint.editor.objectivesHint")}
                      />
                      <div className="mt-1.5 flex flex-wrap items-center gap-2">
                        <label className="text-[10.5px] text-slate-400 dark:text-slate-500">
                          {t("blueprint.editor.stageSelectLabel")}
                        </label>
                        <select
                          value={node.stage_id}
                          onChange={(event) =>
                            updateNode(nodeIndex, {
                              stage_id: event.target.value,
                            })
                          }
                          className="input max-w-full flex-1 !py-1 text-[11.5px]"
                        >
                          {draft.learning_path.map((option) => (
                            <option key={option.id} value={option.id}>
                              {option.title || option.id}
                            </option>
                          ))}
                          {!stageIds.has(node.stage_id) ? (
                            <option value={node.stage_id}>
                              {t("blueprint.editor.unassignedStage")}
                            </option>
                          ) : null}
                        </select>
                        {node.unit_id ? (
                          <span className="chip-muted">
                            {t("blueprint.editor.linkedUnit")}
                          </span>
                        ) : null}
                      </div>
                      <FieldNote
                        error={fieldError(`outline[${nodeIndex}].stage_id`)}
                      />
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => addNode(stage.id)}
                    className="btn btn-ghost w-full justify-center"
                  >
                    <Plus size={13} />
                    {t("blueprint.editor.addNode")}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="glass sticky bottom-3 z-20 flex flex-wrap items-center gap-2 rounded-2xl border-indigo-300/40 p-3 shadow-glass dark:border-indigo-400/20 sm:bottom-4">
        <button
          type="button"
          data-testid="blueprint-save-button"
          onClick={onSave}
          disabled={saving}
          className="btn btn-primary min-w-0 flex-1 sm:flex-none"
        >
          {saving ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Save size={14} />
          )}
          {saving ? t("blueprint.editor.saving") : t("blueprint.editor.save")}
        </button>
        <button
          type="button"
          data-testid="blueprint-cancel-button"
          onClick={onCancel}
          disabled={saving}
          className="btn btn-ghost min-w-0 flex-1 sm:flex-none"
        >
          <X size={14} />
          {t("blueprint.editor.cancel")}
        </button>
        {errors.length > 0 ? (
          <p
            role="alert"
            data-testid="blueprint-editor-error"
            className="w-full text-[11px] leading-relaxed text-rose-600 dark:text-rose-300"
          >
            {errors[0].message}
            {errors.length > 1
              ? ` · ${t("blueprint.editor.moreErrors", {
                  count: errors.length - 1,
                })}`
              : ""}
          </p>
        ) : saveError ? (
          <p
            role="alert"
            data-testid="blueprint-editor-error"
            className="w-full text-[11px] leading-relaxed text-rose-600 dark:text-rose-300"
          >
            {saveError}
          </p>
        ) : (
          <p className="hidden text-[10.5px] text-slate-400 dark:text-slate-500 sm:block">
            {t("blueprint.editor.unsavedHint")}
          </p>
        )}
      </div>
    </div>
  );
}

function FieldNote({ error, hint }: { error?: string; hint?: string }) {
  if (error) {
    return (
      <p className="mt-1 text-[10.5px] leading-snug text-rose-600 dark:text-rose-300">
        {error}
      </p>
    );
  }
  if (!hint) return null;
  return (
    <p className="mt-1 text-[10px] text-slate-400 dark:text-slate-500">{hint}</p>
  );
}

function IconButton({
  label,
  icon,
  onClick,
  disabled,
  danger,
}: {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={clsx(
        "grid h-7 w-7 place-items-center rounded-lg border text-slate-500 transition disabled:cursor-not-allowed disabled:opacity-35 dark:text-slate-300",
        danger
          ? "border-rose-200/70 hover:bg-rose-500/10 hover:text-rose-600 dark:border-rose-300/20"
          : "border-slate-200/70 hover:bg-indigo-500/10 hover:text-indigo-600 dark:border-white/10",
      )}
    >
      {icon}
    </button>
  );
}
