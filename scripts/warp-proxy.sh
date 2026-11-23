#!/usr/bin/env bash
# Start a local Cloudflare WARP SOCKS5 proxy, free, to use as a fallback route:
#
#   scripts/warp-proxy.sh            # listens on socks5h://127.0.0.1:40000, Ctrl-C to stop
#   yad2 --fallback-proxy socks5h://127.0.0.1:40000 realestate rent --city raanana
#
# It downloads two small open-source tools (checked against their published SHA-256 sums):
#   wgcf      https://github.com/ViRb3/wgcf      registers a free WARP account, writes a WireGuard profile
#   wireproxy https://github.com/whyvl/wireproxy runs that WireGuard tunnel in user space as a SOCKS5 proxy
# No root needed, and your machine's own network routes are left untouched.
# Registering a WARP account means accepting Cloudflare's terms of service.
#
# Options (environment): YAD2_WARP_DIR (default ~/.cache/yad2-warp). Argument: port (default 40000).
set -euo pipefail

PORT="${1:-40000}"
DIR="${YAD2_WARP_DIR:-$HOME/.cache/yad2-warp}"
WGCF_VERSION=2.3.1
WIREPROXY_VERSION=1.1.3

os="$(uname -s | tr '[:upper:]' '[:lower:]')"
case "$(uname -m)" in
  x86_64 | amd64) arch=amd64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) echo "unsupported CPU $(uname -m): use the official WARP client in proxy mode" >&2; exit 1 ;;
esac
case "$os" in
  linux | darwin) ;;
  *) echo "unsupported OS $os: use the official WARP client in proxy mode" >&2; exit 1 ;;
esac

sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }

# download URL, check it against the line for NAME in the release's checksums.txt, save as OUT
fetch_checked() {
  local url="$1" sums_url="$2" name="$3" out="$4" expected
  curl -fsSL --retry 3 -o "$out.tmp" "$url"
  expected="$(curl -fsSL --retry 3 "$sums_url" | awk -v n="$name" '$2 == n {print $1}')"
  if [ -z "$expected" ] || [ "$(sha256 "$out.tmp")" != "$expected" ]; then
    rm -f "$out.tmp"; echo "checksum mismatch for $name, aborting" >&2; exit 1
  fi
  mv "$out.tmp" "$out"
}

mkdir -p "$DIR" && chmod 700 "$DIR" && cd "$DIR"

if [ ! -x wgcf ]; then
  base="https://github.com/ViRb3/wgcf/releases/download/v$WGCF_VERSION"
  name="wgcf_${WGCF_VERSION}_${os}_${arch}"
  fetch_checked "$base/$name" "$base/checksums.txt" "$name" wgcf
  chmod +x wgcf
fi
if [ ! -x wireproxy ]; then
  base="https://github.com/whyvl/wireproxy/releases/download/v$WIREPROXY_VERSION"
  name="wireproxy_${os}_${arch}.tar.gz"
  fetch_checked "$base/$name" "$base/checksums.txt" "$name" wireproxy.tar.gz
  tar xzf wireproxy.tar.gz wireproxy && rm wireproxy.tar.gz
fi

if [ ! -f wgcf-account.toml ]; then
  echo "Registering a free Cloudflare WARP account (Cloudflare's terms of service apply)..."
  ./wgcf register --accept-tos >/dev/null
fi
[ -f wgcf-profile.conf ] || ./wgcf generate >/dev/null

cat > wireproxy.conf <<EOF
WGConfig = $DIR/wgcf-profile.conf

[Socks5]
BindAddress = 127.0.0.1:$PORT
EOF

echo "WARP proxy ready on socks5h://127.0.0.1:$PORT (Ctrl-C to stop)"
exec ./wireproxy -s -c wireproxy.conf
