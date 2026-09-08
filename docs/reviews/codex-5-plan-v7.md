# Codex 5차 리뷰 (PLAN 7판, 2026-09-09) 원문

검토 범위는 PLAN.md, 6판과의 diff, Codex 4차 리뷰, 리서치 10·12·13·14·15·16, 의존 문서 대장이다. 파일은 수정하지 않았다.

## A. Codex 4차 리뷰 발견사항 처리 상태

| 4차 리뷰 ID | 7판 상태 | 해결한 7판 위치 | 판정 근거 |
|---|---|---|---|
| V5-C1 / 이전-4·5: image `SystemFlow` 종점 불가능 | resolved | §2.3 `SystemFlow`, §2.8 | `image` 종점을 `EntryPoint`가 아니라 `Container{image, built_by}`의 빌드 지점 span으로 분리했다. Phase 6의 `helm→image→repo`와 이제 일치한다. |
| V5-C2 / 이전-3: `PageInput` 누락 및 canonical form 부재 | resolved | §2.9 | 14개 입력, 페이지별 slice closure, 정렬·POSIX 경로·UTF-8·부동소수 처리·SHA-256 결합 규칙을 명시했다. |
| V5-I1 / 이전-8: 9×4와 24건의 기수 불일치 | resolved | §2.9 M01–M24 | 실제 24개 case를 입력 항목과 연산별로 열거했다. 더 이상 "행렬 전체"라고 오해할 표현도 없다. |
| V5-I2 / 이전-4: `Hop`과 join 규칙 부재 | resolved | §2.3, §2.8 | `Hop` 자료형과 topic/http/contract/artifact/image별 종점 규칙, ambiguous/unresolved 처리를 정의했다. |
| V5-I3 / 이전-5·12: Phase 6 표본·판정과 링크백 분모 | resolved | §5 Phase 6 | 층화 표본 10개, 검토자 2인, 제3자 판정 및 링크백 분모를 resolved edge/hop 양 끝점으로 닫았다. |
| V5-I4 / 이전-2: 타입 관계 "일치" 정의 | resolved | §2.3, §3 | Jaccard, precision, 해석률 세 조건을 §3에서도 "§2.3의 세 조건 전부"로 참조한다. |
| V5-I5 / 이전-12·18: fixture·threshold 불완전 | resolved | §5 Phase 1, 4 | `changes/` 비교 필드와 집합 동등성, 대화형 그래프 DOM/canvas 노드 수와 콘솔 오류 조건을 추가했다. 다만 전체 Phase 측정성에는 아래 신규 문제가 있다. |
| V5-I6 / 이전-7: "이전 판과 같은 사유" | resolved | §7 | 각 제외 사유가 자립적으로 적혀 있다. |
| V5-I7 / 이전-13: code-maat 기본값 | resolved | §2.9 | 명령 입력, 기본 파라미터, 공식 및 불일치 판정 절차가 유지됐다. |
| V5-I8: frontmatter 타입/enum | resolved | §2.4 | Pydantic 정본과 타입·enum을 정의했고 `index.md`와 `log.md` 예외도 명시했다. |
| V5-M1 / 이전-6: 서빙 범위 문구 반복 | unresolved | §0, §1, §7, §11, §13 | 정본을 §1로 삼았지만 같은 결론이 여러 절에 여전히 반복된다. 정확성 문제는 아니다. |
| V5-M2 / 이전-18: ELK 선가정 | resolved | §2.5, §8 | Phase 1 사다리 결과에 따른 조건부 스파이크로 바뀌었다. 단, 상한과 충돌하는 신규 문제가 있다. |
| V5-M3: 미래형 기록과 D2 미검증 | partial | 서문, §11 | D2는 명확히 `[unverified]`로 남겼다. 반면 `docs/research/ → docs/reports/research/` 이동은 서문에서 Phase 0 완료 항목이라고 하지만 Phase 0 완료 판정에 명시적으로 열거되지 않았다. |
| V5-M4: 상위 N 미정 | resolved | §2.9 | `FileRank`와 hotspot 모두 N=20으로 고정했다. |
| V5-M5: P-C 명령·환경과 네트워크 증거 | resolved | §5 Phase 5 | 명령, 환경 변수, replay 입력, `--network=none`을 구체화했고 자기보고보다 컨테이너 네트워크 차단을 1차 증거로 삼았다. |

## B. 신규 발견

### 치명

#### 1. 최소 런타임 이미지로는 계획에 명시된 Bedrock 드라이버를 실행할 수 없다

- **위치:** §1 제약, §3 LLM, §5 Phase 5, §8
- **문제:** 계획은 Bedrock 경로를 `AnthropicBedrockMantle`로 명시하지만 런타임 9개 의존에는 기본 `anthropic`만 들어 있다. 공식 SDK는 전용 클라이언트 사용 시 `pip install "anthropic[bedrock]"`을 요구하며, 이 extra의 AWS 의존성은 49-wheel 측정과 자산 manifest에 포함되지 않았다. 현재 설명대로 만든 OCI/tarball은 SigV4 기반 Bedrock 경로에서 import 또는 인증 단계부터 실패한다.
- **최소 변경:** 둘 중 하나를 명시적으로 선택한다. (1) Bedrock을 bearer-token `base_url`로만 지원하고 표준 `Anthropic` 클라이언트를 사용한다고 제한해 `AnthropicBedrockMantle`/SigV4 문구를 삭제하거나, (2) `anthropic[bedrock]`을 정식 의존으로 추가하고 wheel count·SBOM·P-B를 다시 측정한다.

현 상태는 사용자가 명시한 두 LLM 배치 경로 중 하나를 산출물이 수행하지 못하므로 SPEC 원천으로 넘길 수 없는 결함이다.

### 중요

#### 2. `kill -9` 뒤 "중복 LLM 호출 0"은 현재 계약으로 보장할 수 없다

- **위치:** §2.1, §4, §5 Phase 0
- **문제:** 원격 Messages 호출이 성공한 직후, 응답을 SQLite에 commit하기 전에 프로세스가 죽는 구간이 존재한다. SQLite transaction만으로 원격 API와 로컬 checkpoint의 exactly-once 원자성을 만들 수 없다. 또한 두 드라이버, bounded fan-out, job claim/lease, stale submit, retry generation, crash journal, schema migration까지 포함한 안전한 구현을 "약 300줄"로 미리 단정할 근거는 부족하다.
- **최소 변경:** Phase 0에서 crash injection 위치를 열거하고, "durable 응답이 있는 job의 중복 0, 조용한 누락 0"으로 판정 기준을 좁힌다. API fan-out에는 동시 실행 상한 assertion을, session driver에는 중복 `next`/`submit`, lease 소유권 검사를 추가한다.

#### 3. 조건부 스파이크의 자동 채택 규칙이 자체 의존성 상한을 위반한다

- **위치:** §2.5, §3, §8
- **문제:** Node 직접 의존 상한이 이미 3개인데 `@mermaid-js/layout-elk` 채택 시 4개, sigma+graphology까지 채택 시 6개가 된다. 바이너리도 상한 4개인데 cbm 채택 시 5개다. 그러나 §8은 상한 초과 시 같은 수 제거를 요구하고 예외는 LangGraph뿐이라 명시했다.
- **최소 변경:** 각 스파이크 판정에 "채택 시 새 확정 상한과 이유를 §8에 기록한다"를 추가하거나 조건부 도구를 별도 optional profile로 분리한다.

#### 4. ast-grep이 tree-sitter tags를 대체한다는 상위 판정이 증거보다 강하다

- **위치:** §0, §2.7, §3, §7, §10
- **문제:** 리서치 15의 실측은 30줄 Java·25줄 Python 파일 두 개뿐이다. §10은 규모 동일성 미검증을 인정하지만 §0·§7은 대체가 이미 입증된 사실처럼 쓴다. Phase 1의 4개 레포는 TypeScript def/ref 품질을 판정하지 않는데도 전체 계획은 TS 타입·호출까지 언급한다.
- **최소 변경:** §0 판정을 "임시 대체, Phase 1 채택 조건부"로 낮추고, Java·Scala·Python·TypeScript별 fixture로 언어별 precision/recall ≥0.98을 요구한다.

#### 5. GitLab "렌더 parity"를 두 Mermaid 버전의 `parse()` 성공만으로 판정한다

- **위치:** §2.5, §3, §5 Phase 1·4
- **문제:** `mermaid.parse`는 문법 수용 여부만 확인하며, GitLab 실제 초기화 설정·보안 설정·DOM 렌더·레이아웃 결과 동일성은 보장하지 않는다.
- **최소 변경:** 대표 다섯 diagram type fixture를 실제 GitLab Markdown 렌더 또는 동일 frontend bundle에서 렌더해 렌더 오류 0, SVG 생성, label 보존을 판정한다.

#### 6. chars/token p95를 "결정적 하드 게이트"라고 부르는 것은 통계적으로 부정확하다

- **위치:** §0, §3, §4, §5 Phase 0
- **문제:** p95는 상한이 아니라 분포의 약 5%가 이를 넘을 수 있다는 뜻이다. §4 마지막 문장은 하드 게이트가 `count_tokens`라면서 앞 문장은 게이트웨이가 count endpoint를 막으면 p95가 게이트라 한다. P-C는 replay만 하므로 이 대체 게이트가 실제로는 필요 없다.
- **최소 변경:** API 생성=`count_tokens` 하드 게이트, count endpoint 없는 게이트웨이 생성=`max_observed`/p99+안전계수+초과 시 재분할("approximate" 표기), P-C replay=새 토큰 게이트 없음으로 세 모드를 분리한다.

#### 7. "OCI 하나 또는 tarball 하나"의 내용과 다중 플랫폼 단위가 닫혀 있지 않다

- **위치:** §1 목표 7, §5 Phase 5, §8
- **문제:** §8은 플랫폼별 manifest와 x86_64/aarch64/UBI9 검증을 요구하지만 단일 multi-arch OCI인지 플랫폼별 세 개인지 적지 않는다. tarball 필수 내용물도 정의되지 않았다.
- **최소 변경:** `repowiki-oci.tar`(multi-arch index/digest 목록)와 `repowiki-offline-<platform>.tar.zst`(완전한 파일 목록+checksum)로 profile을 정확히 둘로 정의하고 각각 별도 smoke test한다.

#### 8. Phase 완료 기준 일부는 아직 성공 기준으로 충분히 측정 가능하지 않다

- **위치:** §5 Phase 1·2·2b·5
- **문제:** Phase 1 MoJoFM 정답 corpus의 파일·커밋·라벨이 없고, Phase 2 code-maat "상위 20 일치" 뒤 사람 재판정이 경계를 흐리며, Phase 2b "aws-infra 16/16"이 무엇의 16개인지 불명확하고, P-B는 정확성·부분 실패·언어 분포 기준이 없다.
- **최소 변경:** 모든 숫자에 fixture ID와 분모 정의를 붙이고, P-B에 프로젝트 20/20 성공·실패 repo 0·API pagination 전체 수 일치를 명시한다.

#### 9. ELK 라이선스를 "EPL-2.0 또는 GPL 중 EPL을 선택"한다고 설명한 것은 법적으로 부정확하다

- **위치:** §2.5, §8, 리서치 15 반영 문구
- **문제:** elkjs의 배포 라이선스는 EPL-2.0이며 EPL의 secondary-license 조항은 수령자가 임의 SPDX를 고르는 일반 dual-license와 다르다.
- **최소 변경:** SBOM에는 `EPL-2.0`을 그대로 기록하고 GPL secondary license 선택 문구를 삭제하며, EPL 허용 여부는 별도 회사 라이선스 정책 항목으로 명시한다.

### 사소

#### 10. Node 최소 버전이 두 자리 부족하다

- **위치:** §1, §3, §8
- **문제:** jsdom 30.0.1의 engine 조건은 `^22.22.2 || ^24.15.0 || >=26.0.0`인데 PLAN은 `Node ≥22.22`라 22.22.0/22.22.1도 문면상 허용된다.
- **최소 변경:** `Node 22.22.2` 정확 핀으로 통일.

#### 11. Material for MkDocs의 EOL 날짜를 확정 사실처럼 쓴다

- **위치:** §3, §8, 의존 대장 핀 정책
- **문제:** 공식 문구는 "최소 12개월" critical/security fixes이므로 2026-11-05가 엄밀한 종료일이라 단정할 수 없다.
- **최소 변경:** "2026-11-05 이후 지원 보장 없음"으로 표현 수정.

#### 12. §11의 "cbm 스파이크가 기본 경로"는 상태 표현이 모순된다

- **위치:** §11 Serena/LSP 행
- **문제:** cbm은 조건부 스파이크인데 "기본 경로"로 표현했다.
- **최소 변경:** "ast-grep `TypeGraph`가 기본 경로이고 cbm은 조건부 스파이크"로 수정.

#### 13. 의존 문서 대장의 제거된 패키지 문서 미러 목록은 런타임 잔여처럼 보인다

- **위치:** `docs/reference/dependency-docs.md` 문서 미러 목록
- **문제:** tree-sitter, typer, rich, tiktoken, python-gitlab, mkdocs-llmstxt 등이 미러 목록에 남아 air-gap mirror 반입 여부가 불분명하다.
- **최소 변경:** 목록을 채택/스파이크/역사적 조사 근거로 구분한다.

## C. 그대로 유지해도 되는 항목

- 4차 리뷰의 실질적 차단점이었던 image flow join은 정확히 해결됐다.
- `PageInput` 14항, slice closure, canonical serialization 및 역의존 전파는 SPEC 성공 기준으로 옮길 수 있을 정도로 구체적이다.
- M01–M24 변이 목록과 케이스별 waste ≤10%는 이전 기수 모순을 해소했다.
- Pydantic 모델을 frontmatter 정본으로 삼고 JSON Schema를 산출물로 내는 구조는 중복 정본을 제거한다.
- python-gitlab을 httpx2 기반 좁은 REST 어댑터로 대체한 결정은 필요한 API 종류가 셋뿐인 현재 범위에 적합하다.
- typer/rich→argparse, jsonschema→Pydantic, mkdocs-llmstxt 제거, panzoom 제거, codelore 제거, scikit-network 평가 전용 이동은 목적을 훼손하지 않는 타당한 최소화다.
- tree-sitter를 즉시 복구할 근거는 없다. 문제는 삭제 자체가 아니라 ast-grep 대체를 언어별 골든셋 전에 확정 사실로 쓴 것이다.
- P-C에서 실제 LLM 생성을 요구하지 않고 replay만 수행하는 범위 설정은 air-gap 제약과 일관된다.
- jsdom 30.0.1, Mermaid 11.17.2/11.13.0 버전 사실 자체는 대체로 일치하며, 49 resolved wheels·8 native wheels 수치는 리서치 15 원자료와 일치한다.
- MkDocs의 `file://` 채택 근거는 리서치 13 실측과 일관되며 서빙 범위 밖 제약에도 맞는다.

## D. 최종 판정

**아니오. 7판은 아직 SPEC.md 성공 기준의 정본으로 사용할 준비가 되지 않았다.** 6판의 구조적 결함은 대부분 고쳤고 의존성 최소화도 전반적으로 건전하지만, 단일 선행 차단 항목은 **배포 프로필별 실행 의존성 폐쇄성**이다. 현재 확정한 9개 Python 의존과 49-wheel artifact는 계획이 명시한 `AnthropicBedrockMantle` 경로를 포함하지 않아 사내에서 약속한 실행 모드 중 하나가 실제 산출물로 동작하지 않는다. 먼저 bearer-token 표준 클라이언트만 지원할지, `anthropic[bedrock]`과 AWS 의존성을 정식 반입할지 결정하고 그 선택으로 wheel count·SBOM·P-B acceptance를 다시 닫아야 한다. 그 뒤 runner의 crash 의미, 조건부 스파이크 상한, ast-grep 언어별 골든셋을 중요 보완으로 SPEC에 옮길 수 있다.

---

처리 메모(리뷰 밖, 2026-09-09): 치명 1은 anthropic 1.4.0 소스 확인 결과 `AnthropicBedrockMantle`이 bearer 토큰(`AWS_BEARER_TOKEN_BEDROCK`) 모드에서 boto3를 임포트하지 않고, SigV4 경로(`lib/aws/_auth.py`)만 boto3를 지연 임포트한다. 8판은 bearer 모드를 기본 지원으로, SigV4는 `[bedrock]` extra 프로필로 분리했다. 중요 9는 npm `elkjs@0.12.0`의 license 필드가 `EPL-2.0 OR GPL-3.0-or-later` SPDX 표현식이므로 "이중 선택" 서술 자체는 패키지 선언과 같다. 8판은 SBOM에 원 표현식을 그대로 두고 선택 라이선스를 별도 필드로 적으며 EPL 허용 여부를 회사 정책 항목으로 뺐다. 리뷰 당시 7판은 자작 러너 기본이었으나 사용자 결정으로 LangGraph 기본으로 되돌렸고(중요 2의 "300줄" 지적은 그 결정으로 소멸), crash 주입 지점과 판정 기준 축소는 그대로 반영했다.
