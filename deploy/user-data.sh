#!/usr/bin/env bash
# Runs once, as root, on the instance's first boot. Installs what the host needs and generates
# its own read-only GitHub deploy key, whose private half never leaves this machine.
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 docker-buildx git
snap install aws-cli --classic
systemctl enable --now docker

# Stop the instance 8 hours after every boot, in case nobody remembers to.
# run-instances sets shutdown behaviour to "stop", so this never terminates it.
cat >/etc/systemd/system/study-assistant-autostop.service <<'UNIT'
[Unit]
Description=Stop this instance 8 hours after boot
After=multi-user.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/shutdown -h +480

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now study-assistant-autostop.service

mkdir -p /root/.ssh /opt/study-assistant
chmod 700 /root/.ssh
ssh-keygen -t ed25519 -N "" -C "study-assistant-ec2" -f /root/.ssh/id_ed25519
ssh-keyscan -t ed25519 github.com >>/root/.ssh/known_hosts

touch /var/lib/study-assistant-host-ready
