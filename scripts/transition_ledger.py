#!/usr/bin/env python3
"""전이 원장 — 수용 테스트 결과를 acceptance 트리 해시와 함께 기록하고,
해시 변경을 동반한 실패→통과 전이를 표시한다.

근거: 통과는 만들어질 수 있고, LLM 감시자는 복잡한 과제에서 치팅의 절반가량을
놓친다(민감도 42–50% 실측) — 감시자보다 결정적 신호가 먼저다.

사용: pytest tests/acceptance --junitxml=traces/acceptance.xml 실행 뒤
      python3 scripts/transition_ledger.py traces/acceptance.xml

사각: 구현 쪽 특수 케이스로 만든 전이는 acceptance 해시가 변하지 않아 표시
대상 밖이다 — 정확히 그 자리가 사람 리뷰의 몫이다.
"""
import hashlib
import json
import os
import sys
import time
from html.parser import HTMLParser

LEDGER = os.path.join("traces", "transitions.jsonl")
ACCEPTANCE = os.path.join("tests", "acceptance")


def acceptance_hash() -> str:
    h = hashlib.sha256()
    for root, _dirs, files in sorted(os.walk(ACCEPTANCE)):
        for name in sorted(files):
            path = os.path.join(root, name)
            h.update(path.encode())
            with open(path, "rb") as f:
                h.update(f.read())
    return h.hexdigest()[:16]


class _JUnitParser(HTMLParser):
    """junit XML의 testcase/failure/error/skipped만 읽는 최소 파서.

    xml.etree 대신 html.parser를 쓰는 이유: expat(C 확장)에 기대지 않는 순수
    파이썬이라 파이썬 설치 상태와 무관하게 돈다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.outcomes: dict = {}
        self._current = None
        self._verdict = None

    def handle_starttag(self, tag, attrs):
        if tag == "testcase":
            a = dict(attrs)
            self._current = f"{a.get('classname', '')}::{a.get('name', '')}"
            self._verdict = "pass"
        elif tag in ("failure", "error") and self._current:
            self._verdict = "fail"
        elif tag == "skipped" and self._current and self._verdict == "pass":
            self._verdict = "skip"

    def handle_endtag(self, tag):
        if tag == "testcase" and self._current:
            self.outcomes[self._current] = self._verdict
            self._current = None


def read_junit(path: str) -> dict:  # ast-grep-ignore: dict-payload-return — 키가 test_id인 매핑이지 키 이름이 계약인 페이로드가 아니다
    parser = _JUnitParser()
    with open(path, encoding="utf-8") as f:
        parser.feed(f.read())
    return parser.outcomes


def last_entries() -> dict:  # ast-grep-ignore: dict-payload-return — 키가 test_id인 매핑이지 키 이름이 계약인 페이로드가 아니다
    prev = {}
    if not os.path.exists(LEDGER):
        return prev
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            prev[entry["test"]] = entry
    return prev


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1
    junit = sys.argv[1]
    if not os.path.exists(junit):
        print(f"transition_ledger: junit 파일 없음: {junit}", file=sys.stderr)
        return 1
    outcomes = read_junit(junit)
    prev = last_entries()
    cur_hash = acceptance_hash()
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    flagged = 0
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        for test_id, outcome in sorted(outcomes.items()):
            entry = {"ts": ts, "test": test_id, "outcome": outcome, "acceptance_hash": cur_hash}
            before = prev.get(test_id)
            if (
                before
                and before["outcome"] == "fail"
                and outcome == "pass"
                and before["acceptance_hash"] != cur_hash
            ):
                entry["flag"] = "fail->pass with acceptance change"
                flagged += 1
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"transition_ledger: {len(outcomes)}건 기록, hash={cur_hash}")
    if flagged:
        print(
            f"transition_ledger: ⚠ 수용 테스트 변경을 동반한 실패→통과 전이 {flagged}건"
            " — 리뷰에서 확인하라",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
