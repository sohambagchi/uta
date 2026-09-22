#!/usr/bin/env bash
# Install or upgrade the background collector as a systemd user service.
#
# Builds the package from this checkout into a pinned GC root, so later `nix build`s and dev work
# don't change what the collector runs, then (re)writes and restarts uta-collector.service.
# Re-run it to upgrade the collector to the current checkout.
#
#   deploy/install-collector.sh            # uses $UTA_DB or <repo>/data/uta.db
#   UTA_DB=/path/to/uta.db deploy/install-collector.sh
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
db=$(realpath -m "${UTA_DB:-$repo/data/uta.db}")
state=${XDG_STATE_HOME:-$HOME/.local/state}/uta
root=$state/collector
unit_dir=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
unit=$unit_dir/uta-collector.service
nix=$(command -v nix || echo /nix/var/nix/profiles/default/bin/nix)

mkdir -p "$state" "$unit_dir" "$(dirname "$db")"
echo "building $repo -> $root"
"$nix" build "$repo#uta" -o "$root"
store=$(readlink -f "$root")

cat >"$unit" <<EOF
[Unit]
Description=UTA realtime collector ($db)

[Service]
# $store
ExecStart=$root/bin/uta --db $db collect
Environment=TZ=America/Denver
Restart=always
RestartSec=10
# exit 2 = schema mismatch (see db.init); restarting won't fix it
RestartPreventExitStatus=2

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable uta-collector.service
systemctl --user restart uta-collector.service

if [[ $(loginctl show-user "$USER" -p Linger --value 2>/dev/null) != yes ]]; then
  echo "note: lingering is off, so the collector stops when you log out."
  echo "      enable it with: loginctl enable-linger $USER"
fi
systemctl --user --no-pager status uta-collector.service | head -5
