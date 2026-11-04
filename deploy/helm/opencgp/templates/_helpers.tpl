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

{{- define "opencgp.backendHost" -}}
{{- printf "%s-backend" (include "opencgp.fullname" .) -}}
{{- end -}}

{{- define "opencgp.redisHost" -}}
{{- printf "%s-redis" (include "opencgp.fullname" .) -}}
{{- end -}}

{{- define "opencgp.rustfsHost" -}}
{{- printf "%s-rustfs" (include "opencgp.fullname" .) -}}
{{- end -}}

{{- define "opencgp.redisUrl" -}}
{{- if .Values.config.redisUrl -}}
{{- .Values.config.redisUrl -}}
{{- else if .Values.redis.enabled -}}
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
{{- if .Values.config.s3Endpoint -}}
{{- .Values.config.s3Endpoint -}}
{{- else if .Values.rustfs.enabled -}}
{{- printf "http://%s:%v" (include "opencgp.rustfsHost" .) .Values.rustfs.service.port -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end -}}

{{- define "opencgp.backendSecretMount" -}}
{{- include "opencgp.secretName" . -}}
{{- end -}}

{{- define "opencgp.startupFailureThreshold" -}}
{{- div (add (int .Values.backend.probe.startupSeconds) 2) 3 -}}
{{- end -}}
