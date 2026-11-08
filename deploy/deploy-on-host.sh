#!/usr/bin/env bash
# Runs on the instance as root: updates the code, fetches the secrets, rebuilds and restarts.
set -euo pipefail

REPO_DIR=/opt/study-assistant
REGION=us-east-1

cd "$REPO_DIR"
git fetch origin main
git reset --hard origin/main

# Through a pipe on purpose: redirecting the snap AWS CLI straight to a file wrote 0 bytes and
# still exited 0. The check below catches an empty file before it can take the API down.
umask 077
/snap/bin/aws ssm get-parameter --region "$REGION" --name /study-assistant/env --with-decryption \
  --query Parameter.Value --output text | cat >backend/.env
if ! grep -q '^API_PASSWORD=.' backend/.env; then
  echo "backend/.env has no API_PASSWORD; not restarting." >&2
  exit 1
fi
umask 022

docker compose up -d --build
docker image prune -f
