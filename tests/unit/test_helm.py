"""Helm 색인의 단위 검사.

여기서 고정하는 것은 YAML 의 까다로운 모양들이다. 이것들이 틀리면 위키가 없는 선언을
있다고 하거나, 있는 참조를 조용히 버린다.
"""

from __future__ import annotations

from repowiki.analyze.corpus import load_secret_rules, mask
from repowiki.analyze.helm import _keys


def test_a_multi_document_values_file_is_not_lost() -> None:
    """`---`가 있으면 단일 문서 파서는 예외를 낸다. 삼키면 그 차트가 통째로 사라진다."""
    assert _keys("a: 1\n---\nb: 2\n") == [("a", "1", 1), ("b", "2", 3)]


def test_a_merge_key_is_expanded_not_recorded() -> None:
    """`<<: *base`는 키가 아니라 지시다. 그대로 두면 `target.<<`라는 없는 선언이 생긴다."""
    got = dict((key, value) for key, value, _ in _keys("base: &b\n  x: 1\ntarget:\n  <<: *b\n"))
    assert "target.x" in got
    assert not [key for key in got if "<<" in key]


def test_an_explicit_key_beats_a_merged_one() -> None:
    """YAML 은 명시한 키가 머지로 온 것을 이긴다. 반대로 하면 값이 조용히 뒤바뀐다."""
    got = dict((key, value) for key, value, _ in _keys(
        "base: &b {x: base}\ntarget: {x: explicit, <<: *b}\n"
    ))
    assert got["target.x"] == "explicit"


def test_the_first_mapping_in_a_merge_sequence_wins() -> None:
    """`<<: [*a, *b]`는 앞엣것이 이긴다. 발견 순서로 마지막을 쓰면 반대가 된다."""
    got = dict((key, value) for key, value, _ in _keys(
        "a: &a {x: first}\nb: &b {x: second}\nt: {<<: [*a, *b]}\n"
    ))
    assert got["t.x"] == "first"


def test_the_merge_rules_match_pyyaml() -> None:
    """정답은 PyYAML 자신이다. 우리 규칙이 그것과 갈리면 우리가 틀린 것이다."""
    import yaml as _yaml

    for text, holder in (
        ("base: &b {x: base}\ntarget: {x: explicit, <<: *b}\n", "target"),
        ("a: &a {x: first}\nb: &b {x: second}\nt: {<<: [*a, *b]}\n", "t"),
        ("base: &b\n  x: 1\ntarget:\n  <<: *b\n", "target"),
    ):
        truth = str(_yaml.safe_load(text)[holder]["x"])
        got = dict((key, value) for key, value, _ in _keys(text))[f"{holder}.x"]
        assert got == truth, f"{text!r}: PyYAML {truth!r}, 우리 {got!r}"


def test_a_key_containing_a_dot_is_not_a_dotted_path() -> None:
    """`a.b: x`와 `a: {b: x}`는 다른 선언이다. 둘을 합치면 참조가 엉뚱한 쪽에 붙는다.

    Helm 에서 점 든 키는 `index .Values "a.b"`로만 닿으므로 `.Values.a.b` 참조의 대상이
    아니다. 세지 않는다.
    """
    got = _keys('a.b: literal\na:\n  b: nested\n')
    assert ("a.b", "nested", 3) in got
    assert ("a.b", "literal", 1) not in got


def test_a_duplicate_key_keeps_the_last_value() -> None:
    """YAML 은 뒤엣것이 이긴다. 둘 다 내면 있지도 않은 선언이 하나 더 생긴다."""
    assert _keys("a: 1\na: 2\n") == [("a", "2", 2)]


def test_a_base64_wrapped_secret_is_masked() -> None:
    """Kubernetes 의 시크릿은 base64 가 기본 형태다. 겉보기가 평범해 접두어로 안 잡힌다."""
    rules = load_secret_rules()
    # `-----BEGIN PRIVATE KEY-----`를 base64 로 감싼 것
    assert mask("privatePem", "LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0t", rules) == rules.redaction
    # 평범한 값은 건드리지 않는다
    assert mask("image.repository", "nginx", rules) == "nginx"
    assert mask("replicaCount", "3", rules) == "3"


def test_a_pointer_is_not_a_secret() -> None:
    """`configMap.key`는 ConfigMap 안의 키 이름이고 `keyPath`는 파일 경로다.

    가리면 위키가 "이 값이 어디서 오는가"를 말하지 못한다. 값이 실제로 비밀이면 값 모양
    규칙과 base64 풀기가 잡는다.
    """
    rules = load_secret_rules()
    assert mask("kubeApiServer.tlsConfig.ca.configMap.key", "ca.crt", rules) == "ca.crt"
    assert mask("customResourceState.key", "state", rules) == "state"
    assert mask("es.ssl.client.keyPath", "/etc/x", rules) == "/etc/x"
    # 진짜 비밀은 계속 가린다
    assert mask("adminPassword", "p", rules) == rules.redaction
    assert mask("anything", "-----BEGIN PRIVATE KEY-----", rules) == rules.redaction


def test_a_certificate_is_not_a_secret_but_a_private_key_is() -> None:
    """PEM 은 머리로 갈린다. 인증서와 공개키는 공개하라고 있는 것이다.

    `-----BEGIN` 하나로 잡으면 "이 차트가 어느 CA 를 신뢰하는가"를 위키가 못 말한다.
    """
    import base64

    rules = load_secret_rules()
    public = ("-----BEGIN CERTIFICATE-----", "-----BEGIN PUBLIC KEY-----")
    private = (
        "-----BEGIN PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
    )
    for value in public:
        assert mask("caBundle", value, rules) == value
        assert mask("blob", base64.b64encode(value.encode()).decode(), rules) != rules.redaction
    for value in private:
        assert mask("caBundle", value, rules) == rules.redaction
        assert mask("blob", base64.b64encode(value.encode()).decode(), rules) == rules.redaction
