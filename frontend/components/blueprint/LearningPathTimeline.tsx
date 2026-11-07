import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import clsx from "clsx";
import {
  ChevronDown,
  Clock3,
  CornerDownRight,
  ListChecks,
  Lock,
  Waypoints,
} from "lucide-react";
import type { Blueprint, OutlineNode } from "@/lib/api";
import StatusBadge, { statusDotClass } from "@/components/series/StatusBadge";
import { useI18n } from "@/i18n/I18nProvider";
import { pluralLabel } from "@/i18n/labels";

type Translate = (path: string, vars?: Record<string, string | number>) => string;

type LearningPathTimelineProps = {
  blueprint: Blueprint;
  highlightedUnitIds?: Set<string>;
  onOpenUnit: (unitId: string) => void;
};

function nodeMinutes(t: Translate, node: OutlineNode): string {
  return node.estimated_minutes > 0
    ? t("blueprint.minutes", { count: node.estimated_minutes })
    : t("blueprint.durationTbd");
}

export default function LearningPathTimeline({
  blueprint,
  highlightedUnitIds,
  onOpenUnit,
}: LearningPathTimelineProps) {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const stageNodes = useMemo(() => {
    const grouped = new Map<string, OutlineNode[]>();
    blueprint.outline.forEach((node) => {
      const key = node.stage_id || "";
      const bucket = grouped.get(key);
      if (bucket) {
        bucket.push(node);
      } else {
        grouped.set(key, [node]);
      }
    });
    return grouped;
  }, [blueprint.outline]);

  const orphanNodes = useMemo(() => {
    const stageIds = new Set(blueprint.learning_path.map((stage) => stage.id));
    return blueprint.outline.filter(
      (node) => !node.stage_id || !stageIds.has(node.stage_id),
    );
  }, [blueprint.learning_path, blueprint.outline]);

  const toggle = (stageId: string) =>
    setCollapsed((prev) => ({ ...prev, [stageId]: !prev[stageId] }));

  const renderNode = (node: OutlineNode, index: number) => {
    const bound = Boolean(node.unit_id);
    const applied = Boolean(node.unit_id && highlightedUnitIds?.has(node.unit_id));
    return (
      <motion.li
        key={node.id || `${node.title}-${index}`}
        data-testid="blueprint-node"
        data-applied={applied ? "true" : "false"}
        data-unit-id={node.unit_id ?? ""}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.22, delay: Math.min(index * 0.03, 0.2) }}
        className="relative pl-6"
      >
        <span
          className={clsx(
            "absolute left-0 top-3 h-2 w-2 rounded-full ring-2 ring-white/70 dark:ring-slate-900/60",
            statusDotClass(node.status),
          )}
        />
        <div
          className={clsx(
            "rounded-2xl border px-3 py-2.5 transition",
            applied
              ? "border-emerald-400/60 bg-emerald-500/10 ring-1 ring-emerald-400/30 dark:border-emerald-300/35 dark:bg-emerald-400/10"
              : bound
                ? "border-indigo-300/50 bg-white/60 hover:border-indigo-400/60 hover:bg-white/80 dark:border-indigo-400/25 dark:bg-white/[0.05] dark:hover:border-indigo-400/40 dark:hover:bg-white/[0.08]"
                : "border-slate-200/70 bg-white/40 dark:border-white/10 dark:bg-white/[0.03]",
          )}
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="min-w-0 flex-1 text-[13px] font-medium leading-snug text-slate-700 dark:text-slate-200">
              {node.title}
            </p>
            <div className="flex items-center gap-1.5">
              {applied ? (
                <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-700 ring-1 ring-emerald-500/25 dark:bg-emerald-400/15 dark:text-emerald-300 dark:ring-emerald-300/25">
                  {t("blueprint.appliedBadge")}
                </span>
              ) : null}
              <StatusBadge status={node.status} />
            </div>
          </div>
          {node.summary ? (
            <p className="mt-1 text-[11.5px] leading-relaxed text-slate-500 dark:text-slate-400">
              {node.summary}
            </p>
          ) : null}
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="chip-muted">
              <Clock3 size={10} />
              {nodeMinutes(t, node)}
            </span>
            {node.objectives.length > 0 ? (
              <span className="chip-muted">
                <ListChecks size={10} />
                {pluralLabel(t, "blueprint.objectives", node.objectives.length)}
              </span>
            ) : null}
            {node.prerequisites.length > 0 ? (
              <span className="chip-muted">
                <Lock size={10} />
                {pluralLabel(t, "blueprint.prerequisites", node.prerequisites.length)}
              </span>
            ) : null}
            {node.unit_id ? (
              <button
                type="button"
                onClick={() => onOpenUnit(node.unit_id as string)}
                className="btn-quiet !px-2 !py-1 text-[10px]"
              >
                <CornerDownRight size={10} />
                {t("blueprint.openReader")}
              </button>
            ) : (
              <span className="text-[10px] text-slate-400 dark:text-slate-500">
                {t("blueprint.notLinked")}
              </span>
            )}
          </div>
        </div>
      </motion.li>
    );
  };

  if (blueprint.learning_path.length === 0 && blueprint.outline.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300/70 px-5 py-8 text-center dark:border-white/15">
        <Waypoints
          size={18}
          className="mx-auto text-slate-400 dark:text-slate-500"
        />
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          {t("blueprint.noPath")}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="relative">
        <span
          aria-hidden
          className="absolute bottom-4 left-[7px] top-4 w-px bg-gradient-to-b from-indigo-400/50 via-violet-400/35 to-transparent dark:from-indigo-400/40 dark:via-violet-400/25"
        />
        <ol className="space-y-4">
          {blueprint.learning_path.map((stage, stageIndex) => {
            const nodes = stageNodes.get(stage.id) ?? [];
            const isCollapsed = Boolean(collapsed[stage.id]);
            return (
              <li key={stage.id || `stage-${stageIndex}`} className="relative">
                <div className="flex items-start gap-3">
                  <span className="brand-gradient relative z-10 mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full text-[9px] font-semibold text-white shadow-brand">
                    {stageIndex + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <button
                      type="button"
                      onClick={() => toggle(stage.id)}
                      className="group flex w-full items-start justify-between gap-3 text-left"
                    >
                      <div className="min-w-0">
                        <p className="text-[13.5px] font-semibold tracking-tight text-slate-800 dark:text-slate-100">
                          {stage.title}
                        </p>
                        {stage.goal ? (
                          <p className="mt-0.5 text-[11.5px] leading-relaxed text-slate-500 dark:text-slate-400">
                            {stage.goal}
                          </p>
                        ) : null}
                        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                          <span className="chip">
                            {pluralLabel(t, "blueprint.nodeCount", nodes.length)}
                          </span>
                          <span className="chip-muted">
                            <Clock3 size={10} />
                            {stage.estimated_minutes > 0
                              ? t("blueprint.minutes", {
                                  count: stage.estimated_minutes,
                                })
                              : t("blueprint.durationTbd")}
                          </span>
                        </div>
                      </div>
                      <ChevronDown
                        size={14}
                        className={clsx(
                          "mt-1 shrink-0 text-slate-400 transition group-hover:text-indigo-500 dark:text-slate-500",
                          isCollapsed && "-rotate-90",
                        )}
                      />
                    </button>

                    <AnimatePresence initial={false}>
                      {!isCollapsed && nodes.length > 0 ? (
                        <motion.ul
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: "auto" }}
                          exit={{ opacity: 0, height: 0 }}
                          transition={{ duration: 0.2 }}
                          className="relative mt-2 space-y-1.5 overflow-hidden pl-2"
                        >
                          {nodes.map(renderNode)}
                        </motion.ul>
                      ) : null}
                    </AnimatePresence>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      </div>

      {orphanNodes.length > 0 ? (
        <div className="rounded-2xl border border-slate-200/70 bg-white/40 p-3 dark:border-white/10 dark:bg-white/[0.03]">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
            {t("blueprint.unassigned")}
          </p>
          <ul className="relative mt-2 space-y-1.5">{orphanNodes.map(renderNode)}</ul>
        </div>
      ) : null}
    </div>
  );
}
