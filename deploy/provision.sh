#!/usr/bin/env bash
# One-time AWS setup for study.foxbet.ai. Safe to rerun: anything that exists is left alone.
# Needs an admin profile (never root). Charges start once the instance is created.
#
#   ADMIN_PROFILE=exam-rag-admin deploy/provision.sh
set -euo pipefail

ADMIN_PROFILE="${ADMIN_PROFILE:-exam-rag-admin}"
REGION=us-east-1
NAME=study-assistant
ROLE="$NAME-instance"
OPS_USER=exam-rag-ops
MODEL=anthropic.claude-haiku-4-5-20251001-v1:0
DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"

a() { aws "$@" --profile "$ADMIN_PROFILE" --region "$REGION"; }

ACCOUNT="$(a sts get-caller-identity --query Account --output text)"
if a sts get-caller-identity --query Arn --output text | grep -q ':root$'; then
  echo "Refusing to run with root credentials." >&2
  exit 1
fi

# ---------------------------------------------------------------- firewall
VPC="$(a ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
SUBNET="$(a ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC" Name=availability-zone,Values=us-east-1a \
  Name=default-for-az,Values=true --query 'Subnets[0].SubnetId' --output text)"
SG="$(a ec2 describe-security-groups --filters "Name=group-name,Values=$NAME" "Name=vpc-id,Values=$VPC" \
  --query 'SecurityGroups[0].GroupId' --output text)"
if [[ "$SG" == "None" ]]; then
  SG="$(a ec2 create-security-group --group-name "$NAME" --vpc-id "$VPC" \
    --description "Study assistant: web traffic only, no SSH" --query GroupId --output text)"
  a ec2 authorize-security-group-ingress --group-id "$SG" --ip-permissions \
    'IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0}],Ipv6Ranges=[{CidrIpv6=::/0}]' \
    'IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0}],Ipv6Ranges=[{CidrIpv6=::/0}]' \
    'IpProtocol=udp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0}],Ipv6Ranges=[{CidrIpv6=::/0}]' \
    >/dev/null
fi
echo "Security group: $SG"

# ---------------------------------------------------------------- instance role
if ! a iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  a iam create-role --role-name "$ROLE" --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}]
  }' >/dev/null
  a iam attach-role-policy --role-name "$ROLE" \
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
fi
a iam put-role-policy --role-name "$ROLE" --policy-name invoke-haiku-and-read-env --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {\"Effect\": \"Allow\",
     \"Action\": [\"bedrock:InvokeModel\", \"bedrock:InvokeModelWithResponseStream\"],
     \"Resource\": [
       \"arn:aws:bedrock:*::foundation-model/$MODEL\",
       \"arn:aws:bedrock:$REGION:$ACCOUNT:inference-profile/us.$MODEL\"
     ]},
    {\"Effect\": \"Allow\",
     \"Action\": \"ssm:GetParameter\",
     \"Resource\": \"arn:aws:ssm:$REGION:$ACCOUNT:parameter/$NAME/*\"}
  ]
}"
if ! a iam get-instance-profile --instance-profile-name "$ROLE" >/dev/null 2>&1; then
  a iam create-instance-profile --instance-profile-name "$ROLE" >/dev/null
  a iam add-role-to-instance-profile --instance-profile-name "$ROLE" --role-name "$ROLE"
fi
echo "Instance role: $ROLE"

# ---------------------------------------------------------------- instance
INSTANCE="$(a ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" \
  Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)"
if [[ "$INSTANCE" == "None" ]]; then
  AMI="$(a ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
    --query Parameter.Value --output text)"
  # A new instance profile can take a few seconds to become usable.
  for attempt in 1 2 3 4 5 6 7 8; do
    if INSTANCE="$(a ec2 run-instances --image-id "$AMI" --instance-type t3.large --subnet-id "$SUBNET" \
      --security-group-ids "$SG" --iam-instance-profile "Name=$ROLE" \
      --instance-initiated-shutdown-behavior stop \
      --metadata-options 'HttpTokens=required,HttpPutResponseHopLimit=2,HttpEndpoint=enabled' \
      --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=40,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
      "ResourceType=volume,Tags=[{Key=Name,Value=$NAME}]" \
      --user-data "fileb://$DEPLOY_DIR/user-data.sh" \
      --query 'Instances[0].InstanceId' --output text 2>/dev/null)"; then
      break
    fi
    if [[ "$attempt" == 8 ]]; then
      echo "Could not start the instance after 8 attempts." >&2
      exit 1
    fi
    sleep 10
  done
fi
a ec2 wait instance-exists --instance-ids "$INSTANCE"
echo "Instance: $INSTANCE"

# ---------------------------------------------------------------- fixed IP
ALLOCATION="$(a ec2 describe-addresses --filters "Name=tag:Name,Values=$NAME" \
  --query 'Addresses[0].AllocationId' --output text)"
if [[ "$ALLOCATION" == "None" ]]; then
  ALLOCATION="$(a ec2 allocate-address --domain vpc \
    --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$NAME}]" \
    --query AllocationId --output text)"
fi
a ec2 wait instance-running --instance-ids "$INSTANCE"
a ec2 associate-address --instance-id "$INSTANCE" --allocation-id "$ALLOCATION" >/dev/null
IP="$(a ec2 describe-addresses --allocation-ids "$ALLOCATION" --query 'Addresses[0].PublicIp' --output text)"
echo "Elastic IP: $IP"

# ---------------------------------------------------------------- on/off user (scripts/server.sh)
if ! a iam get-user --user-name "$OPS_USER" >/dev/null 2>&1; then
  a iam create-user --user-name "$OPS_USER" >/dev/null
fi
# ---------------------------------------------------------------- deploy command (scripts/server.sh deploy)
DOC="$NAME-deploy"
if a ssm describe-document --name "$DOC" >/dev/null 2>&1; then
  # shellcheck disable=SC2016 # $LATEST is SSM's literal version name, not a shell variable
  VERSION="$(a ssm update-document --name "$DOC" --document-version '$LATEST' \
    --content "file://$DEPLOY_DIR/ssm-deploy-document.json" \
    --query DocumentDescription.DocumentVersion --output text 2>/dev/null || true)"
  if [[ -n "$VERSION" ]]; then
    a ssm update-document-default-version --name "$DOC" --document-version "$VERSION" >/dev/null
  fi
else
  a ssm create-document --name "$DOC" --document-type Command --document-format JSON \
    --content "file://$DEPLOY_DIR/ssm-deploy-document.json" >/dev/null
fi
echo "Deploy document: $DOC"

# Start, stop and deploy this one instance, and nothing else. The deploy document takes no
# parameters, so this can't run arbitrary commands on the server.
a iam delete-user-policy --user-name "$OPS_USER" --policy-name start-stop-study-assistant \
  >/dev/null 2>&1 || true
a iam put-user-policy --user-name "$OPS_USER" --policy-name operate-study-assistant --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {\"Effect\": \"Allow\",
     \"Action\": [\"ec2:StartInstances\", \"ec2:StopInstances\"],
     \"Resource\": \"arn:aws:ec2:$REGION:$ACCOUNT:instance/$INSTANCE\"},
    {\"Effect\": \"Allow\",
     \"Action\": \"ssm:SendCommand\",
     \"Resource\": [
       \"arn:aws:ec2:$REGION:$ACCOUNT:instance/$INSTANCE\",
       \"arn:aws:ssm:$REGION:$ACCOUNT:document/$DOC\"
     ]},
    {\"Effect\": \"Allow\",
     \"Action\": [\"ec2:DescribeInstances\", \"ssm:GetCommandInvocation\",
                \"ssm:DescribeInstanceInformation\"],
     \"Resource\": \"*\"}
  ]
}"
if ! aws configure list-profiles | grep -qx "$OPS_USER"; then
  # Goes straight into ~/.aws/credentials and is never printed.
  read -r KEY_ID KEY_SECRET < <(a iam create-access-key --user-name "$OPS_USER" \
    --query 'AccessKey.[AccessKeyId,SecretAccessKey]' --output text)
  aws configure set aws_access_key_id "$KEY_ID" --profile "$OPS_USER"
  aws configure set aws_secret_access_key "$KEY_SECRET" --profile "$OPS_USER"
  aws configure set region "$REGION" --profile "$OPS_USER"
fi
echo "On/off profile: $OPS_USER"
