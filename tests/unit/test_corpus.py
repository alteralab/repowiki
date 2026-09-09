"""비코드 사실의 단위 검사.

여기서 고정하는 것은 "무엇을 문서로 보는가"이다. 라이선스 머리말을 문서의 절로 읽으면
페이지가 그것을 도메인 근거로 인용하고, 그 순간 위키는 저장소가 아니라 라이선스를 설명한다.
"""

from __future__ import annotations

from repowiki.analyze.corpus import build, citable_paths, config_keys_of, headings_of, role_of

MARKDOWN = """# 제목

문단.

## 절 하나

내용.

```
# 울타리 안의 우물 정 자는 제목이 아니다
```

## 절 둘

끝.
"""


def test_role_puts_test_paths_first() -> None:
    assert role_of("src/test/java/a/README.md", True, False) == "test"
    assert role_of("README.md", False, False) == "doc"
    assert role_of(".github/workflows/ci.yml", False, False) == "ci"
    assert role_of("pom.xml", False, False) == "build"
    assert role_of("config/server.properties", False, False) == "config"
    assert role_of("bin/run.sh", False, False) == "script"
    assert role_of("src/main/java/A.java", False, True) == "main"
    assert role_of("assets/logo.png", False, False) == "data"


def test_headings_skip_code_fences_and_span_their_section() -> None:
    found = headings_of("doc.md", MARKDOWN)
    assert [(h.level, h.title) for h in found] == [
        (1, "제목"),
        (2, "절 하나"),
        (2, "절 둘"),
    ]
    # 절 하나는 절 둘이 시작하기 전까지다.
    assert found[1].span.start_line == 5
    assert found[1].span.end_line == 12


def test_a_document_without_headings_is_still_citable_as_a_whole() -> None:
    found = headings_of("README.md", "배지와 산문만 있는 문서다.\n두 줄이다.\n")
    assert [(h.title, h.span.start_line, h.span.end_line) for h in found] == [
        ("README.md", 1, 2)
    ]


def test_a_txt_file_is_not_a_document() -> None:
    assert role_of("NOTICE.txt", False, False) == "data"
    assert "NOTICE.txt" not in citable_paths(["NOTICE.txt", "README.md"], set(), set())


def test_config_keys_skip_comments_lists_and_block_openers() -> None:
    text = "# 주석\nname: repowiki\nempty:\n  - 목록\n[section]\nport = 8080\n"
    found = config_keys_of("app.yml", text)
    assert [(k.key, k.value, k.span.start_line) for k in found] == [
        ("name", "repowiki", 2),
        ("port", "8080", 6),
    ]


def test_build_indexes_only_documents_and_settings() -> None:
    facts = build(
        {"README.md": MARKDOWN, "app.yml": "port: 1\n", "src/A.java": "class A {}"},
        ["README.md", "app.yml", "src/A.java"],
        {"src/A.java"},
        set(),
        ["."],
    )
    assert {r.path: r.role for r in facts.roles} == {
        "README.md": "doc",
        "app.yml": "config",
        "src/A.java": "main",
    }
    assert {h.path for h in facts.headings} == {"README.md"}
    assert {k.path for k in facts.config_keys} == {"app.yml"}
