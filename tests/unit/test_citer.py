"""인용 표기의 단위 검사. 위키의 모든 인용이 이 하나를 지난다(C-DUP-2)."""

from __future__ import annotations

from repowiki.bundle.links import Citer, Forge
from repowiki.models import Span

FORGES = [Forge(name="github", match=["github.com"], blob="/blob/{commit}", line="#L{start}-L{end}")]
SPAN = Span(path="pom.xml", start_line=89, end_line=89)


def test_a_citation_becomes_a_link_when_the_remote_is_known() -> None:
    citer = Citer(remote_url="https://github.com/o/r", commit="abc123", forges=FORGES)
    assert citer.markdown(SPAN) == (
        "[`pom.xml:L89-L89`](https://github.com/o/r/blob/abc123/pom.xml#L89-L89)"
    )


def test_a_citation_without_a_remote_keeps_the_path_and_lines() -> None:
    """반입 환경에는 원격이 없다. 그때도 사람이 손으로 찾아갈 수 있어야 한다."""
    assert Citer().markdown(SPAN) == "`pom.xml:L89-L89`"
