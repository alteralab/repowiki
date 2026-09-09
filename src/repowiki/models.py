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
    remote_url: str = ""
    file_count: int
    languages: dict[str, LanguageStat]
    excluded: dict[str, int] = Field(default_factory=dict)


class CallEdge(BaseModel):
    """멤버 사이의 호출 하나.

    `receiver_kind`는 수신자를 어떤 스코프에서 풀었는지다. 이 값이 있어야 나중에 "필드로
    들고 있는 협력자"와 "인자로 받은 협력자"를 갈라 볼 수 있다.
    """

    src_type: str
    src_member: str
    dst_type: str
    dst_member: str
    span: Span
    src_module: str
    dst_module: str
    src_path: str
    dst_path: str
    receiver_kind: str


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


class HistoryFacts(BaseModel):
    """이력 사실. 계산은 `analyze/history.py`가 하고 이 형태로 경계를 넘는다."""

    window_months: int
    commit_count: int
    hotspots: list[dict]
    couplings: list[dict]
    issue_keys: dict
    periods: list[dict] = Field(default_factory=list)


class PageType(StrEnum):
    """페이지 종류. frontmatter의 `type`과 같은 값이다(PLAN §2.4)."""

    QUICKSTART = "quickstart"
    ARCHITECTURE_OVERVIEW = "architecture-overview"
    SUBSYSTEM = "subsystem"
    MODULE = "module"
    FLOWS = "flows"
    HISTORY = "history"
    STACK = "stack"
    CONCEPT = "concept"
    QUALITY = "quality"
    USAGE = "usage"
    DATA_MODEL = "data-model"


class FactTable(BaseModel):
    """페이지에 실릴 표 하나. 값은 전부 사실에서 왔고 LLM은 이 표를 고치지 않는다.

    다이어그램과 같은 규칙이다. 표에 든 숫자와 버전은 사람이 그대로 믿을 자리라, 쓰는 층이
    한 칸이라도 바꾸면 그 페이지는 근거 없는 값을 실은 것이 된다.
    """

    id: str
    title: str
    columns: list[str]
    rows: list[list[str]]
    note: str = ""


class ToolVersion(BaseModel):
    """언어나 런타임의 버전 선언 하나. `source`는 그 값을 적은 자리의 이름이다."""

    language: str
    version: str
    source: str
    module: str
    span: Span


class Dependency(BaseModel):
    """라이브러리 하나. `version`이 비면 저장소가 버전을 적지 않은 것이다."""

    name: str
    version: str
    scope: str
    ecosystem: str
    module: str
    span: Span


class ToolchainFacts(BaseModel):
    """도구 사슬 사실. 계산은 `analyze/toolchain.py`가 한다."""

    languages: list[ToolVersion] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    truncated: int = 0


class Evidence(BaseModel):
    """페이지가 인용할 수 있는 근거 하나. `id`로 가리키고 `span`이 자리다.

    `text`는 그 자리의 원문이다. 이것이 없으면 쓰는 층은 구조만 보고 쓰게 되고, 구조에서
    나올 수 있는 문장은 "A가 B에 기댄다" 부류로 닫힌다. 무엇을 볼지는 결정층이 정하고,
    본 것만 말하며 본 자리를 가리키는 것이 근거 계약이다(docs/plans/depth.md).
    """

    id: str
    span: Span
    note: str
    text: str = ""


class PageJob(BaseModel):
    """페이지 하나를 쓰는 작업. LLM은 이 안의 사실만 읽는다(PLAN §2.1, §4)."""

    id: str
    path: str
    type: PageType
    title: str
    purpose: str
    facts: dict
    section: str = ""
    parent: str | None = None
    siblings: list[dict] = Field(default_factory=list)
    evidence: list[Evidence]
    diagrams: list[Diagram] = Field(default_factory=list)
    tables: list[FactTable] = Field(default_factory=list)
    input_hash: str


class PageOutput(BaseModel):
    """세션이나 SDK가 낸 페이지. `submit`이 이 형태로 검증한다."""

    job_id: str
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    body_markdown: str
    citations: list[str] = Field(default_factory=list)


class EntityFacts(BaseModel):
    """데이터 모델 사실. 계산은 `analyze/entities.py`가 한다."""

    entities: list[dict] = Field(default_factory=list)
    relations: list[dict] = Field(default_factory=list)


class FileRole(BaseModel):
    """파일 하나의 역할. 이 값이 페이지가 무엇을 인용해도 되는지를 가른다."""

    path: str
    role: str
    module: str


class Heading(BaseModel):
    """문서의 제목 하나. `level`은 1부터다."""

    path: str
    level: int
    title: str
    span: Span


class ConfigKey(BaseModel):
    """설정 키 하나. `value`는 적힌 그대로이고 해석하지 않는다."""

    path: str
    key: str
    value: str
    span: Span


class Cluster(BaseModel):
    """개념 묶음 하나. `source`는 무엇이 이 묶음을 정했는지다."""

    id: str
    title: str
    directory: str
    module: str
    members: list[str] = Field(default_factory=list)
    source: str


class CorpusFacts(BaseModel):
    """비코드 사실. 계산은 `analyze/corpus.py`가 한다."""

    roles: list[FileRole] = Field(default_factory=list)
    headings: list[Heading] = Field(default_factory=list)
    config_keys: list[ConfigKey] = Field(default_factory=list)


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
    history: HistoryFacts | None = None
    entities: EntityFacts | None = None
    call_edges: list[CallEdge] = Field(default_factory=list)
    clusters: list[Cluster] = Field(default_factory=list)
    type_labels: dict[str, str] = Field(default_factory=dict)
    corpus: CorpusFacts | None = None
    toolchain: ToolchainFacts | None = None
    unresolved: list[str] = Field(default_factory=list)
