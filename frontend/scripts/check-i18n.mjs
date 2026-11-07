#!/usr/bin/env node
/**
 * i18n guard.
 *
 * Fails when a `t("...")` call in the frontend references a key that neither the
 * nested dictionary nor the flat additions map provides — those keys would render
 * as raw text in the UI. Also reports keys that exist in one language only.
 *
 * Usage: npm run check:i18n
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const SRC = join(ROOT, "src");
const COMPONENTS = join(ROOT, "components");
const DICT = join(SRC, "i18n", "dict.ts");
const ADDITIONS = join(SRC, "i18n", "dict-additions.ts");

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name.startsWith(".")) continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.(ts|tsx)$/.test(name)) out.push(full);
  }
  return out;
}

/** Strip string literals so braces inside translations do not confuse the scanner. */
const codeOnly = (line) => line.replace(/"(?:[^"\\]|\\.)*"/g, '""');

function parseNested(text, marker) {
  const lines = text.split("\n");
  const start = lines.findIndex((l) => new RegExp(marker).test(l));
  if (start < 0) return new Set();
  let depth = 1;
  let end = lines.length - 1;
  for (let i = start + 1; i < lines.length; i += 1) {
    const c = codeOnly(lines[i]);
    depth += (c.match(/\{/g) || []).length - (c.match(/\}/g) || []).length;
    if (depth === 0) {
      end = i;
      break;
    }
  }
  const keys = new Set();
  const stack = [];
  for (let i = start + 1; i < end; i += 1) {
    const line = lines[i];
    const indent = line.length - line.trimStart().length;
    const code = codeOnly(line).trim();
    const open = /^([A-Za-z0-9_]+):\s*\{$/.exec(code);
    const leaf = /^([A-Za-z0-9_]+):\s*"/.exec(code);
    const close = /^\},?$/.exec(code);
    if (open) {
      while (stack.length && stack[stack.length - 1][0] >= indent) stack.pop();
      stack.push([indent, open[1]]);
    } else if (leaf) {
      while (stack.length && stack[stack.length - 1][0] >= indent) stack.pop();
      keys.add([...stack.map(([, n]) => n), leaf[1]].join("."));
    } else if (close) {
      while (stack.length && stack[stack.length - 1][0] >= indent) stack.pop();
    }
  }
  return keys;
}

function parseFlat(text) {
  const keys = new Set();
  for (const m of text.matchAll(/"([A-Za-z0-9_.]+)":\s*"/g)) keys.add(m[1]);
  return keys;
}

const dictText = readFileSync(DICT, "utf8");
const additionsText = readFileSync(ADDITIONS, "utf8");
const zh = new Set([...parseNested(dictText, "^export const zh = \\{"), ...parseFlat(additionsText.split("enAdditions")[0])]);
const en = new Set([...parseNested(dictText, "^export const en: Dict = \\{"), ...parseFlat(additionsText.split("enAdditions")[1] ?? "")]);

const used = new Map();
for (const file of [...walk(SRC), ...walk(COMPONENTS)]) {
  if (file === DICT || file === ADDITIONS) continue;
  const text = readFileSync(file, "utf8");
  for (const m of text.matchAll(/\bt\(\s*"([A-Za-z0-9_.]+)"/g)) {
    if (!used.has(m[1])) used.set(m[1], relative(ROOT, file));
  }
}

const missingZh = [...used.keys()].filter((k) => !zh.has(k)).sort();
const missingEn = [...used.keys()].filter((k) => !en.has(k)).sort();

console.log(`keys used: ${used.size} | zh: ${zh.size} | en: ${en.size}`);

let failed = false;
for (const [label, list] of [
  ["missing in zh", missingZh],
  ["missing in en", missingEn],
]) {
  if (list.length === 0) {
    console.log(`\u2713 ${label}: 0`);
    continue;
  }
  failed = true;
  console.error(`\u2717 ${label}: ${list.length}`);
  for (const key of list) console.error(`    ${key}  (${used.get(key)})`);
}
process.exit(failed ? 1 : 0);
