#!/usr/bin/env bash
# Turn the study assistant's EC2 instance on or off from your own machine.
#
#   scripts/server.sh start    start it and wait until the app is ready
#   scripts/server.sh stop     stop it (compute billing stops; disk and IP charges continue)
#   scripts/server.sh status   show whether it's running and the app is healthy
#   scripts/server.sh deploy   rebuild and restart it from what's pushed to main (start it first)
#
# Always passes its own profile and region: the shell's AWS_PROFILE and AWS_REGION point elsewhere.
set -euo pipefail

PROFILE="${STUDY_AWS_PROFILE:-exam-rag-ops}"
REGION="${STUDY_AWS_REGION:-us-east-1}"
INSTANCE_NAME="${STUDY_INSTANCE_NAME:-study-assistant}"
SITE_URL="${STUDY_SITE_URL:-https://study.foxbet.ai}"
READY_TIMEOUT_SECONDS="${STUDY_READY_TIMEOUT_SECONDS:-300}"

DEPLOY_DOCUMENT="${STUDY_DEPLOY_DOCUMENT:-study-assistant-deploy}"
DEPLOY_TIMEOUT_SECONDS="${STUDY_DEPLOY_TIMEOUT_SECONDS:-3000}"

aws_ec2() {
  aws ec2 "$@" --profile "$PROFILE" --region "$REGION"
}

aws_ssm() {
  aws ssm "$@" --profile "$PROFILE" --region "$REGION"
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

deploy() {
  local id state command_id status waited=0
  id="$(instance_id)"
  state="$(instance_state "$id")"
  if [[ "$state" != "running" ]]; then
    echo "The instance is $state. Run: $0 start" >&2
    exit 1
  fi
  until [[ "$(aws_ssm describe-instance-information --filters "Key=InstanceIds,Values=$id" \
    --query 'InstanceInformationList[0].PingStatus' --output text)" == "Online" ]]; do
    if ((waited >= 120)); then
      echo "The server isn't accepting commands yet. Try again in a minute." >&2
      exit 1
    fi
    sleep 5
    waited=$((waited + 5))
  done

  command_id="$(aws_ssm send-command --instance-ids "$id" --document-name "$DEPLOY_DOCUMENT" \
    --comment "scripts/server.sh deploy" --query Command.CommandId --output text)"
  echo "Deploying (a rebuild takes a few minutes; longer if dependencies changed)..."
  waited=0
  while true; do
    status="$(aws_ssm get-command-invocation --command-id "$command_id" --instance-id "$id" \
      --query Status --output text 2>/dev/null || echo Pending)"
    case "$status" in
      Pending | InProgress | Delayed) ;;
      *) break ;;
    esac
    if ((waited >= DEPLOY_TIMEOUT_SECONDS)); then
      echo "Still running after ${waited}s; check later with: $0 status" >&2
      exit 1
    fi
    sleep 10
    waited=$((waited + 10))
  done

  aws_ssm get-command-invocation --command-id "$command_id" --instance-id "$id" \
    --query StandardOutputContent --output text
  if [[ "$status" != "Success" ]]; then
    aws_ssm get-command-invocation --command-id "$command_id" --instance-id "$id" \
      --query StandardErrorContent --output text >&2
    echo "Deploy $status. The previous version is still running unless the log says otherwise." >&2
    exit 1
  fi
  if app_is_healthy; then
    echo "Deployed: $SITE_URL"
  else
    echo "Deployed, but $SITE_URL/api/health isn't answering yet." >&2
    exit 1
  fi
}

case "${1:-}" in
  start | stop | status | deploy) "$1" ;;
  *)
    echo "Usage: $0 {start|stop|status|deploy}" >&2
    exit 2
    ;;
esac
