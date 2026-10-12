#!/usr/bin/env bash
# Run AdIntel as supervised background services that start at boot/login and restart on failure.
#
#   scripts/install_services.sh            # macOS: launchd agents in ~/Library/LaunchAgents
#                                          # Linux: systemd units in /etc/systemd/system (needs sudo)
#   scripts/install_services.sh --print    # write the generated files to deploy/services/out/ only
#   scripts/install_services.sh --uninstall
#
# Services: deploy/services/services.txt. Logs: var/log/<service>.log (launchd) or journalctl (systemd).
set -euo pipefail
cd "$(dirname "$0")/.."
HOME_DIR="$(pwd)"
MODE="${1:-install}"
OUT="deploy/services/out"
mkdir -p "$OUT" var/log
OS="$(uname -s)"

services() { grep -v '^#' deploy/services/services.txt | awk 'NF' ; }

launchd_plist() {  # name, command, role
  local name=$1 cmd=$2 role=$3 env=""
  [ "$role" != "-" ] && env="<key>ADINTEL_PROCESS_ROLE</key><string>${role}</string>"
  cat <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.adintel.${name}</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>-lc</string><string>exec ${cmd}</string></array>
  <key>WorkingDirectory</key><string>${HOME_DIR}</string>
  <key>EnvironmentVariables</key><dict>${env}<key>PYTHONUNBUFFERED</key><string>1</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>${HOME_DIR}/var/log/${name}.log</string>
  <key>StandardErrorPath</key><string>${HOME_DIR}/var/log/${name}.log</string>
</dict></plist>
PLIST
}

systemd_unit() {  # name, command, role
  local name=$1 cmd=$2 role=$3 user="adintel" extra=""
  if [ "$name" = executor ]; then
    user="adintel-exec"   # separate OS user: the only one that can read the write-credential key
    extra="LoadCredential=write.key:/etc/adintel/keys/write.key
LoadCredential=read.key:/etc/adintel/keys/read.key"
  elif [ "$role" = worker ] || [ "$role" = api ]; then
    extra="LoadCredential=read.key:/etc/adintel/keys/read.key"
  fi
  cat <<UNIT
[Unit]
Description=AdIntel ${name}
After=network-online.target docker.service
Wants=network-online.target

[Service]
User=${user}
WorkingDirectory=${HOME_DIR}
EnvironmentFile=-${HOME_DIR}/.env
Environment=PYTHONUNBUFFERED=1$( [ "$role" != "-" ] && printf '\nEnvironment=ADINTEL_PROCESS_ROLE=%s' "$role" )
ExecStart=/bin/bash -lc 'exec ${cmd}'
Restart=on-failure
RestartSec=5
TimeoutStopSec=130
${extra}
# hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=${HOME_DIR}/var ${HOME_DIR}/data/import
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
CapabilityBoundingSet=
AmbientCapabilities=

[Install]
WantedBy=multi-user.target
UNIT
}

while read -r name rest; do
  role="${rest##* }"; cmd="${rest% *}"; cmd="${cmd%"${cmd##*[![:space:]]}"}"
  if [ "$OS" = Darwin ]; then
    launchd_plist "$name" "$cmd" "$role" > "$OUT/com.adintel.${name}.plist"
  else
    [[ "$name" == mlx-* ]] && continue   # mlx-lm is Apple Silicon only; use a model-server profile on Linux
    systemd_unit "$name" "$cmd" "$role" > "$OUT/adintel-${name}.service"
  fi
done < <(services)

case "$MODE" in
  --print) echo "generated in $OUT:"; ls "$OUT" ;;
  --uninstall)
    if [ "$OS" = Darwin ]; then
      for f in "$OUT"/*.plist; do launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/$(basename "$f")" 2>/dev/null || true
        rm -f "$HOME/Library/LaunchAgents/$(basename "$f")"; done
    else
      for f in "$OUT"/*.service; do sudo systemctl disable --now "$(basename "$f")" || true; sudo rm -f "/etc/systemd/system/$(basename "$f")"; done
      sudo systemctl daemon-reload
    fi ;;
  *)
    if [ "$OS" = Darwin ]; then
      for f in "$OUT"/*.plist; do cp "$f" "$HOME/Library/LaunchAgents/"
        launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/$(basename "$f")" 2>/dev/null || true; done
      echo "loaded: launchctl list | grep com.adintel ; logs in var/log/"
    else
      sudo cp "$OUT"/*.service /etc/systemd/system/ && sudo systemctl daemon-reload
      for f in "$OUT"/*.service; do sudo systemctl enable --now "$(basename "$f")"; done
      echo "running: systemctl status 'adintel-*' ; logs: journalctl -u adintel-api"
    fi ;;
esac
