"""위키 Markdown을 Fumadocs 콘텐츠로 옮긴다(PLAN §2.4, SC-4.4).

경계 계약: 입력은 위키 디렉토리의 파일 내용이고 출력은 사이트 콘텐츠 파일 내용이다.
파일을 읽고 쓰는 것은 호출자의 일이다(C-DEPTH-3).

옮기면서 하는 일은 셋이다. 생성기가 쓰지 않는 머리말 필드를 걷어내고, Mermaid 코드
울타리를 사이트가 렌더하는 컴포넌트 호출로 바꾸고, 디렉토리마다 차례 파일을 만든다.
본문 문장은 건드리지 않는다.

사각: 이 모듈은 Markdown을 문자열로 다룬다. 코드 울타리 안의 백틱 세 개는 다루지 않는다.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

_FENCE = "```"
_MERMAID_FENCE = "```mermaid"


class SitePage(BaseModel):
    """사이트에 놓일 페이지 하나."""

    path: str
    content: str


def _front_matter(raw: str) -> tuple[dict[str, str], str]:
    """위키 페이지의 머리말과 본문을 가른다. 머리말이 없으면 빈 표를 낸다."""
    if not raw.startswith("---\n"):
        return {}, raw
    end = raw.find("\n---\n", 4)
    if end == -1:
        return {}, raw
    head_text, body = raw[4:end], raw[end + 5 :]
    head: dict[str, str] = {}
    for line in head_text.splitlines():
        if line.startswith((" ", "-")) or ":" not in line:
            continue
        key, _, value = line.partition(":")
        head[key.strip()] = value.strip().strip('"')
    return head, body


def _mermaid_to_component(body: str) -> str:
    """Mermaid 울타리를 `<Mermaid chart={...} />`로 바꾼다.

    사이트는 mermaid 패키지를 브라우저에서 부르므로 울타리가 아니라 컴포넌트여야 한다.
    소스는 그대로 넘긴다 — 그림을 여기서 고치지 않는다.
    """
    lines = body.splitlines()
    out: list[str] = []
    buffer: list[str] | None = None
    for line in lines:
        if buffer is None and line.strip() == _MERMAID_FENCE:
            buffer = []
            continue
        if buffer is not None and line.strip() == _FENCE:
            chart = "\\n".join(buffer).replace('"', '\\"')
            out.append(f'<Mermaid chart={{"{chart}"}} />')
            buffer = None
            continue
        if buffer is not None:
            buffer.append(line)
            continue
        out.append(line)
    return "\n".join(out)


def _escape(value: str) -> str:
    return value.replace('"', "'")


def to_site_page(wiki_path: str, raw: str) -> SitePage:
    """위키 페이지 하나를 사이트 페이지로 옮긴다."""
    head, body = _front_matter(raw)
    title = head.get("title") or wiki_path
    description = head.get("description", "")
    commit = head.get("analyzed_commit", "")
    banner = ""
    if commit:
        # 사이트가 렌더하는 컴포넌트로 넣는다. `:::` 지시문 문법은 이 템플릿에서
        # 글자 그대로 나온다.
        banner = "\n<Callout title=\"분석 커밋\">`" + commit[:12] + "`</Callout>\n"
    content = (
        "---\n"
        f'title: "{_escape(title)}"\n'
        f'description: "{_escape(description)}"\n'
        "---\n"
        f"{banner}\n"
        f"{_mermaid_to_component(body).strip()}\n"
    )
    return SitePage(path=wiki_path.removesuffix(".md") + ".mdx", content=content)


def meta_files(paths: list[str], repo_name: str) -> dict[str, str]:
    """디렉토리마다 차례 파일을 만든다. 루트 차례가 사이드바의 뼈대다."""
    tree: dict[str, list[str]] = {}
    for path in sorted(paths):
        parts = path.split("/")
        directory = "/".join(parts[:-1])
        tree.setdefault(directory, []).append(parts[-1].removesuffix(".mdx"))

    files: dict[str, str] = {}
    root_pages = sorted(
        {directory.split("/")[0] for directory in tree if directory}
        | {name for name in tree.get("", []) if name != "index"}
    )
    files["meta.json"] = json.dumps(
        {"title": f"{repo_name} 아키텍처 위키", "root": True, "pages": root_pages},
        ensure_ascii=False,
        indent=1,
    )
    for directory, names in tree.items():
        if not directory:
            continue
        files[f"{directory}/meta.json"] = json.dumps(
            {"title": directory, "pages": sorted(names)}, ensure_ascii=False, indent=1
        )
    return files
