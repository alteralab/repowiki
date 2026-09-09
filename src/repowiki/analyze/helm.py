"""Helm 차트의 선언과 참조(PLAN §2.7, SPEC SC-2b.1).

경계 계약: 입력은 파일 경로와 그 내용이고 출력은 `HelmFacts`다. 파일을 읽지 않고 명령을
부르지 않는다(C-DEPTH-3).

렌더하지 않는다. `helm template`은 의존이 있는 차트에서 `helm dependency build`를
요구하고 그 명령은 차트 저장소를 내려받는다. 오프라인 반입이 전제인 이 도구의 기본
경로에 둘 수 없다. 실측(2026-09-09, prometheus-community/helm-charts): 차트 46개 중
4개가 의존을 선언하고 그 넷은 네트워크 없이 렌더가 실패한다. 같은 날 DeepWiki 의 Helm
저장소 다섯 곳 203쪽을 실측했더니 `# Source:` 표식이 0건이었다 — 그쪽도 렌더하지 않고
소스를 그대로 인용한다.

파서가 둘인 이유가 있다. `Chart.yaml`과 `values.yaml`은 유효한 YAML 이라 PyYAML 의
노드 표식으로 점 표기 경로와 줄 번호를 함께 얻는다. `templates/`는 Go 템플릿이라 YAML
파서가 거부한다(ast-grep 의 yaml 문법도 ERROR 노드를 낸다). 그쪽은 `.Values.x.y`라는
고정된 어휘를 줄 단위로 찾는다. 어휘가 고정돼 있고 범위가 한 줄이라 그것이 맞는 도구다.

사각: 템플릿의 제어 흐름을 읽지 않는다. `if`나 `range` 안의 참조도 밖의 것과 같게 센다.
`.Values` 를 변수에 담아 쓰는 형태(`{{ $v := .Values.x }}`)는 그 담는 자리만 잡는다.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import PurePosixPath

import yaml

from repowiki.analyze.corpus import SecretRules, mask
from repowiki.models import (
    HelmChart,
    HelmDependency,
    HelmFacts,
    HelmImage,
    HelmUse,
    HelmValue,
    Span,
)

CHART_FILE = "Chart.yaml"
VALUES_FILE = "values.yaml"

# 템플릿이 values 를 가리키는 형태. `.Values` 뒤에 점으로 이어진 이름들이다.
# ast-grep-ignore: regex-on-structure — 어휘: Go 템플릿의 고정 표기 판정이다.
_USE = re.compile(r"\.Values((?:\.[A-Za-z_][A-Za-z0-9_]*)+)")


def chart_root(path: str) -> str:
    """이 파일이 속한 차트의 뿌리. `Chart.yaml`이 있는 디렉토리다."""
    return str(PurePosixPath(path).parent)


def _keys(text: str) -> list[tuple[str, str, int]]:
    """YAML 의 키를 점 표기 경로와 값과 줄 번호와 함께 낸다.

    `safe_load`가 아니라 `compose`를 쓴다. 앞의 것은 값만 내고 자리를 버린다. 자리가 없는
    사실은 이 도구가 실을 수 없다(SC-1.7).
    """
    try:
        node = yaml.compose(text)
    except yaml.YAMLError:
        return []
    if node is None:
        return []
    found: list[tuple[str, str, int]] = []
    _walk(node, "", found)
    return found


# 값이 비어 있는 선언의 표시. `affinity: {}`도 선언이고 템플릿이 그것을 쓴다.
# 값 자체가 없다는 것과 키가 없다는 것은 다르다.
EMPTY = "(빈 값)"


def _walk(node, prefix: str, out: list[tuple[str, str, int]]) -> None:
    """매핑을 따라 내려가며 키를 모은다. 목록 안은 열쇠가 없으므로 들어가지 않는다.

    빈 매핑과 빈 목록도 키다. `affinity: {}`와 `tolerations: []`는 차트가 "이 자리를
    비워 두었다"고 선언한 것이고, 템플릿이 `.Values.affinity`로 실제로 쓴다. 스칼라만
    걷으면 그 참조가 선언에 안 닿아 엣지가 통째로 사라진다(2026-09-10 실측:
    prometheus-community 에서 6438건이 그렇게 빠졌다).
    """
    if not isinstance(node, yaml.MappingNode):
        return
    for key, value in node.value:
        if not isinstance(key, yaml.ScalarNode):
            continue
        path = f"{prefix}.{key.value}" if prefix else key.value
        line = key.start_mark.line + 1
        if isinstance(value, yaml.ScalarNode):
            out.append((path, value.value, line))
        elif not value.value:
            out.append((path, EMPTY, line))
        else:
            # 안이 채워진 매핑과 목록은 그 자체도 키이고 안쪽도 키다. 템플릿이 둘 다 쓴다.
            out.append((path, EMPTY, line))
            _walk(value, path, out)


def _chart_of(text: str, path: str) -> tuple[HelmChart, list[HelmDependency]] | None:
    """`Chart.yaml` 하나를 차트와 의존 목록으로."""
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(loaded, dict) or not loaded.get("name"):
        return None
    lines = {key: line for key, _, line in _keys(text)}
    directory = chart_root(path)
    chart = HelmChart(
        name=str(loaded["name"]),
        version=str(loaded.get("version", "")),
        app_version=str(loaded.get("appVersion", "")),
        directory=directory,
        span=Span(path=path, start_line=lines.get("name", 1), end_line=lines.get("name", 1)),
    )
    found: list[HelmDependency] = []
    for position, item in enumerate(loaded.get("dependencies") or []):
        if not isinstance(item, dict) or not item.get("name"):
            continue
        line = lines.get(f"dependencies.{position}.name", chart.span.start_line)
        found.append(
            HelmDependency(
                chart=chart.name,
                name=str(item["name"]),
                version=str(item.get("version", "")),
                repository=str(item.get("repository", "")),
                condition=str(item.get("condition", "")),
                span=Span(path=path, start_line=line, end_line=line),
            )
        )
    return chart, found


def _dependency_lines(text: str) -> list[int]:
    """의존 항목이 시작하는 줄. `compose`는 목록 안으로 들어가지 않으므로 따로 센다."""
    node = None
    try:
        node = yaml.compose(text)
    except yaml.YAMLError:
        return []
    if not isinstance(node, yaml.MappingNode):
        return []
    for key, value in node.value:
        if getattr(key, "value", "") == "dependencies" and isinstance(value, yaml.SequenceNode):
            return [item.start_mark.line + 1 for item in value.value]
    return []


def _images(chart: str, values: list[HelmValue]) -> list[HelmImage]:
    """`repository`와 `tag`가 같은 부모 아래 있으면 한 이미지다."""
    by_parent: dict[str, dict[str, HelmValue]] = {}
    for item in values:
        head, _, leaf = item.key.rpartition(".")
        if leaf in ("repository", "tag"):
            by_parent.setdefault(head, {})[leaf] = item
    found: list[HelmImage] = []
    for parent in sorted(by_parent):
        pair = by_parent[parent]
        if "repository" not in pair:
            continue
        repository = pair["repository"]
        tag = pair.get("tag")
        found.append(
            HelmImage(
                chart=chart,
                repository=repository.value,
                tag=tag.value if tag is not None else "",
                span=repository.span,
            )
        )
    return found


def _charts_of(texts: dict[str, str]) -> tuple[list[HelmChart], list[HelmDependency]]:
    """저장소의 모든 `Chart.yaml`을 차트와 의존으로."""
    charts: list[HelmChart] = []
    dependencies: list[HelmDependency] = []
    for path in sorted(texts):
        if PurePosixPath(path).name != CHART_FILE:
            continue
        made = _chart_of(texts[path], path)
        if made is None:
            continue
        chart, deps = made
        lines = _dependency_lines(texts[path])
        for position, item in enumerate(deps):
            if position < len(lines):
                item.span = Span(path=path, start_line=lines[position], end_line=lines[position])
        charts.append(chart)
        dependencies.extend(deps)
    return charts, dependencies


def _values_of(
    texts: dict[str, str],
    by_directory: dict[str, str],
    rules: SecretRules,
    counts: Counter[str],
) -> list[HelmValue]:
    """차트마다의 `values.yaml`. 자격증명 유사 키의 값은 가린다(SC-2b.4)."""
    found: list[HelmValue] = []
    for path in sorted(texts):
        if PurePosixPath(path).name != VALUES_FILE:
            continue
        name = by_directory.get(chart_root(path))
        if name is None:
            counts["차트 밖의 values.yaml"] += 1
            continue
        for key, value, line in _keys(texts[path]):
            found.append(
                HelmValue(
                    chart=name,
                    key=key,
                    value=mask(key, value, rules),
                    span=Span(path=path, start_line=line, end_line=line),
                )
            )
    return found


def _uses_of(
    texts: dict[str, str],
    by_directory: dict[str, str],
    declared: set[tuple[str, str]],
    counts: Counter[str],
) -> list[HelmUse]:
    """템플릿이 values 키를 쓰는 자리. 선언에 안 닿는 참조는 엣지가 아니다."""
    found: list[HelmUse] = []
    for path in sorted(texts):
        name = _template_chart(path, by_directory)
        if name is None:
            continue
        for line, text in enumerate(texts[path].splitlines(), start=1):
            for match in _USE.finditer(text):
                key = match.group(1)[1:]
                if (name, key) not in declared:
                    counts["선언되지 않은 values 키"] += 1
                    continue
                found.append(
                    HelmUse(
                        chart=name,
                        key=key,
                        span=Span(path=path, start_line=line, end_line=line),
                    )
                )
    return found


def build(texts: dict[str, str], rules: SecretRules) -> HelmFacts | None:
    """Helm 사실. `Chart.yaml`이 하나도 없으면 `None`이다."""
    charts, dependencies = _charts_of(texts)
    if not charts:
        return None

    by_directory = {chart.directory: chart.name for chart in charts}
    counts: Counter[str] = Counter()
    values = _values_of(texts, by_directory, rules, counts)
    uses = _uses_of(texts, by_directory, {(v.chart, v.key) for v in values}, counts)
    images: list[HelmImage] = []
    for chart in charts:
        images.extend(_images(chart.name, [v for v in values if v.chart == chart.name]))

    return HelmFacts(
        charts=charts,
        dependencies=dependencies,
        values=values,
        uses=uses,
        images=images,
        unresolved=[f"{reason} {count}건" for reason, count in sorted(counts.items()) if count],
    )


def _template_chart(path: str, by_directory: dict[str, str]) -> str | None:
    """이 파일이 어느 차트의 템플릿인가. 차트 뿌리의 `templates/` 아래여야 한다."""
    parts = PurePosixPath(path).parts
    if "templates" not in parts:
        return None
    index = parts.index("templates")
    root = "/".join(parts[:index]) or "."
    return by_directory.get(root)
