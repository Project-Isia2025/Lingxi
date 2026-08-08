{{- define "ai-agent-matrix.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "ai-agent-matrix.fullname" -}}
{{- printf "%s" (include "ai-agent-matrix.name" .) }}
{{- end }}

{{- define "ai-agent-matrix.labels" -}}
app.kubernetes.io/name: {{ include "ai-agent-matrix.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end }}

{{- define "ai-agent-matrix.selectorLabels" -}}
app: {{ include "ai-agent-matrix.name" . }}
{{- end }}
