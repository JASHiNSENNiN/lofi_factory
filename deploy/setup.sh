#!/usr/bin/env bash
# setup.sh — install Lo-fi Factory as auto-starting systemd user services,
# plus a Cloudflare named tunnel. Idempotent: safe to re-run.
#
#   bash deploy/setup.sh
#
# What it does (only the mechanical parts — interactive Cloudflare login is
# prompted, never automated):
#   1. install cloudflared binary to ~/.local/bin (if missing)
#   2. install + enable the lofi-webui user service
#   3. install + enable the lofi-auto timer (daily render+upload, default
#      midnight) — the timer just arms the schedule, so it's safe to enable
#      immediately; change the schedule from the web UI's Automation tab,
#      dashboard.py, or `python publish.py auto-service schedule ...`
#   4. enable user lingering so services start at boot without login
#   5. create the named tunnel + DNS route + config.yml (once you're logged in)
#   6. enable + start the cloudflared user service
#   7. OS hardening baseline: UFW (SSH only), Fail2Ban, unattended-upgrades
#      -- each step skips gracefully (with a warning) if its package isn't
#      installed, rather than failing the whole script
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$HOME/.local/bin"
UNIT_DIR="$HOME/.config/systemd/user"
CF_DIR="$HOME/.cloudflared"
TUNNEL_NAME="lofi"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }

mkdir -p "$BIN" "$UNIT_DIR" "$CF_DIR"

# ── 0. read hostname from .env (PUBLIC_BASE_URL) ──────────────────────────────
HOSTNAME=""
if [ -f "$ROOT/.env" ]; then
  base="$(grep -E '^PUBLIC_BASE_URL=' "$ROOT/.env" | head -1 | cut -d= -f2- | tr -d ' ')"
  HOSTNAME="${base#http*://}"; HOSTNAME="${HOSTNAME%%/*}"
fi

# ── 1. cloudflared binary ─────────────────────────────────────────────────────
if ! command -v cloudflared >/dev/null 2>&1 && [ ! -x "$BIN/cloudflared" ]; then
  say "Installing cloudflared to $BIN ..."
  arch="$(uname -m)"; case "$arch" in
    x86_64) cf_arch=amd64 ;; aarch64|arm64) cf_arch=arm64 ;; *) cf_arch=amd64 ;;
  esac
  curl -fsSL -o "$BIN/cloudflared" \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${cf_arch}"
  chmod +x "$BIN/cloudflared"
else
  say "cloudflared already present."
fi
CFLARED="$(command -v cloudflared || echo "$BIN/cloudflared")"

# ── 2. web UI service ─────────────────────────────────────────────────────────
say "Installing lofi-webui user service ..."
cp "$ROOT/deploy/lofi-webui.service" "$UNIT_DIR/lofi-webui.service"
systemctl --user daemon-reload
systemctl --user enable --now lofi-webui.service
say "lofi-webui status: $(systemctl --user is-active lofi-webui.service)"

# ── 3. auto-upload timer (daily, default midnight) ────────────────────────────
say "Installing lofi-auto timer + service ..."
cp "$ROOT/deploy/lofi-auto.service" "$UNIT_DIR/lofi-auto.service"
cp "$ROOT/deploy/lofi-auto.timer" "$UNIT_DIR/lofi-auto.timer"
# Triggered via lofi-auto.service's OnFailure= -- never enabled/started
# directly, systemd just needs to be able to find it when that fires.
cp "$ROOT/deploy/lofi-auto-notify-failure.service" "$UNIT_DIR/lofi-auto-notify-failure.service"
systemctl --user daemon-reload
systemctl --user enable --now lofi-auto.timer
say "lofi-auto.timer status: $(systemctl --user is-active lofi-auto.timer)"

# ── 4. linger (start at boot without an active login session) ─────────────────
if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]; then
  say "Enabling lingering (needs sudo once) ..."
  sudo loginctl enable-linger "$USER" || warn "Could not enable linger — run: sudo loginctl enable-linger $USER"
fi

# ── 5. Cloudflare tunnel ──────────────────────────────────────────────────────
if [ ! -f "$CF_DIR/cert.pem" ]; then
  warn "Not logged into Cloudflare yet."
  echo "    Run this (opens a browser, pick your domain), then re-run setup.sh:"
  echo "      $CFLARED tunnel login"
  exit 0
fi

if ! "$CFLARED" tunnel list 2>/dev/null | grep -q "[[:space:]]$TUNNEL_NAME[[:space:]]"; then
  say "Creating tunnel '$TUNNEL_NAME' ..."
  "$CFLARED" tunnel create "$TUNNEL_NAME"
fi
UUID="$("$CFLARED" tunnel list 2>/dev/null | awk -v n="$TUNNEL_NAME" '$2==n{print $1}')"

if [ -z "$HOSTNAME" ] || [ "$HOSTNAME" = "lofi.yourdomain.com" ]; then
  warn "Set PUBLIC_BASE_URL in .env to your real hostname (e.g. https://lofi.yourdomain.com), then re-run."
  exit 0
fi

say "Writing $CF_DIR/config.yml (hostname: $HOSTNAME) ..."
cat > "$CF_DIR/config.yml" <<YAML
tunnel: $UUID
credentials-file: $CF_DIR/$UUID.json

ingress:
  - hostname: $HOSTNAME
    service: http://127.0.0.1:8080
  - service: http_status:404
YAML

say "Routing DNS $HOSTNAME -> tunnel ..."
"$CFLARED" tunnel route dns "$TUNNEL_NAME" "$HOSTNAME" || warn "DNS route may already exist — ok."

say "Installing cloudflared user service ..."
cp "$ROOT/deploy/cloudflared-lofi.service" "$UNIT_DIR/cloudflared-lofi.service"
systemctl --user daemon-reload
systemctl --user enable --now cloudflared-lofi.service
say "cloudflared status: $(systemctl --user is-active cloudflared-lofi.service)"

# ── 7. OS hardening baseline ───────────────────────────────────────────────────
# Scoped to what a single-purpose personal automation box actually needs, not
# a full security audit: SSH is the only thing that needs to stay reachable
# from outside (the web panel goes through the Cloudflare tunnel above, so it
# needs no inbound port at all). Each check skips gracefully with a warning
# if its package isn't installed, rather than failing the whole script --
# `sudo apt install ufw fail2ban unattended-upgrades` covers all three.
say "Applying OS hardening baseline (UFW, Fail2Ban, unattended-upgrades) ..."

if command -v ufw >/dev/null 2>&1; then
  # Allow SSH BEFORE enabling -- getting this order backwards on a remote
  # box is how you lock yourself out.
  sudo ufw allow OpenSSH >/dev/null 2>&1 || sudo ufw allow ssh >/dev/null 2>&1 || true
  sudo ufw --force enable >/dev/null 2>&1
  say "ufw: $(sudo ufw status | head -1)"
else
  warn "ufw not installed -- skipping firewall (sudo apt install ufw)"
fi

if command -v fail2ban-client >/dev/null 2>&1; then
  sudo systemctl enable --now fail2ban >/dev/null 2>&1
  say "fail2ban: $(systemctl is-active fail2ban 2>/dev/null || echo unknown)"
else
  warn "fail2ban not installed -- skipping (sudo apt install fail2ban)"
fi

if dpkg -s unattended-upgrades >/dev/null 2>&1; then
  sudo systemctl enable --now unattended-upgrades >/dev/null 2>&1
  say "unattended-upgrades: enabled"
else
  warn "unattended-upgrades not installed -- skipping (sudo apt install unattended-upgrades)"
fi

echo
say "Done. Panel should be live at https://$HOSTNAME"
echo "    Logs:    journalctl --user -u lofi-webui -f"
echo "             journalctl --user -u cloudflared-lofi -f"
echo "    Restart: systemctl --user restart lofi-webui"
echo
echo "    Auto-upload schedule (default: daily at 00:00, timer already armed):"
echo "      Status:   python publish.py auto-service status"
echo "      Change:   python publish.py auto-service schedule --start 0 --every-hours 6"
echo "                (every-hours must be 6, 8, 12, or 24)"
echo "      Run now:  python publish.py auto-service run-now"
echo "      Logs:     python publish.py auto-service logs"
