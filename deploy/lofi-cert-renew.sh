#!/usr/bin/env bash
# lofi-cert-renew.sh — keep the Tailscale MagicDNS TLS cert fresh for lofi-webui.
#
# `tailscale cert` is idempotent and cheap to re-run: it only actually talks to
# the CA when the cert is close to expiry (respects --min-validity), otherwise
# it's a no-op. Safe to run on a schedule indefinitely.
set -euo pipefail

DOMAIN="akashic.warthog-pythagorean.ts.net"
CERT_DIR="/home/jashin/lofi_factory/certs"
CERT_FILE="$CERT_DIR/$DOMAIN.crt"

mkdir -p "$CERT_DIR"
chmod 700 "$CERT_DIR"

before_hash=""
if [ -f "$CERT_FILE" ]; then
  before_hash="$(sha256sum "$CERT_FILE" | cut -d' ' -f1)"
fi

cd "$CERT_DIR"
tailscale cert --min-validity=720h "$DOMAIN"
chmod 600 "$DOMAIN.key"

after_hash="$(sha256sum "$CERT_FILE" | cut -d' ' -f1)"

if [ "$before_hash" != "$after_hash" ]; then
  echo "Certificate renewed -- restarting lofi-webui to pick it up."
  systemctl --user restart lofi-webui
else
  echo "Certificate still valid, no renewal needed."
fi
