#!/usr/bin/env bash
# Runs on the instance as root: updates the code, fetches the secrets, rebuilds and restarts.
# Everything is inside main() because the git reset below can rewrite this file while it runs;
# bash reads a whole function before running it, so the rest of the old version still runs as is.
set -euo pipefail

REPO_DIR=/opt/study-assistant
REGION=us-east-1
LOG=/var/log/study-assistant-deploy.log

main() {
  cd "$REPO_DIR"
  git fetch origin main
  git reset --hard origin/main
  echo "Deploying $(git log --oneline -1)"

  # Through a pipe on purpose: redirecting the snap AWS CLI straight to a file wrote 0 bytes and
  # still exited 0. The check below catches an empty file before it can take the API down.
  umask 077
  /snap/bin/aws ssm get-parameter --region "$REGION" --name /study-assistant/env \
    --with-decryption --query Parameter.Value --output text | cat >backend/.env
  if ! grep -q '^API_PASSWORD=.' backend/.env; then
    echo "backend/.env has no API_PASSWORD; not restarting." >&2
    exit 1
  fi
  umask 022

  # A failed build exits here, and the containers already running are left alone.
  if ! docker compose up -d --build >"$LOG" 2>&1; then
    echo "Build or start failed; the previous version is still running. Last lines of $LOG:" >&2
    tail -25 "$LOG" >&2
    exit 1
  fi
  docker image prune -f >/dev/null

  local waited=0
  until [[ "$(docker inspect study-assistant-api-1 --format '{{.State.Health.Status}}')" == healthy ]]; do
    if ((waited >= 300)); then
      echo "The API isn't healthy after ${waited}s. Last log lines:" >&2
      docker compose logs --tail 20 api >&2
      exit 1
    fi
    sleep 5
    waited=$((waited + 5))
  done
  echo "Healthy after about ${waited}s."
  df -h / | tail -1
}

main "$@"
