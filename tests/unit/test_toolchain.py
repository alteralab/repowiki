"""도구 사슬 파서의 단위 검사.

버전 표는 사람이 그대로 믿는 자리다. 여기서 고정하는 것은 "저장소가 적은 것만 읽는다"이다.
부모 POM이 저장소 밖이면 `${...}`가 그대로 남아야 하고, 지어내면 안 된다.
"""

from __future__ import annotations

from repowiki.analyze.toolchain import build, manifest_paths

POM = """<project>
  <properties>
    <maven.compiler.source>1.8</maven.compiler.source>
    <maven.compiler.target>1.8</maven.compiler.target>
    <commons.io.version>2.22.0</commons.io.version>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.junit</groupId>
        <artifactId>junit-bom</artifactId>
        <version>5.11.4</version>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>commons-io</groupId>
      <artifactId>commons-io</artifactId>
      <version>${commons.io.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit</groupId>
      <artifactId>junit-bom</artifactId>
    </dependency>
    <dependency>
      <groupId>org.example</groupId>
      <artifactId>outside</artifactId>
      <version>${not.declared.here}</version>
    </dependency>
  </dependencies>
</project>
"""

PYPROJECT = """[project]
requires-python = ">=3.10,!=3.15"
dependencies = [
  "pydantic==2.13.5",
  "networkx>=3.6",
]

[project.optional-dependencies]
api = ["anthropic==0.80.0"]
"""

PACKAGE_JSON = """{
  "name": "site",
  "engines": {
    "node": ">=22"
  },
  "dependencies": {
    "next": "16.3.4"
  },
  "devDependencies": {
    "typescript": "5.9.3"
  }
}
"""

GO_MOD = """module example.com/svc

go 1.25.0

require (
\tgithub.com/google/uuid v1.6.0
\tgithub.com/davecgh/go-spew v1.1.1 // indirect
)
"""


def test_manifest_paths_skips_vendored_and_installed_trees() -> None:
    chosen = manifest_paths(
        [
            "pom.xml",
            "web/package.json",
            "web/node_modules/left-pad/package.json",
            "third/vendor/x/go.mod",
            "src/Main.java",
        ]
    )
    assert chosen == ["pom.xml", "web/package.json"]


def test_maven_reads_language_version_and_resolves_declared_properties() -> None:
    facts = build({"pom.xml": POM}, ["."])
    versions = {(v.language, v.version) for v in facts.languages}
    assert versions == {("Java", "1.8")}
    by_name = {d.name: d for d in facts.dependencies}
    assert by_name["commons-io:commons-io"].version == "2.22.0"
    assert by_name["commons-io:commons-io"].scope == "test"


def test_dependency_management_supplies_a_missing_version_and_is_not_a_dependency() -> None:
    facts = build({"pom.xml": POM}, ["."])
    names = [d.name for d in facts.dependencies]
    assert names.count("org.junit:junit-bom") == 1
    assert next(d for d in facts.dependencies if d.name == "org.junit:junit-bom").version == "5.11.4"


def test_a_property_declared_outside_the_repository_stays_unresolved() -> None:
    facts = build({"pom.xml": POM}, ["."])
    outside = next(d for d in facts.dependencies if d.name == "org.example:outside")
    assert outside.version == "${not.declared.here}"


def test_pyproject_reads_requires_python_and_both_dependency_groups() -> None:
    facts = build({"pyproject.toml": PYPROJECT}, ["."])
    assert [(v.language, v.version) for v in facts.languages] == [("Python", ">=3.10,!=3.15")]
    found = {(d.name, d.version, d.scope) for d in facts.dependencies}
    assert found == {
        ("pydantic", "==2.13.5", "main"),
        ("networkx", ">=3.6", "main"),
        ("anthropic", "==0.80.0", "api"),
    }


def test_package_json_reads_engines_and_separates_dev_dependencies() -> None:
    facts = build({"package.json": PACKAGE_JSON}, ["."])
    assert [(v.language, v.version) for v in facts.languages] == [("Node", ">=22")]
    assert {(d.name, d.version, d.scope) for d in facts.dependencies} == {
        ("next", "16.3.4", "main"),
        ("typescript", "5.9.3", "dev"),
    }


def test_go_mod_reads_the_go_line_and_marks_indirect_requirements() -> None:
    facts = build({"go.mod": GO_MOD}, ["."])
    assert [(v.language, v.version) for v in facts.languages] == [("Go", "1.25.0")]
    assert {(d.name, d.scope) for d in facts.dependencies} == {
        ("github.com/google/uuid", "main"),
        ("github.com/davecgh/go-spew", "indirect"),
    }


def test_every_citation_points_at_the_line_that_declares_it() -> None:
    facts = build({"pyproject.toml": PYPROJECT}, ["."])
    lines = PYPROJECT.splitlines()
    for dependency in facts.dependencies:
        quoted = lines[dependency.span.start_line - 1]
        assert dependency.name in quoted


PARENT_POM = """<project>
  <properties>
    <x.version>1.0</x.version>
  </properties>
</project>
"""

CHILD_POM = """<project>
  <parent>
    <relativePath>../pom.xml</relativePath>
  </parent>
  <dependencies>
    <dependency>
      <groupId>g</groupId>
      <artifactId>a</artifactId>
      <version>${x.version}</version>
    </dependency>
  </dependencies>
</project>
"""

SIBLING_POM = """<project>
  <properties>
    <x.version>2.0</x.version>
  </properties>
</project>
"""

STRANGER_POM = """<project>
  <dependencies>
    <dependency>
      <groupId>g</groupId>
      <artifactId>b</artifactId>
      <version>${x.version}</version>
    </dependency>
  </dependencies>
</project>
"""


def test_a_property_is_inherited_along_the_declared_parent_chain() -> None:
    facts = build(
        {"pom.xml": PARENT_POM, "mod/pom.xml": CHILD_POM, "other/pom.xml": SIBLING_POM},
        ["."],
    )
    assert [(d.name, d.version) for d in facts.dependencies] == [("g:a", "1.0")]


def test_an_unrelated_sibling_pom_does_not_supply_a_property() -> None:
    facts = build({"a/pom.xml": SIBLING_POM, "c/pom.xml": STRANGER_POM}, ["."])
    assert [(d.name, d.version) for d in facts.dependencies] == [("g:b", "${x.version}")]


def test_an_environment_marker_quote_is_not_a_separate_dependency() -> None:
    text = '[project]\ndependencies = [\n  "importlib-metadata; python_version < \'3.12\'",\n]\n'
    facts = build({"pyproject.toml": text}, ["."])
    assert [(d.name, d.version) for d in facts.dependencies] == [("importlib-metadata", "")]


def test_extras_are_not_a_version() -> None:
    text = '[project]\ndependencies = ["requests[security]>=2"]\n'
    facts = build({"pyproject.toml": text}, ["."])
    assert [(d.name, d.version) for d in facts.dependencies] == [("requests", ">=2")]


def test_a_version_catalog_joins_group_and_name_and_refuses_a_guessed_version() -> None:
    text = (
        "[versions]\n"
        'v = "1.2.3"\n'
        "[libraries]\n"
        'foo = { group = "org.example", name = "thing", version.ref = "v" }\n'
        'bar = { module = "g:a", classifier = "docs.api" }\n'
    )
    facts = build({"gradle/libs.versions.toml": text}, ["."])
    assert {(d.name, d.version) for d in facts.dependencies} == {
        ("org.example:thing", "1.2.3"),
        ("g:a", ""),
    }
