#!/usr/bin/env bash
# llms-full.txt 에서 낱말이 든 절만 낸다. 전체를 읽지 않으려는 자리다(PLAN §2.10).
#
# 사용: search-wiki.sh <낱말> [위키 디렉토리 | llms-full.txt] [--max N] [--lines N]
#   낱말      대소문자 구분 없는 고정 문자열. 정규식이 아니다.
#   둘째 인자  뿌리(그 안의 system/llms.txt 가 가리키는 위키 전부), 위키 디렉토리(그 안의
#            llms-full.txt 또는 llms-full/*.md), 또는 파일. 없으면 이 스크립트가 놓인 자리 기준
#            ../../.. 뿌리다 — 스킬이 뿌리에 놓인 배치다. 작업 디렉토리는 전제하지 않는다.
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
[ -n "$target" ] || target="$here/../../.."

# 한 위키의 원문 파일들. shard 로 나뉘어 있으면 그 조각 전부다.
wiki_files() {
  if [ -f "$1/llms-full.txt" ]; then
    printf '%s\n' "$1/llms-full.txt"
  elif [ -d "$1/llms-full" ]; then
    for f in "$1"/llms-full/*.md; do [ "$(basename "$f")" = index.md ] || printf '%s\n' "$f"; done
  fi
}

# 읽을 파일 목록. 뿌리면 system/llms.txt 의 위키 전부, 위키면 그 원문, 파일이면 그 파일이다.
# 뿌리의 인덱스 줄은 `- [이름](../경로/llms.txt): 설명` 고정 형식이고 링크는 system/ 기준이라
# 앞의 `../` 를 떼면 뿌리 기준 경로다. 위키가 여럿이면 절마다 그 경로를 이름표로 붙인다.
files=(); labels=""; nwikis=1; rs=$'\x1f'   # 이름표 행 구분자. awk -v 는 줄바꿈을 못 받는다
if [ -d "$target" ] && [ -f "$target/system/llms.txt" ]; then
  nwikis=0
  while IFS= read -r -u 9 line; do
    case "$line" in "- ["*"]("*"/llms.txt)"*) ;; *) continue ;; esac
    rel=${line#*\](}; rel=${rel%%/llms.txt)*}
    # 인덱스가 가리키는 자리는 정확히 `../<뿌리 아래 경로>` 다. 밖으로 나가는 경로나 이름표를
    # 깨뜨리는 문자(탭·제어 문자·역슬래시)는 거부한다.
    case "$rel" in ../*) rel=${rel#../} ;; *) printf '인덱스 링크가 system/ 기준이 아니다: %s\n' "$line" >&2; exit 2 ;; esac
    case "/$rel/" in *"/../"*|*"//"*|"/./"*|*[[:cntrl:]\\]*) printf '인덱스 링크의 경로가 안전하지 않다: %s\n' "$rel" >&2; exit 2 ;; esac
    case "$rel" in /*) printf '인덱스 링크가 절대 경로다: %s\n' "$rel" >&2; exit 2 ;; esac
    nwikis=$((nwikis + 1)); found=0
    while IFS= read -r -u 8 f; do
      [ -n "$f" ] || continue
      files+=("$f"); labels="$labels$f	$rel$rs"; found=1
    done 8< <(wiki_files "$target/$rel" </dev/null)
    [ "$found" -eq 1 ] || { printf '인덱스가 가리키는 위키에 원문이 없다: %s/%s\n' "$target" "$rel" >&2; exit 2; }
  done 9< "$target/system/llms.txt"
elif [ -d "$target" ] && [ ! -f "$target/llms-full.txt" ] && [ ! -d "$target/llms-full" ] && [ -d "$target/wiki" ]; then
  # 시스템 인덱스가 없는 뿌리. 그 아래 위키 하나를 본다.
  while IFS= read -r -u 9 f; do [ -n "$f" ] && files+=("$f"); done 9< <(wiki_files "$target/wiki" </dev/null)
elif [ -d "$target" ]; then
  while IFS= read -r -u 9 f; do [ -n "$f" ] && files+=("$f"); done 9< <(wiki_files "$target" </dev/null)
elif [ -f "$target" ]; then
  files=("$target")
fi
[ "${#files[@]}" -gt 0 ] || { printf '원문이 없다: %s\n' "$target" >&2; exit 2; }

# 절 단위로 자른다. 낱말이 든 절만 내고, 절마다 쪽 경로를 앞에 둔다.
awk -v needle="$(printf '%s' "$keyword" | tr '[:upper:]' '[:lower:]')" -v max="$max" -v maxlines="$lines" -v nwikis="$nwikis" -v labels="$labels" '
  function flush(   i, shown) {
    if (!hit) { n = 0; hit = 0; return }
    total++
    if (total > max) { n = 0; hit = 0; return }
    printf "== %s%s :: %s\n", (wiki == "" ? "" : wiki "/"), page, (title == "" ? "(쪽 머리)" : title)
    shown = (n < maxlines) ? n : maxlines
    for (i = 1; i <= shown; i++) print buf[i]
    if (n > shown) printf "(... %d줄 더)\n", n - shown
    print ""
    n = 0; hit = 0
  }
  # 쪽 머리의 frontmatter(`---` 울타리)는 절이 아니다. 쪽 표식 바로 다음의 `---` 가 그것이고,
  # 그 밖의 `---` 는 쪽 사이의 구분선이다.
  # 이름표는 뿌리에서 위키까지의 경로다(파일 -> 경로 대응은 셸이 탭으로 넘긴다). 위키가
  # 하나면 붙이지 않는다.
  BEGIN { m = split(labels, rows, "\037"); for (i = 1; i <= m; i++) { k = index(rows[i], "\t"); if (k) label[substr(rows[i], 1, k - 1)] = substr(rows[i], k + 1) } }
  FNR == 1 { flush(); wiki = (nwikis > 1 && (FILENAME in label)) ? label[FILENAME] : "" }
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
