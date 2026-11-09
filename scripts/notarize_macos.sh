#!/usr/bin/env bash
# Notarize a signed macOS binary with Apple's notary service.
#
# Usage: scripts/notarize_macos.sh <binary>
# Env:   APPLE_API_KEY_PATH, APPLE_API_KEY_ID, APPLE_API_ISSUER_ID
#
# A bare Mach-O executable cannot be stapled (only .app, .pkg and .dmg can).
# Gatekeeper therefore checks the notarization ticket online on first run.
# Notarization does not modify the file, so its sha256 stays valid.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <binary>" >&2
  exit 2
fi
binary="$1"
[[ -f "$binary" ]] || { echo "binary not found: $binary" >&2; exit 2; }
: "${APPLE_API_KEY_PATH:?APPLE_API_KEY_PATH is required}"
: "${APPLE_API_KEY_ID:?APPLE_API_KEY_ID is required}"
: "${APPLE_API_ISSUER_ID:?APPLE_API_ISSUER_ID is required}"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
zip_path="$workdir/$(basename "$binary").zip"

auth=(--key "$APPLE_API_KEY_PATH" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER_ID")

ditto -c -k --keepParent "$binary" "$zip_path"

echo "Submitting $(basename "$binary") for notarization..."
# Keep going on a non-zero exit so a rejected submission still prints its log below.
result="$(xcrun notarytool submit "$zip_path" "${auth[@]}" --wait --output-format json)" || true

read -r status id < <(
  printf '%s' "$result" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d.get("status", ""), d.get("id", ""))
'
)

echo "Notarization status: ${status:-unknown} (id: ${id:-unknown})"
if [[ "$status" != "Accepted" ]]; then
  if [[ -n "${id:-}" ]]; then
    xcrun notarytool log "$id" "${auth[@]}" || true
  fi
  exit 1
fi
