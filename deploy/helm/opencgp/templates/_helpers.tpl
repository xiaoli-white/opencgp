{{- define "opencgp.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "opencgp.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "opencgp.labels" -}}
helm.sh/chart: {{ include "opencgp.chart" . }}
{{ include "opencgp.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: opencgp
{{- end -}}

{{- define "opencgp.selectorLabels" -}}
app.kubernetes.io/name: {{ include "opencgp.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "opencgp.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "opencgp.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.configMapName" -}}
{{- printf "%s-config" (include "opencgp.fullname" .) -}}
{{- end -}}

{{- define "opencgp.nginxConfigMapName" -}}
{{- printf "%s-nginx" (include "opencgp.fullname" .) -}}
{{- end -}}

{{- define "opencgp.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- printf "%s-secret" (include "opencgp.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.backendName" -}}
{{- printf "%s-backend" (include "opencgp.fullname" .) -}}
{{- end -}}

{{- define "opencgp.apiName" -}}
{{- printf "%s-api" (include "opencgp.fullname" .) -}}
{{- end -}}

{{- define "opencgp.workerName" -}}
{{- printf "%s-worker" (include "opencgp.fullname" .) -}}
{{- end -}}

{{- define "opencgp.postgresName" -}}
{{- printf "%s-postgres" (include "opencgp.fullname" .) -}}
{{- end -}}

{{- define "opencgp.apiWorkloadName" -}}
{{- if eq .Values.mode "ha" -}}
{{- include "opencgp.apiName" . -}}
{{- else -}}
{{- include "opencgp.backendName" . -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.apiWorkloadEnabled" -}}
{{- true -}}
{{- end -}}

{{- define "opencgp.workerWorkloadEnabled" -}}
{{- if .Values.worker.enabled -}}
{{- if or (eq .Values.mode "ha") .Values.worker.autoscaling.enabled -}}
{{- true -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.backendHost" -}}
{{- if eq .Values.mode "ha" -}}
{{- include "opencgp.apiName" . -}}
{{- else -}}
{{- include "opencgp.backendName" . -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.redisHost" -}}
{{- printf "%s-redis" (include "opencgp.fullname" .) -}}
{{- end -}}

{{- define "opencgp.rustfsHost" -}}
{{- printf "%s-rustfs" (include "opencgp.fullname" .) -}}
{{- end -}}

{{- define "opencgp.postgresHost" -}}
{{- include "opencgp.postgresName" . -}}
{{- end -}}

{{- define "opencgp.postgresPort" -}}
{{- 5432 -}}
{{- end -}}

{{- define "opencgp.builtinPostgresEnabled" -}}
{{- if and .Values.postgres.enabled (eq .Values.mode "single") -}}
{{- true -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.databaseDsn" -}}
{{- if .Values.externalDatabase.enabled -}}
{{- required "externalDatabase.enabled=true 时必须设置 externalDatabase.dsn（形如 postgresql://user:password@host:5432/dbname）" .Values.externalDatabase.dsn -}}
{{- else if .Values.externalDatabase.dsn -}}
{{- .Values.externalDatabase.dsn -}}
{{- else if and .Values.postgres.enabled (eq .Values.mode "single") -}}
{{- $creds := .Values.postgres.credentials -}}
{{- printf "postgresql://%s:%s@%s:%v/%s" $creds.user $creds.password (include "opencgp.postgresHost" .) (include "opencgp.postgresPort" .) $creds.database -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.redisUrl" -}}
{{- if .Values.externalRedis.enabled -}}
{{- required "externalRedis.enabled=true 时必须设置 externalRedis.url（形如 redis://:password@host:6379/0）" .Values.externalRedis.url -}}
{{- else if .Values.externalRedis.url -}}
{{- .Values.externalRedis.url -}}
{{- else if .Values.config.redisUrl -}}
{{- .Values.config.redisUrl -}}
{{- else if and .Values.redis.enabled (eq .Values.mode "single") -}}
{{- if and .Values.redis.auth.enabled .Values.redis.auth.password -}}
{{- printf "redis://:%s@%s:%v/0" .Values.redis.auth.password (include "opencgp.redisHost" .) .Values.redis.service.port -}}
{{- else -}}
{{- printf "redis://%s:%v/0" (include "opencgp.redisHost" .) .Values.redis.service.port -}}
{{- end -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.s3Endpoint" -}}
{{- if .Values.externalS3.enabled -}}
{{- required "externalS3.enabled=true 时必须设置 externalS3.endpoint（形如 https://s3.us-east-1.amazonaws.com 或 http://minio:9000）" .Values.externalS3.endpoint -}}
{{- else if .Values.externalS3.endpoint -}}
{{- .Values.externalS3.endpoint -}}
{{- else if .Values.config.s3Endpoint -}}
{{- .Values.config.s3Endpoint -}}
{{- else if and .Values.rustfs.enabled (eq .Values.mode "single") -}}
{{- printf "http://%s:%v" (include "opencgp.rustfsHost" .) .Values.rustfs.service.port -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.s3Bucket" -}}
{{- if .Values.externalS3.enabled -}}
{{- .Values.externalS3.bucket | default .Values.config.s3Bucket -}}
{{- else -}}
{{- .Values.config.s3Bucket -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.s3Region" -}}
{{- if .Values.externalS3.enabled -}}
{{- .Values.externalS3.region | default .Values.config.s3Region -}}
{{- else -}}
{{- .Values.config.s3Region -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.s3Prefix" -}}
{{- if .Values.externalS3.enabled -}}
{{- .Values.externalS3.prefix | default .Values.config.s3Prefix -}}
{{- else -}}
{{- .Values.config.s3Prefix -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.s3AccessKey" -}}
{{- if and .Values.externalS3.enabled .Values.externalS3.accessKey -}}
{{- .Values.externalS3.accessKey -}}
{{- else -}}
{{- .Values.secrets.s3AccessKey -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.s3SecretKey" -}}
{{- if and .Values.externalS3.enabled .Values.externalS3.secretKey -}}
{{- .Values.externalS3.secretKey -}}
{{- else -}}
{{- .Values.secrets.s3SecretKey -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.validate" -}}
{{- if not (has .Values.mode (list "single" "ha")) -}}
{{- fail (printf "mode 只能是 single 或 ha，当前为 %q" (toString .Values.mode)) -}}
{{- end -}}
{{- if eq .Values.mode "ha" -}}
{{- if not .Values.externalDatabase.dsn -}}
{{- fail "mode=ha 必须提供 externalDatabase.dsn（例如 --set externalDatabase.dsn=postgresql://opencgp:pass@pg.database.svc:5432/opencgp）。Chart 在 HA 模式下不内置 PostgreSQL" -}}
{{- end -}}
{{- if not (include "opencgp.redisUrl" .) -}}
{{- fail "mode=ha 必须提供外部 Redis（--set externalRedis.url=redis://host:6379/0），且所有 API/Worker 实例必须指向同一个 Redis DB" -}}
{{- end -}}
{{- if not (include "opencgp.s3Endpoint" .) -}}
{{- fail "mode=ha 必须提供外部对象存储（--set externalS3.enabled=true --set externalS3.endpoint=https://s3.example.com）" -}}
{{- end -}}
{{- if not .Values.worker.enabled -}}
{{- fail "mode=ha 必须保持 worker.enabled=true：api.jobConcurrency=0 时若没有 Worker 就没有任何实例消费队列" -}}
{{- end -}}
{{- if ne (int .Values.api.jobConcurrency) 0 -}}
{{- fail "mode=ha 要求 api.jobConcurrency=0（API 节点只处理 HTTP，不消费任务）；消费者并发请配置 worker.jobConcurrency" -}}
{{- end -}}
{{- end -}}
{{- if and (eq .Values.config.databaseBackend "postgres") (not (include "opencgp.databaseDsn" .)) -}}
{{- fail "databaseBackend=postgres 但没有可用的 DSN：请启用内置 postgres（postgres.enabled=true，仅 single）或设置 externalDatabase.dsn" -}}
{{- end -}}
{{- if and (eq .Values.config.queueBackend "redis") (not (include "opencgp.redisUrl" .)) -}}
{{- fail "queueBackend=redis 但没有可用的 Redis URL：请启用内置 redis（redis.enabled=true，仅 single）、设置 config.redisUrl 或 externalRedis.url" -}}
{{- end -}}
{{- if and (eq .Values.config.storageBackend "s3") (not (include "opencgp.s3Endpoint" .)) -}}
{{- fail "storageBackend=s3 但没有可用的 endpoint：请启用内置 rustfs（rustfs.enabled=true，仅 single）、设置 config.s3Endpoint 或 externalS3.endpoint" -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.startupFailureThreshold" -}}
{{- div (add (int .Values.backend.probe.startupSeconds) 2) 3 -}}
{{- end -}}

{{- define "opencgp.apiStartupFailureThreshold" -}}
{{- div (add (int .Values.api.probe.startupSeconds) 2) 3 -}}
{{- end -}}

{{- define "opencgp.workerStartupFailureThreshold" -}}
{{- div (add (int .Values.api.probe.startupSeconds) 2) 3 -}}
{{- end -}}
