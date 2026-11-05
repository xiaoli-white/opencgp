#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${GH_TOKEN:?需要设置 GH_TOKEN（fine-grained PAT，Contents: Read and write）}"
PORT="${TUNNEL_PORT:-8899}"
if ! timeout 2 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/$PORT" 2>/dev/null; then
  nohup python3 tools/github_tunnel.py >/tmp/github_tunnel.log 2>&1 &
  sleep 2
fi
git -c http.proxy="http://127.0.0.1:$PORT" -c http.postBuffer=524288000 push "$@" https://github.com/xiaoli-white/opencgp.git HEAD:main
