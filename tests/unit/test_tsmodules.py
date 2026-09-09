"""TypeScript 모듈 해석의 단위 검사.

여기서 고정하는 것은 해석의 순서와 후보 시험 순서다. 순서가 곧 우선순위라, 바뀌면 같은
임포트가 다른 파일로 풀린다. 그리고 못 푸는 것을 푼 것으로 만들지 않는다 — 저장소 밖의
패키지를 저장소 안의 우연히 같은 이름의 파일로 잇는 것이 이 층의 가장 나쁜 실패다.
"""

from __future__ import annotations

from repowiki.analyze.tsmodules import build, load_configs, parse_jsonc

APP_CONFIG = """{
  // tsconfig 는 JSON 이 아니라 JSONC 다.
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "src/*": ["./src/*"],
      "openapi/*": ["./openapi-gen/*"],
      "*": ["./*"],
    },
  },
}
"""

FILES = [
    "ui/tsconfig.json",
    "ui/src/utils/index.ts",
    "ui/src/theme.ts",
    "ui/src/components/Clear/index.tsx",
    "ui/src/components/Clear/Button.tsx",
    "ui/src/pages/DagsList/DagCard.tsx",
    "ui/src/pages/DagsList/List.tsx",
    "ui/openapi-gen/queries/index.ts",
    "ui/src/types.d.ts",
    "ui/src/legacy.js",
    "other/src/theme.ts",
]


def _resolver():
    return build(load_configs({"ui/tsconfig.json": APP_CONFIG}), FILES)


def test_jsonc_reads_comments_and_trailing_commas() -> None:
    data = parse_jsonc(APP_CONFIG)
    assert data["compilerOptions"]["paths"]["src/*"] == ["./src/*"]


def test_jsonc_does_not_treat_a_slash_inside_a_string_as_a_comment() -> None:
    data = parse_jsonc('{"a": "http://x//y", "b": "/* not a comment */"}')
    assert data == {"a": "http://x//y", "b": "/* not a comment */"}


def test_a_relative_import_resolves_within_its_own_directory() -> None:
    found = _resolver().resolve("./List", "ui/src/pages/DagsList/DagCard.tsx")
    assert (found.kind, found.target) == ("relative", "ui/src/pages/DagsList/List.tsx")


def test_a_directory_resolves_to_its_index_file() -> None:
    found = _resolver().resolve("src/components/Clear", "ui/src/pages/DagsList/DagCard.tsx")
    assert (found.kind, found.target) == ("alias", "ui/src/components/Clear/index.tsx")


def test_a_path_alias_is_substituted() -> None:
    found = _resolver().resolve("openapi/queries", "ui/src/theme.ts")
    assert (found.kind, found.target) == ("alias", "ui/openapi-gen/queries/index.ts")


def test_the_longer_alias_prefix_wins_over_the_catch_all_star() -> None:
    """`*` 무늬는 무엇이든 걸린다. 그것이 `src/*`를 이기면 별칭이 뜻을 잃는다."""
    found = _resolver().resolve("src/utils", "ui/src/theme.ts")
    assert found.target == "ui/src/utils/index.ts"


def test_a_js_specifier_finds_the_ts_file() -> None:
    """NodeNext 는 `./a.js`로 적고 `./a.ts`를 가리킨다."""
    found = _resolver().resolve("../../theme.js", "ui/src/components/Clear/index.tsx")
    assert found.target == "ui/src/theme.ts"


def test_a_real_js_file_still_resolves_when_no_ts_twin_exists() -> None:
    found = _resolver().resolve("./legacy.js", "ui/src/theme.ts")
    assert found.target == "ui/src/legacy.js"


def test_a_package_outside_the_repository_is_not_linked_to_a_same_named_file() -> None:
    """`react`는 패키지다. 저장소 안에 같은 이름의 파일이 있어도 그것이 아니다."""
    found = _resolver().resolve("react", "ui/src/theme.ts")
    assert (found.kind, found.target) == ("external", "")


def test_a_file_outside_the_config_directory_does_not_get_its_aliases() -> None:
    """`other/`에는 tsconfig 가 없다. `src/theme`이 UI 의 별칭으로 풀리면 안 된다."""
    found = _resolver().resolve("src/theme", "other/src/main.ts")
    assert (found.kind, found.target) == ("external", "")


def test_an_unresolvable_relative_import_is_named_as_such() -> None:
    """상대 경로인데 파일이 없다. 저장소 밖이라고 말하면 거짓이다."""
    found = _resolver().resolve("./gridHover.css", "ui/src/theme.ts")
    assert found.kind == "unresolved-relative"


def test_a_relative_path_escaping_the_repository_root_resolves_to_nothing() -> None:
    found = _resolver().resolve("../../../etc/passwd", "ui/src/theme.ts")
    assert found.target == ""


def test_extends_inherits_the_parent_paths_and_the_child_wins() -> None:
    base = '{"compilerOptions": {"baseUrl": ".", "paths": {"a/*": ["./base/*"]}}}'
    child = '{"extends": "./tsconfig.base.json", "compilerOptions": {"paths": {"b/*": ["./src/*"]}}}'
    files = ["p/tsconfig.base.json", "p/tsconfig.json", "p/src/x.ts", "p/base/y.ts", "p/main.ts"]
    resolver = build(
        load_configs({"p/tsconfig.base.json": base, "p/tsconfig.json": child}), files
    )
    assert resolver.resolve("b/x", "p/main.ts").target == "p/src/x.ts"
    assert resolver.resolve("a/y", "p/main.ts").target == "p/base/y.ts"
