#!/usr/bin/env bash
# 봉인 경로 커밋 검사 (pre-commit, 하네스 무관) — 봉인 경로의 변경이 다른 변경과
# 한 커밋에 섞이면 실패시킨다. 봉인 대상의 정본은 scripts/sealed_paths.txt 하나다.
#
# 사각: 커밋을 가른다는 형식만 검사한다. 단독 커밋의 내용을 사람이 실제로
# 승인했는지는 기계가 못 본다 — 리뷰가 본다.
set -euo pipefail

sealed_file="$(dirname "$0")/sealed_paths.txt"
if [ ! -f "$sealed_file" ]; then
  echo "SEAL: 봉인 목록이 없다: $sealed_file" >&2
  exit 1   # 목록 없이 조용히 통과하지 않는다
fi

total=$(git diff --cached --name-only | wc -l | tr -d ' ')
sealed=0
while IFS= read -r p; do
  [ -z "$p" ] && continue
  case "$p" in \#*) continue ;; esac
  # .gitkeep 면제: 봉인의 대상은 테스트 내용이지 뼈대 마커가 아니다 —
  # 인스턴스 첫 커밋이 이 면제 없이는 항상 걸린다.
  n=$(git diff --cached --name-only -- "${p%/}/" | { grep -v '/\.gitkeep$' || true; } | wc -l | tr -d ' ')
  sealed=$((sealed + n))
done < "$sealed_file"
other=$((total - sealed))

if [ "$sealed" -gt 0 ] && [ "$other" -gt 0 ]; then
  if [ "${ACCEPTANCE_UNSEAL:-0}" = "1" ]; then
    exit 0
  fi
  echo "SEAL: 봉인 경로 변경(${sealed}건)이 다른 변경(${other}건)과 섞여 있다." >&2
  echo "봉인 경로(scripts/sealed_paths.txt) 변경은 사람 승인 하에 단독 커밋으로 가르라." >&2
  exit 1
fi
