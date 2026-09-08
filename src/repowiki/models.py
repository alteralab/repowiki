"""경계를 넘는 자료형(C-PY-1). 생산자와 소비자는 PLAN §2.3의 표를 따른다.

이 모듈은 계산을 하지 않는다. 계약만 있다. 필드의 의미가 바뀌면 PLAN §2.3과
같은 편집 단위에서 고친다(C-COMMENT-1).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RepoKind(StrEnum):
    """저장소 종류. 감지 순서와 조건은 PLAN §2.7."""

    CODE = "code"
    HELM = "helm"
    TERRAFORM = "terraform"
    K8S = "k8s"
    MIXED = "mixed"


class Span(BaseModel):
    """근거 위치. 줄 번호는 1부터 세고 양 끝을 포함한다.

    `path`는 저장소 루트 기준 POSIX 경로다. 절대 경로를 담지 않는다(C-STATE-4).
    """

    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    def cite(self) -> str:
        """인용 문자열 `path:Lx-Ly`. 페이지 본문과 `.report.json`이 같은 형식을 쓴다."""
        return f"{self.path}:L{self.start_line}-L{self.end_line}"


class SymbolKind(StrEnum):
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    RECORD = "record"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    FIELD = "field"
    FUNCTION = "function"


class Symbol(BaseModel):
    """선언 하나. `module`은 파일이 속한 모듈 id이고 `parent`는 감싸는 타입의 이름이다."""

    kind: SymbolKind
    name: str
    span: Span
    module: str
    language: str
    parent: str | None = None
    is_test: bool = False


class Module(BaseModel):
    """빌드 파일 경계로 자른 모듈. `id`는 저장소 루트 기준 상대 디렉토리다."""

    id: str
    build_file: str | None
    languages: dict[str, int] = Field(default_factory=dict)
    file_count: int = 0
    main_file_count: int = 0
    subsystem: str | None = None


class ModuleEdge(BaseModel):
    """모듈 사이의 import 엣지. `weight`는 뒷받침하는 import 건수다."""

    src: str
    dst: str
    weight: int
    evidence: list[Span] = Field(default_factory=list)


class SubsystemSource(StrEnum):
    BUILD_TREE = "build-tree"
    LOUVAIN = "louvain"
    INSTRUCTIONS = "instructions"


class Subsystem(BaseModel):
    id: str
    modules: list[str]
    source: SubsystemSource


class TypeEdgeKind(StrEnum):
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    FIELD_TYPE = "field_type"
    PARAM_TYPE = "param_type"
    STATIC_CALL = "static_call"
    CALL = "call"


class TypeEdge(BaseModel):
    """타입 사이의 관계. `resolution`은 근거의 출처다.

    `static`은 ast-grep 정적 근사이고, 해석기를 붙이면 `cbm`이 된다(PLAN §2.3).
    해석되지 않은 이름은 엣지를 만들지 않는다.
    """

    src: str
    dst: str
    kind: TypeEdgeKind
    resolution: str = "static"
    span: Span
    src_module: str
    dst_module: str | None = None
    # 양 끝의 선언 위치와 정규화된 이름. 단순 이름만으로는 같은 이름의 다른 선언을
    # 구분하지 못하고, 파일 하나에 중첩 선언이 여럿이면 경로도 부족하다. 이 넷이
    # 엣지의 식별자이자 위키가 링크할 자리다.
    src_path: str | None = None
    dst_path: str | None = None
    src_declaration: Span | None = None
    dst_declaration: Span | None = None
    src_qualified: str | None = None
    dst_qualified: str | None = None


class EntryPointKind(StrEnum):
    MAIN = "main"
    ROUTE = "route"
    CLI = "cli"
    SCHEDULER = "scheduler"
    LISTENER = "listener"


class EntryPoint(BaseModel):
    kind: EntryPointKind
    name: str
    span: Span
    module: str
    framework: str | None = None


class FileRank(BaseModel):
    """파일 랭킹. 세 점수의 산식은 PLAN §2.3과 `analyze/rank.py`가 소유한다."""

    path: str
    module: str
    authority: float
    hub: float
    fused: float


class FlowHop(BaseModel):
    """흐름의 한 홉. 근거 span이 없는 홉은 만들지 않는다(PLAN §1 비목표)."""

    src_module: str
    dst_module: str
    kind: TypeEdgeKind
    span: Span
    symbol: str


class CrossModuleFlow(BaseModel):
    """진입점에서 시작해 모듈 둘 이상을 지나는 경로."""

    id: str
    entry: EntryPoint
    hops: list[FlowHop]
    modules: list[str]


class LanguageStat(BaseModel):
    files: int
    lines: int
    main_files: int


class RepoProfile(BaseModel):
    """저장소 개요. `excluded`는 제외 글로브별 파일 수이고 사유를 함께 담는다."""

    root_name: str
    kind: RepoKind
    head_sha: str
    file_count: int
    languages: dict[str, LanguageStat]
    excluded: dict[str, int] = Field(default_factory=dict)


class DiagramLimit(BaseModel):
    """다이어그램 한도와 레이아웃. 정본은 `data/diagram-limits.yml`이다(PLAN §2.5).

    `layout`은 렌더 엔진 이름이다. `dagre`는 Mermaid 내장이라 지시문을 넣지 않고,
    그 밖의 값은 소스 머리에 init 지시문으로 적는다.
    """

    level: str
    max_nodes: int
    max_source_chars: int
    max_blocks_per_page: int
    layout: str = "dagre"


class Diagram(BaseModel):
    """컴파일된 Mermaid 블록 하나. `degraded_reason`이 있으면 사다리에서 강등된 것이다."""

    id: str
    level: str
    source: str
    node_count: int
    edge_count: int
    degraded_reason: str | None = None


class RepoFacts(BaseModel):
    """결정층의 산출 전부. LLM 층은 이 자료만 읽는다(PLAN §2.1)."""

    profile: RepoProfile
    modules: list[Module]
    module_edges: list[ModuleEdge]
    subsystems: list[Subsystem]
    symbols: list[Symbol]
    type_edges: list[TypeEdge]
    entry_points: list[EntryPoint]
    file_ranks: list[FileRank]
    flows: list[CrossModuleFlow]
    diagrams: list[Diagram]
    unresolved: list[str] = Field(default_factory=list)
