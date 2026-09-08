"""페이지 게이트. 제출된 페이지가 실을 만한지 판정한다(PLAN §1 목표 3, §2.6, §6 2).

경계 계약: 입력은 작업과 제출물이고 출력은 위반 목록이다. 고치지 않는다. 통과하지 못한
페이지는 같은 작업을 사유와 함께 다시 내보내는 것이 조율 층의 일이다.

보는 것 넷.
1. 인용이 작업이 준 근거 id 안에 있는가. 밖을 가리키면 그 페이지는 사실이 아닌 것을 쓴 것이다.
2. 중요한 명제에 인용이 붙었는가(문단 수 대비 최소 인용 수).
3. 산문 규범을 어겼는가(엠대시, 이모지, 이중 피동, 명사형 종결).
4. 작업이 준 Mermaid 블록이 본문에 그대로 있는가. LLM은 그림을 새로 그리지도 빼지도 않는다.

사각: 인용이 문장을 실제로 지지하는지는 보지 못한다. 그 판정은 사람과 판정자 선별의 몫이고
이 게이트는 존재와 범위만 본다(C-GATE-2).
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from repowiki.models import PageJob, PageOutput

MIN_CITATIONS = 3

# ast-grep-ignore: regex-on-structure — 어휘: 인용 표기는 `E숫자` 고정 형식이다.
_CITE = re.compile(r"\[\^(E\d+)\]")
# ast-grep-ignore: regex-on-structure — 어휘: 코드 울타리는 줄머리 백틱 셋의 고정 형식이다.
_FENCE = re.compile(r"^```", re.MULTILINE)
_FORBIDDEN = {
    # ast-grep-ignore: regex-on-structure — 어휘: 금지 기호 한 글자 판정이다.
    "em-dash": re.compile(r"—"),
    # ast-grep-ignore: regex-on-structure — 어휘: 금지 기호 한 글자 판정이다.
    "interpunct": re.compile(r"·"),
    # ast-grep-ignore: regex-on-structure — 어휘: 이모지 코드 포인트 범위 판정이다.
    "emoji": re.compile(r"[\U0001F300-\U0001FAFF☀-➿]"),
    # 이중 피동. `되`와 `된`은 다른 글자라 문자 집합으로 함께 잡는다.
    # "만들어지게 된다"처럼 사이에 공백이 들어가는 형태도 같은 형태다.
    # ast-grep-ignore: regex-on-structure — 어휘: 한 줄 안의 어미 형태 판정이다.
    "double-passive": re.compile(r"되어지|되어진|지게\s*[되된됨됩]"),
}


class PageViolation(BaseModel):
    """페이지 위반 하나."""

    job_id: str
    rule: str
    detail: str


def _mermaid_blocks(body: str) -> list[str]:
    """본문의 Mermaid 블록 소스. 울타리 안쪽만 꺼낸다."""
    blocks: list[str] = []
    inside = False
    buffer: list[str] = []
    for line in body.splitlines():
        if line.strip().startswith("```mermaid"):
            inside, buffer = True, []
            continue
        if inside and line.strip().startswith("```"):
            blocks.append("\n".join(buffer).strip())
            inside = False
            continue
        if inside:
            buffer.append(line)
    return blocks


def check_page(job: PageJob, output: PageOutput) -> list[PageViolation]:
    """페이지 하나를 판정한다. 통과면 빈 목록이다."""
    violations: list[PageViolation] = []
    body = output.body_markdown

    known = {item.id for item in job.evidence}
    used = set(_CITE.findall(body))
    for unknown in sorted(used - known):
        violations.append(
            PageViolation(
                job_id=job.id,
                rule="citation-out-of-range",
                detail=f"{unknown}은 이 작업이 준 근거가 아니다",
            )
        )
    # 근거가 셋보다 적은 페이지에 셋을 요구하면 통과할 수 없는 요구가 된다.
    required = min(MIN_CITATIONS, len(job.evidence))
    if required and len(used) < required:
        violations.append(
            PageViolation(
                job_id=job.id,
                rule="too-few-citations",
                detail=f"인용 {len(used)}건이 최소 {required}건에 못 미친다",
            )
        )

    outside_code = _FENCE.split(body)[0::2]
    joined = "\n".join(outside_code)
    for rule, expression in _FORBIDDEN.items():
        found = expression.search(joined)
        if found is not None:
            violations.append(
                PageViolation(job_id=job.id, rule=rule, detail=f"금지 표기 {found.group(0)!r}")
            )

    expected = {diagram.source.strip() for diagram in job.diagrams}
    present = {block for block in _mermaid_blocks(body)}
    for missing in sorted(expected - present):
        violations.append(
            PageViolation(
                job_id=job.id,
                rule="diagram-missing",
                detail=f"작업이 준 다이어그램이 본문에 없다: {missing.splitlines()[0][:40]}",
            )
        )
    for block in _mermaid_blocks(body):
        if block not in expected:
            violations.append(
                PageViolation(
                    job_id=job.id,
                    rule="diagram-not-from-facts",
                    detail="작업이 준 다이어그램과 다른 Mermaid 블록이 있다",
                )
            )
            break
    if not output.description.strip():
        violations.append(
            PageViolation(job_id=job.id, rule="empty-description", detail="설명이 비었다")
        )
    return violations
