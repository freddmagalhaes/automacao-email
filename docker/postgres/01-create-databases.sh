#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  --set=n8n_password="$N8N_DB_PASSWORD" \
  --set=automation_password="$AUTOMATION_DB_PASSWORD" \
  --set=app_password="$APP_DB_PASSWORD" <<'SQL'
CREATE ROLE n8n_app LOGIN PASSWORD :'n8n_password';
CREATE ROLE automacao_app LOGIN PASSWORD :'automation_password';
CREATE ROLE painel_app LOGIN PASSWORD :'app_password';
CREATE DATABASE n8n OWNER n8n_app;
CREATE DATABASE atendimento OWNER postgres;
REVOKE CONNECT ON DATABASE n8n FROM PUBLIC;
GRANT CONNECT ON DATABASE n8n TO n8n_app;
REVOKE CONNECT ON DATABASE atendimento FROM PUBLIC;
GRANT CONNECT ON DATABASE atendimento TO automacao_app, painel_app;
SQL
