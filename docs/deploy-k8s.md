# OpenCGP 在 Kubernetes 上的部署指南

本指南对应 `deploy/helm/opencgp` 目录中的 Helm Chart（`version 0.1.0` / `appVersion 0.1.0`）。

Chart 支持两种部署模式，由 `mode` 控制：

| 模式 | 渲染的工作负载 | 依赖 | 适用场景 |
|---|---|---|---|
| `single` | `*-backend`（API+Worker 合一）+ `*-postgres` + `*-redis` + `*-rustfs` + `*-frontend` | Chart 内置，全部单副本 | 演示、单机、内网小规模 |
| `ha` | `*-api`（只处理 HTTP，`JOB_CONCURRENCY=0`）+ `*-worker`（只消费任务）+ `*-frontend` | 必须外部 PostgreSQL / Redis / S3 | 生产、多副本、水平扩容 |

Chart 的工作负载一览：

| 组件 | 资源 | 说明 |
|---|---|---|
| API | Deployment + Service（仅 HA） | FastAPI，端口 8000，`/health` 探针，`/metrics` 暴露 Prometheus 指标，`JOB_CONCURRENCY=0` |
| Worker | Deployment（仅 HA，无 Service） | 同一镜像，`JOB_CONCURRENCY={{ worker.jobConcurrency }}`，只消费队列，liveness 用 `/health`，不接流量 |
| Backend（单机） | Deployment + Service + PVC | API+Worker 合一，`JOB_CONCURRENCY>0` |
| 前端 | Deployment + Service + ConfigMap | nginx 托管静态站点，同源反代 `/api` 到 API/Backend Service |
| PostgreSQL | StatefulSet + Service（仅单机） | 内置 `postgres:16-alpine`，`PGDATA=/var/lib/postgresql/data/pgdata` |
| Redis | StatefulSet + headless Service（仅单机） | 任务队列与 SSE 事件总线，`--appendonly yes` |
| rustfs | StatefulSet + headless Service（仅单机） | S3 兼容对象存储，端口 9000 / 9001 |

> **注意**：内置 PostgreSQL / Redis / rustfs 只在 `mode=single` 渲染。`mode=ha` 时即使 `postgres.enabled` / `redis.enabled` / `rustfs.enabled` 仍为 `true`，这些内置工作负载也不会创建。

---

## 1. 前置条件

- Kubernetes 1.24+（`autoscaling/v2`、`policy/v1`、`networking.k8s.io/v1` Ingress）
- Helm 3.12+（本 Chart 用 `lookup` 保留已生成的密钥，3.16.3 实测通过）
- 集群内有默认 StorageClass，或通过 `backend.persistence.storageClass` / `postgres.storageClass` / `redis.persistence.storageClass` / `rustfs.persistence.storageClass` 显式指定
- 已构建并推送 `opencgp/backend` 与 `opencgp/frontend` 镜像（见第 3 节）
- HA 模式还需要：外部 PostgreSQL（建议 15/16）、外部 Redis（6+/7）、S3 兼容对象存储
- （可选）Ingress Controller、Prometheus（注解式抓取或 Operator）、Grafana

验证 Helm 与 Chart：

```bash
helm version
helm lint deploy/helm/opencgp
helm template opencgp deploy/helm/opencgp > /tmp/render.yaml
```

---

## 2. 两种模式的差异

| 项 | `mode=single` | `mode=ha` |
|---|---|---|
| 内置 PostgreSQL | 渲染，1 副本，PVC `postgres.storage` | 不渲染；必须给 `externalDatabase.dsn` |
| 内置 Redis / rustfs | 渲染 | 不渲染；必须给 `externalRedis.url` / `externalS3.endpoint` |
| 后端工作负载 | `*-backend`，`replicas=backend.replicas`（必须为 1） | `*-api` + `*-worker` |
| `JOB_CONCURRENCY` | `config.jobConcurrency`（默认 2） | API 恒为 `0`，Worker 为 `worker.jobConcurrency` |
| 校验 | 无强制 | 缺 DSN / Redis / S3 → 渲染直接失败并给出可读错误 |
| Service 名 | `*-backend` | `*-api`（nginx 与 NOTES 自动跟随） |

`mode=ha` 的强校验（`helm template` / `helm install` 阶段即失败）：

- `externalDatabase.dsn` 为空 → `mode=ha 必须提供 externalDatabase.dsn ...`
- 无可用 Redis（`externalRedis.url` 与 `config.redisUrl` 都为空）→ `mode=ha 必须提供外部 Redis ...`
- 无可用 S3 endpoint → `mode=ha 必须提供外部对象存储 ...`
- `worker.enabled=false` → 报错（否则 `api.jobConcurrency=0` 时无人消费任务）
- `api.jobConcurrency != 0` → 报错

---

## 3. 构建镜像

仓库提供了两个参考 Dockerfile（`deploy/docker/`）：

```bash
docker build -f deploy/docker/backend.Dockerfile -t registry.example.com/opencgp/backend:0.1.0 backend
docker push registry.example.com/opencgp/backend:0.1.0

docker build -f deploy/docker/frontend.Dockerfile \
  --build-arg VITE_API_BASE=/api \
  -t registry.example.com/opencgp/frontend:0.1.0 frontend
docker push registry.example.com/opencgp/frontend:0.1.0
```

关键点：

- `VITE_API_BASE` 是 **构建期** 变量（Vite 会把它内联进 bundle）。必须构建为 `/api`，否则前端会回落到 `http://127.0.0.1:8000`。
- 运行时由 Chart 注入的 nginx 配置把 `/api` 反代到 `{release}-api`（HA）或 `{release}-backend`（单机），浏览器只发同源请求，不需要 CORS。
- 后端镜像内置 `libcairo/libpango`（PDF 导出依赖）。中文字体需自行随镜像带入，并通过 `OPENCGP_EXPORTER_FONT_REGULAR` / `_FONT_BOLD` 指向 `.ttf` 路径。
- 后端容器以非 root（uid 10001）运行且根文件系统只读，写盘目录只有 `/data`（仅单机 backend）与 `emptyDir`（`/tmp`）；Chart 已注入 `XDG_CACHE_HOME=/tmp/.cache`、`HOME=/tmp`。
- `backend.image` 同时用于单机 backend、API 与 Worker，三者的镜像必须完全一致。

---

## 4. 单机模式安装

最小安装（内置 PostgreSQL + Redis + rustfs，单副本）：

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

带自定义并发与资源配置的安装：

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

访问：

```bash
kubectl -n opencgp port-forward svc/opencgp-frontend 8080:80
curl -s http://127.0.0.1:8080/health
```

单机模式的限制（务必记住）：

- `backend.replicas` 只能为 1：内置 PostgreSQL / Redis / rustfs 都是单副本 + `ReadWriteOnce` PVC。
- 需要多副本、滚动发布不中断、独立扩缩容 Worker —— 请用 HA 模式。

---

## 5. HA 模式安装

### 5.1 外部依赖最小配置

先准备好三样东西（最小可用配置）：

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

安装：

```bash
helm install opencgp deploy/helm/opencgp -n opencgp --create-namespace -f my-ha-values.yaml
```

纯 `--set` 版本（等价，便于 CI 一次性命令）：

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

### 5.2 外部 PostgreSQL 最小要求

- 版本 15 / 16，库名与账号需提前创建：

```sql
CREATE ROLE opencgp LOGIN PASSWORD 'password';
CREATE DATABASE opencgp OWNER opencgp;
```

- 必须允许 `pgvector` 扩展可用：`VECTORSTORE_BACKEND=postgres` 复用同一 DSN，向量表依赖 `vector` 扩展；托管服务请确认扩展白名单。
- 连接数：`api.replicas * config.databasePoolSize + worker.replicas * worker 侧连接`，默认 `databasePoolSize=8`，20 个 Pod 就是 160 条连接，请相应调整 `max_connections` 或使用 PgBouncer。
- DSN 里出现 `@ : / ? # %` 等特殊字符时必须 percent-encode，Chart 不会做转义。
- 备份/高可用（主从、Patroni、云托管）由数据库侧负责，Chart 只管连接。

### 5.3 外部 Redis 最小要求

```bash
redis-cli -h redis.database.svc.cluster.local -a password ping
```

- 版本 6+（用到 `BRPOP`、Pub/Sub）。
- **所有 API 与 Worker 必须指向同一个 Redis DB 编号**（URL 结尾的 `/0` 必须一致）。
- 建议开启 AOF `appendonly yes`；队列任务丢失会导致「提交了但永远不执行」。
- 多租户/多环境共用一个 Redis 实例时，用不同 DB 编号隔离**整套环境**，但同一环境内所有实例必须一致。

### 5.4 外部 S3 最小要求

- 适配器使用 S3 兼容协议 + path-style 寻址，MinIO / rustfs / 阿里云 OSS（S3 兼容）/ AWS S3 均可。
- 桶不存在时首次使用会自动 `PUT bucket`，因此账号需要 `s3:CreateBucket`，或预先建桶并收窄权限。
- `externalS3.accessKey` / `secretKey` 非空时会写进 Chart 管理的 Secret；留空则随机生成（仅内置 rustfs 场景有意义）。
- 生产建议 `secrets.existingSecret` + 外部密钥系统。

### 5.5 首次登录

`config.authMode=required` 时，**第一个注册的账号会自动置为 active 并成为 owner**，后续注册用户默认 `pending`，需管理员在 `/api/v1/admin/users?status=pending` 审核通过后才能登录（`config.requireApproval` 控制）。

---

## 6. values 关键项

| 键 | 默认值 | 说明 |
|---|---|---|
| `mode` | `single` | `single` / `ha` |
| `backend.image.repository` / `.tag` | `opencgp/backend` / `0.1.0` | 后端镜像，API / Worker / 单机 backend 共用 |
| `backend.replicas` | `1` | 仅单机模式；多副本必须切 `mode=ha` |
| `backend.persistence.enabled` | `true` | 单机模式挂载 `/data` |
| `api.replicas` | `2` | API 副本数（HA） |
| `api.jobConcurrency` | `0` | HA 下必须为 0：API 节点不消费任务 |
| `api.resources` | 250m/512Mi → 2/2Gi | API 资源 |
| `api.autoscaling.enabled` | `false` | API HPA（按 CPU；单机模式下作用于 `*-backend`） |
| `api.pdb.enabled` / `.minAvailable` | `false` / `1` | API PodDisruptionBudget |
| `worker.enabled` | `true` | HA 下必须为 true |
| `worker.replicas` | `2` | Worker 副本数 |
| `worker.jobConcurrency` | `2` | 单个 Worker Pod 的消费并发；总并发 = `replicas * jobConcurrency` |
| `worker.resources` | 500m/1Gi → 2/3Gi | Worker 资源（CPU 型任务给足 CPU） |
| `worker.autoscaling.metric` | `cpu` | `cpu` 或 `queue`（队列积压，依赖 prometheus-adapter） |
| `worker.autoscaling.queueBacklogThreshold` | `50` | `metric=queue` 时每 Pod 目标 `opencgp_queue_backlog` 平均值 |
| `externalDatabase.enabled` / `.dsn` | `false` / `""` | 外部 PostgreSQL；`enabled=true` 时 `dsn` 必填 |
| `externalRedis.enabled` / `.url` | `false` / `""` | 外部 Redis；HA 必需 |
| `externalS3.enabled` / `.endpoint` / `.bucket` / `.region` / `.accessKey` / `.secretKey` / `.prefix` | `false` / 空 | 外部对象存储 |
| `postgres.enabled` | `true` | 内置 PostgreSQL（仅 `mode=single` 生效） |
| `postgres.image` | `postgres:16-alpine` | 内置 PG 镜像 |
| `postgres.storage` | `20Gi` | 内置 PG PVC 大小 |
| `postgres.credentials` | `opencgp` / `opencgp` / `opencgp` | user / password / database，**生产必须改密码** |
| `redis.enabled` | `true` | 内置 Redis（仅单机） |
| `redis.auth.enabled` | `false` | 开启后自动写进 `OPENCGP_REDIS_URL` |
| `rustfs.enabled` | `true` | 内置对象存储（仅单机） |
| `config.databaseBackend` | `postgres` | 统一 PostgreSQL，Chart 不再提供 SQLite |
| `config.vectorstoreBackend` | `postgres` | 复用 `DATABASE_DSN`；需要则单独设 `OPENCGP_VECTORSTORE_DSN` |
| `config.queueBackend` | `redis` | `local` / `redis` |
| `config.storageBackend` | `s3` | `local` / `s3` / `rustfs` |
| `config.authMode` | `required` | `disabled` 时隐式 owner、免登录（仅本地自用） |
| `config.requireApproval` | `"true"` | 注册是否需要管理员审核 |
| `config.jobConcurrency` | `2` | 仅单机 backend 使用的默认并发（ConfigMap 默认值） |
| `config.notifyBackend` / `smtpHost` / `smtpPort` / `smtpUser` / `smtpFrom` / `smtpTls` | `none` / 空 | 通知与 SMTP 占位；密码走 `secrets.smtpPassword` |
| `config.executorBackend` | `none` | 集群内没有 docker socket，保持 none（见第 14 节） |
| `secrets.existingSecret` | `""` | 使用外部 Secret，Chart 不再渲染 Secret |
| `secrets.smtpPassword` | `""` | SMTP 密码，写入 Secret |
| `ingress.enabled` / `className` / `hosts` / `tls` | `false` | Ingress 只指向 frontend Service |
| `networkPolicy.enabled` | `false` | 限制 api/worker/backend / postgres / redis / rustfs 的入站来源 |

ConfigMap 里的键统一带 `OPENCGP_` 前缀（例如逻辑上的 `DATABASE_BACKEND` 实际是 `OPENCGP_DATABASE_BACKEND`），`JOB_CONCURRENCY` 由各 Deployment 用 `env` 覆盖 ConfigMap 的默认值。

> `values.yaml` 顶层的 `notes` 字段是纯说明性文本，Helm 会原样保留，不会渲染进任何资源。

---

## 7. API / Worker 分离

### 7.1 为什么要 `JOB_CONCURRENCY=0`

`JOB_CONCURRENCY` 是这个进程是否启动消费者协程的开关（后端 `JobsConfig.concurrency`，`0` 表示只提供 API、不消费任务）。把 API 与 Worker 拆开的原因：

- **互不拖累**：一次长任务（PPT 生成、PDF 导出、大文档解析）会占满 CPU 与事件循环，和 HTTP 请求抢资源。拆开之后 API 的 P95 延迟不受任务影响，Worker 可以给更大的 CPU 配额。
- **独立扩缩容**：API 按流量（CPU / RPS）扩，Worker 按队列积压扩，两者比例通常不是 1:1。
- **独立滚动发布**：Worker 重启会中断正在执行的任务（`terminationGracePeriodSeconds=120` 让任务尽量收尾），API 重启则只影响连接；拆开可以把两类抖动隔离开。
- **故障隔离**：任务里的 OOM 不会把 API 一起打挂。

对应到 Chart：`api-deployment.yaml` 里 `OPENCGP_JOB_CONCURRENCY` 恒为 `"0"`；`worker-deployment.yaml` 里为 `{{ .Values.worker.jobConcurrency }}`。Worker 没有 Service、没有 readinessProbe，不进入任何 Service Endpoints，因此不会收到 HTTP 流量。

### 7.2 为什么必须同一个 Redis DB

- 队列是 Redis List（`BRPOP`），任务只存在于某个 DB 的 key 里。API 写进 DB 0、Worker 读 DB 1 → 任务永远不动，而且**不报错**，只表现为「任务一直排队」。
- SSE 事件走 Pub/Sub：频道名不带 DB 前缀，但连接本身绑定 DB；不同 DB 的实例收不到彼此的事件，前端会一直转圈。
- 分布式锁（`LOCK_TTL_SECONDS`）也落在同一个 Redis：不共享会导致同一任务被多个 Worker 同时领取、重复写数据。

所以：同一环境内**所有 API/Worker 的 `REDIS_URL` 必须是同一个主机、同一个端口、同一个 `/<db>` 编号**。不同环境（staging / prod）才用不同 DB 编号或不同实例。

### 7.3 部署拓扑建议

```
Ingress -> frontend(nginx) -> Service *-api (ClusterIP, 只做 HTTP)
                                   |
                                   +--> PostgreSQL (DATABASE_DSN)
                                   +--> Redis (同一 DB)
                                   +--> S3

*-worker (无 Service) -----------> Redis (同一 DB)
                                   +--> PostgreSQL / S3
```

排查「任务不动」时先确认：

```bash
kubectl -n opencgp get deploy ocgp-opencgp-api ocgp-opencgp-worker -o wide
kubectl -n opencgp exec deploy/ocgp-opencgp-api -- printenv | grep -E 'JOB_CONCURRENCY|REDIS_URL'
kubectl -n opencgp exec deploy/opencgp-opencgp-worker -- printenv | grep -E 'JOB_CONCURRENCY|REDIS_URL'
```

两个 Deployment 的 `REDIS_URL` 必须逐字符相同，而 `JOB_CONCURRENCY` 应为 `0` 与 `>0`。

---

## 8. 扩缩容建议

### 8.1 API

- 指标：CPU utilization（默认 70%）+ 可选 memory。
- 起始值：`minReplicas=2`（可用性下限）、`maxReplicas` 按「单 Pod RPS × 副本数 ≥ 峰值 RPS」反推。
- 冷启动较慢（导入、建连接池），建议配合 `startupProbe`（默认 30s 预算）与 `pdb.minAvailable=1`，保证滚动发布不中断。

```bash
helm upgrade opencgp deploy/helm/opencgp -n opencgp --reuse-values \
  --set api.autoscaling.enabled=true \
  --set api.autoscaling.minReplicas=2 \
  --set api.autoscaling.maxReplicas=8 \
  --set api.autoscaling.targetCPUUtilizationPercentage=70 \
  --set api.pdb.enabled=true --set api.pdb.minAvailable=1
```

### 8.2 Worker

两种策略，二选一（`worker.autoscaling.metric`）：

| metric | 依据 | 适用 |
|---|---|---|
| `cpu` | Resource CPU Utilization | 任务 CPU 密集、积压与 CPU 正相关 |
| `queue` | `opencgp_queue_backlog`（Pods 指标，每 Pod 目标平均值） | 任务 IO/等待密集（LLM 调用、外部 API），CPU 不涨但队列会堆积 |

`queue` 模式需要集群里有 prometheus-adapter，并能把 `opencgp_queue_backlog` 暴露为 Pods 指标（Prometheus 抓取 Pod 注解 → custom metrics API）。参考 adapter 规则：

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

手工扩缩（不用 HPA）：

```bash
kubectl -n opencgp scale deploy/ocgp-opencgp-worker --replicas=6
```

注意事项：

- Worker 总量并发 = `replicas * worker.jobConcurrency`，同时会放大对 PostgreSQL 连接数、LLM/图片 API 的 QPS，扩缩容前先确认下游配额。
- Worker 缩容会中断正在跑的任务；`terminationGracePeriodSeconds=120` + 任务幂等/重试（`JOB_MAX_ATTEMPTS`）共同兜底。
- 数据库连接数上限是硬约束：`(api.replicas + worker.replicas) * pool_size` 不要超过 PG `max_connections` 的 80%。

---

## 9. 密钥管理

默认情况下 Chart 自己生成并管理 Secret（`{release}-secret`）：

| Key | 来源 |
|---|---|
| `OPENCGP_AUTH_SECRET` | `randAlphaNum 48`，`lookup` 保留旧值 |
| `OPENCGP_DATABASE_DSN` | 由 `externalDatabase.dsn` 或内置 PG 拼接（含密码，因此放在 Secret 而不是 ConfigMap） |
| `OPENCGP_S3_ACCESS_KEY` / `_SECRET_KEY` | `externalS3.*` 或 `secrets.*`，否则随机生成 |
| `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` | 与上面同值，供内置 rustfs 使用 |
| `OPENCGP_LLM_API_KEY` / `_IMAGE_API_KEY` / `_WEBSEARCH_API_KEY` | 仅当 `secrets.*ApiKey` 非空时写入 |
| `OPENCGP_SMTP_PASSWORD` | 仅当 `secrets.smtpPassword` 非空时写入 |

读取自动生成的管理密钥：

```bash
kubectl -n opencgp get secret ocgp-opencgp-secret -o jsonpath='{.data.OPENCGP_AUTH_SECRET}' | base64 -d
kubectl -n opencgp get secret ocgp-opencgp-secret -o jsonpath='{.data.OPENCGP_DATABASE_DSN}' | base64 -d
```

生产环境推荐用外部 Secret（SealedSecret / External Secrets / Vault）：

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

注意：

- `secrets.existingSecret` 生效时 Chart 不再渲染 Secret，也不会 `lookup` 保留逻辑——**`OPENCGP_DATABASE_DSN`、`AUTH_SECRET`、`S3_*` 都必须由外部 Secret 提供**，键名保持 `OPENCGP_` 大写下划线风格。
- `OPENCGP_AUTH_SECRET` 一旦变化，所有已签发 token 立即失效（用户需重新登录）。
- Secret 带 `helm.sh/resource-policy: keep`，`helm uninstall` 不会删除它，便于原地重装时保持 token 有效。
- **永远不要把敏感值写进 `values.yaml` 提交到仓库**，用 `--set` / `--set-file` / 外部 Secret。

---

## 10. 指标采集（Prometheus）

API / Worker / 单机 backend 的 Pod 模板都带注解：

```yaml
prometheus.io/scrape: "true"
prometheus.io/port: "8000"
prometheus.io/path: "/metrics"
```

**`/metrics` 不走 Ingress，也不经 frontend 暴露：**

- nginx 配置里 `location = /metrics { deny all; return 403; }`，前端域名访问 `/metrics` 会被拒绝；
- Ingress 只指向 frontend Service，不直连 API；
- API Service 是 `ClusterIP`，仅集群内可达；
- Prometheus 通过 Pod 注解直接抓 Pod IP:8000，与 Ingress 无关。

这样做的好处：指标不会被公网暴露（`/metrics` 里有租户名、配额使用量、route 结构等内部信息），也不需要为监控单独开一条入站路径，更不受 Ingress 认证/限流策略影响。

Prometheus 用注解式抓取（`kubernetes-pods` job）即可，示例 `scrape_config`：

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

若用 Prometheus Operator，可直接加 `ServiceMonitor`（HA 模式把 `component: backend` 换成 `component: api`）：

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

Worker 没有 Service，`ServiceMonitor` 抓不到它，请用上面的 Pod 注解方式（或 `PodMonitor`）。

关键指标：

| 指标 | 类型 | 说明 |
|---|---|---|
| `opencgp_http_requests_total{method,route,status}` | counter | 请求数 |
| `opencgp_http_request_duration_seconds_bucket{route,le}` | histogram | 请求耗时 |
| `opencgp_jobs_total{kind,status}` | gauge | 按类型/状态的任务数 |
| `opencgp_jobs_active` | gauge | 排队 + 运行中任务数 |
| `opencgp_queue_backlog` | gauge | 队列积压长度（Worker HPA 依据） |
| `opencgp_adapter_up{name}` | gauge | adapter 探活（1/0） |
| `opencgp_quota_usage{kind}` | gauge | 当前租户本月用量 |
| `opencgp_exec_runs_total{backend,result}` | counter | 代码执行次数 |
| `opencgp_info{version,env}` | gauge | 版本/环境 |

---

## 11. Grafana 导入

面板文件：`deploy/grafana/opencgp-dashboard.json`（6 个面板，数据源变量 `${DS_PROMETHEUS}`）。

导入步骤：

1. Grafana → 左侧 **Dashboards** → **New** → **Import**。
2. **Upload JSON file** 选择 `deploy/grafana/opencgp-dashboard.json`（或把文件内容粘贴到 **Import via panel json**）。
3. 在 `DS_PROMETHEUS` 下拉里选择集群的 Prometheus 数据源（这是导入时唯一需要填的选项）。
4. 点 **Import**，面板会落在 `opencgp-overview` UID 上，后续重复导入会覆盖同一块面板。

命令行 / 自动化（ConfigMap 方式，Grafana sidecar 会自动加载）：

```bash
kubectl -n monitoring create configmap grafana-dashboard-opencgp \
  --from-file=opencgp-dashboard.json=deploy/grafana/opencgp-dashboard.json \
  --dry-run=client -o yaml \
  | kubectl label --local -f - grafana_dashboard=1 -o yaml \
  | kubectl apply -n monitoring -f -
```

或直接调 API：

```bash
curl -s -X POST http://admin:admin@grafana:3000/api/dashboards/db \
  -H 'Content-Type: application/json' \
  -d "{\"dashboard\": $(cat deploy/grafana/opencgp-dashboard.json), \"overwrite\": true}"
```

面板清单：

| 面板 | 查询 |
|---|---|
| 请求速率（按 route） | `sum by (route) (rate(opencgp_http_requests_total[5m]))` |
| P95 延迟（按 route） | `histogram_quantile(0.95, sum by (le, route) (rate(opencgp_http_request_duration_seconds_bucket[5m])))` |
| 任务吞吐（kind/status） | `sum by (kind, status) (rate(opencgp_jobs_total[5m]))` |
| 队列积压 | `max(opencgp_queue_backlog)` / `sum(opencgp_queue_backlog)` |
| 适配器健康 | `min by (name) (opencgp_adapter_up)` |
| 配额用量（按 kind） | `sum by (kind) (opencgp_quota_usage)` |

校验 JSON 合法性：

```bash
python -c "import json;d=json.load(open('deploy/grafana/opencgp-dashboard.json'));print(len(d['panels']))"
```

---

## 12. 升级与回滚

```bash
helm upgrade opencgp deploy/helm/opencgp -n opencgp -f my-ha-values.yaml
helm history opencgp -n opencgp
helm rollback opencgp 2 -n opencgp
```

- Pod 模板带 `checksum/config`、`checksum/secret` 注解：改 ConfigMap / Secret 会自动滚动重启。
- 单机模式 `backend.replicas <= 1` 且持久化开启时策略为 `Recreate`（避免 RWO PVC 被两个 Pod 同时挂载）；HA 模式与前端为 `RollingUpdate`（`maxSurge=1, maxUnavailable=0`）。
- API / Worker 建议先滚 API 再滚 Worker（或反过来配合 `pdb`），避免版本混跑期间队列协议不兼容。
- 回滚 Chart 版本不会回滚数据（PVC 带 `helm.sh/resource-policy: keep`）。

---

## 13. 从单机迁移到 HA（数据搬迁）

Chart 不做数据迁移，步骤如下：

1. 停写：`kubectl -n opencgp scale deploy/opencgp-backend --replicas=0`（或先切只读维护页）。
2. 导出内置 PG：
   ```bash
   kubectl -n opencgp exec ocgp-opencgp-postgres-0 -- \
     pg_dump -U opencgp -Fc opencgp > /tmp/opencgp.dump
   ```
3. 导入外部 PG：
   ```bash
   pg_restore -h pg.database.svc -U opencgp -d opencgp --clean --if-exists /tmp/opencgp.dump
   ```
4. 同步对象存储（内置 rustfs → 外部桶）：
   ```bash
   kubectl -n opencgp port-forward svc/ocgp-opencgp-rustfs 9000:9000
   aws --endpoint-url http://127.0.0.1:9000 s3 sync s3://<旧bucket> s3://opencgp --profile local
   ```
5. 用第 5 节的 HA values 执行 `helm upgrade --install`（`mode=ha` + 外部依赖）。
6. 校验：`/health` 200、登录可用、旧系列能打开、队列能消化。

---

## 14. 常见故障

| 现象 | 原因与处理 |
|---|---|
| `helm template` 报 `mode=ha 必须提供 externalDatabase.dsn` | HA 模式不内置 PG；补 `--set externalDatabase.dsn=postgresql://...` |
| `Error: execution error at (...): mode=ha 必须提供外部 Redis` | 补 `--set externalRedis.url=redis://host:6379/0`，注意所有实例同一 DB |
| 任务提交后一直「排队中」 | API 与 Worker 的 `REDIS_URL` 不一致（尤其 DB 编号不同），或 Worker 副本为 0；用第 7.3 节的命令逐字符比对 |
| 任务被重复执行 / 结果错乱 | 多实例指向不同 Redis DB，分布式锁各管各的；统一 DB 编号 |
| `/api/v1/exec` 返回 503「未配置代码执行后端」 | 集群 Pod 内没有 docker daemon/socket，`executor.backend=docker` 不可用。保持 `config.executorBackend=none`；需要代码实跑请把 `local` 后端部署到可信节点，或单独跑一个带 docker socket 的 runner |
| `CreateContainerConfigError: secret "xxx" not found` | 设了 `secrets.existingSecret` 但没建对应 Secret，或键名不匹配（需 `OPENCGP_*` 大写键，且 HA 下必须含 `OPENCGP_DATABASE_DSN`） |
| 后端启动报 `未配置 OPENCGP_DATABASE_DSN` | 用了 `secrets.existingSecret` 但外部 Secret 缺 DSN；Chart 自己管理 Secret 时不会出现 |
| PostgreSQL 报 `too many clients` | `(api.replicas + worker.replicas) * pool_size` 超限；调小 `config.databasePoolSize` 或上 PgBouncer |
| 向量检索报 `type "vector" does not exist` | 外部 PG 未启用 `pgvector` 扩展，或当前账号无权 `CREATE EXTENSION` |
| 前端 502 / `/api` 打不通 | 确认 Service 名与模式匹配（HA 是 `*-api`，单机是 `*-backend`，Chart 已自动关联），以及 `api.service.port` 与容器端口一致 |
| 页面刷新 404 | nginx 已配 `try_files $uri $uri/ /index.html`；若自行替换镜像请保留该规则 |
| 上传文档 413 | 调大 `frontend.clientMaxBodySize`（默认 32m），并确认 Ingress 的 `proxy-body-size` |
| 任务 SSE 卡住不刷新 | Ingress 默认缓冲；Chart 的 nginx 已 `proxy_buffering off`，若前置还有一层 LB/Ingress 需同样关闭缓冲并调大 `proxy-read-timeout` |
| 上传/导出报 `Read-only file system` | 根文件系统只读；写盘只能走 `/data`（仅单机）与 `/tmp`，自定义路径请加 `backend.extraVolumes` |
| PDF 中文变方块 | 镜像缺少 NotoSansSC；把字体放进镜像并设 `OPENCGP_EXPORTER_FONT_REGULAR` / `_FONT_BOLD` |
| rustfs Pod CrashLoopBackOff | `rustfs.image.tag` 默认 `latest`，请按实际发布版固定；并用 `kubectl logs` 确认 `args` 与镜像 CLI 一致 |
| HPA 显示 `<unknown>/70%` | Pod 未设置 `resources.requests.cpu`（Chart 默认已设），或 metrics-server 未就绪 |
| `metric=queue` 的 Worker HPA 不扩 | prometheus-adapter 未配置 `opencgp_queue_backlog` 的 Pods 规则（见第 8.2 节） |
| 改名/换 namespace 后用户全部掉登录 | `OPENCGP_AUTH_SECRET` 变了；外部 Secret 场景请显式固定该值 |

排查命令：

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

## 15. 卸载

```bash
helm uninstall opencgp -n opencgp
```

`PVC` 与 `Secret` 带 `helm.sh/resource-policy: keep`，会保留下来；如需彻底清理：

```bash
kubectl -n opencgp delete pvc ocgp-opencgp-data
kubectl -n opencgp delete secret ocgp-opencgp-secret
```

StatefulSet 的 `volumeClaimTemplates` 产生的 PVC（`data-ocgp-opencgp-postgres-0`、`data-ocgp-opencgp-redis-0`、`data-ocgp-opencgp-rustfs-0`）在删 StatefulSet 后仍保留，需手动删除。

---

## 16. 部署前自检清单

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

应当确认：

- `mode=single`：出现 `backend` Deployment、内置 `postgres` StatefulSet，**不出现** `api` / `worker` Deployment；
- `mode=ha`：出现 `api`（`JOB_CONCURRENCY=0`）与 `worker`（`JOB_CONCURRENCY>0`）Deployment，**不出现** `backend` Deployment 与内置 `postgres` StatefulSet；
- `mode=ha` 且缺 `externalDatabase.dsn` 时 `helm template` 直接失败并给出可读错误；
- `OPENCGP_AUTH_SECRET` 与 `OPENCGP_DATABASE_DSN` 只出现在 Secret，绝不出现在 ConfigMap；
- 目标环境已有可用的 StorageClass、镜像仓库凭据，以及外部 PG / Redis / S3。
