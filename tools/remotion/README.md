# OpenCGP Remotion video template

A small, dependency-light Remotion project that renders the OpenCGP promo/explanatory
clip (1280x720, dark theme, ~10 s at 30 fps) from a JSON payload.

The backend calls it through the CLI entry point:

```bash
node tools/remotion/render.mjs --out /tmp/x.mp4 --props /tmp/props.json
```

## Requirements

| Item | Version / path |
| --- | --- |
| Node.js | 22.x (this machine: `/vol1/@apphome/astrbot/node/bin`, not on the default `PATH`) |
| remotion | `4.0.541` |
| @remotion/cli | `4.0.541` |
| @remotion/bundler | `4.0.541` |
| @remotion/renderer | `4.0.541` |
| React / React DOM | `18.3.1` |
| Chrome / Chromium | must already exist locally, see below |
| FFmpeg | system `ffmpeg` (Remotion picks it up from `PATH`) |

Because Node is not on the default `PATH`:

```bash
export PATH=/vol1/@apphome/astrbot/node/bin:$PATH
```

## Install

```bash
cd tools/remotion
npm install
```

## Render

From the repository root:

```bash
export PATH=/vol1/@apphome/astrbot/node/bin:$PATH

node tools/remotion/render.mjs \
  --out /tmp/x.mp4 \
  --props /tmp/props.json
```

The script prints a single JSON line on stdout when it succeeds:

```json
{"output":"/tmp/x.mp4","bytes":1234567,"durationInFrames":300}
```

Progress and diagnostics go to stderr, so stdout stays machine readable.

### Flags

| Flag | Default | Description |
| --- | --- | --- |
| `--out` | required | Output mp4 path. Parent directories are created. |
| `--props` | built-in defaults | Path to the JSON props file. |
| `--browser-executable` | `CHROME_PATH`, then a bundled Playwright Chromium path | Chrome/Chromium binary used for rendering. |
| `--composition` | `OpenCGPStory` | Remotion composition id. |
| `--frames` | full composition | Render a sub-range only, e.g. `--frames 0-89`. Handy for smoke tests. |
| `--concurrency` | Remotion default | Number of parallel frame renderers. |

### Browser executable resolution

The sandbox cannot download Chrome, so the renderer never tries to. It resolves the
browser in this order:

1. `--browser-executable <path>`
2. `CHROME_PATH` environment variable
3. `BROWSER_EXECUTABLE` environment variable
4. `/vol1/@apphome/astrbot/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`

If none of them exists the process exits with a descriptive error.

## Props format

```json
{
  "title": "Why Illustrated Notes Stick",
  "points": ["First point", "Second point"],
  "images": ["https://example.com/a.png", "https://example.com/b.jpg"],
  "brand": "OpenCGP",
  "durationInFrames": 300,
  "fps": 30
}
```

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `title` | string | `""` | Headline. Fades in and lifts up at the start. |
| `points` | string[] | `[]` | Bullet points, revealed one by one. Capped at 6 items. |
| `images` | string[] | `[]` | Optional. `http(s)` URLs, `file://` URLs, or absolute local paths. Capped at 6. When empty the layout goes full-width text only. |
| `brand` | string | `"OpenCGP"` | Shown at the end of the clip. |
| `durationInFrames` | number | `300` | Clamped to `60..1800`. |
| `fps` | number | `30` | Clamped to `15..60`. |

Local images are inlined as `data:` URIs before rendering, so `file:///tmp/pic.png` and
`/tmp/pic.png` both work even though the Remotion bundle is served over `http://localhost`.
Remote images must be publicly reachable from the rendering machine.

## What the clip looks like

- 1280x720, dark gradient background, accent blue.
- Title fades in while sliding up (~frame 4-34).
- Points appear one by one, staggered, each with a numbered badge.
- Images (if any) crossfade on the right with a slow Ken Burns zoom and pan.
- `brand` fades in near the end, with a thin progress bar along the bottom edge.

## Local development

```bash
cd tools/remotion
export PATH=/vol1/@apphome/astrbot/node/bin:$PATH
npx remotion studio src/index.ts --browser-executable /vol1/@apphome/astrbot/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
```

Type checking:

```bash
cd tools/remotion
npx tsc --noEmit
```

## Performance notes

The bundled Chrome runs with software GL (`swangle`) because the host has no GPU.
On a 2-core Celeron a full 300-frame 720p render takes roughly 7-10 minutes; use
`--frames 0-29` for a quick smoke test. Frame rendering is CPU bound, so a faster
host scales almost linearly.
