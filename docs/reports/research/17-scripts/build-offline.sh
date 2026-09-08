#!/bin/zsh
# Offline npm ci + next build, both under macOS sandbox-exec denying non-loopback egress (same method as research 13).
set -e
cd "$(dirname "$0")/site"
export npm_config_cache="$PWD/../../docs-site/npm-cache"
export NEXT_TELEMETRY_DISABLED=1
export HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9
echo "== npm ci --offline"; /usr/bin/time -p sandbox-exec -f ../sandbox-noegress.sb npm ci --offline --no-audit --no-fund 2>&1 | tail -5
echo "== lock packages: $(python3 -c "import json;d=json.load(open('package-lock.json'));print(len([k for k in d['packages'] if k]))")"
echo "== node_modules: $(du -sk node_modules | cut -f1) KB, $(find node_modules -type f | wc -l | tr -d ' ') files"
echo "== next build"; /usr/bin/time -p sandbox-exec -f ../sandbox-noegress.sb npx next build 2>&1 | grep -v '^\s*$' | tail -30
echo "== out: $(du -sk out | cut -f1) KB, $(find out -type f | wc -l | tr -d ' ') files; html $(find out -name '*.html' | wc -l | tr -d ' '), txt $(find out -name '*.txt' | wc -l | tr -d ' ') ($(find out -name '*.txt' -exec du -k {} + | awk '{s+=$1} END{print s}') KB)"
