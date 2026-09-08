---
status: 실측 완료 (2026-09-08) — Apache SkyWalking 13 레포(shallow), 추출 파이프라인 5 s, 근거 span 524, 스팟체크 9/9. [web] 출처 URL, UNVERIFIED 표기
scope: 멀티 레포 시스템의 레포 간 관계 결정적 추출, 시스템 수준 문서 형태(C4·arc42·DDD 컨텍스트 맵), SystemGraph 설계
---

# System-level (multi-repo) design research for repowiki

스크립트: `12-scripts/`(`run_all.sh`, `extract_{maven,go,npm,proto,graphql,infra,strings}.py`, `build_graph.py`, `sg_topic_literal.yml`), 웹 리서치 전문 `01_cross_repo_tools.md`, `02_wiki_generators.md`, `03_c4_arc42_ddd.md`.

## 0. TL;DR
1. 조사한 AI 코드 위키 생성기 전부(DeepWiki/Devin Wiki, deepwiki-open, Google Code Wiki, OpenWiki code 모드, CodeWiki)는 **레포 단위**이고 레포 간 관계를 만들지 않는다. deepwiki-open의 멀티 레포 요청(#66, 2025-05)은 미답. 멀티 레포 집계는 관계가 **선언된** 곳(Swimm, Mintlify, Antora, TechDocs)에만 있다. [web]
2. 결정적 레포 간 엣지는 정밀도 순 다섯 증거 계열: **declared**(`.gitmodules`, `catalog-info.yaml`, GitLab `trigger:/include: project:`) > **artifact**(Maven/Go/npm 좌표) > **contract**(proto import/copy, GraphQL root field, OpenAPI) > **config/infra**(이미지명, 토픽 리터럴, 서비스 URL) > **text**(README 링크). 전부 빌드 없이 file:line 근거로 추출 가능. [verified]
3. SkyWalking 13 레포: 클론 4 s, 추출 5 s, **span 524 → 레포 쌍 97(집합 내 41, 그중 비텍스트 근거 30)**; 스팟체크 9/9 정확. 발견해 고친 정밀도 함정: vendored 서드파티 proto(envoy/validate/otel)가 거짓 contract 엣지, 이미지명은 빌더 맵 필요(이름 부분일치 금지), test/e2e 근거는 scope 분리(Maven 엣지 12 중 11이 `test/`).
4. 추출이 **드리프트 신호**를 공짜로 준다: 소비자마다 contract 모듈 핀이 11개월 벌어짐, vendored proto 7파일이 10–388줄 발산, 스키마에 없는 클라이언트 GraphQL 연산 6개, deprecated 필드 사용 1.
5. 권고: `repowiki system <group-url>` → `SystemGraph`(노드=레포, 엣지=종류+근거 span+신뢰 등급+scope) → C4-L1/L2 페이지, 관계 표, "미해결 참조" 페이지; 레포 위키에는 "Part of system X" 배너. LLM 추정 엣지 금지, span 없는 엣지는 존재하지 않는다.

## 1. 신호 카탈로그
| 신호 | 생산 측 | 소비 측 | 추출(빌드 없음) | 정밀도/주의 | 상태 |
|---|---|---|---|---|---|
| Maven artifact | `pom.xml` `groupId:artifactId`(groupId/version은 `<parent>` 상속, artifactId는 아님) | `<dependency>`; 버전은 `${prop}`/BOM | XML 파싱 + `relativePath` 부모 체인; regex로 줄 번호 | 좌표 일치 높음; 외부 BOM이면 버전 미해결. 전이 그래프는 불필요(레포 간은 직접 좌표만) | `extract_maven.py` [verified] |
| Gradle | `group`/`version`, `rootProject.name`; publication 좌표 | `implementation("g:a:v")`, `libs.versions.toml`, `includeBuild` | ast-grep Kotlin/Groovy 문자열 + TOML | 중간: 좌표가 스크립트 실행으로 계산될 수 있음 | 미실행 |
| npm | `package.json` `name`(non-private) | `dependencies`/`dev`/`peer` | JSON | 높음; `workspace:`/`file:` = 모노레포 힌트 | [verified] |
| Python | `[project] name` | dependencies, `requirements*.txt` | TOML/regex | 높음; PEP 503 정규화 | 미실행 |
| Go module | `go.mod` `module`(vanity path 정상) | `require`, `// indirect`, `replace` | 줄 파서 | 매우 높음; pseudo-version에 커밋 날짜 → 드리프트 | [verified] |
| 버전 핀 드리프트 | 생산자 HEAD | 소비자 핀 | 비교; Go는 날짜, 이미지는 SHA vs `gh api` | 결정적; 해석은 "오래됨"이지 "깨짐" 아님 | [verified] |
| .proto contract | `package`, `service`, `option java_package/go_package`; buf `deps` | `import "x/y.proto"`, vendored 복사, submodule | regex; import를 경로 접미로 다른 레포 파일에 해결; 같은 `(package, filename)` 해시 비교 | **함정**: 서드파티 vendored proto가 서로 해결됨 → 네임스페이스 deny-list; 복사본은 발산 | [verified] |
| GraphQL contract | `type Query/Mutation` + `extend type` in `.graphqls` | `.graphql` 연산, TS 템플릿 리터럴 | regex; 최상위 selection 필드를 스키마 root 필드에 매칭 | 높음(root 제한 시); 일반명(`version`)은 root 제한으로 처리 | [verified: 88 엣지] |
| OpenAPI/Avro/JSON schema | `info.title`, `paths`; `.avsc` namespace.name | 외부 `$ref`; 소비 코드의 경로 리터럴 | YAML `$ref`; ast-grep 문자열 리터럴 | 중간: 템플릿 vs 리터럴, `/health` 오탐 | 미실행 |
| Kafka/RabbitMQ/SNS 토픽 | 생산 리터럴, `@KafkaListener(topics=)`, `spring.kafka.*`, AsyncAPI channels | 소비 리터럴 | ast-grep `kind: string_literal` + regex(`sg_topic_literal.yml`); 역할은 같은 파일의 마커(`KafkaProducer`, `@KafkaListener`, `.subscribe(`) | 리터럴은 결정적, **방향은 휴리스틱**(`direction: assumed`); `${TOPIC}`은 미해결 | [verified: 5 토픽 OAP←java-agent] |
| HTTP base URL/서비스명 | k8s `Service`명, compose 서비스명 | `application.yml` URL, `.env.example`, `@FeignClient(name=)`, `http://order-service` | ast-grep Feign; regex host:port; host→레포는 compose/helm service→image→builder 맵 | 중간: host→repo 맵 필요; env 치환 미해결 | 부분 |
| 데이터 저장소 | Flyway/Liquibase `CREATE TABLE`; JPA `@Table(name=)` | 다른 레포의 같은 `@Table`/raw SQL | ast-grep `@Table(name = "$T")`; regex | 무방향 "shared data" | 미실행 |
| 배포/인프라 | 레포 A의 이미지 빌드(`docker build -t`, Makefile `HUB/NAME`, workflow) | Helm `values.yaml` `image.repository`, compose `image:`, k8s, `Dockerfile FROM` | **빌드 지점에서 image→repo 맵** 구성 후 매칭 | **함정**: 이미지명 ≠ 레포명(`apache/skywalking-ui`는 이제 `skywalking-horizon-ui`에서 빌드, `skywalking-helm/.../values.yaml:195-208`) | [verified] |
| CI 교차 프로젝트 | — | GitLab `trigger: project:`(Free), `needs: project:`(Premium), `include: project:`(Free), `include: component:`; GitHub `uses: org/repo@ref` | YAML | 매우 높음(선언) | GitHub 형 27건 [verified]; GitLab 형 미실행 |
| Git submodule | — | `.gitmodules` `url =` | INI | 선언, 최고 신뢰 | [verified: 5] |
| 조직 | Backstage `catalog-info.yaml` `spec.system/dependsOn/providesApis/consumesApis`; GitLab 그룹; CODEOWNERS(Premium) | — | YAML; GitLab API | 선언 = 그룹핑·소유권 정본; SkyWalking에는 0건 | [verified 부재] |
| 텍스트 링크 | — | README의 `github.com/org/<repo>` | regex | 최저 등급; 힌트/미해결 목록 전용 | [verified: 261 span, 29쌍 text-only] |

## 2. 도구 지형 (전문 `01_cross_repo_tools.md`)
Backstage 카탈로그(선언 관계, GitLab discovery provider), GitLab Dependency List/SBOM(Ultimate, 패키지 인벤토리, 서비스 그래프 없음), GitLab CI 키워드(유일한 명시적 repo→repo 엣지), GitHub dependency graph(GHES는 dependents 없음), Sourcegraph(검색+SCIP, 서비스 그래프 없음), CodeScene(커밋 이력 change coupling, 레포당 컴포넌트 1), Structurizr DSL(`workspace extends`, `!include`), Kroki(self-host 렌더), **Code2DFD**(정적 Java/Spring: Feign·Kafka·RabbitMQ·Eureka·compose → DFD, JSS 2023), MicroDepGraph(compose), Prophet(정적 Java → context map, ASE 2021), Context Mapper discovery(`@SpringBootApplication`/`@RequestMapping`/compose `depends_on` → CML, generic U/D만), Cortex/OpsLevel/Port/Compass(선언 yml, SaaS), Confluent Stream Lineage/Conduktor(런타임). UNVERIFIED: "arch-unit-ts"/"madge cross repo", Sourcegraph `repo:deps`, CodeScene 명명된 cross-repo 기능.

## 3. 시스템 문서 형태
### C4 ↔ 레포
| C4 | repowiki 대응 | 근거 |
|---|---|---|
| Landscape | GitLab 인스턴스/최상위 그룹의 모든 시스템 | 그룹핑 규칙 |
| Software System(L1) | **레포 그룹**(Backstage `spec.system`, GitLab 그룹, 공유 parent POM/BOM) + 외부 시스템(집합 밖 대상) | declared > 휴리스틱 |
| Container(L2) | **배포 단위**: 빌드된 이미지/서비스마다 하나; 레포당 0(contract, helm)·1(서비스)·N(skywalking은 `oap`·`data-generator` 두 이미지) | 이미지 빌드 지점, Dockerfile, Helm; 라이브러리·contract 레포는 컨테이너 아님 |
| Component(L3) | 레포 안 모듈 = 기존 레포 위키 | 레포 분석 |
| Dynamic | 양 끝에 contract 엣지가 있을 때만 교차 레포 흐름(agent → Kafka topic → OAP) | contract/config 엣지 |
| Deployment | Helm/compose/k8s | infra 엣지 |
C4 문면: 한 팀 소유 마이크로서비스 = 한 시스템 안 컨테이너 그룹, 다른 팀 = 다른 시스템 → **소유권(CODEOWNERS/GitLab 그룹)이 시스템 경계를 정하고 레포 수는 아니다.**

### arc42: §3 Context and Scope = 시스템 페이지(기술 컨텍스트 표: 엣지마다 채널 gRPC/GraphQL/Kafka/HTTP/Maven — "모든 외부 인터페이스를 보여라"), §5 Building Block L1 = 레포 블랙박스, L2 = 레포 위키, §7 Deployment = Helm/compose, §9 ADR = 미해결 참조 페이지가 ADR 백로그.

### DDD 컨텍스트 맵: 추론 가능 vs 선언
| 관계 | 정적 신호 | 판정 |
|---|---|---|
| Published Language | contract 레포를 ≥2 레포가 소비 | **추론 가능**(SkyWalking `data-collect-protocol`←skywalking, java, goapi; `query-protocol`←skywalking, cli, booster-ui) |
| Open Host Service | 한 레포가 높은 fan-in 스키마/API 노출 | 추론 가능(중간) |
| Shared Kernel | 양쪽이 소비하는 라이브러리 + 양 팀 커밋 | 부분(공동 소유는 이력/CODEOWNERS 필요) |
| Conformist | 상류 모델/DTO 아티팩트 직접 import, 번역층 없음 | 휴리스틱만 |
| Anticorruption Layer | `*Adapter`/`*Translator`/`acl` 패키지 | 휴리스틱만 |
| generic upstream/downstream | 어떤 의존 엣지든 | 추론 가능; Context Mapper도 "customer-supplier와 다르다"고 경고 |
| Customer/Supplier, Partnership | 조직·계획 | **선언 필수** |
| Separate Ways, Big Ball of Mud | 엣지 부재/순환 | 결정으로 추론 불가 |
자동 라벨은 generic U/D + Published Language + OHS만; 나머지는 미해결 페이지의 **후보**로 사람 확인.

## 4. 실측: Apache SkyWalking 13 레포
선택 이유: 순수 contract 레포 둘(`skywalking-data-collect-protocol` gRPC proto, `skywalking-query-protocol` GraphQL), Java 클라이언트 아티팩트(`banyandb-java-client`), Go API 모듈(`goapi`), Helm 차트, showcase(compose/k8s), 소비자 여럿(OAP `skywalking`, `skywalking-java`, `cli`, `satellite`, `rover`, `booster-ui`); OAP `.gitmodules`가 13번째(`skywalking-banyandb-client-proto`)를 가리켜 추가.
타이밍: 12 레포 병렬 shallow 클론 **4 s**; 파이프라인 `run_all.sh` **5 s**/14,300 파일(8 패스). 주의: Homebrew Python 3.14의 `pyexpat`가 깨져 `uv run --python 3.13`.

| kind | class | spans | main | test/CI |
|---|---|---|---|---|
| declared:gitmodule | 1 | 5 | 5 | 0 |
| artifact:maven | 2 | 12 | 1 | 11 |
| artifact:go | 2 | 4 | 3 | 1 |
| contract:graphql-field | 3 | 88 | 88 | 0 |
| contract:proto-import | 3 | 14 | 14 | 0 |
| contract:proto-copy(drift) | 3 | 7 | 7 | 0 |
| config:kafka-topic | 4 | 5 | 5 | 0 |
| infra:image | 4 | 85 | 14 | 71 |
| infra:ci-ref | 4 | 27 | 0 | 27 |
| infra:ref | 4 | 23 | 8 | 15 |
| text:link | 5 | 261 | 252 | 9 |

레포 쌍 97; 집합 내 41; **비텍스트 근거 30**; text-only 29; 집합 밖 대상 23(`skywalking-go`, `-python`, `-nodejs`, `-banyandb`, `-swck`, `-horizon-ui`…) = "미해결 참조" 페이지의 내용.
아티팩트: `skywalking → banyandb-java-client` 0.9.2(`oap-server-bom/pom.xml:436`, 생산자 HEAD 0.9.0-SNAPSHOT → 릴리스 태그 vs main 불일치를 드리프트 열이 드러냄); `skywalking → skywalking-java` Maven 5(전부 `test/e2e-v2/`); Go `cli/rover/satellite → goapi` 핀 2026-09-05 / 2025-10-21 / 2026-05-21(**11개월 스프레드**). Contract: `goapi → data-collect-protocol` 14 import; `cli → query-protocol` root 필드 78(71 distinct), `booster-ui` 10; `banyandb-java-client → banyandb-client-proto` vendored 7파일 **전부 발산**(10–388줄). 메시징: Kafka 토픽 5(`skywalking-segments/-metrics/-meters/-managements/-profilings`) OAP `KafkaFetcherConfig.java:61-69`(소비) ↔ agent `KafkaReporterPluginConfig.java:35-45`(생산); 불일치 관찰: agent `skywalking-logging` vs OAP `skywalking-logs`/`-logs-json`(미설명). 인프라: helm → skywalking(`values.yaml:35`), → satellite(`:576`), → horizon-ui(`:208`); showcase `Makefile.in:39-57`가 이미지 8개를 커밋 SHA로 핀(OAP `e27cc276` 2026-09-02 vs HEAD 2026-09-06).
스팟체크 9/9 정확(BOM 줄 436, `cli/go.mod:21`, `SniffData.proto:24-27`, `alarm.ts:21`↔`alarm.graphqls:102`(deprecated), 토픽 양측, `values.yaml:574-577`, `Makefile.in:39-41`, 스키마에 없는 클라이언트 연산 6개 실재, `version`은 진짜 root 필드).
정밀도 문제와 수정: (1) 서드파티 vendored proto 거짓 엣지 9 → 네임스페이스 deny-list; (2) 이미지명 부분일치 오류 → 빌드 지점 기반 빌더 맵 + 최장 prefix; 사내에서는 CI `docker build -t`/`$CI_REGISTRY_IMAGE`가 결정적 맵; (3) test/e2e 근거 지배(infra:image 97 중 82, Maven 12 중 11) → scope 열; (4) contract 레포 감지 "≥50% 스키마 파일"이 `banyandb-client-proto`를 놓침 → 30% 또는 `-proto/-protocol` 접미; (5) 레포명 regex의 후행 점.
미실행: Gradle, Python, OpenAPI/Avro, RabbitMQ/SQS, JPA, Terraform, GitLab CI 키워드, Backstage, CODEOWNERS.

## 5. 설계 권고
### SystemGraph
```
System     { id, name, source: declared(catalog|gitlab-group|parent-pom|ci-template) | manual, repos: [RepoRef] }
RepoRef    { id(gitlab project path), url, default_branch, head_sha, kind: service|library|contract|infra|docs|unknown,
             containers: [Container], produces: [Coordinate], consumes: [Coordinate], systems: [id] }
Container  { id, image | artifact, built_by: Evidence }          # 배포 단위, 레포당 0..N
Coordinate { scheme: maven|gradle|npm|pypi|go|image|proto-pkg|graphql-root|openapi|topic|host, key, version? }
Edge       { src, dst: RepoRef | Unresolved(key), kind, class: 1..5, scope: main|test,
             evidence: [Span{file, line, snippet}], drift?: {consumer_version, producer_head_version}, direction: known|assumed }
Unresolved { scheme, key, referenced_by: [Span] }
```
신뢰 등급 = 증거 계열(평균 내지 않음): 1 declared > 2 artifact > 3 contract > 4 config/infra > 5 text. `Span` 없는 엣지는 생성 시점에 거부.

### CLI와 실행
`repowiki system <gitlab-group-url> [--include repo …] [--system-file system.yaml]`: (1) GitLab API로 그룹/서브그룹 프로젝트 열거(+archived), `catalog-info.yaml` 읽기; (2) shallow fetch 또는 레포 위키 체크아웃 재사용; (3) 레포별 추출(`head_sha`로 증분 캐시) → `repo-facts.json`(produces, consumes, contract, literal, build site); (4) join(항상 재실행): 생산×소비 → 엣지, 미매칭 → Unresolved, HEAD vs 핀 → drift; (5) `system/` 출력: `index.md`(C4-L1 컨텍스트, 외부 시스템 = 집합 밖), `containers.md`(C4-L2, 쌍당 최고 등급 엣지 하나), `relations.md`(src, dst, kind, class, scope, version/drift, 근거 링크), `contracts.md`(contract 레포별 패키지/root 필드와 소비자 = Published Language 뷰), `unresolved.md`(미해결 좌표, 집합 밖 레포, text-only 쌍, 오래된 클라이언트 연산, proto 복사 드리프트), `deployment.md`(Helm/compose 있을 때); (6) 링크백: 레포 위키 헤더 "Part of system X — upstream/downstream", 시스템 페이지는 엣지 끝점의 모듈 페이지로 딥링크.
다이어그램 규칙: L1/L2는 class ≤4·`scope=main`만 그림; test·text는 표에만; 실선 = 1–2, 점선 = 3–4.

### 하지 말 것
LLM 추정 엣지·"아마 호출"; span 없는 엣지; 이름 추측 대상(이미지명 부분일치, README 언급 → unresolved로); test/e2e와 런타임 근거 병합; text와 declared 병합; 이미지명=레포명·아티팩트명=레포명·proto 경로 일치=소유로 취급; generic U/D·Published Language·OHS 외 DDD 라벨(나머지는 후보); 오프라인 전이 Maven 그래프.

### 그룹핑
시스템 소속 우선순위(`System.source`에 규칙 기록): 1 Backstage `spec.system`; 2 GitLab 그룹/서브그룹; 3 공유 parent POM/BOM(형제 레포가 생산하는 아티팩트를 `<parent>`로, 또는 ≥2 레포가 import하는 BOM) + 공유 CI 템플릿(`include: project:`); 4 class ≤3 엣지의 연결 성분(제안으로만).
레포 형태: **monorepo** = 빌드 모듈/컨테이너가 많은 레포 하나(skywalking: pom 117, 이미지 2); **multi-repo** = class ≤3 엣지로 이어진 ≥2 레포; **micro-repo** = contract 하나 또는 라이브러리 하나만인 레포. 레포 kind: `contract`(≥30% 스키마 파일 또는 `-proto/-protocol`), `infra`(Helm/compose만), `library`(좌표 생산, 이미지 없음), `service`(이미지 빌드/main), `docs`.
충돌·다중 소속: 좌표 키 `(scheme, key)` + 생산 레포; 두 레포가 같은 좌표 생산 = 오류 페이지 항목(병합 금지); 이미지는 태그 없는 레지스트리 경로로 키, 태그는 drift; 레포는 여러 시스템에 속할 수 있음(`systems: [id]`), 교차 시스템 엣지는 L1에서 상대 시스템을 외부로 렌더. GitLab self-managed: `RepoRef.id` = 프로젝트 경로, `$CI_REGISTRY_IMAGE`가 image→repo 맵을 공짜로 줌; CODEOWNERS Premium, `include: project:` Free.

## 6. Unverified / 미실행
Devin Search 교차 레포 범위; Compass `compass.yml`; Multiplayer; Oxeye; Prophet ANTLR; Sourcegraph `repo:deps`; CodeScene 교차 레포 명명 기능; Structurizr .NET(404); c4model.com의 repo↔container 비율 언급 없음; Gradle·Python·OpenAPI/Avro·RabbitMQ/SQS·JPA/Flyway·Terraform·GitLab CI 키워드·Backstage·CODEOWNERS 추출기 미실행; Kafka 방향 휴리스틱(`direction: assumed`); `skywalking-logging` vs `skywalking-logs` 불일치 미설명.
