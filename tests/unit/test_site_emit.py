"""위키 Markdown 을 사이트 콘텐츠로 옮기는 층의 검사.

여기서 고정하는 것은 위키 원문과 사이트 산출의 경계다. 위키는 GitHub 에서 보이는 형태로
남고, 사이트에서만 뜻이 있는 변환은 이쪽에서만 일어난다.
"""

from __future__ import annotations

from repowiki.bundle.site_emit import to_site_page

def test_the_source_list_becomes_a_file_tree() -> None:
    """평평한 목록은 같은 접두어를 파일 수만큼 되풀이한다. 디렉토리로 묶으면 한 번이다."""
    body = (
        "<details>\n<summary>근거 소스 2개</summary>\n\n"
        "- [`a/b/One.java`](https://host/blob/c/a/b/One.java#L1-L1)\n"
        "- [`a/b/Two.java`](https://host/blob/c/a/b/Two.java#L1-L1)\n\n"
        "</details>\n\n본문."
    )
    page = to_site_page("x.md", f"---\ntitle: t\n---\n{body}")
    assert "<details>" not in page.content
    assert '<Folder name="a/b" defaultOpen>' in page.content
    assert '<File name="One.java" />' in page.content
    # 접두어가 한 번만 나온다. 트리 밖에 링크 목록을 또 두면 그 반복이 되살아난다.
    assert page.content.count("a/b/One.java") == 1


def test_the_tree_keeps_the_link_to_the_source() -> None:
    """`File`이 주소를 못 받으므로 바깥을 감싼다. 링크가 사라지면 자리로 갈 수 없다."""
    body = (
        "<details>\n<summary>근거 소스 1개</summary>\n\n"
        "- [`a/One.java`](https://host/blob/c/a/One.java#L1-L1)\n\n"
        "</details>\n\n본문."
    )
    page = to_site_page("x.md", f"---\ntitle: t\n---\n{body}")
    assert '<a href="https://host/blob/c/a/One.java#L1-L1">' in page.content


def test_a_source_list_without_links_still_becomes_a_tree() -> None:
    """원격이 없는 저장소는 주소가 없다. 그때도 무엇을 읽었는지는 보여야 한다."""
    body = (
        "<details>\n<summary>근거 소스 1개</summary>\n\n- `a/One.java`\n\n</details>\n\n본문."
    )
    page = to_site_page("x.md", f"---\ntitle: t\n---\n{body}")
    assert '<File name="One.java" />' in page.content
    assert "<a href=" not in page.content


def test_a_page_without_a_source_list_is_untouched() -> None:
    body = "본문만 있다."
    page = to_site_page("x.md", f"---\ntitle: t\n---\n{body}")
    assert "<Files>" not in page.content
    assert "본문만 있다." in page.content


def test_the_sidebar_keeps_the_order_it_was_given() -> None:
    """계획이 정한 순서가 사이드바의 순서다. 사전순으로 다시 줄 세우면 그 판단이 버려진다.

    실측이 그 판단을 받친다. DeepWiki 저장소 53곳에서 첫 1단 항목이 예외 없이 Overview 다.
    """
    import json

    from repowiki.bundle.site_emit import meta_files

    given = ["overview/a.mdx", "areas/b.mdx", "concepts/c.mdx", "glossary.mdx"]
    root = json.loads(meta_files(given, "x")["meta.json"])
    assert root["pages"] == ["overview", "areas", "concepts", "glossary"]


def test_an_internal_link_loses_its_extension_and_gains_a_level() -> None:
    """정적 내보내기가 쪽마다 디렉토리를 만들어 상대 경로의 기준이 한 단 깊어진다."""
    page = to_site_page(
        "glossary.md", '---\ntitle: t\n---\n[a](concepts/x.md) [b](https://h/y.md)'
    )
    assert "](../concepts/x)" in page.content
    # 밖으로 나가는 주소는 건드리지 않는다. 그 `.md`는 진짜 파일 이름이다.
    assert "](https://h/y.md)" in page.content


def test_a_page_carries_the_day_it_was_made() -> None:
    """위키는 생성물이라 언제 것인지가 읽는 사람의 판단에 들어간다.

    분석 커밋은 "무엇을 보고 썼는가"이고 이것은 "언제 썼는가"다. 같은 커밋을 두 번
    분석할 수 있고 그때 바뀌는 것은 이쪽이다.
    """
    page = to_site_page(
        "x.md",
        '---\ntitle: t\ngenerated: {by: "repowiki/0.1.0", at: "2026-09-09T23:14:12+00:00"}\n---\n본문.',
    )
    assert "2026-09-09" in page.content
    assert "23:14" not in page.content
