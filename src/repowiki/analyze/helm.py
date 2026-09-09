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


def _keys(text: str, dropped: list[str] | None = None) -> list[tuple[str, str, int]]:
    """YAML 의 키를 점 표기 경로와 값과 줄 번호와 함께 낸다.

    `safe_load`가 아니라 `compose_all`을 쓴다. `safe_load`는 값만 내고 자리를 버리며,
    단일 문서 `compose`는 `---`가 있으면 예외를 낸다. 그 예외를 빈 목록으로 삼키면 그
    차트의 values 와 이미지와 참조가 통째로 사라지면서 계수에도 안 남는다
    (2026-09-10 적대적 리뷰가 재현했다). 자리가 없는 사실은 이 도구가 실을 수 없다(SC-1.7).

    같은 경로가 여러 번 나오면 YAML 의 규칙대로 고른다. 규칙이 둘이고 서로 반대다.

      같은 매핑 안에 같은 키가 두 번 있으면 **뒤엣것**이 이긴다.
      머지(`<<`)로 온 것은 명시한 것에 지고, 머지 목록은 **앞엣것**이 이긴다.

    그래서 어느 쪽에서 왔는지를 함께 들고 다닌다. 자리로 가르려 하면 틀린다 — 앵커가
    가리키는 노드는 원 선언의 줄을 그대로 들고 있어서 명시 키와 자리가 겹칠 수 있다.
    """
    found: list[tuple[str, str, int, bool]] = []
    try:
        for node in yaml.compose_all(text):
            if node is not None:
                _walk(node, "", found, set(), False, dropped if dropped is not None else [])
    except yaml.YAMLError:
        return []
    chosen: dict[str, tuple[str, str, int, bool]] = {}
    for item in found:
        previous = chosen.get(item[0])
        if previous is None:
            chosen[item[0]] = item
        elif not previous[3] and not item[3]:
            # 둘 다 명시 키다. 같은 매핑의 중복이므로 뒤엣것이 이긴다.
            chosen[item[0]] = item
        elif previous[3] and not item[3]:
            # 먼저 담긴 것이 머지고 이번 것이 명시다. 명시가 이긴다.
            chosen[item[0]] = item
        # 나머지는 먼저 담긴 것이 이긴다. 머지 목록의 앞엣것이 그렇다.
    order = dict.fromkeys(item[0] for item in found)
    return [(key, chosen[key][1], chosen[key][2]) for key in order]


# 값이 비어 있는 선언의 표시. `affinity: {}`도 선언이고 템플릿이 그것을 쓴다.
# 값 자체가 없다는 것과 키가 없다는 것은 다르다.
EMPTY = "(빈 값)"


def _is_merge(key) -> bool:
    """이 열쇠가 머지 지시(`<<`)인가. 키가 아니라 "여기에 저것을 펴라"는 뜻이다."""
    return key.tag == "tag:yaml.org,2002:merge" or key.value == "<<"


def _merge_sources(value) -> list:
    """머지가 가리키는 매핑들. 목록이면 앞엣것이 이긴다(YAML 1.1 머지 규칙)."""
    return list(value.value) if isinstance(value, yaml.SequenceNode) else [value]


def _walk(
    node,
    prefix: str,
    out: list[tuple[str, str, int, bool]],
    seen: set[int],
    merged_in: bool,
    dropped: list[str],
) -> None:
    """매핑을 따라 내려가며 키를 모은다. 목록 안은 열쇠가 없으므로 들어가지 않는다.

    빈 매핑과 빈 목록도 키다. `affinity: {}`와 `tolerations: []`는 차트가 "이 자리를
    비워 두었다"고 선언한 것이고, 템플릿이 `.Values.affinity`로 실제로 쓴다. 스칼라만
    걷으면 그 참조가 선언에 안 닿아 엣지가 통째로 사라진다(2026-09-10 실측:
    prometheus-community 에서 6438건이 그렇게 빠졌다).

    머지의 우선순위는 YAML 이 정한다. 명시한 키가 머지로 가져온 것을 이기고, 머지 목록은
    앞엣것이 뒤엣것을 이긴다. 발견 순서대로 담고 마지막을 채택하면 둘 다 반대가 된다
    (2026-09-10 적대적 리뷰가 `target: {x: explicit, <<: *base}`가 `base`로 기록되는
    것을 재현했다). 그래서 명시 키를 먼저 담고 머지를 뒤에 담되, 채택은 `_keys`가
    **먼저 담긴 것**으로 한다.
    """
    if not isinstance(node, yaml.MappingNode) or id(node) in seen:
        return
    seen = seen | {id(node)}
    merges: list = []
    for key, value in node.value:
        if not isinstance(key, yaml.ScalarNode):
            continue
        if _is_merge(key):
            merges.extend(_merge_sources(value))
            continue
        # 키에 점이 들어 있으면 점 표기로 이을 수 없다. `a.b: x`와 `a: {b: x}`는 서로
        # 다른 선언인데 둘 다 `a.b`가 되고, `.Values.a.b` 참조가 엉뚱한 쪽에 붙는다.
        # Helm 에서 점 든 키는 `index .Values "a.b"`로만 닿으므로 이 참조 규칙의 대상이
        # 아니다. 세지 않고 넘긴다 — 없는 것을 있다고 하지 않는다(C-BRANCH-3).
        if "." in str(key.value):
            # 세지 않고 넘기면 사라진 것이 안 보인다. 자리와 함께 남긴다.
            # 실측(helm-prom, 2026-09-10): 점 든 리터럴 키 18개와 그 아래 하나를 합쳐
            # 19개가 이렇게 빠지고, 그 이름과 똑같은 점 표기 참조는 0개였다.
            # `nodeSelector.kubernetes.io/os`, `annotations.prometheus.io/scrape` 같은
            # 것들이다. 엣지로 잇지 않는 판단은 그대로 두되 잃었다는 사실은 남긴다.
            dropped.append(f"{prefix}.{key.value}" if prefix else str(key.value))
            continue
        path = f"{prefix}.{key.value}" if prefix else key.value
        line = key.start_mark.line + 1
        if isinstance(value, yaml.ScalarNode):
            out.append((path, value.value, line, merged_in))
        elif not value.value:
            out.append((path, EMPTY, line, merged_in))
        else:
            # 안이 채워진 매핑과 목록은 그 자체도 키이고 안쪽도 키다. 템플릿이 둘 다 쓴다.
            out.append((path, EMPTY, line, merged_in))
            _walk(value, path, out, seen, merged_in, dropped)
    # 머지는 명시 키를 다 담은 뒤에 담는다. 목록의 앞엣것이 이기므로 순서를 지킨다.
    for merged in merges:
        _walk(merged, prefix, out, seen, True, dropped)


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
        dropped: list[str] = []
        for key, value, line in _keys(texts[path], dropped):
            found.append(
                HelmValue(
                    chart=name,
                    key=key,
                    value=mask(key, value, rules),
                    span=Span(path=path, start_line=line, end_line=line),
                )
            )
        counts["점이 든 values 키"] += len(dropped)
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
    """이 파일이 어느 차트의 템플릿인가. 차트 뿌리의 `templates/` 아래여야 한다.

    저장소 루트의 차트는 뿌리가 `.`이다. 조각을 이어 붙이면 빈 문자열이 되므로 그 자리를
    `.`으로 되돌린다. 이것이 없으면 단일 차트 저장소의 템플릿이 어느 차트에도 안 붙는다.
    """
    parts = PurePosixPath(path).parts
    if "templates" not in parts:
        return None
    index = parts.index("templates")
    root = "/".join(parts[:index]) or "."
    return by_directory.get(root)
