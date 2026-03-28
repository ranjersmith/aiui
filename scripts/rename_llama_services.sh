#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

UNIT_TEMPLATE="/etc/systemd/system/llama@.service"

declare -A OLD_TO_NEW=(
  [qwen35b]="8081"
  [qwen25vl]="8082"
  [nomic]="8083"
)

echo "Using port-number llama instance names:"
echo "  8081 -> llama@8081.service"
echo "  8082 -> llama@8082.service"
echo "  8083 -> llama@8083.service"
echo

if [[ ! -f "$UNIT_TEMPLATE" ]]; then
  echo "Missing systemd template: $UNIT_TEMPLATE" >&2
  exit 1
fi

echo "Requesting sudo once..."
sudo -v

sudo mkdir -p /etc/llama

for old in "${!OLD_TO_NEW[@]}"; do
  new="${OLD_TO_NEW[$old]}"
  old_env="/etc/llama/${old}.env"
  new_env="/etc/llama/${new}.env"
  old_service="llama@${old}.service"
  new_service="llama@${new}.service"

  if [[ -f "$old_env" ]]; then
    echo "Copying $old_env -> $new_env"
    sudo cp "$old_env" "$new_env"
  else
    echo "Skipping missing env: $old_env"
  fi

  if systemctl list-units --full --all "$old_service" | rg -Fq "$old_service"; then
    if systemctl is-active --quiet "$old_service"; then
      echo "Stopping old unit: $old_service"
      sudo systemctl stop "$old_service"
    fi
    if systemctl is-enabled --quiet "$old_service" 2>/dev/null; then
      echo "Disabling old unit: $old_service"
      sudo systemctl disable "$old_service"
    fi
  fi

  if [[ -f "$new_env" ]]; then
    echo "Enabling and restarting new unit: $new_service"
    sudo systemctl enable "$new_service"
    sudo systemctl restart "$new_service"
  fi
done

echo
echo "Current llama units:"
systemctl list-units 'llama@*' --no-pager
echo
echo "Config files:"
ls -1 /etc/llama | sort
