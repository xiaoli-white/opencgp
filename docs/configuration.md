# Configuration

Every setting is read from the environment, optionally seeded by a `.env` file.
All keys use the `OPENCGP_` prefix; the historical `COURSE_STUDIO_` prefix is still
accepted as a fallback for older deployments.

Reference implementation: `backend/app/config.py`. The shipped template is
`backend/.env.example` and it is kept in sync with the code — if a key is not in
that file, the code does not read it.

## How values are resolved

1. Real environment variables win.
2. `OPENCGP_<KEY>` is checked first, then `COURSE_STUDIO_<KEY>`.
3. `.env` files are loaded without overriding anything already set. Lookup order:
   current directory → `backend/` → project root.
4. Anything still unset falls back to the default listed below.

Empty strings are treated as "unset" for most numeric and boolean keys, so you can
leave a line in `.env` without a value while you decide.

## Where to put the file

| Scenario | File | Used by |
|---|---|---|
| Local development | `backend/.env` | `uvicorn app.main:app` |
| Docker Compose | `backend/.env` (backend) + `.env` at repo root (ports, build args) | `docker compose` |
| Kubernetes | chart values, rendered into a ConfigMap and a Secret | Helm release |

## Application

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_APP_NAME` | `OpenCGP` | string | Shown in `/health` and the UI title |
| `OPENCGP_ENV` | `development` | `development` \| `production` | Environment label only; no behaviour switch |

## Auth and sessions

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_AUTH_MODE` | `disabled` | `disabled` \| `required` | `disabled` runs every request as a local owner (single-user box); `required` enables login and per-tenant roles |
| `OPENCGP_AUTH_SECRET` | *(empty)* | long random string | Token signing key. Required in production: `openssl rand -base64 32` |
| `OPENCGP_AUTH_TOKEN_TTL_HOURS` | `168` | int | Session lifetime in hours |
| `OPENCGP_REQUIRE_APPROVAL` | `true` | bool | New signups wait for an admin approval |
| `OPENCGP_LOCK_TTL_SECONDS` | `120` | int | How long a unit edit lock survives without a heartbeat |

## Database

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_DATABASE_BACKEND` | `sqlite` | `sqlite` \| `postgres` | Storage engine for all relational data |
| `OPENCGP_DATABASE_PATH` | `data/opencgp.db` | path | Used by `sqlite` |
| `OPENCGP_DATABASE_DSN` | *(empty)* | DSN | Used by `postgres`, e.g. `postgresql://user:pass@host:5432/opencgp` |
| `OPENCGP_DATABASE_POOL_SIZE` | `8` | int | Connection pool for `postgres` |

## Vector store and hybrid retrieval

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_VECTORSTORE_BACKEND` | `simple` | `simple` \| `postgres` \| `pgvector` | `simple` is SQLite FTS5 based; the Postgres options use `pg_trgm` |
| `OPENCGP_VECTORSTORE_PATH` | `data/vectorstore` | path | Used by `simple` |
| `OPENCGP_VECTORSTORE_DSN` | *(empty)* | DSN | Falls back to `DATABASE_DSN` when empty |
| `OPENCGP_VECTORSTORE_POOL_SIZE` | `8` | int | Pool size for the Postgres vector store |
| `OPENCGP_SEARCH_MIN_SCORE` | `0.15` | 0–1 | Keyword score a chunk must reach to count as a hit |
| `OPENCGP_HYBRID_FUSION` | `rrf` | `rrf` \| anything else | `rrf` is rank fusion (recommended); any other value uses weighted score blending |
| `OPENCGP_HYBRID_VECTOR_WEIGHT` | `0.55` | 0–1 | Vector weight, only used by weighted blending |
| `OPENCGP_HYBRID_RRF_K` | `60` | int | RRF constant |
| `OPENCGP_HYBRID_MAX_PER_SOURCE` | `3` | int | Max chunks kept per source after fusion |
| `OPENCGP_HYBRID_MAX_VECTOR_ROWS` | `200000` | int | Upper bound of vector rows scanned per query |
| `OPENCGP_HYBRID_LSH_BITS` | `12` | int | LSH bucket bits for the simple store (12 bits = 4096 buckets) |

## Ingestion

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_INGEST_CHUNK_SIZE` | `800` | int | Characters per chunk |
| `OPENCGP_INGEST_CHUNK_OVERLAP` | `120` | int | Overlap between consecutive chunks |
| `OPENCGP_INGEST_MAX_FILE_MB` | `20` | int | Upload size limit |
| `OPENCGP_PARSER_BACKEND` | `builtin` | `builtin` | Document parser implementation |

## Embedding (optional, off by default)

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_EMBEDDING_BACKEND` | `none` | `none` \| `openai` \| `openai_compat` \| `hash` | `hash` is for offline testing only |
| `OPENCGP_EMBEDDING_BASE_URL` | *(empty)* | URL | OpenAI-compatible endpoint |
| `OPENCGP_EMBEDDING_API_KEY` | *(empty)* | string | Provider key |
| `OPENCGP_EMBEDDING_MODEL` | `text-embedding-3-small` | string | Model id |
| `OPENCGP_EMBEDDING_DIM` | *(empty)* | int | Expected dimension, used to validate provider output |
| `OPENCGP_EMBEDDING_DIMENSION` | `1024` | int | Alias used only when `EMBEDDING_DIM` is empty |
| `OPENCGP_EMBEDDING_BATCH` | `32` | int | Texts per request |
| `OPENCGP_EMBEDDING_TIMEOUT` | `20` | seconds | Per-request timeout |
| `OPENCGP_EMBEDDING_QUERY_PREFIX` | *(empty)* | string | Prepended to queries only, e.g. `query: ` |

## Rerank (optional, off by default)

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_RERANK_BACKEND` | `none` | `none` \| `dashscope` \| `qwen` \| `llm` \| `http` \| `cohere` \| `jina` \| `siliconflow` \| `zhipu` \| `tei` \| `generic` | Provider dialect |
| `OPENCGP_RERANK_API_KEY` | *(empty)* | string | Provider key |
| `OPENCGP_RERANK_BASE_URL` | *(empty)* | URL | Required for `generic` / `tei` / `http` |
| `OPENCGP_RERANK_MODEL` | *(empty)* | string | Required for `generic` / `tei` / `http` |
| `OPENCGP_RERANK_TOP_N` | `12` | int | Candidates sent to the reranker for scoring; `0` = score every candidate |
| `OPENCGP_RERANK_WEIGHT` | `0.5` | 0–1 | Final blend weight of the rerank score |
| `OPENCGP_RERANK_TIMEOUT` | `20` | seconds | Per-request timeout |
| `OPENCGP_RERANK_RETRIES` | `2` | int | Retries on transient failures |
| `OPENCGP_RERANK_BATCH` | `100` | int | Documents per request |
| `OPENCGP_RERANK_CHARS` | `2000` | int | Characters of each candidate sent to the provider |
| `OPENCGP_RERANK_NORMALIZE` | `auto` | `auto` \| `sigmoid` \| `minmax` \| `none` | Score normalisation |
| `OPENCGP_RERANK_RAW_SCORES` | `false` | bool | Keep provider scores next to normalised ones |

## Generation and illustrations

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_GENERATION_TOP_K` | `8` | int | Evidence chunks retrieved per unit |
| `OPENCGP_GENERATION_EVIDENCE_CHAR_LIMIT` | `600` | int | Characters of each evidence snippet |
| `OPENCGP_GENERATION_MAX_EVIDENCE` | `8` | int | Evidence items kept after diversifying |
| `OPENCGP_GENERATION_DEFAULT_MODE` | `strict` | `strict` \| `loose` | `strict` requires citations for every paragraph |
| `OPENCGP_ASSETS_AUTO_IMAGES` | `true` | bool | Let the model place `[[image: ...]]` markers that get turned into real images |
| `OPENCGP_ASSETS_MAX_IMAGES` | `3` | 0–6 | Upper bound per generation; `0` disables illustrations |
| `OPENCGP_BLUEPRINT_TOP_K` | `6` | int | Evidence chunks used when drafting an outline |
| `OPENCGP_BLUEPRINT_DEFAULT_MODE` | *(empty)* | `strict` \| `loose` | Empty means "follow `GENERATION_DEFAULT_MODE`" |

A creation profile can override the illustration settings per work with
`spec.assets = {auto_images, max_images, style}`; the profile wins over these
environment defaults.

## Conversation context

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_CONVERSATION_HISTORY_LIMIT` | `20` | int | Messages kept in the follow-up window |
| `OPENCGP_CONVERSATION_HISTORY_CHAR_LIMIT` | `400` | int | Characters per history message |
| `OPENCGP_CONVERSATION_CONTENT_CHAR_LIMIT` | `6000` | int | Characters of the article sent as context |
| `OPENCGP_CONVERSATION_EVIDENCE_CHAR_LIMIT` | `600` | int | Characters of each evidence snippet |

## LLM

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_LLM_BACKEND` | `openai_compat` | `openai_compat` \| `dummy` | `dummy` returns canned text and needs no key |
| `OPENCGP_LLM_BASE_URL` | *(empty)* | URL | e.g. `https://api.deepseek.com/v1` |
| `OPENCGP_LLM_MODEL` | *(empty)* | string | e.g. `deepseek-chat` |
| `OPENCGP_LLM_API_KEY` | *(empty)* | string | Provider key |

Per-user and per-tenant channels configured in the UI take precedence over these defaults.

## Web search (optional)

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_WEBSEARCH_BACKEND` | `none` | `none` \| `deepseek` \| `generic` | Search provider |
| `OPENCGP_WEBSEARCH_URL` | *(empty)* | URL | Provider endpoint |
| `OPENCGP_WEBSEARCH_API_KEY` | *(empty)* | string | Provider key |
| `OPENCGP_WEBSEARCH_RESULT_PATH` | `results` | string | JSON path of the result array (`generic` only) |
| `OPENCGP_WEBSEARCH_METHOD` | `POST` | `POST` \| `GET` | HTTP method (`generic` only) |
| `OPENCGP_WEBSEARCH_TIMEOUT` | `10` | seconds | Search timeout |
| `OPENCGP_WEBSEARCH_FETCH_ENABLED` | `true` | bool | Fetch full page text instead of relying on snippets |
| `OPENCGP_WEBSEARCH_FETCH_TOP` | `2` | int | How many hits to fetch |
| `OPENCGP_WEBSEARCH_FETCH_CHARS` | `4000` | int | Characters kept per fetched page |
| `OPENCGP_WEBSEARCH_FETCH_TIMEOUT` | `8` | seconds | Per-page fetch timeout |

## Queue and jobs

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_QUEUE_BACKEND` | `local` | `local` \| `redis` | `redis` is required for more than one instance |
| `OPENCGP_REDIS_URL` | *(empty)* | URL | e.g. `redis://127.0.0.1:6379/0` |
| `OPENCGP_JOB_CONCURRENCY` | `2` | int | Workers per instance; `0` means API only (no consumption) |
| `OPENCGP_JOB_MAX_ATTEMPTS` | `3` | int | Retries per job |
| `OPENCGP_JOB_SSE_INTERVAL` | `0.6` | seconds | Progress event interval |
| `OPENCGP_JOB_SSE_MAX_SECONDS` | `600` | seconds | How long one SSE stream may stay open |
| `OPENCGP_JOB_SSE_PING_SECONDS` | `15` | seconds | Keep-alive ping interval |
| `OPENCGP_JOB_BRPOP_TIMEOUT` | `2` | seconds | Redis blocking pop timeout |

## Object storage

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_STORAGE_BACKEND` | `local` | `local` \| `s3` \| `rustfs` | Where uploads and generated media live |
| `OPENCGP_STORAGE_ROOT` | `data/storage` | path | Used by `local` |
| `OPENCGP_S3_ENDPOINT` | *(empty)* | URL | Used by `s3` / `rustfs` |
| `OPENCGP_S3_BUCKET` | *(empty)* | string | Bucket name |
| `OPENCGP_S3_REGION` | `us-east-1` | string | Region |
| `OPENCGP_S3_ACCESS_KEY` | *(empty)* | string | Access key |
| `OPENCGP_S3_SECRET_KEY` | *(empty)* | string | Secret key |
| `OPENCGP_S3_PREFIX` | *(empty)* | string | Key prefix, e.g. `tenants` |
| `OPENCGP_S3_TIMEOUT` | `10` | seconds | Request timeout |

## Export (Markdown / HTML / EPUB / PDF)

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_EXPORTER_BACKEND` | `builtin` | `builtin` | Exporter implementation |
| `OPENCGP_EXPORTER_FONT_REGULAR` | *(empty)* | path | TTF/TTC used by the PDF renderer; empty means auto-detect (WenQuanYi / Noto CJK / system fonts) |
| `OPENCGP_EXPORTER_FONT_BOLD` | *(empty)* | path | Bold face for the PDF renderer |
| `OPENCGP_EXPORTER_PDF_MARGIN_MM` | `18` | int | Page margin |

PDF export needs WeasyPrint plus Pango/Cairo at runtime. The bundled Docker image
installs them together with a CJK font, so Chinese text exports correctly out of the box.

## Image generation (optional)

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_IMAGE_BACKEND` | `none` | `none` \| `openai_images` | Image provider dialect |
| `OPENCGP_IMAGE_BASE_URL` | `https://api.openai.com/v1` | URL | Provider endpoint |
| `OPENCGP_IMAGE_MODEL` | `gpt-image-1` | string | Model id, e.g. `qwen-image-3.0` |
| `OPENCGP_IMAGE_API_KEY` | *(empty)* | string | Provider key |
| `OPENCGP_IMAGE_MAX_BYTES` | `8388608` | int | Reject larger images |
| `OPENCGP_IMAGE_TIMEOUT` | `60` | seconds | Per-image timeout; raise it for slow models |

Providers that ignore `response_format=b64_json` and return a URL are handled by
downloading the image server-side.

## Video rendering (optional)

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_VIDEO_BACKEND` | `none` | `none` \| `remotion` | `remotion` shells out to the Node template in `tools/remotion` |
| `OPENCGP_VIDEO_NODE_BIN` | `node` | path | Node binary |
| `OPENCGP_VIDEO_PROJECT` | `tools/remotion` | path | Template project |
| `OPENCGP_VIDEO_TIMEOUT` | `300` | seconds | Render timeout; software rendering of 300 frames takes several minutes |
| `OPENCGP_VIDEO_DURATION_FRAMES` | `300` | int | Frames per video (30 fps by default) |
| `OPENCGP_VIDEO_PUBLIC_BASE_URL` | *(empty)* | URL | Base URL the renderer uses to fetch media; empty means the renderer reads the bytes directly and inlines them |

## Code sandbox

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_EXECUTOR_BACKEND` | `docker` | `docker` \| `local` \| `none` | Where `code-check` runs |
| `OPENCGP_EXEC_TIMEOUT` | `10` | seconds | Wall clock limit |
| `OPENCGP_EXEC_MAX_BYTES` | `65536` | bytes | Captured output limit |
| `OPENCGP_EXEC_IMAGES` | *(empty)* | comma separated | Images the docker executor may use |

## Notifications

| Key | Default | Values | Meaning |
|---|---|---|---|
| `OPENCGP_NOTIFY_BACKEND` | `none` | `none` \| `smtp` | Email transport |
| `OPENCGP_SMTP_HOST` | *(empty)* | host | SMTP host |
| `OPENCGP_SMTP_PORT` | `587` | int | SMTP port |
| `OPENCGP_SMTP_USER` | *(empty)* | string | SMTP user |
| `OPENCGP_SMTP_PASSWORD` | *(empty)* | string | SMTP password |
| `OPENCGP_SMTP_FROM` | *(empty)* | address | From header |
| `OPENCGP_SMTP_TLS` | `true` | bool | `STARTTLS`; implicit SSL/SMTPS is not supported |
| `OPENCGP_SMTP_TIMEOUT` | `10` | seconds | Per-send timeout |
| `OPENCGP_NOTIFY_ADMIN_EMAIL` | *(empty)* | addresses | Fallback recipients for admin notices |

## Docker and Helm differences

`docker compose` sets `OPENCGP_DATABASE_BACKEND=sqlite`,
`OPENCGP_QUEUE_BACKEND=local` and `OPENCGP_STORAGE_BACKEND=local` by default so a
fresh checkout works without external services. Override them at the repo root:

```bash
OPENCGP_QUEUE_BACKEND=redis docker compose up -d
```

The Helm chart renders non-secret keys into a ConfigMap, keeps keys and passwords in
a Secret, and exposes the rest through the chart's `tuning` map, so anything listed
above can be set with `--set tuning.EMBEDDING_BASE_URL=...`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/health` reports `degraded` | An optional adapter is unreachable (S3, Redis, LLM) | Check the `error` field of that adapter |
| `attempt to write a readonly database` in Docker | The bind mount is not writable by uid `10001` | Make `backend/data` owned by `10001:10001` |
| Generated text ignores your profile | The profile was edited but the work still points at the old one | Rebind the profile on the series/piece |
| Embedding provider returns a different dimension | Model changed | Set `EMBEDDING_DIM` or run the backfill endpoint again |
| PDF export returns 503 | WeasyPrint or Pango/Cairo missing | Use the bundled image, or install the system packages |
