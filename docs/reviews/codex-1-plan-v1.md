# Codex 1차 리뷰 (PLAN 1판, 2026-09-08) — 원문 요지

기준: 오버엔지니어링, 목적(사람이 Mermaid로 구조와 결합을 인지) 적합성과 패키징·사내 제약, 내부 모순.

## 치명
1. §2.3/§2.5/§10: 모듈 아래 코드 수준 결합 관계를 제공할 결정적 모델이 없다(호출·상속·구현·참조 없음, Serena는 선택형이고 commons-cli 87파일도 56 s). → 상위 핵심 타입 간 상속·구현·정적 호출 관계의 최소 분석 모델 추가 또는 요구사항을 모듈 수준으로 명시적으로 낮출 것.
2. §2.4/§2.5/§9: 대형 모듈 그래프(Kafka 65, Dubbo 119, Airflow ~150)를 사람이 읽을 수 있게 축약하는 전략이 없다. → 서브시스템 축약 + 서브시스템별 그래프 + 허브 중심 상세 그래프의 결정적 분할 기준을 Phase 1 수용 조건에.
3. §2.4/§2.5/§4: 저장소를 관통하는 데이터 흐름 계약이 없다. → `CrossModuleFlow` 모델(진입점→호출/이벤트→상태 저장→외부 경계, 근거 span)과 교차 모듈 흐름 페이지 필수화.
4. §8/§3/§2.6: 오프라인 단일 산출물이 현재 의존성 목록(LangGraph, ormsgpack, hanlint, Vale, MkDocs)으로 검증되지 않았다. → lock 전체로 이미지 빌드 후 `--network none` 실행, 또는 Vale·사이트 빌드·Serena 제외.
5. §1/§4/§5: "인터넷 없이 설치·실행"과 URL 입력·LLM 호출을 포함한 오프라인 시험 경계가 미정의. → 설치 무인터넷 / 외부 차단+사내 GitLab·LLM 허용 / 완전 차단 세 프로파일 분리.
6. §1/§2.3/§4/§5: claim 기반 증분이 새 관계·누락을 탐지 못하고, "모든 명제 결속"과 span 실재율 95%·`unverified` 목록이 서로 안 맞는다. → 페이지별 분석 입력·그래프 슬라이스 해시를 manifest에, 중요 claim 100% 결속, `unverified`는 본문 밖 리포트로.

## 중요
1. 세션 드라이버에서 "LLM은 facts만 읽는다"가 보장되지 않는다. → 작업 디렉토리 격리 + evidence id 검증.
2. "구현 하나면 추상 안 만든다"와 두 드라이버 배치의 긴장; 드라이버 프로토콜·상태 전이 명시, 결정 단계는 노드 하나로.
3. Claims 사이드카 + span 해시·앵커 재배치는 MVP 대비 과대. → inline span + 페이지 입력 해시만.
4. 산문 게이트 스택(hanlint 1★, Vale CJK 미검증, 100자 문장 지시)이 과대. → 핵심 규칙만 필수, 나머지 경고.
5. 이력(timeline·hotspot·coupling·ownership·releases + tag×module 맵리듀스)이 과대(kafka 200버킷 120만 토큰, airflow 태그 9,288). → 최근 hotspot과 coupling만.
6. 평가 장치(LEDGER, openwiki 비교, DeepWiki 비교, 사람 루브릭)가 제품과 맞먹음. → 골든셋 + 소수 이해도 태스크 + openwiki 비교 1회.
7. 완료 판정 절차 미정의(표본 30파일 100% 일치의 기준, span 실재율은 정확성이 아님, ≤N은 0도 통과). → recall/precision 골든셋, 표본 판정, 필수 재생성 집합.
8. §2.1 backfill vs §3/§9 `--name-only --no-renames` 불일치. → backfill 삭제, metadata/full-clone 모드 분리.
9. Serena가 검증 없이 패키징에 남음(+110 MB). → 1차 릴리스와 기본 tarball에서 제외.

## 사소
1. "OKF 코어만"과 고정 필드 경계가 흐림 → "repowiki OKF 호환 프로필".
2. "수정 없이 렌더" 보장이 과함 → "공통 문법만 생성".
3. Phase 0 셸 절차가 계획서에 들어 있고 리서치 이동 후 참조가 깨짐 → 별도 부트스트랩 기록 + 참조 갱신 검사.

## Keep as is
임베딩 제외; `ModuleGraph` 컴파일 + 실제 `mermaid.parse` + text 강등; ast-grep kind 룰과 엔트리포인트 오탐 억제; 얕은 클론·CodeQL·mmdc·Langfuse 기각; `uv pip install --no-index --find-links --require-hashes`와 캐시 동봉; 테스트·생성·vendor·모듈 잡음 제외와 기존 설계 문서 재사용.

## 종합
정적 분석 우선·근거 span·Mermaid 검증·오프라인 벤더링의 중심축은 좋으나 코드 수준 결합과 교차 흐름이 약하고 Claims·이력 요약·다중 평가·산문 게이트·LSP는 과대. 핵심 분석·계층형 다이어그램·교차 흐름·완성 이미지 검증에 집중하고 나머지는 후속으로.
