"""번들 산출: frontmatter, 인덱스, llms.txt(PLAN §2.4, §2.10).

경계 계약: 입력은 작업과 제출물과 사실이고 출력은 파일 내용 문자열이다. 파일을 쓰는 것은
호출자의 일이다(C-DEPTH-3).

frontmatter의 정본은 이 모듈의 pydantic 모델이고 `.schema/frontmatter.json`은 그 모델에서
낸 산출물이다. `index.md`와 `log.md`는 OKF 예약 파일이라 이 스키마의 대상이 아니다.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from repowiki.bundle.links import Forge, load_forges, source_url
from repowiki.models import PageJob, PageOutput, RepoFacts, Span

WIKI_VERSION = "repowiki/0.1.0"


class Generated(BaseModel):
    by: str
    at: str


class SourceRef(BaseModel):
    """근거 하나. `resource`는 저장소 상대 경로와 줄 범위다."""

    id: str
    resource: str
    commit: str


class Frontmatter(BaseModel):
    """페이지 머리말. OKF 호환 프로필의 고정 필드다(PLAN §2.4)."""

    type: str
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    generated: Generated
    analyzed_commit: str
    sources: list[SourceRef] = Field(default_factory=list)
    status: str = "draft"
    verified: list[dict] = Field(default_factory=list)


def _quote(value: str) -> str:
    """YAML 스칼라. 따옴표와 줄바꿈만 다룬다."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{escaped}"'


# ast-grep-ignore: regex-on-structure — 어휘: 인용 표기는 `E숫자` 고정 형식이다.
_CITE = re.compile(r"\[\^(E\d+)\]")


def frontmatter_of(job: PageJob, output: PageOutput, facts: RepoFacts, now: str) -> Frontmatter:
    """제출물과 작업에서 머리말을 만든다. LLM이 정하는 것은 제목과 설명과 태그뿐이다.

    `sources`에는 본문이 실제로 인용한 근거만 담는다. 주어진 근거를 전부 싣는 것은
    페이지가 쓰지도 않은 것을 출처로 주장하는 일이다.
    """
    commit = facts.profile.head_sha
    used = set(_CITE.findall(output.body_markdown))
    return Frontmatter(
        type=job.type.value,
        title=output.title or job.title,
        description=output.description,
        tags=output.tags,
        generated=Generated(by=WIKI_VERSION, at=now),
        analyzed_commit=commit,
        sources=[
            SourceRef(
                id=item.id,
                resource=f"repo://{item.span.path}#L{item.span.start_line}-L{item.span.end_line}",
                commit=commit,
            )
            for item in job.evidence
            if item.id in used
        ],
    )


def render_page(
    job: PageJob,
    output: PageOutput,
    facts: RepoFacts,
    now: str | None = None,
    forges: list[Forge] | None = None,
) -> str:
    """머리말과 본문을 합쳐 최종 Markdown을 만든다."""
    stamp = now or datetime.now(UTC).isoformat(timespec="seconds")
    head = frontmatter_of(job, output, facts, stamp)
    lines = [
        "---",
        f"type: {head.type}",
        f"title: {_quote(head.title)}",
        f"description: {_quote(head.description)}",
        f"tags: [{', '.join(_quote(t) for t in head.tags)}]",
        f"generated: {{by: {_quote(head.generated.by)}, at: {_quote(head.generated.at)}}}",
        f"analyzed_commit: {_quote(head.analyzed_commit)}",
        "sources:",
    ]
    for source in head.sources:
        lines.append(
            f"  - {{id: {_quote(source.id)}, resource: {_quote(source.resource)},"
            f" commit: {_quote(source.commit)}}}"
        )
    if not head.sources:
        lines[-1] = "sources: []"
    lines += [f"status: {head.status}", "verified: []", "---", ""]
    body = output.body_markdown.rstrip()
    spans = {item.id: item.span for item in job.evidence}
    forges = forges if forges is not None else load_forges()
    remote, commit = facts.profile.remote_url, facts.profile.head_sha
    header = _source_header(head.sources, spans, remote, commit, forges)
    footnotes = _footnotes(head.sources, spans, remote, commit, forges)
    if header:
        body = f"{header}\n\n{body}"
    if footnotes:
        body = f"{body}\n\n{chr(10).join(footnotes)}"
    return "\n".join(lines) + body + "\n"


def _cite_text(span: Span) -> str:
    """인용 표기. 본문의 각주와 머리의 목록이 같은 형식을 쓴다."""
    return f"{span.path}:L{span.start_line}-L{span.end_line}"


def _linked(span: Span, remote: str, commit: str, forges: list[Forge]) -> str:
    """자리 하나의 표기. 링크를 만들 수 있으면 링크로, 아니면 코드 표기로 낸다.

    원격이 없는 작업본(반입 환경)에서는 링크가 없는 것이 정상이고, 그때도 경로와 줄은
    그대로 남아 사람이 손으로 찾아갈 수 있다.
    """
    url = source_url(remote, commit, span, forges)
    label = _cite_text(span)
    return f"[`{label}`]({url})" if url else f"`{label}`"


def _footnotes(
    sources: list[SourceRef],
    spans: dict[str, Span],
    remote: str,
    commit: str,
    forges: list[Forge],
) -> list[str]:
    """각주 정의. 인용 하나가 소스 한 자리로 이어진다."""
    found: list[str] = []
    for source in sources:
        span = spans.get(source.id)
        if span is None:
            continue
        found.append(f"[^{source.id}]: {_linked(span, remote, commit, forges)}")
    return found


def _source_header(
    sources: list[SourceRef],
    spans: dict[str, Span],
    remote: str,
    commit: str,
    forges: list[Forge],
) -> str:
    """페이지가 근거로 삼은 파일 목록. 읽는 사람이 무엇을 읽고 쓴 글인지 먼저 본다.

    파일 단위로 접는다. 같은 파일의 여러 자리를 낱낱이 세면 목록이 본문보다 길어진다.
    """
    paths: list[str] = []
    for source in sources:
        span = spans.get(source.id)
        if span is not None and span.path not in paths:
            paths.append(span.path)
    if not paths:
        return ""
    items = []
    for path in paths:
        span = next(s for s in spans.values() if s.path == path)
        url = source_url(remote, commit, Span(path=path, start_line=1, end_line=1), forges)
        items.append(f"- [`{path}`]({url})" if url else f"- `{path}`")
    return "\n".join(["> **근거 소스**", ">", *[f"> {line}" for line in items]])


def render_index(pages: list[tuple[str, Frontmatter]], repo_name: str) -> str:
    """`index.md`. OKF 예약 파일이라 스키마의 대상이 아니고 목록만 담는다."""
    lines = [
        "---",
        'okf_version: "0.2"',
        f"title: {_quote(f'{repo_name} 아키텍처 위키')}",
        "---",
        "",
        f"# {repo_name} 아키텍처 위키",
        "",
        "결정적 분석이 뽑은 사실 위에서 쓴 페이지들이다. 각 페이지의 중요한 명제에는",
        "저장소의 줄 범위를 가리키는 각주가 달려 있다.",
        "",
    ]
    for path, head in sorted(pages):
        lines.append(f"- [{head.title}]({path}) {head.description}")
    return "\n".join(lines) + "\n"


def render_llms_txt(pages: list[tuple[str, Frontmatter]], repo_name: str) -> str:
    """`llms.txt`. 에이전트가 먼저 읽고 링크를 따라가는 인덱스다(PLAN §2.10)."""
    lines = [
        f"# {repo_name}",
        "",
        f"> {repo_name}의 아키텍처 위키다. 페이지는 결정적 분석 결과에서 만들어졌고",
        "> 중요한 명제마다 `path:Lx-Ly` 근거가 붙어 있다.",
        "",
        "## 페이지",
        "",
    ]
    for path, head in sorted(pages):
        lines.append(f"- [{head.title}]({path}): {head.description}")
    return "\n".join(lines) + "\n"


def render_llms_full(pages: list[tuple[str, str]]) -> str:
    """`llms-full.txt`. 페이지 원문을 한 파일에 잇는다."""
    chunks = [f"<!-- {path} -->\n{body.rstrip()}" for path, body in sorted(pages)]
    return "\n\n---\n\n".join(chunks) + "\n"
