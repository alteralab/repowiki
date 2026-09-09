"""사이트 어댑터. Fumadocs 프로젝트를 세우고 빌드하고 루프백으로 연다(PLAN §0 사이트).

경계 계약: 이 파일이 npm과 next와 http.server를 아는 유일한 자리다. 서버는 127.0.0.1에만
바인드한다 — 서빙은 이 계획의 범위 밖이고, 여기서 여는 것은 사람이 자기 기계에서 읽기
위한 것이다.

사각: `npm install`은 네트워크가 필요하다. 반입 환경에서는 `node_modules`를 이미지에 함께
싣고 이 함수를 건너뛴다(PLAN §8 자산 manifest).
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pydantic import BaseModel

TEMPLATE = Path(__file__).resolve().parent.parent / "data" / "site-template"


class SiteError(RuntimeError):
    """사이트 준비나 빌드 실패."""


class BuildResult(BaseModel):
    """빌드 결과. `out`은 정적 export 디렉토리다."""

    out: str
    pages: int
    seconds: float


APP_NAME_TOKEN = "__REPOWIKI_APP_NAME__"


def _replace(source: Path, destination: Path) -> None:
    """대상 자리를 비우고 원본을 옮긴다. 파일과 디렉토리를 같은 방식으로 다룬다."""
    if destination.is_dir():
        shutil.rmtree(destination)
    elif destination.exists():
        destination.unlink()
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def scaffold(target: Path, content: dict[str, str], app_name: str = "repowiki") -> None:
    """템플릿을 옮기고 콘텐츠를 채운다. `node_modules`는 건드리지 않는다.

    템플릿의 상표 자리는 표식으로 두고 여기서 저장소 이름으로 바꾼다.
    """
    if not TEMPLATE.exists():
        raise SiteError(f"사이트 템플릿이 없다: {TEMPLATE}")
    target.mkdir(parents=True, exist_ok=True)
    for item in TEMPLATE.iterdir():
        if item.name != "content":
            _replace(item, target / item.name)

    shared = target / "lib" / "shared.ts"
    if shared.exists():
        shared.write_text(
            shared.read_text(encoding="utf-8").replace(APP_NAME_TOKEN, app_name), encoding="utf-8"
        )

    docs = target / "content" / "docs"
    if docs.exists():
        shutil.rmtree(docs)
    docs.mkdir(parents=True)
    for path, text in content.items():
        file = docs / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")


def install(target: Path, offline: bool) -> None:
    """의존성을 설치한다. 이미 있으면 건너뛴다."""
    if (target / "node_modules").exists():
        return
    args = ["npm", "ci"] + (["--offline"] if offline else [])
    result = subprocess.run(args, cwd=target, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        raise SiteError(f"npm ci 종료 상태 {result.returncode}: {result.stderr.strip()[:400]}")


def build(target: Path) -> BuildResult:
    """정적 export를 만든다."""
    import time

    started = time.time()
    result = subprocess.run(  # noqa: S603
        ["npx", "--no-install", "next", "build"],
        cwd=target,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SiteError(f"next build 종료 상태 {result.returncode}: {result.stderr.strip()[:600]}")
    out = target / "out"
    pages = len(list(out.rglob("index.html"))) if out.exists() else 0
    return BuildResult(out=str(out), pages=pages, seconds=round(time.time() - started, 1))


def serve(directory: Path, port: int) -> tuple[ThreadingHTTPServer, str]:
    """루프백에서 정적 파일을 낸다. 외부 인터페이스에 바인드하지 않는다."""
    handler = partial(_QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


# 문자 집합을 붙여 내보낼 형식. 붙이지 않으면 브라우저가 인코딩을 추측하고, 한글 본문이
# 깨져 보인다(`llms.txt`가 그랬다). 파일은 정상 UTF-8인데 헤더가 그 사실을 말하지 않은 것이다.
_TEXT_TYPES = (
    "text/plain",
    "text/html",
    "text/markdown",
    "text/css",
    "text/csv",
    "application/javascript",
    "application/json",
    "application/xml",
)


class _QuietHandler(SimpleHTTPRequestHandler):
    """요청 로그를 표준 오류로 쏟지 않고, 글자 파일에 문자 집합을 붙이는 핸들러."""

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".md": "text/markdown",
        ".mdx": "text/markdown",
        ".txt": "text/plain",
    }

    def guess_type(self, path: str) -> str:
        """이 파일의 형식. 글자 파일이면 UTF-8이라고 밝힌다."""
        found = super().guess_type(path)
        base = found.split(";", 1)[0].strip()
        return f"{base}; charset=utf-8" if base in _TEXT_TYPES else found

    def log_message(self, *_args: object) -> None:
        return
