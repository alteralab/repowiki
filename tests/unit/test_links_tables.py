"""소스 링크와 사실 표의 단위 검사.

링크는 위키에 실려 사람이 누른다. 자격 증명이 섞이거나 커밋이 아닌 브랜치를 가리키면
그 위키는 틀린 자리를 보여 준다. 표는 게이트가 문자 단위로 비교하므로 렌더가 정본이다.
"""

from __future__ import annotations

from repowiki.bundle.links import Forge, normalize, source_url
from repowiki.bundle.tables import blocks_in, body_of, html_tables_in, render
from repowiki.models import FactTable, Span

FORGES = [
    Forge(name="github", match=["github.com"], blob="/blob/{commit}", line="#L{start}-L{end}"),
    Forge(name="gitlab", match=["gitlab.corp.io"], blob="/-/blob/{commit}", line="#L{start}-{end}"),
]
SPAN = Span(path="src/Main.java", start_line=10, end_line=20)


def test_normalize_accepts_ssh_and_https_and_drops_credentials() -> None:
    assert normalize("git@github.com:apache/kafka.git") == "https://github.com/apache/kafka"
    assert normalize("https://user:token@github.com/o/r.git") == "https://github.com/o/r"


def test_normalize_drops_the_ssh_port_but_keeps_an_https_port() -> None:
    assert normalize("ssh://git@gitlab.corp.io:22/g/p.git") == "https://gitlab.corp.io/g/p"
    assert normalize("https://gitlab.corp.io:8443/g/p.git") == "https://gitlab.corp.io:8443/g/p"


def test_source_url_pins_the_commit_and_uses_the_host_line_syntax() -> None:
    assert source_url("https://github.com/o/r", "abc123", SPAN, FORGES) == (
        "https://github.com/o/r/blob/abc123/src/Main.java#L10-L20"
    )
    assert source_url("https://gitlab.corp.io/g/p", "abc123", SPAN, FORGES) == (
        "https://gitlab.corp.io/g/p/-/blob/abc123/src/Main.java#L10-20"
    )


def test_an_unknown_host_makes_no_link_rather_than_a_wrong_one() -> None:
    assert source_url("https://svn.example.org/r", "abc123", SPAN, FORGES) == ""


def test_no_remote_and_no_commit_make_no_link() -> None:
    assert source_url("", "abc123", SPAN, FORGES) == ""
    assert source_url("https://github.com/o/r", "", SPAN, FORGES) == ""


def test_render_escapes_pipes_and_pads_short_rows() -> None:
    table = FactTable(
        id="t1",
        title="언어 버전",
        columns=["언어", "버전", "근거"],
        rows=[["Java", "1.8", "pom.xml:L89"], ["Kotlin|JVM", "2.1"]],
        note="부모 POM이 저장소 밖이면 값이 풀리지 않는다.",
    )
    text = render(table)
    assert "**언어 버전**" in text
    assert "| Kotlin\\|JVM | 2.1 |  |" in text
    assert text.rstrip().endswith("부모 POM이 저장소 밖이면 값이 풀리지 않는다.")


def test_body_of_is_exactly_what_blocks_in_finds_in_a_page() -> None:
    table = FactTable(id="t1", title="표", columns=["a", "b"], rows=[["1", "2"]])
    page = f"머리말\n\n{render(table)}\n\n꼬리말\n"
    assert body_of(table) in blocks_in(page)


def test_blocks_in_ignores_pipes_inside_a_code_fence() -> None:
    page = "글\n\n```\n| a | b |\n| --- | --- |\n```\n\n끝\n"
    assert blocks_in(page) == []


def test_a_url_query_is_dropped_so_a_token_never_reaches_the_wiki() -> None:
    assert normalize("https://github.com/org/repo.git?access_token=SECRET") == (
        "https://github.com/org/repo"
    )


def test_a_plain_http_remote_becomes_https() -> None:
    assert normalize("http://gitlab.corp.io/g/p.git") == "https://gitlab.corp.io/g/p"


def test_a_path_with_a_hash_is_encoded_so_the_anchor_still_works() -> None:
    span = Span(path="docs/a#old.md", start_line=1, end_line=2)
    assert source_url("https://github.com/o/r", "abc123", span, FORGES) == (
        "https://github.com/o/r/blob/abc123/docs/a%23old.md#L1-L2"
    )


def test_a_commit_that_is_not_a_hash_makes_no_link() -> None:
    assert source_url("https://github.com/o/r", "refs/heads/main", SPAN, FORGES) == ""


def test_a_path_that_escapes_the_repository_makes_no_link() -> None:
    span = Span(path="../etc/passwd", start_line=1, end_line=1)
    assert source_url("https://github.com/o/r", "abc123", span, FORGES) == ""


def test_prose_beginning_with_a_pipe_is_not_a_table() -> None:
    assert blocks_in("| 이것은 산문이다\n다음 줄") == []


def test_a_table_inside_a_blockquote_is_still_a_table() -> None:
    page = "> | 버전 | 값 |\n> | --- | --- |\n> | Java | 999 |\n"
    assert len(blocks_in(page)) == 1


def test_html_tables_are_counted_separately() -> None:
    assert html_tables_in("<table><tr><td>1</td></tr></table>") == 1


def test_a_lookalike_host_is_not_matched() -> None:
    """`evilgithub.com`은 `github.com`이 아니다. 부분 문자열 판정이면 통과한다."""
    assert source_url("https://evilgithub.com/o/r", "abc123", SPAN, FORGES) == ""


def test_a_subdomain_of_a_known_host_matches() -> None:
    assert source_url("https://code.gitlab.corp.io/g/p", "abc123", SPAN, FORGES).startswith(
        "https://code.gitlab.corp.io/g/p/-/blob/abc123/"
    )


def test_a_table_without_leading_pipes_is_still_a_table() -> None:
    assert len(blocks_in("A | B\n--- | ---\n999 | 지어낸 값")) == 1


def test_a_table_inside_an_html_comment_is_not_rendered_and_not_counted() -> None:
    assert blocks_in("<!--\n| a | b |\n| --- | --- |\n-->") == []
    assert html_tables_in("<!-- <table> -->") == 0
