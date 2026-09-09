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
import re

from pydantic import BaseModel

_FENCE = "```"
_MERMAID_FENCE = "```mermaid"

# 근거 목록의 머리. `bundle/emit.py`가 내는 형태다.
_SOURCES_OPEN = "<details>\n<summary>근거 소스 "
_SOURCES_CLOSE = "</details>"
# 목록 한 줄. `- [`경로`](주소)` 이거나 주소 없는 `- `경로``이다.
# ast-grep-ignore: regex-on-structure — 어휘: 생성한 목록 줄의 고정 형식 판정이다.
_SOURCE_ITEM = re.compile(r"^- \[`([^`]+)`\]\(([^)]*)\)|^- `([^`]+)`", re.MULTILINE)


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


def _files_tree(paths: list[tuple[str, str]]) -> str:
    """근거 파일 목록을 디렉토리 트리로. 사이트는 이 컴포넌트를 렌더한다.

    평평한 목록은 같은 접두어를 파일 수만큼 되풀이한다. commons-cli 의 한 쪽은 여덟 줄이
    34글자 접두어를 여덟 번 반복했다. 디렉토리로 묶으면 그것이 한 번이 되고, 저장소의
    모양이 같은 눈길에 들어온다.

    링크는 버리지 않는다. `File`이 주소를 받지 못하므로(`name: string`, `icon?: ReactNode`)
    바깥을 `<a>`로 감싼다. 트리 아래에 링크 목록을 따로 두면 같은 접두어를 두 번 반복하게
    되고, 그것이 이 변환이 없애려던 바로 그 반복이다.
    """
    grouped: dict[str, list[tuple[str, str]]] = {}
    for path, url in paths:
        directory, _, name = path.rpartition("/")
        grouped.setdefault(directory, []).append((name or path, url))

    def item(name: str, url: str, indent: str) -> str:
        node = f'<File name="{_escape(name)}" />'
        return f'{indent}<a href="{_escape(url)}">{node}</a>' if url else f"{indent}{node}"

    lines = ["<Files>"]
    for directory in sorted(grouped):
        if directory:
            lines.append(f'  <Folder name="{_escape(directory)}" defaultOpen>')
            lines += [item(name, url, "    ") for name, url in grouped[directory]]
            lines.append("  </Folder>")
        else:
            lines += [item(name, url, "  ") for name, url in grouped[directory]]
    lines.append("</Files>")
    return "\n".join(lines)


def _sources_to_component(body: str) -> str:
    """근거 목록의 `<details>`를 사이트 컴포넌트로 바꾼다.

    위키 원문은 건드리지 않는다. `<details>`는 GitHub 에서 그대로 접히는 표준 형태이고,
    이 변환은 사이트 쪽에서만 뜻이 있다(사이트에서는 아무 꾸밈 없는 맨 위젯으로 나온다).
    """
    start = body.find(_SOURCES_OPEN)
    if start == -1:
        return body
    end = body.find(_SOURCES_CLOSE, start)
    if end == -1:
        return body
    block = body[start:end]
    paths = [
        (linked or plain, url)
        for linked, url, plain in _SOURCE_ITEM.findall(block)
        if linked or plain
    ]
    if not paths:
        return body
    summary = block[len(_SOURCES_OPEN) :].split("</summary>", 1)[0].strip()
    replaced = "\n".join(
        [
            "<Accordions>",
            f'<Accordion title="근거 소스 {_escape(summary)}">',
            "",
            _files_tree(paths),
            "",
            "</Accordion>",
            "</Accordions>",
        ]
    )
    return body[:start] + replaced + body[end + len(_SOURCES_CLOSE) :]


# MDX 가 코드로 읽는 자리. 중괄호는 JSX 표현식이고, `<`로 시작하는 이름은 컴포넌트다.
# 사실의 값에 그런 글자가 들어 있을 수 있다 — kafka 의 `api-checker`가 의존 판을
# `${apiCheckerVersions.junit}` 같은 Gradle 변수로 적어 두었고, 그것이 표에 실려
# 사이트 빌드를 깨뜨렸다(2026-09-10). 위키 원문은 Markdown 이라 그대로 두어야 하고,
# 막는 자리는 MDX 로 옮기는 여기다.
# ast-grep-ignore: regex-on-structure — 어휘: 중괄호 한 글자 판정이다.
_BRACE = re.compile(r"[{}]")


def _mdx_safe(body: str) -> str:
    """MDX 가 코드로 읽을 글자를 막는다. 코드 울타리 안과 컴포넌트 호출은 건드리지 않는다.

    울타리 안은 MDX 도 코드로 읽지 않으므로 그대로 둔다. 울타리 밖에서도 이 도구가 직접
    넣은 컴포넌트 줄(`<Mermaid`, `<Files`, `<Accordion`, `<File`, `<Folder`, `<a`, `</`)은
    JSX 로 읽혀야 하므로 건드리지 않는다.
    """
    out: list[str] = []
    inside = False
    for line in body.splitlines():
        if line.strip().startswith(_FENCE):
            inside = not inside
            out.append(line)
            continue
        if inside or line.lstrip().startswith(("<", "{")):
            out.append(line)
            continue
        out.append(_BRACE.sub(lambda m: "\\" + m.group(0), line))
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
        f"{_mdx_safe(_sources_to_component(_mermaid_to_component(body))).strip()}\n"
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
