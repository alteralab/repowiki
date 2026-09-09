"""인용을 소스 링크로 바꾼다. 순수 계산이다(C-DEPTH-3).

경계 계약: 입력은 원격 URL과 커밋과 자리이고 출력은 URL 문자열이다. 네트워크를 부르지
않는다 — 링크가 실제로 열리는지는 이 층이 아는 일이 아니다.

링크는 분석 커밋에 고정한다. 브랜치 이름으로 걸면 저장소가 움직인 뒤 위키의 줄 번호가
다른 코드를 가리키고, 그 순간 근거는 근거가 아니게 된다.

사각: 호스트 판정은 `data/forges.yml`의 표를 따른다. 표에 없는 호스트는 링크를 만들지
않고 경로 문자열로 남긴다. 없는 링크보다 틀린 링크가 나쁘다.
"""

from __future__ import annotations

from urllib.parse import quote

import yaml
from pydantic import BaseModel

from repowiki.analyze.domain import DATA_DIR
from repowiki.models import Span


class Forge(BaseModel):
    """호스팅 종류 하나. `blob`은 경로 앞에 붙는 조각이다."""

    name: str
    match: list[str]
    blob: str
    line: str


def load_forges() -> list[Forge]:
    """`data/forges.yml`이 호스팅 규칙의 정본이다."""
    raw = yaml.safe_load((DATA_DIR / "forges.yml").read_text(encoding="utf-8"))
    return [Forge(name=name, **values) for name, values in raw["forges"].items()]


def normalize(remote_url: str) -> str:
    """원격 URL을 웹 주소의 뿌리로 만든다. 못 만들면 빈 문자열이다.

    `git@host:group/project.git`과 `https://host/group/project.git`을 같은 자리로 모은다.
    자격 증명이 박힌 URL은 그 부분을 버린다 — 위키에 실릴 문자열이다(C-SEC-1).
    """
    url = remote_url.strip()
    if not url:
        return ""
    from_ssh = True
    if url.startswith("git@"):
        host, _, path = url[4:].partition(":")
        if not host or not path:
            return ""
        url = f"https://{host}/{path}"
    elif url.startswith("ssh://"):
        url = "https://" + url[6:]
    elif url.startswith(("http://", "https://")):
        from_ssh = False
    else:
        return ""
    _, _, rest = url.partition("://")
    authority, _, path = rest.partition("/")
    if "@" in authority:
        authority = authority.split("@", 1)[1]
    if from_ssh and ":" in authority:
        # ssh 포트는 웹 포트가 아니다. 그대로 두면 열리지 않는 주소가 된다.
        authority = authority.split(":", 1)[0]
    # 질의와 조각은 버린다. 원격 URL에 토큰이 질의로 붙어 있는 일이 있고, 그것을 그대로
    # 두면 위키의 모든 인용 링크에 그 토큰이 실린다(C-SEC-1).
    path = path.split("?", 1)[0].split("#", 1)[0]
    if not authority:
        return ""
    # 스킴은 https로 고정한다. 평문 http로 적힌 원격을 위키가 퍼뜨릴 이유가 없다.
    return f"https://{authority}/{path}".removesuffix(".git").rstrip("/")


def _safe_commit(commit: str) -> str:
    """커밋 해시. 16진수가 아니면 링크를 만들지 않는다 — 주소에 실릴 값이다."""
    cleaned = commit.strip()
    if not cleaned or len(cleaned) > 64:
        return ""
    return cleaned if all(ch in "0123456789abcdefABCDEF" for ch in cleaned) else ""


def _safe_path(path: str) -> str:
    """저장소 상대 경로를 URL 조각으로. 위로 올라가는 경로는 거부한다.

    파일 이름에는 공백과 `#`과 `?`가 들어갈 수 있다. 인코딩하지 않으면 `#`이 조각을 열어
    링크가 다른 파일의 다른 줄을 가리킨다.
    """
    if not path or path.startswith("/") or ".." in path.split("/"):
        return ""
    return "/".join(quote(segment, safe="") for segment in path.split("/"))


def _host_matches(host: str, forge: Forge) -> bool:
    """호스트가 이 호스팅에 속하는가. 점 경계로 맞춘다.

    부분 문자열로 맞추면 `evilgithub.com`이 `github.com`으로 통과한다. 그 링크는 위키가
    사람을 남의 사이트로 보내는 것이다(C-SEC-1).
    """
    bare = host.split(":", 1)[0].lower()
    for token in forge.match:
        marker = token.rstrip(".").lower()
        if bare == marker or bare.endswith(f".{marker}"):
            return True
    return False


def source_url(remote_url: str, commit: str, span: Span, forges: list[Forge]) -> str:
    """자리 하나를 가리키는 웹 주소. 만들 수 없으면 빈 문자열이다.

    만들 수 없을 때 빈 문자열을 내는 것이 계약이다. 없는 링크보다 틀린 링크가 나쁘다.
    """
    base = normalize(remote_url)
    safe_commit = _safe_commit(commit)
    safe_path = _safe_path(span.path)
    if not base or not safe_commit or not safe_path:
        return ""
    host = base.split("://", 1)[1].split("/", 1)[0]
    forge = next((f for f in forges if _host_matches(host, f)), None)
    if forge is None:
        return ""
    anchor = forge.line.format(start=span.start_line, end=span.end_line)
    return f"{base}{forge.blob.format(commit=safe_commit)}/{safe_path}{anchor}"
