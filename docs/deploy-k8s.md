# OpenCGP 在 Kubernetes 上的部署指南

本指南对应 `deploy/helm/opencgp` 目录中的 Helm Chart（`version 0.1.0` / `appVersion 0.1.0`）。

Chart 会把整套 OpenCGP 拆成四类工作负载：

| 组件 | 资源 | 说明 |
|---|---|---|
| 后端 | Deployment + Service + PVC | FastAPI，端口 8000，`/health` 探针，`/metrics` 暴露 Prometheus 指标 |
| 前端 | Deployment + Service + ConfigMap | nginx 托管静态站点，同源反代 `/api` 到后端 |
| Redis | StatefulSet + headless Service | 任务队列与 SSE 事件总线，`--appendonly yes` |
| rustfs | StatefulSet + headless Service | S3 兼容对象存储，端口 9000 / 9001 |

---

## 1. 前置条件

- Kubernetes 1.24+（`autoscaling/v2`、`networking.k8s.io/v1` Ingress）
- Helm 3.12+（本 Chart 用 `lookup` 保留已生成的密钥，3.16.3 实测通过）
- 集群内有默认 StorageClass，或通过 `backend.persistence.storageClass` / `redis.persistence.storageClass` / `rustfs.persistence.storageClass` 显式指定
- 已构建并推送 `opencgp/backend` 与 `opencgp/frontend` 镜像（见第 2 节）
- （可选）Ingress Controller 与 Prometheus Operator

验证 Helm：

```bash
helm version
helm lint deploy/helm/opencgp
helm template opencgp deploy/helm/opencgp > /tmp/render.yaml
```

---

## 2. 构建镜像

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
- 运行时由 Chart 注入的 nginx 配置把 `/api` 反代到 `{release}-backend:8000`，因此浏览器只发同源请求，不需要 CORS，也不需要把后端地址写进前端。
- 后端镜像内置 `libcairo/libpango`（PDF 导出依赖）。中文字体需自行随镜像带入，并通过 `COURSE_STUDIO_EXPORTER_FONT_REGULAR` / `_FONT_BOLD` 指向 `.ttf` 路径，否则导出的 PDF 中文会缺字。
- 后端容器以非 root（uid 10001）运行且根文件系统只读，因此写盘目录只有 PVC（`/data`）与 `emptyDir`（`/tmp`）；Chart 已注入 `XDG_CACHE_HOME=/tmp/.cache`、`HOME=/tmp`。

---

## 3. 快速安装

最小安装（内置 Redis + rustfs，SQLite 落到 PVC，单副本）：

```bash
helm install opencgp deploy/helm/opencgp \
  --namespace opencgp --create-namespace \
  --set backend.image.repository=registry.example.com/opencgp/backend \
  --set frontend.image.repository=registry.example.com/opencgp/frontend \
  --set ingress.enabled=true \
  --set ingress.className=nginx \
  --set ingress.hosts[0].host=opencgp.example.com
```

带自定义值的安装：

```bash
helm install opencgp deploy/helm/opencgp -n opencgp --create-namespace -f my-values.yaml
```

访问：

```bash
kubectl -n opencgp port-forward svc/opencgp-frontend 8080:80
curl -s http://127.0.0.1:8080/health
```

首次使用：`config.authMode=required` 时，**第一个注册的账号会自动置为 active 并成为 owner**（引导逻辑），后续注册用户默认 `pending`，需管理员在 `/api/v1/admin/users?status=pending` 审核通过后才能登录（`config.requireApproval` 控制）。

---

## 4. values 关键项

| 键 | 默认值 | 说明 |
|---|---|---|
| `backend.image.repository` / `.tag` | `opencgp/backend` / `0.1.0` | 后端镜像 |
| `backend.replicas` | `1` | 后端副本数；>1 受限（见第 6 节） |
| `backend.persistence.enabled` | `true` | 挂载 `/data`（SQLite + 向量库 + 本地对象存储） |
| `backend.persistence.existingClaim` | `""` | 复用已有 PVC |
| `backend.podAnnotations` | `prometheus.io/scrape=true` 等 | Prometheus 抓取注解 |
| `backend.probe.startupSeconds` | `30` | startupProbe 预算（换算为 `failureThreshold=10, periodSeconds=3`） |
| `frontend.containerPort` | `8080` | nginx 监听端口（非 root 不能绑 80） |
| `frontend.apiPrefix` | `/api` | nginx 反代路径前缀，需与 `VITE_API_BASE` 一致 |
| `redis.enabled` | `true` | 关闭后 `COURSE_STUDIO_REDIS_URL` 置空，队列自动回落 local |
| `redis.auth.enabled` | `false` | 开启后自动写进 `COURSE_STUDIO_REDIS_URL` |
| `rustfs.enabled` | `true` | 关闭后需自行提供 `config.s3Endpoint` |
| `config.authMode` | `required` | `disabled` 时隐式 owner、免登录（仅本地自用） |
| `config.requireApproval` | `"true"` | 注册是否需要管理员审核 |
| `config.queueBackend` | `redis` | `local` / `redis` |
| `config.storageBackend` | `s3` | `local` / `s3` / `rustfs` |
| `config.executorBackend` | `none` | 集群内没有 docker socket，保持 none（见第 9 节） |
| `config.jobConcurrency` | `2` | 单实例 worker 并发度 |
| `config.s3Endpoint` / `s3Bucket` / `s3Region` / `s3Prefix` | 空 / `course-studio` / `us-east-1` / `tenants` | 留空时自动指向内置 rustfs Service |
| `secrets.existingSecret` | `""` | 使用外部 Secret，Chart 不再渲染 Secret |
| `secrets.authSecret` | `""` | 留空自动生成 48 位随机串，并用 `lookup` 保持已存在的值不被轮换 |
| `ingress.enabled` / `className` / `hosts` / `tls` | `false` | Ingress 指向 frontend Service |
| `autoscaling.enabled` | `false` | HPA 按 CPU 70% 扩缩后端（`minReplicas` / `maxReplicas`） |
| `networkPolicy.enabled` | `false` | 限制 backend / redis / rustfs 的入站来源 |

> `values.yaml` 顶层的 `notes` 字段是纯说明性文本，Helm 会原样保留，不会渲染进任何资源。

---

## 5. 密钥管理

默认情况下 Chart 自己生成并管理 Secret（`{release}-secret`）：

| Key | 来源 |
|---|---|
| `COURSE_STUDIO_AUTH_SECRET` | `randAlphaNum 48`，`lookup` 保留旧值 |
| `COURSE_STUDIO_S3_ACCESS_KEY` / `_SECRET_KEY` | 可显式指定，否则随机生成 |
| `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` | 与上面同值，供 rustfs 使用 |
| `COURSE_STUDIO_LLM_API_KEY` / `_IMAGE_API_KEY` / `_WEBSEARCH_API_KEY` | 仅当 `secrets.*ApiKey` 非空时写入 |

读取自动生成的管理密钥：

```bash
kubectl -n opencgp get secret opencgp-secret -o jsonpath='{.data.COURSE_STUDIO_AUTH_SECRET}' | base64 -d
```

生产环境推荐用外部 Secret（SealedSecret / External Secrets / Vault）：

```bash
kubectl -n opencgp create secret generic opencgp-secrets \
  --from-literal=COURSE_STUDIO_AUTH_SECRET="$(openssl rand -base64 36)" \
  --from-literal=COURSE_STUDIO_S3_ACCESS_KEY=xxx \
  --from-literal=COURSE_STUDIO_S3_SECRET_KEY=yyy \
  --from-literal=COURSE_STUDIO_LLM_API_KEY=sk-xxx

helm upgrade --install opencgp deploy/helm/opencgp -n opencgp \
  --set secrets.existingSecret=opencgp-secrets
```

注意：`secrets.existingSecret` 生效时，Chart 不再渲染 Secret，也不会做任何 `lookup` 保留逻辑——轮换完全由外部系统负责。`COURSE_STUDIO_AUTH_SECRET` 一旦变化，所有已签发的 token 立即失效（用户需重新登录）。

Secret 带 `helm.sh/resource-policy: keep`，`helm uninstall` 不会删除它，便于原地重装时保持 token 有效。为避免密钥泄漏，**永远不要把敏感值写进 `values.yaml` 提交到仓库**，用 `--set` / `--set-file` / 外部 Secret。

---

## 6. 外部依赖（PostgreSQL / Redis / S3）

### 6.1 Redis

```yaml
redis:
  enabled: false
config:
  queueBackend: redis
  redisUrl: redis://:password@redis-master.cache.svc.cluster.local:6379/0
```

多副本后端必须共用同一个 Redis：任务在实例 A 提交、实例 B 的 SSE 也能收到事件（Pub/Sub 广播）。

### 6.2 对象存储

```yaml
rustfs:
  enabled: false
config:
  storageBackend: s3
  s3Endpoint: https://s3.us-east-1.amazonaws.com
  s3Bucket: my-opencgp
  s3Region: us-east-1
  s3Prefix: tenants
secrets:
  s3AccessKey: ...
  s3SecretKey: ...
```

适配器是 S3 兼容协议 + path-style 寻址；MinIO / rustfs / 阿里云 OSS（S3 兼容模式）都可直接对接。桶不存在时首次使用会自动 `PUT bucket`。

### 6.3 PostgreSQL

`config.databaseBackend` 支持填 `postgres`，但当前代码库只落地了 SQLite adapter（`app/adapters/database/sqlite.py`），填 `postgres` 会在构造 repository 时抛错。因此：

- 单副本：保持 `databaseBackend: sqlite` + PVC；
- 多副本：需先实现 PostgreSQL adapter（Database 端口已抽象，新增 adapter 即可），再关闭 `backend.persistence.enabled`。

这是当前 Chart 唯一无法用纯配置绕过的限制，见第 9 节。

---

## 7. 升级与回滚

```bash
helm upgrade opencgp deploy/helm/opencgp -n opencgp -f my-values.yaml
helm history opencgp -n opencgp
helm rollback opencgp 2 -n opencgp
```

- 后端 Pod 模板带 `checksum/config`、`checksum/secret` 注解：改 ConfigMap / Secret 会自动滚动重启。
- `backend.replicas <= 1` 且持久化开启时策略为 `Recreate`（避免 RWO PVC 被两个 Pod 同时挂载）；否则为 `RollingUpdate`（`maxSurge=1, maxUnavailable=0`）。
- 回滚 Chart 版本不会回滚数据（PVC 带 `helm.sh/resource-policy: keep`）。

---

## 8. 指标采集

后端 Pod 已带注解：

```yaml
prometheus.io/scrape: "true"
prometheus.io/port: "8000"
prometheus.io/path: "/metrics"
```

Prometheus 用注解式抓取（kubernetes-pods job）即可，无需 ServiceMonitor。若用 Prometheus Operator，可直接加 `ServiceMonitor`：

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: opencgp-backend
  namespace: opencgp
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: opencgp
      app.kubernetes.io/component: backend
  endpoints:
    - port: http
      path: /metrics
      interval: 30s
```

关键指标：

| 指标 | 含义 |
|---|---|
| `opencgp_http_requests_total{method,route,status}` | 请求量与错误率 |
| `opencgp_http_request_duration_seconds{route}` | 延迟直方图 |
| `opencgp_jobs_total{kind,status}` / `opencgp_jobs_active` | 异步任务成功率与并发 |
| `opencgp_queue_backlog` | 队列积压（Redis LLEN） |
| `opencgp_adapter_up{name}` | 各 adapter 探活 |
| `opencgp_quota_usage{kind}` | 配额用量 |
| `opencgp_exec_runs_total{backend,result}` | 代码沙箱执行结果 |

注意：前端 nginx 对 `/metrics` 显式 `deny all`，指标只从 Pod 内网抓取，不经 Ingress 暴露。

把 ConfigMap 里的 `config.authMode` 从 `required` 切成 `disabled` 会让所有接口免鉴权，**严禁在生产开启**。

---

## 9. 常见故障

| 现象 | 原因与处理 |
|---|---|
| `/api/v1/exec` 返回 503「未配置代码执行后端」 | 集群 Pod 内没有 docker daemon/socket，`executor.backend=docker` 不可用。保持 `config.executorBackend=none`；需要代码实跑请把 `local` 后端部署到可信节点，或单独跑一个带 docker socket 的 runner 并让后端通过 HTTP 调用 |
| `helm upgrade` 后仍连旧 Redis / 旧桶 | 检查是否用了 `--reuse-values` 覆盖掉新 Values；`helm diff` 对比渲染结果 |
| Pod `CreateContainerConfigError: secret "xxx" not found` | 设了 `secrets.existingSecret` 但没建对应 Secret，或键名不匹配（需 `COURSE_STUDIO_*` 大写键） |
| 前端 502 / `/api` 打不通 | 后端 Service 名与 nginx 配置不匹配（Chart 已按 `{release}-backend` 生成）；确认 `backend.service.port` 与容器监听端口一致 |
| 页面刷新 404 | nginx 已配 `try_files $uri $uri/ /index.html`；若自行替换镜像请保留该规则 |
| 上传文档 413 | 调大 `frontend.clientMaxBodySize`（默认 32m），并确认 Ingress 的 `proxy-body-size` |
| 任务 SSE 卡住不刷新 | Ingress 默认缓冲；Chart 的 nginx 已 `proxy_buffering off`，若前置还有一层 LB/Ingress 需同样关闭缓冲并调大 `proxy-read-timeout` |
| 上传/导出报 `Read-only file system` | 根文件系统只读；写盘只能走 `/data` 与 `/tmp`，自定义路径请加 `backend.extraVolumes` |
| PDF 中文变方块 | 镜像缺少 NotoSansSC；把字体放进镜像并设 `COURSE_STUDIO_EXPORTER_FONT_REGULAR` / `_FONT_BOLD` |
| rustfs Pod CrashLoopBackOff | `rustfs.image.tag` 默认 `latest`，请按实际发布版固定；并用 `kubectl logs` 确认 `args`（`--address` / `--console-address`）与镜像 CLI 一致 |
| SQLite `database is locked` | 多副本同时挂 PVC；把 `backend.replicas` 设回 1（见第 6.3 节） |
| 改名/换 namespace 后用户全部掉登录 | `COURSE_STUDIO_AUTH_SECRET` 变了；外部 Secret 场景请显式固定该值 |

排查命令：

```bash
kubectl -n opencgp get pods -o wide
kubectl -n opencgp logs deploy/opencgp-backend --tail=200
kubectl -n opencgp exec -it deploy/opencgp-backend -- python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read()[:200])"
kubectl -n opencgp port-forward svc/opencgp-backend 8000:8000 &
curl -s http://127.0.0.1:8000/health | python -m json.tool
```

---

## 10. 卸载

```bash
helm uninstall opencgp -n opencgp
```

`PVC` 与 `Secret` 带 `helm.sh/resource-policy: keep`，会保留下来；如需彻底清理：

```bash
kubectl -n opencgp delete pvc opencgp-data
kubectl -n opencgp delete secret opencgp-secret
```

StatefulSet 的 `volumeClaimTemplates` 产生的 PVC（`data-opencgp-redis-0`、`data-opencgp-rustfs-0`）在删 StatefulSet 后仍保留，需手动删除。

---

## 11. 部署前自检清单

```bash
helm lint deploy/helm/opencgp
helm template opencgp deploy/helm/opencgp --set ingress.enabled=true --set autoscaling.enabled=true > /tmp/render.yaml
helm template opencgp deploy/helm/opencgp --set secrets.existingSecret=opencgp-secrets --set backend.replicas=3 > /tmp/render-r3.yaml

python - <<'PY'
import yaml, collections
docs=[d for d in yaml.safe_load_all(open('/tmp/render.yaml')) if d]
print(collections.Counter(d['kind'] for d in docs))
PY
```

应当确认：

- 默认渲染包含 2 个 Deployment、2 个 StatefulSet、4 个 Service、2 个 ConfigMap、1 个 Secret、1 个 ServiceAccount、1 个 PVC；
- 关闭 `redis.enabled` / `rustfs.enabled` 后渲染结果里不再出现对应 StatefulSet；
- `COURSE_STUDIO_AUTH_SECRET` 只出现在 Secret，绝不出现在 ConfigMap；
- 目标环境已有可用的 StorageClass 与镜像仓库凭据。
