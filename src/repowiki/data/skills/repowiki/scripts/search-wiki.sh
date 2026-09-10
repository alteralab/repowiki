#!/usr/bin/env bash
# llms-full.txt 에서 낱말이 든 절만 낸다. 전체를 읽지 않으려는 자리다(PLAN §2.10).
#
# 사용: search-wiki.sh <낱말> [위키 디렉토리 | llms-full.txt] [--max N] [--lines N]
#   낱말      대소문자 구분 없는 고정 문자열. 정규식이 아니다.
#   둘째 인자  위키 디렉토리(그 안의 llms-full.txt 또는 llms-full/*.md)나 파일. 없으면 이 스크립트가
#            놓인 자리 기준 ../../../wiki 다 — 스킬이 위키 옆에 놓인 배치다. 작업 디렉토리는
#            전제하지 않는다.
#   --max N   낼 절의 수. 기본 8. 넘는 것은 수만 말한다.
#   --lines N 절 하나에서 낼 줄 수. 기본 60.
# 종료 코드: 찾으면 0, 없으면 1, 인자나 파일 문제면 2.
#
# 형식 계약: llms-full.txt 는 쪽마다 `<!-- <path> -->` 줄로 시작하고 쪽 사이는 `---` 다
# (bundle/emit.py render_llms_full). 절은 `## `/`### ` 머리말이 가른다.
set -euo pipefail

usage() { printf 'usage: %s <낱말> [위키 디렉토리|llms-full.txt] [--max N] [--lines N]\n' "$(basename "$0")" >&2; exit 2; }

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
keyword=""; target=""; max=8; lines=60
while [ $# -gt 0 ]; do
  case "$1" in
    --max) [ $# -ge 2 ] || usage; max=$2; shift 2 ;;
    --lines) [ $# -ge 2 ] || usage; lines=$2; shift 2 ;;
    -h|--help) usage ;;
    --*) usage ;;
    *) if [ -z "$keyword" ]; then keyword=$1; elif [ -z "$target" ]; then target=$1; else usage; fi; shift ;;
  esac
done
[ -n "$keyword" ] || usage
# 수는 1 이상의 정수여야 한다. awk 에 그대로 넘기면 `nope` 이 0 이 되어 조용히 아무것도 안 낸다.
case "$max" in ''|*[!0-9]*|0) usage ;; esac
case "$lines" in ''|*[!0-9]*|0) usage ;; esac
[ -n "$target" ] || target="$here/../../../wiki"

# 읽을 파일 목록. 디렉토리면 그 안의 전체 원문이고, shard 로 나뉘어 있으면 그 조각 전부다.
files=()
if [ -d "$target" ]; then
  if [ -f "$target/llms-full.txt" ]; then
    files=("$target/llms-full.txt")
  elif [ -d "$target/llms-full" ]; then
    for f in "$target"/llms-full/*.md; do [ "$(basename "$f")" = index.md ] || files+=("$f"); done
  fi
elif [ -f "$target" ]; then
  files=("$target")
fi
[ "${#files[@]}" -gt 0 ] || { printf '원문이 없다: %s\n' "$target" >&2; exit 2; }

# 절 단위로 자른다. 낱말이 든 절만 내고, 절마다 쪽 경로를 앞에 둔다.
awk -v needle="$(printf '%s' "$keyword" | tr '[:upper:]' '[:lower:]')" -v max="$max" -v maxlines="$lines" '
  function flush(   i, shown) {
    if (!hit) { n = 0; hit = 0; return }
    total++
    if (total > max) { n = 0; hit = 0; return }
    printf "== %s :: %s\n", page, (title == "" ? "(쪽 머리)" : title)
    shown = (n < maxlines) ? n : maxlines
    for (i = 1; i <= shown; i++) print buf[i]
    if (n > shown) printf "(... %d줄 더)\n", n - shown
    print ""
    n = 0; hit = 0
  }
  # 쪽 머리의 frontmatter(`---` 울타리)는 절이 아니다. 쪽 표식 바로 다음의 `---` 가 그것이고,
  # 그 밖의 `---` 는 쪽 사이의 구분선이다.
  /^<!-- .* -->$/ { flush(); page = $0; sub(/^<!-- /, "", page); sub(/ -->$/, "", page); title = ""; expect_fm = 1; next }
  /^---$/ && expect_fm { fm = 1; expect_fm = 0; next }
  fm { if ($0 == "---") fm = 0; next }
  { expect_fm = 0 }
  /^---$/ { flush(); next }
  /^##+ / { flush(); title = $0; sub(/^#+ /, "", title) }
  /^<details>/ { flush(); title = "근거 소스" }
  /^<\/details>/ { buf[++n] = $0; flush(); title = ""; next }
  {
    buf[++n] = $0
    if (index(tolower($0), needle) > 0) hit = 1
  }
  END {
    flush()
    if (total == 0) exit 1
    if (total > max) printf "(절 %d개 중 %d개만 냈다. --max 로 늘린다)\n", total, max
  }
' "${files[@]}"
