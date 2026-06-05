{{- define "isochrone.image" -}}
{{ .Values.image.registry }}/{{ .Values.image.repository }}:{{ .Values.image.tag }}
{{- end -}}

{{- define "isochrone.ns" -}}
{{ .Values.namespace }}
{{- end -}}

{{/*
Shared DB env block. Usage: {{ include "isochrone.dbEnv" . | nindent 8 }}
*/}}
{{- define "isochrone.dbEnv" -}}
- name: DB_USER
  valueFrom:
    secretKeyRef:
      name: postgres-secret
      key: POSTGRES_USER
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: postgres-secret
      key: POSTGRES_PASSWORD
- name: DB_NAME
  value: postgres
- name: DB_HOST
  value: postgres-service
- name: DB_PORT
  value: "5432"
{{- end -}}
