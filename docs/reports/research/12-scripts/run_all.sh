#!/bin/sh
set -e
cd "$(dirname "$0")"
start=$(date +%s)
for s in extract_maven extract_go extract_npm extract_proto extract_graphql extract_infra extract_strings build_graph; do
  t=$(date +%s); ${PY:-uv run --no-project --python 3.13 python} $s.py; echo "[$s] $(( $(date +%s)-t ))s" >&2
done
echo "TOTAL $(( $(date +%s)-start ))s" >&2
