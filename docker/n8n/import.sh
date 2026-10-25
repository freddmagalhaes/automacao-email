#!/bin/sh
set -eu
marker=/home/node/.n8n/.email-test-import-v1
if [ -f "$marker" ]; then
  echo 'Bootstrap já executado; fluxos e credenciais existentes foram preservados.'
  exit 0
fi
umask 077
trap 'rm -f /tmp/email-credentials.json' EXIT
node /bootstrap/credentials.mjs
n8n import:credentials --input=/tmp/email-credentials.json
n8n import:workflow --separate --input=/workflows
touch "$marker"
echo 'Fluxos importados DESATIVADOS. Configure Gmail/Gemini antes de publicar.'
