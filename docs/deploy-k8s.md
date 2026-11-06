# Deploying OpenCGP on Kubernetes

This guide covers the Helm chart in `deploy/helm/opencgp` (`version 0.1.0` / `appVersion 0.1.0`).

The chart supports two deployment modes, controlled by `mode`:

| Mode | Rendered workloads | Dependencies | Typical use |
|---|---|---|---|
| `single` | `*-backend` (API+Worker combined) + `*-postgres` + `*-redis` + `*-rustfs` + `*-frontend` | Bundled in the chart, all single-replica | Demos, single machine, small internal deployments |
| `ha` | `*-api` (HTTP only, `JOB_CONCURRENCY=0`) + `*-worker` (task consumption only) + `*-frontend` | Requires external PostgreSQL / Redis / S3 | Production, multiple replicas, horizontal scaling |

Workloads created by the chart:

| Component | Resources | Notes |
|---|---|---|
| API | Deployment + Service (HA only) | FastAPI on port 8000, `/health` probe, `/metrics` exposes Prometheus metrics, `JOB_CONCURRENCY=0` |
| Worker | Deployment (HA only, no Service) | Same image, `JOB_CONCURRENCY={{ worker.jobConcurrency }}`, consumes the queue only, liveness via `/health`, receives no traffic |
| Backend (single mode) | Deployment + Service + PVC | API+Worker combined, `JOB_CONCURRENCY>0` |
| Frontend | Deployment + Service + ConfigMap | nginx serves the static site and reverse-proxies same-origin `/api` to the API/Backend Service |
| PostgreSQL | StatefulSet + Service (single mode only) | Bundled `postgres:16-alpine`, `PGDATA=/var/lib/postgresql/data/pgdata` |
| Redis | StatefulSet + headless Service (single mode only) | Task queue and SSE event bus, `--appendonly yes` |
| rustfs | StatefulSet + headless Service (single mode only) | S3-compatible object storage, ports 9000 / 9001 |

> **Note**: the bundled PostgreSQL / Redis / rustfs are only rendered when `mode=single`. With `mode=ha` these bundled workloads are not created even if `postgres.enabled` / `redis.enabled` / `rustfs.enabled` remain `true`.

---

## 1. Prerequisites

- Kubernetes 1.24+（`autoscaling/v2`、`policy/v1`、`networking.k8s.io/v1` Ingress）
- Helm 3.12+ (this chart uses `lookup` to preserve generated secrets; verified with 3.16.3)
- A default StorageClass in the cluster, or one set explicitly via `backend.persistence.storageClass` / `postgres.storageClass` / `redis.persistence.storageClass` / `rustfs.persistence.storageClass`
- `opencgp/backend` and `opencgp/frontend` images built and pushed (see section 3)
- HA mode additionally requires: external PostgreSQL (15/16 recommended), external Redis (6+/7), and S3-compatible object storage
- (Optional) an Ingress Controller, Prometheus (annotation-based scraping or the Operator), and Grafana

Verify Helm and the chart:

```bash
helm version
helm lint deploy/helm/opencgp
helm template opencgp deploy/helm/opencgp > /tmp/render.yaml
```

---

## 2. Differences between the two modes

| Item | `mode=single` | `mode=ha` |
|---|---|---|
| Bundled PostgreSQL | Rendered, 1 replica, PVC sized by `postgres.storage` | Not rendered; `externalDatabase.dsn` is required |
| Bundled Redis / rustfs | Rendered | Not rendered; `externalRedis.url` / `externalS3.endpoint` are required |
| Backend workload | `*-backend`, `replicas=backend.replicas` (must be 1) | `*-api` + `*-worker` |
| `JOB_CONCURRENCY` | `config.jobConcurrency` (default 2) | Always `0` for the API; `worker.jobConcurrency` for the worker |
| Validation | None enforced | Missing DSN / Redis / S3 → rendering fails immediately with a readable error |
| Service name | `*-backend` | `*-api` (nginx and NOTES follow automatically) |

Hard validation for `mode=ha` (fails already during `helm template` / `helm install`):

- Empty `externalDatabase.dsn` → `mode=ha requires externalDatabase.dsn ...`
- No usable Redis (both `externalRedis.url` and `config.redisUrl` empty) → `mode=ha requires an external Redis ...`
- No usable S3 endpoint → `mode=ha requires external object storage ...`
- `worker.enabled=false` → error (otherwise nothing consumes tasks while `api.jobConcurrency=0`)
- `api.jobConcurrency != 0` → error

---

## 3. Building images

The repository ships two reference Dockerfiles in `deploy/docker/`:

```bash
docker build -f deploy/docker/backend.Dockerfile -t registry.example.com/opencgp/backend:0.1.0 backend
docker push registry.example.com/opencgp/backend:0.1.0

docker build -f deploy/docker/frontend.Dockerfile \
  --build-arg VITE_API_BASE=/api \
  -t registry.example.com/opencgp/frontend:0.1.0 frontend
docker push registry.example.com/opencgp/frontend:0.1.0
```

Key points:

- `VITE_API_BASE` is a **build-time** variable (Vite inlines it into the bundle). Build with `/api`, otherwise the frontend falls back to `http://127.0.0.1:8000`.
- At runtime the chart-injected nginx config reverse-proxies `/api` to `{release}-api` (HA) or `{release}-backend` (single mode); the browser only makes same-origin requests, so no CORS is needed.
- The backend image bundles `libcairo/libpango` (PDF export dependencies). CJK fonts must be added to the image yourself and pointed at with `OPENCGP_EXPORTER_FONT_REGULAR` / `_FONT_BOLD` (`.ttf` paths).
- The backend container runs as non-root (uid 10001) with a read-only root filesystem; the only writable locations are `/data` (single-mode backend only) and an `emptyDir` (`/tmp`). The chart injects `XDG_CACHE_HOME=/tmp/.cache` and `HOME=/tmp`.
- `backend.image` is used for the single-mode backend, the API, and the worker; all three must run exactly the same image.

---

## 4. Installing in single mode

Minimal install (bundled PostgreSQL + Redis + rustfs, single replica):

```bash
helm install opencgp deploy/helm/opencgp \
  --namespace opencgp --create-namespace \
  --set mode=single \
  --set backend.image.repository=registry.example.com/opencgp/backend \
  --set frontend.image.repository=registry.example.com/opencgp/frontend \
  --set ingress.enabled=true \
  --set ingress.className=nginx \
  --set ingress.hosts[0].host=opencgp.example.com
```

Install with custom concurrency and resource settings:

```bash
helm install opencgp deploy/helm/opencgp -n opencgp --create-namespace \
  --set mode=single \
  --set backend.image.repository=registry.example.com/opencgp/backend \
  --set frontend.image.repository=registry.example.com/opencgp/frontend \
  --set config.jobConcurrency=4 \
  --set backend.replicas=1 \
  --set postgres.storage=20Gi \
  --set postgres.credentials.password='ChangeMe-Str0ng' \
  --set redis.auth.enabled=true \
  --set redis.auth.password='ChangeMe-Redis' \
  --set backend.resources.requests.cpu=500m
```

Access:

```bash
kubectl -n opencgp port-forward svc/opencgp-frontend 8080:80
curl -s http://127.0.0.1:8080/health
```

Single-mode limitations (worth remembering):

- `backend.replicas` can only be 1: the bundled PostgreSQL / Redis / rustfs are all single-replica with `ReadWriteOnce` PVCs.
- If you need multiple replicas, uninterrupted rolling releases, or independent worker scaling, use HA mode.

---

## 5. Installing in HA mode

### 5.1 Minimal external dependency configuration

Prepare three things first (minimum working configuration):

```yaml
# my-ha-values.yaml
mode: ha

externalDatabase:
  enabled: true
  dsn: postgresql://opencgp:password@pg.database.svc.cluster.local:5432/opencgp

externalRedis:
  enabled: true
  url: redis://:password@redis.database.svc.cluster.local:6379/0

externalS3:
  enabled: true
  endpoint: https://s3.us-east-1.amazonaws.com
  bucket: opencgp
  region: us-east-1
  accessKey: AKIA...
  secretKey: ...
  prefix: tenants

api:
  replicas: 2

worker:
  enabled: true
  replicas: 2
  jobConcurrency: 2

postgres:
  enabled: false
redis:
  enabled: false
rustfs:
  enabled: false

backend:
  image:
    repository: registry.example.com/opencgp/backend
    tag: "0.1.0"
frontend:
  image:
    repository: registry.example.com/opencgp/frontend
    tag: "0.1.0"

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: opencgp.example.com
      paths:
        - path: /
          pathType: Prefix
```

Install:

```bash
helm install opencgp deploy/helm/opencgp -n opencgp --create-namespace -f my-ha-values.yaml
```

Pure `--set` variant (equivalent, convenient for one-shot CI commands):

```bash
helm install opencgp deploy/helm/opencgp -n opencgp --create-namespace \
  --set mode=ha \
  --set externalDatabase.dsn='postgresql://opencgp:password@pg.database.svc.cluster.local:5432/opencgp' \
  --set externalRedis.url='redis://:password@redis.database.svc.cluster.local:6379/0' \
  --set externalS3.enabled=true \
  --set externalS3.endpoint=https://s3.us-east-1.amazonaws.com \
  --set externalS3.bucket=opencgp \
  --set externalS3.accessKey=AKIA... \
  --set externalS3.secretKey=... \
  --set postgres.enabled=false \
  --set redis.enabled=false \
  --set rustfs.enabled=false \
  --set api.replicas=2 \
  --set worker.replicas=2 \
  --set worker.jobConcurrency=2 \
  --set backend.image.repository=registry.example.com/opencgp/backend \
  --set frontend.image.repository=registry.example.com/opencgp/frontend
```

### 5.2 Minimum requirements for external PostgreSQL

- Version 15 / 16; create the database and account beforehand:

```sql
CREATE ROLE opencgp LOGIN PASSWORD 'password';
CREATE DATABASE opencgp OWNER opencgp;
```

- The `pgvector` extension must be available: `VECTORSTORE_BACKEND=postgres` reuses the same DSN and the vector tables depend on the `vector` extension; with a managed service, confirm the extension allowlist.
- Connections: `api.replicas * config.databasePoolSize + worker.replicas * worker-side connections`. With the default `databasePoolSize=8`, 20 pods means 160 connections; raise `max_connections` accordingly or use PgBouncer.
- Special characters such as `@ : / ? # %` in the DSN must be percent-encoded; the chart does not escape them.
- Backup/high availability (primary-replica, Patroni, managed cloud) is the database's responsibility; the chart only connects to it.

### 5.3 Minimum requirements for external Redis

```bash
redis-cli -h redis.database.svc.cluster.local -a password ping
```

- Version 6+ (uses `BRPOP` and Pub/Sub).
- **All API and worker pods must point at the same Redis DB number** (the trailing `/0` in the URL must match).
- Enabling AOF (`appendonly yes`) is recommended; losing queued tasks means "submitted but never executed".
- When several tenants/environments share one Redis instance, isolate **whole environments** by DB number, but keep every instance within an environment on the same DB.

### 5.4 Minimum requirements for external S3

- The adapter uses the S3-compatible protocol with path-style addressing; MinIO / rustfs / Alibaba Cloud OSS (S3-compatible) / AWS S3 all work.
- If the bucket is missing it is created with `PUT bucket` on first use, so the account needs `s3:CreateBucket` — or pre-create the bucket and narrow the permissions.
- Non-empty `externalS3.accessKey` / `secretKey` are written into the chart-managed Secret; if empty they are generated randomly (only meaningful for the bundled rustfs).
- For production, prefer `secrets.existingSecret` plus an external secret store.

### 5.5 First sign-in

With `config.authMode=required`, **the first registered account is automatically activated and becomes the owner**; later sign-ups default to `pending` and can only sign in after an admin approves them at `/api/v1/admin/users?status=pending` (controlled by `config.requireApproval`).

---

## 6. Key values

| Key | Default | Notes |
|---|---|---|
| `mode` | `single` | `single` / `ha` |
| `backend.image.repository` / `.tag` | `opencgp/backend` / `0.1.0` | Backend image shared by the API / worker / single-mode backend |
| `backend.replicas` | `1` | Single mode only; multiple replicas require `mode=ha` |
| `backend.persistence.enabled` | `true` | Mounts `/data` in single mode |
| `api.replicas` | `2` | API replica count (HA) |
| `api.jobConcurrency` | `0` | Must be 0 in HA: API pods do not consume tasks |
| `api.resources` | 250m/512Mi → 2/2Gi | API resources |
| `api.autoscaling.enabled` | `false` | API HPA (CPU-based; in single mode it applies to `*-backend`) |
| `api.pdb.enabled` / `.minAvailable` | `false` / `1` | API PodDisruptionBudget |
| `worker.enabled` | `true` | Must be true in HA |
| `worker.replicas` | `2` | Worker replica count |
| `worker.jobConcurrency` | `2` | Consumption concurrency per worker pod; total = `replicas * jobConcurrency` |
| `worker.resources` | 500m/1Gi → 2/3Gi | Worker resources (give CPU-heavy tasks plenty of CPU) |
| `worker.autoscaling.metric` | `cpu` | `cpu` or `queue` (queue backlog, requires prometheus-adapter) |
| `worker.autoscaling.queueBacklogThreshold` | `50` | Target average `opencgp_queue_backlog` per pod when `metric=queue` |
| `externalDatabase.enabled` / `.dsn` | `false` / `""` | External PostgreSQL; `dsn` is required when `enabled=true` |
| `externalRedis.enabled` / `.url` | `false` / `""` | External Redis; required for HA |
| `externalS3.enabled` / `.endpoint` / `.bucket` / `.region` / `.accessKey` / `.secretKey` / `.prefix` | `false` / empty | External object storage |
| `postgres.enabled` | `true` | Bundled PostgreSQL (only effective with `mode=single`) |
| `postgres.image` | `postgres:16-alpine` | Bundled PG image |
| `postgres.storage` | `20Gi` | Bundled PG PVC size |
| `postgres.credentials` | `opencgp` / `opencgp` / `opencgp` | user / password / database — **change the password in production** |
| `redis.enabled` | `true` | Bundled Redis (single mode only) |
| `redis.auth.enabled` | `false` | When enabled, written into `OPENCGP_REDIS_URL` automatically |
| `rustfs.enabled` | `true` | Bundled object storage (single mode only) |
| `config.databaseBackend` | `postgres` | PostgreSQL only; the chart no longer offers SQLite |
| `config.vectorstoreBackend` | `postgres` | Reuses `DATABASE_DSN`; set `OPENCGP_VECTORSTORE_DSN` separately if needed |
| `config.queueBackend` | `redis` | `local` / `redis` |
| `config.storageBackend` | `s3` | `local` / `s3` / `rustfs` |
| `config.authMode` | `required` | With `disabled`, implicit owner and no sign-in (local self-use only) |
| `config.requireApproval` | `"true"` | Whether registration needs admin approval |
| `config.jobConcurrency` | `2` | Default concurrency used only by the single-mode backend (ConfigMap default) |
| `config.notifyBackend` / `smtpHost` / `smtpPort` / `smtpUser` / `smtpFrom` / `smtpTls` | `none` / empty | Notification and SMTP placeholders; the password comes from `secrets.smtpPassword` |
| `config.executorBackend` | `none` | There is no docker socket inside the cluster, so keep it at none (see section 14) |
| `secrets.existingSecret` | `""` | Use an external Secret; the chart stops rendering one |
| `secrets.smtpPassword` | `""` | SMTP password written into the Secret |
| `ingress.enabled` / `className` / `hosts` / `tls` | `false` | Ingress points only at the frontend Service |
| `networkPolicy.enabled` | `false` | Restricts inbound sources for api/worker/backend / postgres / redis / rustfs |

ConfigMap keys are uniformly prefixed with `OPENCGP_` (e.g. the logical `DATABASE_BACKEND` is actually `OPENCGP_DATABASE_BACKEND`), and each Deployment overrides the ConfigMap default for `JOB_CONCURRENCY` through `env`.

> The top-level `notes` field in `values.yaml` is purely descriptive: Helm keeps it as-is and never renders it into any resource.

---

## 7. Separating API and worker

### 7.1 Why `JOB_CONCURRENCY=0`

`JOB_CONCURRENCY` is the switch that decides whether this process starts consumer coroutines (backend `JobsConfig.concurrency`; `0` means serve the API only and consume no tasks). Reasons to split the API from the worker:

- **No mutual interference**: one long task (slide generation, PDF export, large document parsing) saturates the CPU and the event loop and competes with HTTP requests. Once split, API P95 latency is unaffected by tasks and the worker can get a larger CPU quota.
- **Independent scaling**: the API scales with traffic (CPU / RPS) and the worker scales with queue backlog; the two ratios are rarely 1:1.
- **Independent rolling releases**: restarting a worker interrupts running tasks (`terminationGracePeriodSeconds=120` lets them finish where possible), whereas restarting the API only affects connections; splitting keeps the two kinds of disruption apart.
- **Fault isolation**: an OOM inside a task cannot take the API down with it.

In the chart: `api-deployment.yaml` sets `OPENCGP_JOB_CONCURRENCY` to `"0"` unconditionally, while `worker-deployment.yaml` uses `{{ .Values.worker.jobConcurrency }}`. The worker has no Service and no readinessProbe, is part of no Service Endpoints, and therefore receives no HTTP traffic.

### 7.2 Why the same Redis DB is mandatory

- The queue is a Redis List (`BRPOP`) and tasks live in keys of one specific DB. If the API writes to DB 0 while the worker reads DB 1, tasks never move — and **no error is raised**; it only shows up as "tasks stay queued forever".
- SSE events use Pub/Sub: channel names carry no DB prefix, but the connection itself is bound to a DB. Instances on different DBs never see each other's events and the frontend spins forever.
- Distributed locks (`LOCK_TTL_SECONDS`) also live in the same Redis: without sharing, several workers can claim the same task and write duplicate data.

Therefore, within one environment **every API/worker `REDIS_URL` must use the same host, the same port, and the same `/<db>` number**. Only different environments (staging / prod) should use a different DB number or instance.

### 7.3 Recommended deployment topology

```
Ingress -> frontend(nginx) -> Service *-api (ClusterIP, HTTP only)
                                   |
                                   +--> PostgreSQL (DATABASE_DSN)
                                   +--> Redis (same DB)
                                   +--> S3

*-worker (no Service) -----------> Redis (same DB)
                                   +--> PostgreSQL / S3
```

When diagnosing "tasks not moving", check first:

```bash
kubectl -n opencgp get deploy ocgp-opencgp-api ocgp-opencgp-worker -o wide
kubectl -n opencgp exec deploy/ocgp-opencgp-api -- printenv | grep -E 'JOB_CONCURRENCY|REDIS_URL'
kubectl -n opencgp exec deploy/opencgp-opencgp-worker -- printenv | grep -E 'JOB_CONCURRENCY|REDIS_URL'
```

The `REDIS_URL` of the two Deployments must be character-for-character identical, while `JOB_CONCURRENCY` should be `0` and `>0` respectively.

---

## 8. Scaling recommendations

### 8.1 API

- Metrics: CPU utilization (70% by default) plus optional memory.
- Starting values: `minReplicas=2` (availability floor) and derive `maxReplicas` from "per-pod RPS × replicas ≥ peak RPS".
- Cold start is slow (imports, connection pool creation), so pair it with a `startupProbe` (30s budget by default) and `pdb.minAvailable=1` to keep rolling releases uninterrupted.

```bash
helm upgrade opencgp deploy/helm/opencgp -n opencgp --reuse-values \
  --set api.autoscaling.enabled=true \
  --set api.autoscaling.minReplicas=2 \
  --set api.autoscaling.maxReplicas=8 \
  --set api.autoscaling.targetCPUUtilizationPercentage=70 \
  --set api.pdb.enabled=true --set api.pdb.minAvailable=1
```

### 8.2 Worker

Two strategies, pick one (`worker.autoscaling.metric`):

| metric | Basis | Suits |
|---|---|---|
| `cpu` | Resource CPU Utilization | CPU-heavy tasks where backlog correlates with CPU |
| `queue` | `opencgp_queue_backlog` (Pods metric, target average per pod) | IO/wait-heavy tasks (LLM calls, external APIs) where CPU stays flat but the queue grows |

`queue` mode needs prometheus-adapter in the cluster, exposing `opencgp_queue_backlog` as a Pods metric (Prometheus scrapes pod annotations → custom metrics API). Reference adapter rules:

```yaml
rules:
  - seriesQuery: 'opencgp_queue_backlog{namespace!="",pod!=""}'
    resources:
      overrides:
        namespace: {resource: namespace}
        pod: {resource: pod}
    name:
      matches: '^opencgp_queue_backlog$'
      as: 'opencgp_queue_backlog'
    metricsQuery: 'avg(<<.Series>>{<<.LabelMatchers>>}) by (pod, namespace)'
```

```bash
helm upgrade opencgp deploy/helm/opencgp -n opencgp --reuse-values \
  --set worker.autoscaling.enabled=true \
  --set worker.autoscaling.metric=queue \
  --set worker.autoscaling.minReplicas=2 \
  --set worker.autoscaling.maxReplicas=10 \
  --set worker.autoscaling.queueBacklogThreshold=50
```

Manual scaling (without HPA):

```bash
kubectl -n opencgp scale deploy/ocgp-opencgp-worker --replicas=6
```

Notes:

- Total worker concurrency = `replicas * worker.jobConcurrency`, which also multiplies PostgreSQL connections and QPS against the LLM/image APIs; confirm downstream quotas before scaling.
- Scaling workers down interrupts running tasks; `terminationGracePeriodSeconds=120` plus idempotent tasks/retries (`JOB_MAX_ATTEMPTS`) cover this together.
- The database connection ceiling is a hard constraint: keep `(api.replicas + worker.replicas) * pool_size` below 80% of PG `max_connections`.

---

## 9. Secret management

By default the chart generates and manages its own Secret (`{release}-secret`):

| Key | Source |
|---|---|
| `OPENCGP_AUTH_SECRET` | `randAlphaNum 48`; `lookup` preserves the previous value |
| `OPENCGP_DATABASE_DSN` | Assembled from `externalDatabase.dsn` or the bundled PG (it contains the password, hence a Secret rather than a ConfigMap) |
| `OPENCGP_S3_ACCESS_KEY` / `_SECRET_KEY` | From `externalS3.*` or `secrets.*`, otherwise generated randomly |
| `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` | Same values as above, used by the bundled rustfs |
| `OPENCGP_LLM_API_KEY` / `_IMAGE_API_KEY` / `_WEBSEARCH_API_KEY` | Written only when the matching `secrets.*ApiKey` is non-empty |
| `OPENCGP_SMTP_PASSWORD` | Written only when `secrets.smtpPassword` is non-empty |

Read the auto-generated managed secrets:

```bash
kubectl -n opencgp get secret ocgp-opencgp-secret -o jsonpath='{.data.OPENCGP_AUTH_SECRET}' | base64 -d
kubectl -n opencgp get secret ocgp-opencgp-secret -o jsonpath='{.data.OPENCGP_DATABASE_DSN}' | base64 -d
```

For production, prefer external Secrets (SealedSecret / External Secrets / Vault):

```bash
kubectl -n opencgp create secret generic opencgp-secrets \
  --from-literal=OPENCGP_AUTH_SECRET="$(openssl rand -base64 36)" \
  --from-literal=OPENCGP_DATABASE_DSN='postgresql://opencgp:password@pg:5432/opencgp' \
  --from-literal=OPENCGP_S3_ACCESS_KEY=xxx \
  --from-literal=OPENCGP_S3_SECRET_KEY=yyy \
  --from-literal=OPENCGP_LLM_API_KEY=sk-xxx

helm upgrade --install opencgp deploy/helm/opencgp -n opencgp \
  --set secrets.existingSecret=opencgp-secrets -f my-ha-values.yaml
```

Notes:

- When `secrets.existingSecret` is set the chart renders no Secret and applies no `lookup` preservation — **`OPENCGP_DATABASE_DSN`, `AUTH_SECRET`, and `S3_*` must all be provided by the external Secret**, using the `OPENCGP_` UPPER_SNAKE_CASE key style.
- Changing `OPENCGP_AUTH_SECRET` immediately invalidates every issued token (users must sign in again).
- The Secret carries `helm.sh/resource-policy: keep`, so `helm uninstall` leaves it in place, keeping tokens valid across an in-place reinstall.
- **Never commit sensitive values into a `values.yaml` in the repository**; use `--set` / `--set-file` or an external Secret.

---

## 10. Metrics collection (Prometheus)

The pod templates for the API / worker / single-mode backend all carry annotations:

```yaml
prometheus.io/scrape: "true"
prometheus.io/port: "8000"
prometheus.io/path: "/metrics"
```

**`/metrics` is not exposed through Ingress or through the frontend:**

- The nginx config contains `location = /metrics { deny all; return 403; }`, so `/metrics` on the frontend domain is rejected;
- Ingress points only at the frontend Service and never directly at the API;
- The API Service is `ClusterIP`, reachable only inside the cluster;
- Prometheus scrapes Pod IP:8000 directly via the pod annotations, independent of Ingress.

The benefit: metrics are never exposed to the public internet (`/metrics` carries internal details such as tenant names, quota usage, and route structure), no separate inbound path is opened for monitoring, and nothing is affected by Ingress auth or rate-limiting policies.

Annotation-based scraping (the `kubernetes-pods` job) is enough for Prometheus; sample `scrape_config`:

```yaml
scrape_configs:
  - job_name: kubernetes-pods
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: "true"
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
        action: replace
        target_label: __metrics_path__
        regex: (.+)
      - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        regex: ([^:]+)(?::\d+)?;(\d+)
        replacement: $1:$2
        target_label: __address__
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod
      - source_labels: [__meta_kubernetes_pod_label_app_kubernetes_io_component]
        target_label: component
```

With the Prometheus Operator you can add a `ServiceMonitor` directly (in HA mode replace `component: backend` with `component: api`):

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: opencgp-api
  namespace: opencgp
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: opencgp
      app.kubernetes.io/component: api
  endpoints:
    - port: http
      path: /metrics
      interval: 30s
```

The worker has no Service, so a `ServiceMonitor` cannot scrape it; use the pod-annotation approach above (or a `PodMonitor`).

Key metrics:

| Metric | Type | Notes |
|---|---|---|
| `opencgp_http_requests_total{method,route,status}` | counter | Request count |
| `opencgp_http_request_duration_seconds_bucket{route,le}` | histogram | Request latency |
| `opencgp_jobs_total{kind,status}` | gauge | Job count by kind/status |
| `opencgp_jobs_active` | gauge | Queued + running jobs |
| `opencgp_queue_backlog` | gauge | Queue backlog length (basis for worker HPA) |
| `opencgp_adapter_up{name}` | gauge | Adapter liveness (1/0) |
| `opencgp_quota_usage{kind}` | gauge | Current tenant usage this month |
| `opencgp_exec_runs_total{backend,result}` | counter | Code execution count |
| `opencgp_info{version,env}` | gauge | Version/environment |

---

## 11. Importing into Grafana

Dashboard file: `deploy/grafana/opencgp-dashboard.json` (6 panels, datasource variable `${DS_PROMETHEUS}`).

Import steps:

1. Grafana → **Dashboards** on the left → **New** → **Import**.
2. Use **Upload JSON file** to select `deploy/grafana/opencgp-dashboard.json` (or paste the file contents into **Import via panel json**).
3. Choose the cluster's Prometheus data source in the `DS_PROMETHEUS` dropdown (the only option you need to fill in during import).
4. Click **Import**; the dashboard lands on the `opencgp-overview` UID, and re-importing overwrites the same dashboard.

Command line / automation (ConfigMap approach; the Grafana sidecar loads it automatically):

```bash
kubectl -n monitoring create configmap grafana-dashboard-opencgp \
  --from-file=opencgp-dashboard.json=deploy/grafana/opencgp-dashboard.json \
  --dry-run=client -o yaml \
  | kubectl label --local -f - grafana_dashboard=1 -o yaml \
  | kubectl apply -n monitoring -f -
```

Or call the API directly:

```bash
curl -s -X POST http://admin:admin@grafana:3000/api/dashboards/db \
  -H 'Content-Type: application/json' \
  -d "{\"dashboard\": $(cat deploy/grafana/opencgp-dashboard.json), \"overwrite\": true}"
```

Panel list:

| Panel | Query |
|---|---|
| Request rate (by route) | `sum by (route) (rate(opencgp_http_requests_total[5m]))` |
| P95 latency (by route) | `histogram_quantile(0.95, sum by (le, route) (rate(opencgp_http_request_duration_seconds_bucket[5m])))` |
| Job throughput (kind/status) | `sum by (kind, status) (rate(opencgp_jobs_total[5m]))` |
| Queue backlog | `max(opencgp_queue_backlog)` / `sum(opencgp_queue_backlog)` |
| Adapter health | `min by (name) (opencgp_adapter_up)` |
| Quota usage (by kind) | `sum by (kind) (opencgp_quota_usage)` |

Validate the JSON:

```bash
python -c "import json;d=json.load(open('deploy/grafana/opencgp-dashboard.json'));print(len(d['panels']))"
```

---

## 12. Upgrades and rollbacks

```bash
helm upgrade opencgp deploy/helm/opencgp -n opencgp -f my-ha-values.yaml
helm history opencgp -n opencgp
helm rollback opencgp 2 -n opencgp
```

- Pod templates carry `checksum/config` and `checksum/secret` annotations: changing the ConfigMap / Secret triggers an automatic rolling restart.
- In single mode with `backend.replicas <= 1` and persistence enabled the strategy is `Recreate` (so an RWO PVC is never mounted by two pods at once); HA mode and the frontend use `RollingUpdate` (`maxSurge=1, maxUnavailable=0`).
- Roll the API before the worker (or the other way round together with a `pdb`) to avoid queue-protocol incompatibilities while two versions run side by side.
- Rolling back the chart version does not roll back data (PVCs carry `helm.sh/resource-policy: keep`).

---

## 13. Migrating from single mode to HA (data move)

The chart does not migrate data; the steps are:

1. Stop writes: `kubectl -n opencgp scale deploy/opencgp-backend --replicas=0` (or switch to a read-only maintenance page first).
2. Dump the bundled PG:
   ```bash
   kubectl -n opencgp exec ocgp-opencgp-postgres-0 -- \
     pg_dump -U opencgp -Fc opencgp > /tmp/opencgp.dump
   ```
3. Restore into the external PG:
   ```bash
   pg_restore -h pg.database.svc -U opencgp -d opencgp --clean --if-exists /tmp/opencgp.dump
   ```
4. Sync object storage (bundled rustfs → external bucket):
   ```bash
   kubectl -n opencgp port-forward svc/ocgp-opencgp-rustfs 9000:9000
   aws --endpoint-url http://127.0.0.1:9000 s3 sync s3://<old-bucket> s3://opencgp --profile local
   ```
5. Run `helm upgrade --install` with the HA values from section 5 (`mode=ha` plus external dependencies).
6. Verify: `/health` returns 200, sign-in works, old series open, and the queue drains.

---

## 14. Common failures

| Symptom | Cause and fix |
|---|---|
| `helm template` reports `mode=ha requires externalDatabase.dsn` | HA mode does not bundle PG; add `--set externalDatabase.dsn=postgresql://...` |
| `Error: execution error at (...): mode=ha requires an external Redis` | Add `--set externalRedis.url=redis://host:6379/0` and make sure all instances use the same DB |
| Tasks stay "queued" after submission | The API and worker `REDIS_URL` differ (especially the DB number), or the worker has 0 replicas; compare them character by character with the commands in section 7.3 |
| Tasks run twice / results are inconsistent | Multiple instances point at different Redis DBs, so each lock lives on its own; unify the DB number |
| `/api/v1/exec` returns 503 "no code execution backend configured" | There is no docker daemon/socket inside the cluster pods, so `executor.backend=docker` is unusable. Keep `config.executorBackend=none`; to really run code, deploy the `local` backend on a trusted node or run a separate runner with a docker socket |
| `CreateContainerConfigError: secret "xxx" not found` | `secrets.existingSecret` was set but the Secret was not created, or the key names do not match (they need `OPENCGP_*` uppercase keys, and HA must include `OPENCGP_DATABASE_DSN`) |
| The backend fails to start with `OPENCGP_DATABASE_DSN is not configured` | `secrets.existingSecret` is used but the external Secret lacks the DSN; this cannot happen when the chart manages the Secret itself |
| PostgreSQL reports `too many clients` | `(api.replicas + worker.replicas) * pool_size` exceeds the limit; lower `config.databasePoolSize` or add PgBouncer |
| Vector search reports `type "vector" does not exist` | The external PG does not have the `pgvector` extension enabled, or the account lacks `CREATE EXTENSION` privileges |
| Frontend 502 / `/api` unreachable | Confirm the Service name matches the mode (HA uses `*-api`, single mode uses `*-backend`; the chart wires this automatically) and that `api.service.port` matches the container port |
| Page refresh returns 404 | nginx already has `try_files $uri $uri/ /index.html`; keep that rule if you swap in your own image |
| Document upload returns 413 | Raise `frontend.clientMaxBodySize` (32m by default) and check the Ingress `proxy-body-size` |
| Task SSE stalls and does not refresh | Ingress buffers by default; the chart's nginx already sets `proxy_buffering off`, so any extra LB/Ingress in front must also disable buffering and raise `proxy-read-timeout` |
| Upload/export reports `Read-only file system` | The root filesystem is read-only; only `/data` (single mode only) and `/tmp` are writable, so add `backend.extraVolumes` for custom paths |
| CJK text in PDFs renders as boxes | The image lacks NotoSansSC; add the font to the image and set `OPENCGP_EXPORTER_FONT_REGULAR` / `_FONT_BOLD` |
| rustfs pod CrashLoopBackOff | `rustfs.image.tag` defaults to `latest`; pin it to a real release and use `kubectl logs` to confirm the `args` match the image CLI |
| HPA shows `<unknown>/70%` | The pod has no `resources.requests.cpu` (the chart sets it by default), or metrics-server is not ready |
| The worker HPA with `metric=queue` does not scale | prometheus-adapter has no Pods rule for `opencgp_queue_backlog` (see section 8.2) |
| Every user is signed out after a rename/namespace change | `OPENCGP_AUTH_SECRET` changed; with an external Secret, pin that value explicitly |

Diagnostic commands:

```bash
kubectl -n opencgp get pods -o wide
kubectl -n opencgp logs deploy/ocgp-opencgp-api --tail=200
kubectl -n opencgp logs deploy/ocgp-opencgp-worker --tail=200
kubectl -n opencgp exec -it deploy/ocgp-opencgp-api -- python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read()[:200])"
kubectl -n opencgp port-forward svc/ocgp-opencgp-api 8000:8000 &
curl -s http://127.0.0.1:8000/health | python -m json.tool
curl -s http://127.0.0.1:8000/metrics | head
```

---

## 15. Uninstalling

```bash
helm uninstall opencgp -n opencgp
```

`PVC`s and the `Secret` carry `helm.sh/resource-policy: keep` and are retained; to clean up completely:

```bash
kubectl -n opencgp delete pvc ocgp-opencgp-data
kubectl -n opencgp delete secret ocgp-opencgp-secret
```

PVCs created by a StatefulSet's `volumeClaimTemplates` (`data-ocgp-opencgp-postgres-0`, `data-ocgp-opencgp-redis-0`, `data-ocgp-opencgp-rustfs-0`) survive deletion of the StatefulSet and must be removed manually.

---

## 16. Pre-deployment checklist

```bash
helm lint deploy/helm/opencgp
helm template ocgp deploy/helm/opencgp > /tmp/render-single.yaml
helm template ocgp deploy/helm/opencgp \
  --set mode=ha \
  --set externalDatabase.dsn=postgresql://u:p@db:5432/x \
  --set externalRedis.url=redis://r:6379/0 \
  --set externalS3.enabled=true --set externalS3.endpoint=http://s3:9000 \
  > /tmp/render-ha.yaml

python - <<'PY'
import yaml, collections
for f in ("/tmp/render-single.yaml", "/tmp/render-ha.yaml"):
    docs = [d for d in yaml.safe_load_all(open(f)) if d]
    print(f, collections.Counter(d["kind"] for d in docs))
PY
```

Confirm that:

- `mode=single`: a `backend` Deployment and the bundled `postgres` StatefulSet appear, and **no** `api` / `worker` Deployment appears;
- `mode=ha`: `api` (`JOB_CONCURRENCY=0`) and `worker` (`JOB_CONCURRENCY>0`) Deployments appear, and **no** `backend` Deployment or bundled `postgres` StatefulSet appears;
- with `mode=ha` and no `externalDatabase.dsn`, `helm template` fails immediately with a readable error;
- `OPENCGP_AUTH_SECRET` and `OPENCGP_DATABASE_DSN` appear only in the Secret and never in the ConfigMap;
- the target environment has a usable StorageClass, registry credentials, and external PG / Redis / S3.
