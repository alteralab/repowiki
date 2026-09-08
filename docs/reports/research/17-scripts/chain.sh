#!/bin/zsh
cd "$(dirname "$0")"
./build-offline.sh > build-offline-4.log 2>&1
grep -E '^(real|== out|== lock|== node_modules)' build-offline-4.log
rm -rf out-slim && cp -Rc site/out out-slim && find out-slim -name '*.txt' -not -name 'llms*.txt' -delete && echo "slim: $(du -sk out-slim | cut -f1) KB, $(find out-slim -type f | wc -l | tr -d ' ') files"
(nohup python3 -m http.server 8105 --bind 127.0.0.1 -d out-slim > server-slim.log 2>&1 &)
cd tools && node measure.mjs fuma > measure-loopback.log 2>&1 && node extras.mjs http://127.0.0.1:8002 ../report-fuma-extras.json > extras.log 2>&1
echo CHAIN_DONE
