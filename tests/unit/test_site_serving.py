"""루프백 서빙의 단위 검사.

여기서 고정하는 것은 "글자 파일에는 문자 집합을 밝힌다"이다. 밝히지 않으면 브라우저가
인코딩을 추측하고, 파일이 정상 UTF-8인데도 한글이 깨져 보인다.
"""

from __future__ import annotations

from http.client import HTTPConnection
from pathlib import Path

from repowiki.adapters.site import serve


def _served(tmp_path: Path, name: str, text: str) -> tuple[str, str]:
    (tmp_path / name).write_text(text, encoding="utf-8")
    server, _url = serve(tmp_path, 0)
    try:
        port = server.server_address[1]
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", f"/{name}")
        response = connection.getresponse()
        header = response.getheader("Content-Type") or ""
        body = response.read().decode("utf-8")
        connection.close()
        return header, body
    finally:
        server.shutdown()
        server.server_close()


def test_a_text_file_is_served_as_utf8(tmp_path: Path) -> None:
    header, body = _served(tmp_path, "llms.txt", "# 아키텍처 위키\n")
    assert header == "text/plain; charset=utf-8"
    assert body == "# 아키텍처 위키\n"


def test_markdown_is_served_as_utf8(tmp_path: Path) -> None:
    header, _ = _served(tmp_path, "page.md", "# 제목\n")
    assert header == "text/markdown; charset=utf-8"


def test_a_binary_file_keeps_its_own_type(tmp_path: Path) -> None:
    """이진 파일에 문자 집합을 붙이면 안 된다. 글자가 아니기 때문이다."""
    (tmp_path / "a.png").write_bytes(b"\x89PNG\r\n")
    server, _ = serve(tmp_path, 0)
    try:
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        connection.request("GET", "/a.png")
        header = connection.getresponse().getheader("Content-Type") or ""
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
    assert "charset" not in header
