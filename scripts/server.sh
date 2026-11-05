#!/usr/bin/env bash
# Turn the study assistant's EC2 instance on or off from your own machine.
#
#   scripts/server.sh start    start it and wait until the app is ready
#   scripts/server.sh stop     stop it (compute billing stops; disk and IP charges continue)
#   scripts/server.sh status   show whether it's running and the app is healthy
#
# Always passes its own profile and region: the shell's AWS_PROFILE and AWS_REGION point elsewhere.
set -euo pipefail

PROFILE="${STUDY_AWS_PROFILE:-exam-rag-ops}"
REGION="${STUDY_AWS_REGION:-us-east-1}"
INSTANCE_NAME="${STUDY_INSTANCE_NAME:-study-assistant}"
SITE_URL="${STUDY_SITE_URL:-https://study.foxbet.ai}"
READY_TIMEOUT_SECONDS="${STUDY_READY_TIMEOUT_SECONDS:-300}"

aws_ec2() {
  aws ec2 "$@" --profile "$PROFILE" --region "$REGION"
}

instance_id() {
  local id
  id="$(aws_ec2 describe-instances \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" \
    "Name=instance-state-name,Values=pending,running,stopping,stopped" \
    --query "Reservations[0].Instances[0].InstanceId" --output text)"
  if [[ -z "$id" || "$id" == "None" ]]; then
    echo "No instance named '$INSTANCE_NAME' in $REGION." >&2
    exit 1
  fi
  echo "$id"
}

instance_state() {
  aws_ec2 describe-instances --instance-ids "$1" \
    --query "Reservations[0].Instances[0].State.Name" --output text
}

app_is_healthy() {
  curl --silent --fail --max-time 5 --output /dev/null "$SITE_URL/api/health"
}

wait_until_ready() {
  local waited=0
  until app_is_healthy; do
    if ((waited >= READY_TIMEOUT_SECONDS)); then
      echo "The instance is on, but the app wasn't ready after ${READY_TIMEOUT_SECONDS}s." >&2
      echo "It's still costing money. Check it, or run: $0 stop" >&2
      exit 1
    fi
    sleep 5
    waited=$((waited + 5))
  done
}

start() {
  local id state
  id="$(instance_id)"
  state="$(instance_state "$id")"
  case "$state" in
    stopping)
      echo "Still stopping; waiting for that to finish."
      aws_ec2 wait instance-stopped --instance-ids "$id"
      ;;
  esac
  if [[ "$state" != "running" && "$state" != "pending" ]]; then
    echo "Starting $id..."
    aws_ec2 start-instances --instance-ids "$id" --output text >/dev/null
  fi
  aws_ec2 wait instance-running --instance-ids "$id"
  echo "Instance is running. Waiting for the app to warm up..."
  wait_until_ready
  echo "Ready: $SITE_URL"
}

stop() {
  local id
  id="$(instance_id)"
  echo "Stopping $id..."
  aws_ec2 stop-instances --instance-ids "$id" --output text >/dev/null
  aws_ec2 wait instance-stopped --instance-ids "$id"
  echo "Stopped. $SITE_URL is now offline."
}

status() {
  local id state
  id="$(instance_id)"
  state="$(instance_state "$id")"
  echo "Instance $id: $state"
  if [[ "$state" == "running" ]]; then
    if app_is_healthy; then
      echo "App: healthy at $SITE_URL"
    else
      echo "App: not responding yet at $SITE_URL"
    fi
  fi
}

case "${1:-}" in
  start | stop | status) "$1" ;;
  *)
    echo "Usage: $0 {start|stop|status}" >&2
    exit 2
    ;;
esac
