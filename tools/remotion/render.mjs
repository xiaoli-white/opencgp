#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ENTRY_POINT = path.join(HERE, "src", "index.ts");
const COMPOSITION_ID = "OpenCGPStory";

const DEFAULT_CHROME =
  "/vol1/@apphome/astrbot/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";

const DEFAULT_PROPS = {
  title: "Your title goes here",
  points: [],
  images: [],
  brand: "OpenCGP",
  durationInFrames: 300,
  fps: 30,
};


function isLoadableSource(value) {
  return typeof value === "string" && /^(https?:|file:|data:)/i.test(value.trim());
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (next === undefined || next.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = next;
      i += 1;
    }
  }
  return args;
}

function fail(message) {
  process.stderr.write(`[render] ${message}\n`);
  process.exit(1);
}

function parseFrameRange(value) {
  if (typeof value !== "string") return null;
  const match = value.trim().match(/^(\d+)-(\d+)$/);
  if (!match) return null;
  const from = Number(match[1]);
  const to = Number(match[2]);
  if (!Number.isFinite(from) || !Number.isFinite(to) || to < from) return null;
  return [from, to];
}

const MIME_BY_EXT = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".avif": "image/avif",
};

async function toDataUri(reference) {
  let filePath = reference;
  if (reference.startsWith("file://")) {
    filePath = fileURLToPath(reference);
  } else if (!path.isAbsolute(reference)) {
    return reference;
  }
  try {
    await fs.access(filePath);
  } catch {
    return reference;
  }
  const buffer = await fs.readFile(filePath);
  const mime = MIME_BY_EXT[path.extname(filePath).toLowerCase()] ?? "image/png";
  return `data:${mime};base64,${buffer.toString("base64")}`;
}

async function normalizeImages(images) {
  const list = Array.isArray(images) ? images : [];
  const resolved = [];
  for (const item of list) {
    if (typeof item !== "string" || item.trim().length === 0) continue;
    resolved.push(await toDataUri(item.trim()));
  }
  return resolved;
}

async function resolveChrome(explicit) {
  const candidates = [
    explicit,
    process.env.CHROME_PATH,
    process.env.BROWSER_EXECUTABLE,
    DEFAULT_CHROME,
  ].filter((item) => typeof item === "string" && item.length > 0);
  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      return candidate;
    } catch {
      continue;
    }
  }
  fail(
    "No browser executable found. Pass --browser-executable <path> or set CHROME_PATH.",
  );
}

async function loadProps(propsPath) {
  if (!propsPath) return { ...DEFAULT_PROPS };
  let raw;
  try {
    raw = await fs.readFile(propsPath, "utf8");
  } catch (error) {
    fail(`Cannot read props file ${propsPath}: ${error.message}`);
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    fail(`Invalid JSON in ${propsPath}: ${error.message}`);
  }
  return {
    title: typeof parsed.title === "string" ? parsed.title : "",
    points: Array.isArray(parsed.points) ? parsed.points : [],
    images: Array.isArray(parsed.images)
      ? parsed.images.filter(isLoadableSource).slice(0, 6)
      : [],
    brand: typeof parsed.brand === "string" ? parsed.brand : DEFAULT_PROPS.brand,
    durationInFrames: Number.isFinite(Number(parsed.durationInFrames))
      ? Number(parsed.durationInFrames)
      : DEFAULT_PROPS.durationInFrames,
    fps: Number.isFinite(Number(parsed.fps)) ? Number(parsed.fps) : DEFAULT_PROPS.fps,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const outPath = typeof args.out === "string" ? path.resolve(args.out) : null;
  if (!outPath) fail("Missing --out <file.mp4>");

  const browserExecutable = await resolveChrome(
    typeof args["browser-executable"] === "string" ? args["browser-executable"] : undefined,
  );

  const props = await loadProps(typeof args.props === "string" ? path.resolve(args.props) : null);
  props.images = await normalizeImages(props.images);

  const compositionId =
    typeof args.composition === "string" ? args.composition : COMPOSITION_ID;
  const concurrency = Number.isFinite(Number(args.concurrency))
    ? Number(args.concurrency)
    : undefined;
  const timeoutInMilliseconds = Number.isFinite(Number(args.timeout))
    ? Number(args.timeout)
    : 180000;
  const frameRange = parseFrameRange(args.frames);

  await fs.mkdir(path.dirname(outPath), { recursive: true });

  process.stderr.write(`[render] bundling ${ENTRY_POINT}\n`);
  const serveUrl = await bundle({
    entryPoint: ENTRY_POINT,
    onProgress: (percent) => {
      if (percent % 25 === 0) {
        process.stderr.write(`[render] bundle ${percent}%\n`);
      }
    },
  });

  process.stderr.write(`[render] browser: ${browserExecutable}\n`);
  const composition = await selectComposition({
    serveUrl,
    id: compositionId,
    inputProps: props,
    browserExecutable,
    chromiumOptions: { gl: "swangle" },
    timeoutInMilliseconds,
  });

  process.stderr.write(
    `[render] ${composition.width}x${composition.height} @ ${composition.fps}fps, ` +
      `${composition.durationInFrames} frames\n`,
  );

  let lastReported = -1;
  await renderMedia({
    composition: { ...composition, props },
    serveUrl,
    codec: "h264",
    imageFormat: "jpeg",
    jpegQuality: 82,
    outputLocation: outPath,
    inputProps: props,
    browserExecutable,
    chromiumOptions: { gl: "swangle" },
    timeoutInMilliseconds,
    concurrency,
    frameRange: frameRange ?? undefined,
    overwrite: true,
    onProgress: ({ progress }) => {
      const percent = Math.floor(progress * 100);
      if (percent >= lastReported + 20) {
        lastReported = percent;
        process.stderr.write(`[render] encoding ${percent}%\n`);
      }
    },
  });

  const stat = await fs.stat(outPath);
  process.stdout.write(
    JSON.stringify({ output: outPath, bytes: stat.size, durationInFrames: composition.durationInFrames }) +
      "\n",
  );
}

main().catch((error) => {
  fail(error && error.stack ? error.stack : String(error));
});
