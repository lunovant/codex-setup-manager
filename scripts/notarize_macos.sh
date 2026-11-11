#!/usr/bin/env bash
# Notarize a signed macOS binary with Apple's notary service.
#
# Usage: scripts/notarize_macos.sh <binary | App.app | archive.zip | archive.dmg>
# Env:   APPLE_API_KEY_PATH, APPLE_API_KEY_ID, APPLE_API_ISSUER_ID
#
# A bare Mach-O executable cannot be stapled (only .app, .pkg and .dmg can).
# Gatekeeper therefore checks the notarization ticket online on first run.
# Notarization does not modify the file, so its sha256 stays valid.
#
# For a .app bundle the app is zipped for submission; on Accepted the ticket is
# stapled to the app and the release zip (dist/codex-setup-macos-<arch>-app.zip,
# next to the app) plus its .sha256 are re-created from the stapled app.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <binary | App.app | archive.zip | archive.dmg>" >&2
  exit 2
fi
binary="$1"
binary="${binary%/}"
[[ -e "$binary" ]] || { echo "not found: $binary" >&2; exit 2; }
is_app=0
if [[ -d "$binary" ]]; then
  [[ "$binary" == *.app ]] || { echo "directory is not a .app bundle: $binary" >&2; exit 2; }
  is_app=1
fi
: "${APPLE_API_KEY_PATH:?APPLE_API_KEY_PATH is required}"
: "${APPLE_API_KEY_ID:?APPLE_API_KEY_ID is required}"
: "${APPLE_API_ISSUER_ID:?APPLE_API_ISSUER_ID is required}"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
zip_path="$workdir/$(basename "$binary").zip"

auth=(--key "$APPLE_API_KEY_PATH" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER_ID")

submit_path="$zip_path"
case "$binary" in
  *.zip|*.dmg) submit_path="$binary" ;;
  *) ditto -c -k --keepParent "$binary" "$zip_path" ;;
esac

echo "Submitting $(basename "$binary") for notarization..."
# Keep going on a non-zero exit so a rejected submission still prints its log below.
result="$(xcrun notarytool submit "$submit_path" "${auth[@]}" --wait --output-format json)" || true

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

if [[ "$is_app" -eq 1 ]]; then
  xcrun stapler staple "$binary"
  xcrun stapler validate "$binary"
  case "$(uname -m)" in
    arm64) arch=arm64 ;;
    x86_64) arch=x64 ;;
    *) arch="$(uname -m)" ;;
  esac
  release_zip="$(dirname "$binary")/codex-setup-macos-${arch}-app.zip"
  rm -f "$release_zip"
  ditto -c -k --keepParent "$binary" "$release_zip"
  (cd "$(dirname "$release_zip")" && shasum -a 256 "$(basename "$release_zip")" > "$(basename "$release_zip").sha256")
  echo "Stapled app and re-created $release_zip"
fi
