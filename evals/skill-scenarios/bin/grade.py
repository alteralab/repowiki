#!/usr/bin/env python3
"""시나리오 실행 기록을 채점한다. 결정적으로 잴 수 있는 기준만 여기서 판정하고, 나머지는
사람(또는 판정 모델)의 몫이다 — 판정이 비어 있으면 통과가 아니라 `pending` 이다. 지어낸
발견을 막는 분리이고, 미판정을 통과로 세지 않는 것이 이 자의 규칙이다.

입력: 실행 디렉터리(run.sh 의 출력). 시나리오마다 trace.jsonl 과 output.md 가 있다.
판정: 같은 디렉터리의 judgments.json `{"<기준>": {"pass": true, "by": "human:<id>", "note": "..."}}`.
출력: 시나리오마다 grades.json, 전체 요약을 stdout 에. 전부 통과면 0, 아니면 1.

잴 수 있는 기준(id 는 scenario.md 체크리스트와 같다). 도구 이벤트는 Read 와 Bash 를 한 시간열로 본다.
  skill_triggered / skill_not_triggered  Skill 도구 호출이나 SKILL.md 읽기
  index_first        llms.txt 읽기가 쪽 원문 읽기(Read 든 cat 류든)보다 앞선다
  right_page         기대 쪽을 읽었거나(Read, cat 류) search-wiki 출력이 그 쪽을 냈다
  used_search_script search-wiki.sh 를 Bash 로 돌렸다
  searched           llms.txt 읽기 또는 search-wiki.sh 실행
  no_full_dump       llms-full.txt 를 Read 로도 cat 류로도 열지 않았다
  no_wiki_reads      llms.txt / search-wiki.sh 를 건드리지 않았다
  cited              답에 기대 쪽 링크가 있거나 `path:Lx-Ly` 범위 인용이 있다
  says_absent        답에 "위키에 없다"류 문장이 있다
  no_unsourced_numbers  답에 초·ms·분 단위 수치가 없다
  answered           답이 비어 있지 않고 대상 파일을 읽었다
판정으로 남기는 것: no_fabrication
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"
# 아래 넷은 전부 산문이나 명령 한 줄 안의 낱말 존재 검사다. 구조를 풀지 않는다.
# ast-grep-ignore: regex-on-structure — 어휘: 답 안의 `path:Lx-Ly` 인용 표기 존재 검사
_SPAN = re.compile(r"\b[\w/.-]+\.(?:java|scala|py|kt|ts|md):L\d+-L\d+\b")
# ast-grep-ignore: regex-on-structure — 어휘: 답 한 줄 안에서 "위키"와 부재 낱말의 동시 존재 검사
_ABSENT = re.compile(r"(위키|wiki)[^\n]{0,60}(없다|없습니다|찾지 못|나오지 않|실려 있지 않)")
# ast-grep-ignore: regex-on-structure — 어휘: 단위가 붙은 수치의 존재 검사
_UNIT_NUMBER = re.compile(r"\d[\d,.]*\s*(초|ms|밀리초|분|시간)\b")
# ast-grep-ignore: regex-on-structure — 어휘: 명령 한 줄 안의 읽기 명령 낱말과 파일 이름의 동시 존재 검사
_DUMP = re.compile(r"\b(cat|sed|head|tail|less|more|awk|grep|python3?|node)\b[^\n|;&]*llms-full")
# ast-grep-ignore: regex-on-structure — 어휘: 명령 한 줄 안의 읽기 명령 낱말 뒤 `.md` 토큰 추출
_PAGE_IN_COMMAND = re.compile(r"\b(cat|sed|head|tail|less|more)\b[^\n|;&]*?([\w/.-]+\.md)")


def _events(trace: Path) -> tuple[list[dict], list[str]]:
    """도구 호출을 시간순으로, 도구 결과의 본문을 따로 낸다."""
    calls: list[dict] = []
    results: list[str] = []
    for line in trace.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        for block in obj.get("message", {}).get("content", []) if isinstance(obj.get("message"), dict) else []:
            if obj.get("type") == "assistant" and block.get("type") == "tool_use":
                calls.append({"tool": block.get("name"), "input": block.get("input", {})})
            if obj.get("type") == "user" and block.get("type") == "tool_result":
                content = block.get("content")
                if isinstance(content, list):
                    content = "\n".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
                results.append(str(content or ""))
    return calls, results


def _opened(calls: list[dict]) -> list[str]:
    """열어 본 파일을 시간순으로. Read 의 경로와 Bash 의 cat 류 대상이다."""
    opened: list[str] = []
    for call in calls:
        if call["tool"] == "Read":
            opened.append(str(call["input"].get("file_path", "")))
        elif call["tool"] == "Bash":
            command = str(call["input"].get("command", ""))
            opened += [m.group(2) for m in _PAGE_IN_COMMAND.finditer(command)]
            # ast-grep-ignore: regex-on-structure — 어휘: 명령 한 줄 안의 읽기 명령 낱말 존재 검사
            if "llms.txt" in command and re.search(r"\b(cat|sed|head|tail|less|more)\b", command):
                opened.append("llms.txt")
    return opened


def measure(calls: list[dict], results: list[str], answer: str, page: str | None) -> dict[str, bool]:
    commands = [str(c["input"].get("command", "")) for c in calls if c["tool"] == "Bash"]
    opened = _opened(calls)
    skill_used = any(
        c["tool"] == "Skill" and "repowiki" in json.dumps(c["input"]) for c in calls
    ) or any(path.endswith("repowiki/SKILL.md") for path in opened)
    index_at = [i for i, p in enumerate(opened) if p.endswith("llms.txt")]
    page_at = [i for i, p in enumerate(opened) if p.endswith(".md") and not p.endswith("SKILL.md")]
    search_ran = any("search-wiki.sh" in c for c in commands)
    got = {
        "skill_triggered": skill_used,
        "skill_not_triggered": not skill_used,
        "index_first": bool(index_at) and (not page_at or index_at[0] < page_at[0]),
        "used_search_script": search_ran,
        "searched": bool(index_at) or search_ran,
        "no_full_dump": not any(p.endswith("llms-full.txt") for p in opened)
        and not any(_DUMP.search(c) for c in commands),
        "no_wiki_reads": not index_at and not search_ran and not any("llms" in c for c in commands),
        "cited": bool(_SPAN.search(answer)) or (page is not None and f"]({page})" in answer),
        "says_absent": bool(_ABSENT.search(answer)),
        "no_unsourced_numbers": not _UNIT_NUMBER.search(answer),
        "answered": bool(answer.strip()) and any(p.endswith("calc.py") for p in opened),
    }
    if page is not None:
        got["right_page"] = any(p.endswith(page) for p in opened) or any(f"== {page}" in r for r in results)
    return got


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("사용: grade.py <실행 디렉터리>", file=sys.stderr)
        return 2
    runs = Path(argv[1])
    total = passed = pending = 0
    for run in sorted(p for p in runs.iterdir() if p.is_dir()):
        trace = run / "trace.jsonl"
        if not trace.exists():
            continue
        calls, results = _events(trace)
        answer = (run / "output.md").read_text(encoding="utf-8")
        scenario = (SCENARIOS / run.name / "scenario.md").read_text(encoding="utf-8")
        # 체크리스트 줄은 `- [ ] <id>: <설명>` 한 줄 고정 형식이다. 마크다운 구조를 풀지 않는다.
        # ast-grep-ignore: regex-on-structure — 어휘: 고정 형식 한 줄의 칸 가르기
        criteria = re.findall(r"- \[ \] (\w+): (.*)", scenario)
        # ast-grep-ignore: regex-on-structure — 어휘: 한 줄 안의 `.md` 토큰 추출
        page_match = re.search(r"right_page: [^\n]*?([\w/.-]+\.md)", scenario)
        page = page_match.group(1) if page_match else None
        got = measure(calls, results, answer, page)
        judgments_file = run / "judgments.json"
        judgments = json.loads(judgments_file.read_text(encoding="utf-8")) if judgments_file.exists() else {}
        grades: dict[str, object] = {}
        for cid, _text in criteria:
            if cid in got:
                grades[cid] = got[cid]
            elif cid in judgments:
                grades[cid] = {"pass": bool(judgments[cid].get("pass")), "by": judgments[cid].get("by", "?"), "note": judgments[cid].get("note", "")}
            else:
                grades[cid] = "pending"
        unresolved = any(v == "pending" for v in grades.values())
        ok = not unresolved and all(
            (v if isinstance(v, bool) else v["pass"]) for v in grades.values() if v != "pending"
        )
        total += 1
        passed += ok
        pending += unresolved
        (run / "grades.json").write_text(json.dumps(grades, ensure_ascii=False, indent=1), encoding="utf-8")

        def mark(value: object) -> str:
            if value == "pending":
                return "?"
            if isinstance(value, dict):
                return ("✓" if value["pass"] else "✗") + "(판정)"
            return "✓" if value else "✗"

        marks = " ".join(f"{k}={mark(v)}" for k, v in grades.items())
        state = "통과" if ok else ("미판정" if unresolved else "실패")
        print(f"{state} {run.name}: {marks}")
    print(f"통과 {passed}/{total}, 미판정 {pending} (판정은 judgments.json 으로 남긴다)")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
