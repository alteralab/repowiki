"""페이지 게이트. 제출된 페이지가 실을 만한지 판정한다(PLAN §1 목표 3, §2.6, §6 2).

경계 계약: 입력은 작업과 제출물이고 출력은 위반 목록이다. 고치지 않는다. 통과하지 못한
페이지는 같은 작업을 사유와 함께 다시 내보내는 것이 조율 층의 일이다.

보는 것 여섯.
1. 인용이 작업이 준 근거 id 안에 있는가. 밖을 가리키면 그 페이지는 사실이 아닌 것을 쓴 것이다.
2. 중요한 명제에 인용이 붙었는가(문단 수 대비 최소 인용 수).
3. 산문 규범을 어겼는가(엠대시, 이모지, 이중 피동, 명사형 종결).
4. 작업이 준 Mermaid 블록이 본문에 그대로 있는가. LLM은 그림을 새로 그리지도 빼지도 않는다.
5. 작업이 준 사실 표가 본문에 그대로 있는가. 표의 값은 사람이 그대로 믿는 자리라 한 칸도
   바뀌면 안 되고, 작업이 주지 않은 표가 있으면 그 숫자의 출처가 없다.
6. 문단에 견줘 목록이 얼마나 있는가. 처음 보는 코드베이스를 훑는 사람은 산문을 정독하지
   않는다. 이름과 뜻이 짝지어진 것은 목록이라야 눈으로 집힌다.
7. 제목을 지었는가. 계획 층이 주는 제목은 대표 타입 이름을 이은 임시 이름이라 사이드바에
   그대로 나가면 목록이 읽히지 않는다.

사각: 인용이 문장을 실제로 지지하는지는 보지 못한다. 그 판정은 사람과 판정자 선별의 몫이고
이 게이트는 존재와 범위만 본다(C-GATE-2).
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from collections import Counter

from repowiki.bundle.tables import blocks_in, body_of, html_tables_in
from repowiki.write.plan import target_words
from repowiki.models import PageJob, PageOutput

MIN_CITATIONS = 3
# 인용 하나가 받치는 최대 단어 수. 이보다 성기면 근거 없는 문장이 사이에 끼어 있다는 뜻이다.
WORDS_PER_CITATION = 60
# 분량 하한은 페이지 종류의 목표 분량에 비례한다. 목표는 `data/diagram-limits.yml`이
# 소유한다 — 쪽마다 성격이 달라 한 숫자를 모두에게 물릴 수 없다.
WORD_FLOOR_RATIO = 0.5
# 문단 하나당 있어야 하는 목록 줄의 최소 수.
# 2026-09-09에 두 코퍼스를 같은 자로 실측해 잡았다. DeepWiki apache/kafka 59쪽의
# 불릿/문단 비는 중앙값 1.88이고 **최솟값이 0.55**다 — 59쪽 중 0.5 아래가 하나도 없다.
# 같은 자로 잰 repowiki commons-cli 11쪽은 중앙값 0.33, 최소 0.05였다.
# 그래서 0.5는 참조 코퍼스를 한 쪽도 떨구지 않으면서 이쪽의 결함만 잡는 자리다.
# 오검출로 시작하는 게이트는 결국 떼어지므로 이 여백이 규칙의 조건이다(C-GATE-3).
MIN_BULLET_RATIO = 0.5
# 이 문단 수 아래에서는 묻지 않는다. 문단 셋짜리 쪽은 목록이 없어도 눈으로 집힌다.
MIN_PARAGRAPHS_FOR_BULLETS = 4
# 계획 층이 개념 쪽에 붙이는 임시 제목의 형태다. 대표 타입 둘을 이은 것이라 정체가 없다.
# 2026-09-09 실측: kafka에서 개념·영역 쪽 81개 중 57개(70%)가 이 형태였다. 같은 날 조사한
# DeepWiki 저장소 10곳의 2단 제목은 전부 기능 이름이다("Query Engine", "OCR Engine").
# ast-grep-ignore: regex-on-structure — 어휘: 임시 제목의 고정 형태 판정이다.
_FALLBACK_TITLE = re.compile(r"^[A-Z]\w*(\.\w+)?와 [A-Z]\w*(\.\w+)?$")

# ast-grep-ignore: regex-on-structure — 어휘: 인용 표기는 `E숫자` 고정 형식이다.
_CITE = re.compile(r"\[\^(E\d+)\]")
# ast-grep-ignore: regex-on-structure — 어휘: 코드 울타리는 줄머리 백틱 셋의 고정 형식이다.
_FENCE = re.compile(r"^```", re.MULTILINE)
# 목록 줄. 불릿과 번호 목록이다. 표는 세지 않는다 — 표는 사실 층이 준 것이라 그것으로
# 이 문턱을 넘으면 쓰는 층이 아무것도 안 하고 통과한다.
# ast-grep-ignore: regex-on-structure — 어휘: 줄머리 표식 판정이다.
_BULLET = re.compile(r"^([-*+] |\d+\. )")
# 줄 전체가 굵은 글씨인 줄. 사실 표가 앞에 다는 표제의 형태다.
# ast-grep-ignore: regex-on-structure — 어휘: 줄 전체가 별 둘로 감싸였는지의 판정이다.
_LABEL = re.compile(r"^\*\*[^*]+\*\*$")
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


def _prose_words(body: str) -> list[str]:
    """본문의 산문 단어. 코드 울타리와 표는 세지 않는다.

    표와 도식은 사실에서 그대로 온 것이라 쓰는 층이 쓴 글이 아니다. 그것을 분량에 세면
    표만 큰 페이지가 밀도 요구를 통과한다.
    """
    outside = _FENCE.split(body)[0::2]
    lines = [
        line
        for chunk in outside
        for line in chunk.splitlines()
        if not line.strip().startswith(("|", ">", "[^"))
    ]
    return " ".join(lines).split()


def _bullets_and_paragraphs(body: str) -> tuple[int, int]:
    """목록 줄 수와 문단 수.

    문단은 이어진 산문 줄의 덩어리 하나다. 제목과 빈 줄과 표와 인용 각주는 문단을 세지
    않고 끊기만 한다.

    줄 전체가 굵은 글씨인 줄은 문단이 아니라 표제다. 사실 표는 `**이름**` 한 줄과 빈 줄을
    앞에 달고 온다. 그것을 문단으로 세면 표를 실을수록 목록을 더 요구하게 되어, 규칙이
    자기가 권하는 것을 벌한다.

    코드 울타리 안은 보지 않는다. 그 안의 줄은 쓰는 층이 쓴 글이 아니다.
    """
    bullets = paragraphs = 0
    run = 0
    for chunk in _FENCE.split(body)[0::2]:
        lines = chunk.splitlines()
        for position, line in enumerate(lines):
            stripped = line.strip()
            if _BULLET.match(stripped):
                bullets += 1
                paragraphs += run
                run = 0
            elif not stripped or stripped.startswith(("#", "|", ">", "[^")) or _LABEL.match(
                stripped
            ):
                paragraphs += run
                run = 0
            elif position == 0 or not lines[position - 1].strip():
                run += 1
        paragraphs += run
        run = 0
    return bullets, paragraphs


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


def _check_blocks(
    job_id: str,
    expected: dict[str, str],
    present: list[str],
    rules: tuple[str, str],
    noun: str,
) -> list[PageViolation]:
    """작업이 준 블록과 본문의 블록을 맞춘다.

    도식과 표는 같은 계약을 진다. 작업이 준 것은 그대로 있어야 하고, 작업이 주지 않은 것은
    있으면 안 된다. 판정이 같으니 자리도 하나여야 한다(C-DUP-2).

    집합이 아니라 다중집합으로 센다. 같은 표를 두 번 실은 페이지는 한 번 실은 페이지와
    다른 글이고, 집합으로 비교하면 그 차이가 보이지 않는다.

    `expected`의 값은 사람이 읽을 이름이다. 소스의 첫 줄을 사유에 적으면 안 된다 — 레이아웃
    지시문으로 시작하는 도식은 첫 줄이 전부 같아서, 무엇이 빠졌는지 말해 주지 못한다.
    """
    missing_rule, stray_rule = rules
    # 사전을 그대로 세면 값을 개수로 읽는다. 열쇠만 센다.
    wanted, got = Counter(expected.keys()), Counter(present)
    found: list[PageViolation] = []
    for block, count in sorted((wanted - got).items()):
        found.append(
            PageViolation(
                job_id=job_id,
                rule=missing_rule,
                detail=f"작업이 준 {noun} {count}개가 본문에 없다: {expected[block]}",
            )
        )
    for block, count in sorted((got - wanted).items()):
        found.append(
            PageViolation(
                job_id=job_id,
                rule=stray_rule,
                detail=f"작업이 주지 않은 {noun} {count}개가 있다:"
                f" {block.splitlines()[0][:60]}",
            )
        )
    return found


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
    # 밀도는 분량에 비례한다. 긴 글에 인용 셋이면 나머지 문장은 근거가 없다.
    # 근거가 적은 페이지에 많은 인용을 요구하면 통과할 수 없는 요구가 되므로 준 만큼만 센다.
    words = len(_prose_words(body))
    required = min(max(MIN_CITATIONS, words // WORDS_PER_CITATION), len(job.evidence))
    if required and len(used) < required:
        violations.append(
            PageViolation(
                job_id=job.id,
                rule="too-few-citations",
                detail=f"본문 {words}단어에 인용 {len(used)}건이다. {required}건 이상이어야 한다",
            )
        )
    floor = int(target_words(job.type) * WORD_FLOOR_RATIO)
    if floor and words < floor:
        violations.append(
            PageViolation(
                job_id=job.id,
                rule="too-short",
                detail=f"본문 {words}단어가 {job.type.value} 페이지의 하한 {floor}단어에 못 미친다",
            )
        )

    if _FALLBACK_TITLE.match(output.title.strip()):
        violations.append(
            PageViolation(
                job_id=job.id,
                rule="unnamed-page",
                detail=(
                    f"제목이 계획 층의 임시 이름 그대로다: {output.title!r}. "
                    "이 묶음이 무엇을 맡는지로 이름을 짓는다"
                ),
            )
        )

    bullets, paragraphs = _bullets_and_paragraphs(body)
    wanted = int(paragraphs * MIN_BULLET_RATIO)
    if paragraphs >= MIN_PARAGRAPHS_FOR_BULLETS and bullets < wanted:
        violations.append(
            PageViolation(
                job_id=job.id,
                rule="prose-wall",
                detail=(
                    f"문단 {paragraphs}개에 목록 {bullets}줄이다. {wanted}줄 이상이어야 한다. "
                    "이름과 뜻이 짝지어진 것은 `- **이름**: 뜻 [^E1]` 꼴의 목록으로 낸다"
                ),
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

    violations += _check_blocks(
        job.id,
        {diagram.source.strip(): f"`{{{{diagram:{diagram.id}}}}}`" for diagram in job.diagrams},
        _mermaid_blocks(body),
        ("diagram-missing", "diagram-not-from-facts"),
        "다이어그램",
    )
    violations += _check_blocks(
        job.id,
        {body_of(table): f"`{{{{table:{table.id}}}}}`" for table in job.tables},
        blocks_in(body),
        ("table-missing", "table-not-from-facts"),
        "표",
    )
    html_tables = html_tables_in(body)
    if html_tables:
        violations.append(
            PageViolation(
                job_id=job.id,
                rule="html-table",
                detail=f"HTML 표 {html_tables}개가 있다. 표는 사실에서 온 Markdown 표여야 한다",
            )
        )

    if not output.description.strip():
        violations.append(
            PageViolation(job_id=job.id, rule="empty-description", detail="설명이 비었다")
        )
    return violations
