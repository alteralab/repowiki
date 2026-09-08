#!/usr/bin/env python3
"""봉인 경로 세션 훅 (Claude Code 어댑터) — 구현 세션의 봉인 경로 쓰기를 차단한다.

봉인 대상의 정본은 scripts/sealed_paths.txt 하나다 — 이 훅은 그 목록을 읽어
집행하는 어댑터일 뿐이고, 다른 하네스의 세션 어댑터도 같은 파일을 읽는다.

근거: 테스트가 에이전트의 쓰기 권한 안에 있으면 통과가 만들어진다는 실측
(ImpossibleBench). 읽기는 허용 — 읽기 전용이 정직한 성능을 보존하면서 테스트
수정 경로를 닫는 중간 지대다.

해제: 사람이 변경을 승인한 세션에서 ACCEPTANCE_UNSEAL=1 로만.

사각: 이 훅은 네 치팅 경로 중 '테스트 수정' 하나만 닫는다. 특수 케이스 처리·
연산자 오버로딩·상태 기록은 구현 파일 안에서 성립한다 — 전이 원장
(scripts/transition_ledger.py)과 사람 리뷰가 받는다.
"""
import json
import os
import sys


def sealed_paths(project: str) -> list:
    listing = os.path.join(project, "scripts", "sealed_paths.txt")
    paths = []
    try:
        with open(listing, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    paths.append(line.rstrip("/"))
    except OSError:
        sys.stderr.write(f"SEAL: 봉인 목록을 읽을 수 없다: {listing}\n")
        sys.exit(2)  # 목록 없이 조용히 통과하지 않는다 — 돌지 않는 게이트 금지
    return paths


def main() -> int:
    if os.environ.get("ACCEPTANCE_UNSEAL") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # 판정 대상 없음 — 경로가 없는 호출은 봉인과 무관하다
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not path:
        return 0
    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(project))
    for sealed in sealed_paths(project):
        prefix = sealed.replace("/", os.sep)
        if rel == prefix or rel.startswith(prefix + os.sep):
            sys.stderr.write(
                f"SEAL: {sealed}/ 는 구현 중 읽기 전용이다. "
                "테스트가 명세와 어긋나 보이면 멈추고 사람에게 설명하라. "
                "(변경은 사람 승인 후 ACCEPTANCE_UNSEAL=1 세션에서만)\n"
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
