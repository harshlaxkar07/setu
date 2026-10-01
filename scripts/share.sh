#!/usr/bin/env bash
# Share the citizen page with judges via a temporary public URL + QR code.
#
#   scripts/share.sh          # asks for confirmation first
#   scripts/share.sh --yes    # skip the prompt
#
# Uses a Cloudflare "quick tunnel" (free, no account): a random
# https://<words>.trycloudflare.com address that forwards to your local
# backend (port 8000) until you press Ctrl+C. Never started automatically.
#
# PRIVACY — what becomes reachable from the internet while it runs:
#   * the citizen page (/citizen/) — anyone with the link can submit reports;
#   * the backend's read API — aggregate clusters, scores and recommendations
#     (no names or phone numbers are ever collected);
#   * decision endpoints stay protected by reviewer sign-in.
# The dashboard (port 8501) is NOT exposed. Stop the tunnel after the demo.
set -euo pipefail

PORT="${SETU_BACKEND_PORT:-8000}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is not installed. On macOS:  brew install cloudflared"
  echo "Other systems: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  exit 1
fi
if ! curl -fsS "http://localhost:${PORT}/health" >/dev/null; then
  echo "The Setu backend is not answering on http://localhost:${PORT} — run: docker compose up -d"
  exit 1
fi

if [[ "${1:-}" != "--yes" ]]; then
  sed -n '8,16p' "$0" | sed 's/^# \{0,1\}//'
  read -r -p "Expose the citizen page publicly until you press Ctrl+C? [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] || { echo "Cancelled — nothing was exposed."; exit 0; }
fi

LOG="$(mktemp -t setu-tunnel.XXXXXX)"
cloudflared tunnel --no-autoupdate --url "http://localhost:${PORT}" >"$LOG" 2>&1 &
TUNNEL_PID=$!
trap 'kill "$TUNNEL_PID" 2>/dev/null; rm -f "$LOG"; echo; echo "Tunnel stopped — the page is no longer public."' EXIT INT TERM

URL=""
for _ in $(seq 1 60); do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)"
  [[ -n "$URL" ]] && break
  sleep 1
done
if [[ -z "$URL" ]]; then
  echo "Could not start the tunnel. cloudflared said:"; tail -20 "$LOG"; exit 1
fi

PAGE="${URL}/citizen/"
echo
echo "Citizen page for judges:  ${PAGE}"
echo "Field-worker mode:        ${PAGE}?mode=assisted"
echo
if command -v qrencode >/dev/null 2>&1; then
  qrencode -t ANSIUTF8 "$PAGE"
else
  echo "(Install qrencode for a scannable QR code here:  brew install qrencode)"
fi
echo
echo "Press Ctrl+C to stop sharing."
wait "$TUNNEL_PID"
