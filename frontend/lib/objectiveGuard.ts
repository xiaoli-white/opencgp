import type { Unit } from "./api";

const GAP_MARKERS = [
  "insufficient material",
  "no evidence",
  "not covered by evidence",
  "not supported by evidence",
  "cannot be determined from the evidence",
  "cannot be written from evidence",
  "无法覆盖",
  "未被证据覆盖",
  "证据未覆盖",
  "证据不足",
  "没有证据",
  "无证据",
  "材料不足",
  "缺乏证据",
  "无法确定",
];

const TEMPLATE_MARKERS = [
  "<title>",
  "<chapter title>",
  "<stage title>",
  "<stage goal>",
  "<node title>",
  "<unit title>",
  "讲 title",
  "章 title",
  "节 title",
  "chapter title",
  "stage title",
  "stage goal",
  "node title",
  "unit title",
  "learning objective",
];

const CJK = /[\u3400-\u9fff]/;
const MAX_OBJECTIVE_CHARS = 180;
const MAX_GAP_CHARS = 220;

function normalized(value: unknown): string {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function clip(value: string, limit: number): string {
  return value.length <= limit ? value : `${value.slice(0, limit - 1).trimEnd()}…`;
}

export function hasGapMarker(value: unknown): boolean {
  const lowered = normalized(value).toLowerCase();
  return Boolean(lowered) && GAP_MARKERS.some((marker) => lowered.includes(marker));
}

function isTemplateValue(value: unknown): boolean {
  const lowered = normalized(value).toLowerCase();
  return !lowered || TEMPLATE_MARKERS.some((marker) => lowered.includes(marker));
}

function cleanLabel(value: unknown, fallback: string): string {
  const text = normalized(value).replace(/^[\s:：;；,，.。、|/\\\-—–_·•<>[\]{}"'“”‘’]+|[\s:：;；,，.。、|/\\\-—–_·•<>[\]{}"'“”‘’]+$/g, "");
  return !text || hasGapMarker(text) || isTemplateValue(text) ? fallback : clip(text, 80);
}

function styleFor(seriesTitle: string, nodeTitle: string, language: string): "zh" | "en" {
  if ((language || "").toLowerCase().startsWith("zh")) return "zh";
  return CJK.test(seriesTitle) || CJK.test(nodeTitle) ? "zh" : "en";
}

export function deriveObjectives({
  seriesTitle,
  nodeTitle,
  stageTitle = "",
  nodePosition = 1,
  language = "",
}: {
  seriesTitle: string;
  nodeTitle: string;
  stageTitle?: string;
  nodePosition?: number;
  language?: string;
}): string[] {
  const style = styleFor(seriesTitle, nodeTitle, language);
  const position = Math.max(1, Math.trunc(nodePosition || 1));
  const fallbackNode = style === "zh" ? `第 ${position} 讲` : `lesson ${position}`;
  const fallbackStage = style === "zh" ? "本阶段" : "this stage";
  const topic = cleanLabel(seriesTitle, style === "zh" ? "本课程" : "this course");
  const label = cleanLabel(nodeTitle, fallbackNode);
  const stageLabel = cleanLabel(stageTitle, fallbackStage);
  if (style === "zh") {
    return [
      clip(`能够说明「${label}」在「${topic}」的${stageLabel}中要解决的问题，并判断其适用边界。`, MAX_OBJECTIVE_CHARS),
      clip(`能够用自己的话解释「${label}」的核心概念，并给出一个具体应用例子。`, MAX_OBJECTIVE_CHARS),
      clip(`能够依据${stageLabel}的阶段目标完成「${label}」的自测，并记录尚未弄清的问题。`, MAX_OBJECTIVE_CHARS),
    ];
  }
  return [
    clip(`Can explain the problem "${label}" addresses in the ${stageLabel} stage of "${topic}" and judge where it applies.`, MAX_OBJECTIVE_CHARS),
    clip(`Can describe the core concepts of "${label}" in one's own words and give a concrete example.`, MAX_OBJECTIVE_CHARS),
    clip(`Can complete the self-check for "${label}" against the stage goal and record open questions.`, MAX_OBJECTIVE_CHARS),
  ];
}

function appendUnique(
  values: string[],
  seen: Set<string>,
  candidate: string,
  reserved?: Set<string>,
): boolean {
  const text = clip(candidate, MAX_OBJECTIVE_CHARS);
  const key = text.toLowerCase();
  if (!text || seen.has(key) || reserved?.has(key)) return false;
  seen.add(key);
  values.push(text);
  return true;
}

function withPosition(value: string, position: number, style: "zh" | "en"): string {
  const suffix = style === "zh" ? `（第 ${position} 讲）` : ` (unit ${position})`;
  if (value.endsWith("。")) return clip(`${value.slice(0, -1)}${suffix}。`, MAX_OBJECTIVE_CHARS);
  if (value.endsWith(".")) return clip(`${value.slice(0, -1)}${suffix}.`, MAX_OBJECTIVE_CHARS);
  return clip(`${value}${suffix}`, MAX_OBJECTIVE_CHARS);
}

export function extractContentGaps(content: string, limit = 5): string[] {
  const found: string[] = [];
  const seen = new Set<string>();
  for (const line of String(content || "").split(/\r?\n/)) {
    const strippedLine = line.trim().replace(/^[-*+>#\s]+/, "").trim();
    if (!strippedLine) continue;
    for (const rawSentence of strippedLine.split(/[。\n；;]/)) {
      const snippet = rawSentence.trim().replace(/^[\s\-—:：]+/, "");
      if (!snippet) continue;
      const lowered = snippet.toLowerCase();
      const startsWithMarker = GAP_MARKERS.some((marker) => lowered.startsWith(marker));
      const startsWithGapLabel = ["证据缺口", "无法覆盖", "证据不足"].some((marker) => snippet.startsWith(marker));
      if (!startsWithMarker && !startsWithGapLabel) continue;
      if (["证据缺口", "无法覆盖", "证据不足"].includes(snippet)) continue;
      if (lowered.includes("<gap description>") || snippet.includes("<缺口描述>")) continue;
      let description = snippet;
      for (const marker of GAP_MARKERS) {
        if (description.toLowerCase().startsWith(marker)) {
          description = description.slice(marker.length).replace(/^[\s:：\-—]+/, "");
          break;
        }
      }
      if (!description) continue;
      const clipped = clip(description, MAX_GAP_CHARS);
      const key = clipped.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      found.push(clipped);
      if (found.length >= limit) return found;
    }
  }
  return found;
}

function derivePrerequisite(seriesTitle: string, language: string): string[] {
  const style = styleFor(seriesTitle, seriesTitle, language);
  const topic = cleanLabel(seriesTitle, style === "zh" ? "本课程" : "this course");
  return [style === "zh" ? `已掌握「${topic}」的基础概念和学习前提` : `Basic concepts and prerequisites of "${topic}"`];
}

export function guardUnits(units: Unit[], seriesTitle: string): Unit[] {
  const reserved = new Set<string>();
  return units.map((unit) => {
    const language = "";
    const rawObjectives = Array.isArray(unit.learning_objectives) ? unit.learning_objectives : [];
    const force = rawObjectives.some((objective) => hasGapMarker(objective));
    const values: string[] = [];
    const seen = new Set<string>();
    if (!force) {
      for (const item of rawObjectives) {
        const text = normalized(item);
        if (!text || hasGapMarker(text)) continue;
        const key = text.toLowerCase();
        if (seen.has(key) || reserved.has(key)) continue;
        seen.add(key);
        values.push(clip(text, MAX_OBJECTIVE_CHARS));
        if (values.length >= 3) break;
      }
    }
    const derived = deriveObjectives({
      seriesTitle,
      nodeTitle: unit.title,
      nodePosition: unit.order_index,
      language,
    });
    for (const candidate of derived) {
      if (values.length >= 2) break;
      if (reserved.has(candidate.toLowerCase())) continue;
      appendUnique(values, seen, candidate, reserved);
    }
    for (const candidate of derived) {
      if (values.length >= 2) break;
      appendUnique(
        values,
        seen,
        withPosition(candidate, unit.order_index, styleFor(seriesTitle, unit.title, language)),
        reserved,
      );
    }
    values.forEach((value) => reserved.add(value.toLowerCase()));

    const rawPrerequisites = Array.isArray(unit.prerequisites) ? unit.prerequisites : [];
    const prerequisiteSentinel = rawPrerequisites.some((item) => hasGapMarker(item));
    const prerequisites = rawPrerequisites
      .map((item) => normalized(item))
      .filter((item) => item && !hasGapMarker(item))
      .filter((item, index, list) => list.findIndex((candidate) => candidate.toLowerCase() === item.toLowerCase()) === index);
    const finalPrerequisites = prerequisiteSentinel && prerequisites.length === 0
      ? derivePrerequisite(seriesTitle, language)
      : prerequisites;

    const backendGaps = Array.isArray(unit.evidence_gaps) ? unit.evidence_gaps : [];
    return {
      ...unit,
      learning_objectives: values,
      prerequisites: finalPrerequisites,
      evidence_gaps: backendGaps.length > 0 ? backendGaps : extractContentGaps(unit.content),
    };
  });
}
