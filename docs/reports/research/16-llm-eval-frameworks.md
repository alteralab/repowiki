---
status: 리서치 완료 (2026-09-09). 라벨: [실측] 이 세션 로컬 실행(scratchpad `llm-eval/`, uv 0.11.8, Python 3.12 해석, npm), [웹] 공식 문서와 GitHub 소스 파일 직접 확인, [PyPI] PyPI JSON API, [unverified] 미확인
scope: repowiki 평가 체계에 LLM 기반 지표가 진짜 필요한 자리가 있는지, 있다면 기존 프레임워크(DeepEval, RAGAS, Inspect AI, promptfoo, lm-evaluation-harness, SaaS류)와 자작 판정기 중 무엇이 총 복잡도가 낮은지. 최소 의존성 규칙과 에어갭 배포(사내 게이트웨이 또는 Bedrock만 허용, 텔레메트리 금지)를 전제로 한다
---

# 16. LLM 평가 프레임워크: 필요한 자리와 선택

## 0. 한 줄 결론

v1에 LLM 지표를 **게이트로** 넣을 자리는 없다. 그러나 두 자리는 LLM 판정이 아니면 아예 측정이 안 된다. (a) 20레포 × 최대 300페이지 규모에서 "인용 span이 실제로 그 문장을 지지하는가"를 사람 표본(레포당 50명제, 약 1% 미만) 밖에서 **선별용 경고**로 훑는 일, (b) 프롬프트나 모델을 바꿨을 때 LLM 단계가 나빠졌는지 잡는 `evals/regression`의 **쌍대 비교**. 두 자리 모두 KB의 판정자 주의사항(판정자 모델과 프롬프트 고정과 기록, 위치 교환, 사람 표본 대비 일치도 보고)을 지키면 쓸 수 있고, 지키지 못하면 안 쓰는 편이 낫다.

프레임워크는 셋 다 실측했다. DeepEval 4.2.2는 66패키지에 `openai`, `posthog`, `grpcio`, `opentelemetry-sdk`를 강제로 끌고 오고 텔레메트리가 기본 켜짐, RAGAS 0.4.3은 92패키지 396MB에 LangChain 생태계와 `langchain-openai`를 강제하고 자체 수집 서버로 기본 전송, Inspect AI 0.3.263은 81패키지 149MB이고 텔레메트리 코드가 없다. 프로젝트에 이미 있는 `anthropic` 1.4.0만 쓰는 자작 판정기는 추가 의존성 0이며, KB가 요구하는 것(프롬프트를 저장소 안에 보이게, 판정자 변경을 명시적으로)은 프레임워크의 내장 프롬프트를 쓰면 오히려 위반된다. **권고: 프레임워크를 넣지 않고, `evals/judge/` 아래 약 150줄의 자작 판정기(structured outputs rubric, 위치 교환, 반복 3회, 사람 표본 kappa 보고)를 둔다.** 프레임워크가 필요해지는 조건(§4.4)이 오면 후보는 Inspect AI 하나다.

## 1. 어디에 LLM 판정이 필요한가

PLAN §6은 결정적 게이트(경로와 span 실재, evidence id 범위, Mermaid 파서, 링크, frontmatter 스키마, 산문 정규식, 충실성 diff, 토큰 게이트)와 봉인된 골든셋, 그리고 사람 표본(검토자 2인, 레포당 50명제, 이해도 10문항)으로 구성되어 있고 "LLM 판정자는 쓰지 않는다"고 못박았다. 리서치 06 §3은 그 이유를 KB에서 옮겼다: 같은 판정자도 두 번 돌리면 점수가 다르다, 일관성은 정확성이 아니다, faithfulness라는 이름이 도구마다 다른 정의다, 모델과 프롬프트를 볼 수 없는 판정자는 믿지 마라, 자기선호는 같은 벤더의 다른 모델로 번진다. 아래는 그 전제를 유지한 채 네 후보 자리를 하나씩 본 것이다.

| 자리 | 결정적 게이트 + 사람 표본으로 되는가 | 판정 | 근거 |
|---|---|---|---|
| (a) 근거 지지 선별(grounding screen) | 안 된다. span 실재와 evidence id 범위는 "인용이 존재한다"까지만 보고, "그 span이 이 문장을 지지한다"는 의미 판단이다. 사람 표본 50명제는 레포당 수천 명제의 1% 미만 | **필요, 단 경고 수준** | 20레포 × 300페이지 × 페이지당 인용 ≥3이면 명제 수는 최소 1.8만. 사람이 전수 검토할 수 없다. 판정 결과는 `.report.json`의 `warnings[]`로만 나가고 사람 검토 우선순위를 정하는 데 쓴다. `verified` 스탬프와 pass/fail에는 절대 닿지 않는다 |
| (b) LLM 단계 회귀(`evals/regression`) | 반쯤 된다. facts 스냅샷과 골든셋은 결정층 회귀를 잡지만, 프롬프트나 모델을 바꿨을 때 산문 품질이 떨어졌는지는 결정적 지표(인용 수, 게이트 통과율)가 둔감하다. 사람 표본은 프롬프트를 바꿀 때마다 다시 모을 수 없다 | **필요, 쌍대 비교 형태로** | 같은 판정자, 같은 프롬프트로 구버전과 신버전 페이지를 **위치 교환한 쌍**으로 비교하면 판정자의 절대 편향은 상쇄되고 일관성만 남는다. 일관성은 반복으로 잴 수 있다(§4.2). 절대 점수를 보고하지 않고 "신버전 선호율"과 "반복 간 뒤집힘률"만 보고한다 |
| (c) 이해도 태스크 채점 | 된다. 10문항은 모듈 소유, 의존 방향, 진입점, 흐름 순서, 설정 키처럼 답이 짧고 정해져 있다. 정규화 문자열 일치나 검토자 2인 판정으로 충분하다 | **불필요** | Anthropic 자체 가이드도 "자동 채점이 가능하게 문항을 구조화하라(객관식, 문자열 일치, 코드 채점)"를 첫 원칙으로 둔다 [웹] |
| (d) 다이어그램 주석 품질 | v1에서는 된다. 주석이 가리키는 노드 id가 다이어그램에 실재하는지, 주석의 인용 span이 실재하는지는 결정적이다. "주석이 유용한가"는 주관 판단이고 v1 성공 기준에 없다 | **불필요(v1), 이후 선택** | 필요해지면 (a)의 판정기에 rubric 하나를 더 얹는 형태로 충분하다. 별도 지표를 만들지 않는다 |

### KB 주의사항을 어떻게 지키는가

- **판정자 모델과 프롬프트 고정과 기록**: 판정 프롬프트는 `evals/judge/prompts/grounding.v1.md`처럼 저장소 안의 파일이고, 결과 파일에는 리서치 06 §7이 이미 정한 필수 필드(생성 모델, 판정 모델, effort, 프롬프트 해시, 대상 레포 SHA, 실행일, 반복 횟수)를 그대로 쓴다.
- **seed 고정은 불가능하다**: Claude API에는 `seed` 파라미터가 없고, `claude-opus-5`와 Sonnet 5는 `temperature`, `top_p`, `top_k`를 보내면 400을 돌려준다(claude-api 스킬 캐시 표 기준, 2026-06-24판). 따라서 "seed 고정" 대신 **반복 3회 다수결과 반복 간 뒤집힘률 기록**으로 대체한다. Inspect AI의 `GenerateConfig.seed`는 존재하지만 Anthropic 제공자에서는 의미가 없다 [웹, `src/inspect_ai/model/_generate_config.py` 249행].
- **위치 교환**: (b)의 쌍대 비교는 A/B와 B/A를 둘 다 묻고, 두 답이 다르면 "무승부"로 센다. (a)는 단일 대상 판정이라 위치 편향이 없지만, 명제 순서를 무작위로 섞고 한 호출에 명제를 10개 이하로 넣는다.
- **사람 표본 대비 보정 후에만 신뢰**: Phase 3의 사람 표본(레포당 50명제, 검토자 2인)에 같은 판정기를 돌려 raw agreement와 Cohen's kappa를 보고한다. 이 판정기는 "지지 안 됨"을 찾는 선별기이므로 kappa보다 **사람이 "지지 안 됨"으로 표시한 명제에 대한 판정기 recall**이 핵심이다. 기준값은 정책이다: kappa ≥0.6(Landis와 Koch 1977의 "substantial" 경계, 관례이지 이 과제에 대한 실측치는 아님 [unverified])과 unsupported recall ≥0.8을 초기값으로 두고, 미달이면 판정기를 **끄고** 결과를 `.report.json`에 `judge: disabled(kappa=...)`로 남긴다.
- **자기선호**: 생성기가 `claude-opus-5`이고 게이트웨이가 Claude만 제공하므로 다른 벤더 판정자는 불가능하다. KB대로 같은 벤더의 다른 모델(Sonnet 5)로 갈라도 독립은 얻지 못한다. 그래서 (a)는 절대 점수를 쓰지 않고 선별에만 쓰며, (b)는 쌍대 비교라 자기선호가 양쪽에 같이 걸린다. Anthropic 가이드의 "생성 모델과 다른 모델로 평가하라"는 문장은 지키되 그것이 독립을 만든다고 적지 않는다.
- **판정자 변경 시 기준선 재측정**: 판정 모델 id나 프롬프트 해시가 바뀌면 사람 표본 kappa를 다시 재고, 그 전 회귀 결과와 비교하지 않는다. 결과 파일의 `judge_id = model + prompt_sha256[:12] + effort`가 다르면 비교 스크립트가 거부한다.

## 2. 프레임워크 비교 (2026-09-09 기준)

### 2.1 요약표

| 항목 | DeepEval | RAGAS | Inspect AI | promptfoo | lm-evaluation-harness |
|---|---|---|---|---|---|
| 버전, 날짜 [PyPI/npm] | 4.2.2 (2026-09-06) | 0.4.3 (2026-01-13) | 0.3.263 (2026-09-04) | 0.122.2 (npm) | 0.4.13 |
| 라이선스 | Apache-2.0 | Apache-2.0 | MIT (UK AI Security Institute) | MIT | MIT |
| Anthropic 판정자 | `AnthropicModel` (`deepeval/models/llms/anthropic_model.py`), `anthropic` 패키지는 별도 설치 | `llm_factory(model, provider="anthropic", client=...)`, instructor로 패치 | `anthropic/<model>`, `ANTHROPIC_BASE_URL` 환경 변수 | `anthropic:messages:<model>`, `apiBaseUrl` | API 모델 타입 있음, 판정 워크플로는 없음 |
| Bedrock | `AmazonBedrockModel` (aiobotocore 필요) | LiteLLM 경유 `bedrock/<id>` 또는 LangChain `ChatBedrockConverse` | `anthropic/bedrock/<model>`(SDK `AsyncAnthropicBedrock`) 또는 `bedrock/<id>`(aioboto3) | `bedrock:anthropic.<model>` | 해당 없음 |
| 사내 게이트웨이 `base_url` | 생성자 `**kwargs`가 그대로 `Anthropic(**kw)`로 전달되므로 `base_url=` 가능, 또는 SDK가 읽는 `ANTHROPIC_BASE_URL` | 사용자가 만든 `anthropic.Anthropic(base_url=...)` 클라이언트를 넘김 | `ANTHROPIC_BASE_URL`, Bedrock은 `ANTHROPIC_BEDROCK_BASE_URL` | `ANTHROPIC_BASE_URL` 또는 `apiBaseUrl` | `base_url` 인자 |
| 기본 텔레메트리 | **켜짐**, PostHog(`us.i.posthog.com`, 키 하드코딩) | **켜짐**, 자체 서버 `t.explodinggradients.com` | **없음** | **켜짐**, posthog-node + 업데이트 확인 + 원격 채점 | 없음 [unverified, 코드 미확인] |
| 끄는 법 | `DEEPEVAL_TELEMETRY_OPT_OUT=1` | `RAGAS_DO_NOT_TRACK=true` | 해당 없음 | `PROMPTFOO_DISABLE_TELEMETRY=1`, `PROMPTFOO_DISABLE_UPDATE=1`, `PROMPTFOO_DISABLE_REMOTE_GENERATION=true`, `PROMPTFOO_DISABLE_SHARING=1`, `PROMPTFOO_SELF_HOSTED=1` | 해당 없음 |
| 클라우드 푸시 | `CONFIDENT_API_KEY` 있을 때만 | 없음(tracing extra는 langfuse, mlflow) | 없음. 로그는 로컬 `./logs`(`.eval` zip 또는 `.json`) | 공유와 hosted grading은 선택, 기본 로컬 | 없음 |
| 결과 파일 | `.deepeval/` 로컬 캐시, `-c` 캐시 | 데이터프레임과 JSON | `.eval`(기본, zip) 또는 `.json`, `INSPECT_LOG_FORMAT` | SQLite + JSON | JSON |
| pytest | `deepeval test run`(pytest 래퍼, `assert_test`, `-n -c -r -i`) | 없음 | 없음. `eval()` 파이썬 API를 pytest 안에서 부를 수 있음 | 없음(CLI) | 없음 |
| 데이터셋과 골든 | `EvaluationDataset`, `Golden(input, expected_output, context, retrieval_context, expected_tools, comments, additional_metadata)`, JSON과 CSV 로컬 로드, `save_as` JSON/CSV/JSONL, `pull/push`는 로그인 필요 | HF `datasets` 기반 `EvaluationDataset` | `Sample(input, target, metadata)`, JSON/JSONL/CSV 로더 | YAML/CSV 테스트 케이스 | HF datasets 태스크 YAML |
| 오프라인 동작 | 환경 변수 두 개 끄면 가능(업데이트 확인은 opt-in) | 환경 변수 하나 끄면 가능, `datasets`가 HF 허브를 건드리지 않게 주의 | 그대로 가능 | 환경 변수 다섯 개, 문서가 "방화벽 대체가 아니다"라고 명시 | HF 허브 의존 |
| 용도 적합 | RAG 지표 라이브러리 + SaaS 연동 | RAG 지표 라이브러리, LangChain 결합 | 모델 벤치마크 하네스, 판정 scorer와 로그 뷰어 | 프롬프트 A/B CLI(Node) | 학술 벤치마크 실행기, 로그우도와 생성 태스크. 우리 문제와 맞지 않음 |

### 2.2 DeepEval 4.2.2 [웹, PyPI, 실측]

- 지표: Faithfulness, Hallucination, Answer Relevancy, Contextual Precision/Recall/Relevancy, G-Eval, DAG, Summarization, Bias, Toxicity 등. Faithfulness 정의는 "`actual_output`에서 LLM으로 명제를 뽑고, `retrieval_context`의 사실과 **모순되지 않으면** truthful로 분류, 점수 = truthful 명제 수 / 전체 명제 수". 필수 입력 `input`, `actual_output`, `retrieval_context`. 옵션 `threshold`(0.5), `strict_mode`, `truths_extraction_limit`, `penalize_ambiguous_claims`. 프롬프트 템플릿은 `deepeval/metrics/faithfulness/templates/`에 있고 덮어쓸 수 있다.
- 주의: DeepEval faithfulness는 "모순 없음"을 지지로 친다. RAGAS는 "지지됨"을 센다. 같은 이름이 다른 정의라는 KB 지적이 그대로 확인된다. repowiki가 원하는 것은 "이 span이 이 문장을 **지지**한다"이지 "모순되지 않는다"가 아니다.
- G-Eval은 출력 토큰 확률로 1에서 5 점수를 가중합하는 방식이라 문서가 "**NOT** deterministic"이라고 명시하고, 커스텀 모델(Anthropic 포함)에서는 확률 정규화가 빠진다. DAGMetric은 판정 트리의 **구조**를 고정할 뿐 "Task와 judgement 노드는 여전히 LLM이므로 출력이 달라질 수 있다"고 문서가 답한다.
- 텔레메트리 [웹, 소스]: `deepeval/telemetry/client.py` 25행과 26행에 PostHog 프로젝트 키와 `https://us.i.posthog.com`이 하드코딩되어 있고, 29행 `telemetry_opt_out()`이 `settings.DEEPEVAL_TELEMETRY_OPT_OUT`을 읽는다. `deepeval/config/settings.py` 874행에 `DEEPEVAL_TELEMETRY_OPT_OUT`, 878행에 deprecated 별칭 `DEEPEVAL_TELEMETRY_ENABLED`("OFF 신호가 이기는" 규칙), 886행 `DEEPEVAL_UPDATE_WARNING_OPT_IN`. PyPI 버전 확인(`deepeval/__init__.py` 115행 `check_for_update`, `https://pypi.org/pypi/deepeval/json`)은 147행에서 `DEEPEVAL_UPDATE_WARNING_OPT_IN == "1"`일 때만 호출된다(opt-in). 수집 항목은 이벤트 이름, 지표 이름, Jupyter 여부, 익명 UUID, 공인 IP(문서 `docs/content/docs/data-privacy.mdx`). Confident AI 업로드는 `CONFIDENT_API_KEY`가 있을 때만이며 `deepeval/evaluate/execute/_common.py` 306행이 `is_confident()`로 분기한다. `opentelemetry-sdk`는 강제 의존이지만 OTLP 내보내기는 엔드포인트 설정(settings.py 941행)이 있을 때만이다.
- Anthropic 어댑터 [소스]: `anthropic_model.py`는 `api_key`, `temperature`, `generation_kwargs`, 그 외 `**kwargs`를 받고 `_build_client`(371행)에서 `cls(api_key=..., **self._client_kwargs())`로 SDK 클라이언트를 만든다. 즉 `base_url`은 문서에 없지만 kwargs로 통과하고, SDK의 `ANTHROPIC_BASE_URL`도 먹는다. `max_retries=0`을 강제하고 자체 tenacity 재시도를 쓴다. `amazon_bedrock_model.py`는 `aiobotocore`와 `botocore`를 지연 import하며 `AWS_BEDROCK_REGION`이 필요하다. `gateway_model.py`는 OpenAI 호환 게이트웨이용이다.

### 2.3 RAGAS 0.4.3 [웹, PyPI, 실측]

- Faithfulness 정의: "response의 명제 중 retrieved context가 **지지하는** 명제 수 / 전체 명제 수". 입력 `user_input`, `response`, `retrieved_contexts`. HHEM-2.1-Open 분류기 변형이 있다(로컬 모델, 우리 의존성 규칙상 제외).
- 강제 의존 [소스 `pyproject.toml`]: `openai`, `instructor`, `langchain`, `langchain-core`, `langchain-community`, `langchain_openai`, `datasets`, `scikit-network`, `networkx`, `pillow`. 컴파일 결과 langchain 1.4.0, langchain-openai 1.6.1, openai 2.54.0, datasets 5.0.1, pandas 3.0.5, pyarrow가 들어온다. repowiki는 이미 langchain-core 1.6.2(LangGraph 경유)와 scikit-network를 쓰므로 일부는 겹치지만 `langchain-openai`와 `openai`는 순수하게 새 짐이다.
- Anthropic: `llm_factory(model, provider="anthropic", client=anthropic.Anthropic(base_url=...))`가 instructor로 클라이언트를 패치한다(`src/ragas/llms/base.py` 606행, `src/ragas/llms/adapters/instructor.py`). 문서의 Anthropic 예제는 비어 있고 Bedrock 예제는 LiteLLM 경유다.
- 텔레메트리 [소스 `src/ragas/_analytics.py`]: 37행 `USAGE_TRACKING_URL = "https://t.explodinggradients.com"`, 41행 `RAGAS_DO_NOT_TRACK`, 49행에서 값이 `"true"`일 때만 끔, 233행 `requests.post(USAGE_TRACKING_URL, ...)`. 기본은 전송이다.

### 2.4 Inspect AI 0.3.263 [웹, PyPI, 실측]

- 구조: `Task(dataset, solver, scorer)`, `inspect eval` CLI 또는 `eval()` API. 내장 scorer는 `includes`, `match`, `pattern`, `answer`, `exact`, `f1`, `choice`, `model_graded_qa`, `model_graded_fact`. `model_graded_fact(template, instructions, grade_pattern, partial_credit, model)`에서 `template`을 직접 넘길 수 있고 기본 `grade_pattern`은 마지막 `GRADE: C|P|I`를 잡는다. `model`에 리스트를 주면 `multi_scorer`가 `majority`(기본) 또는 `mode`로 합친다(`src/inspect_ai/scorer/_model.py`).
- 제공자: `anthropic/<model>`에 `ANTHROPIC_API_KEY`와 `ANTHROPIC_BASE_URL`, Bedrock은 `anthropic/bedrock/<model>`이 SDK의 `AsyncAnthropicBedrock`을 쓰고 `ANTHROPIC_BEDROCK_BASE_URL`도 읽는다(`src/inspect_ai/model/_providers/anthropic.py` 27행, 395행에서 408행). 별도 `bedrock/<id>` 제공자는 `aioboto3`다. `anthropic` 패키지는 `dev` extra에만 있어 사용자가 설치한다(repowiki에는 이미 있다).
- 텔레메트리: 저장소 코드 검색에서 `posthog` 0건, `sentry_sdk` 0건, `check_for_update` 0건. `INSPECT_TELEMETRY`는 사용자가 **자기** 패키지의 함수를 가리켜 켜는 opt-in 훅이다(`src/inspect_ai/hooks/_legacy.py` 14행에서 37행, `_startup.py`). 로그는 `./logs`에 `.eval`(zip, 기본) 또는 `.json`(`INSPECT_LOG_FORMAT`)이고 원격 저장은 선택이다.
- 짐: `aioboto3`, `boto3`, `fastapi`, `uvicorn`, `textual`, `debugpy`, `s3fs`, `fsspec`, `numpy`, `tiktoken`이 강제다. 로그 뷰어(`inspect view`)와 샌드박스 기능이 핵심 가치인데 repowiki는 둘 다 안 쓴다.

### 2.5 promptfoo 0.122.2 (Node) [npm 실측, 웹]

- Anthropic `anthropic:messages:<model>`, `apiBaseUrl`, Bedrock `bedrock:anthropic.<model>`. `llm-rubric`과 `factuality` 같은 model-graded assertion의 채점 모델은 `defaultTest.options.provider`로 지정한다.
- 잠금 파일 해석 결과 **967패키지**, `posthog-node`와 `@posthog/core` 포함, 직접 의존 80개에 `openai`, `@anthropic-ai/sdk`. 텔레메트리와 업데이트 확인이 기본 켜짐이고, 오프라인 환경 변수는 다섯 개이며 문서가 "이 설정은 네트워크 방화벽이 아니다, 에어갭은 egress 통제와 같이 쓰라"고 명시한다. repowiki의 Node 트리는 Mermaid 검증용으로만 제한되어 있어(PLAN §3) 채택 대상이 아니다.

### 2.6 lm-evaluation-harness 0.4.13 [PyPI, 웹]

HF `datasets`, `evaluate`, `scikit-learn`, `sacrebleu`, `rouge-score`가 강제이고 태스크는 로그우도 또는 `generate_until` 벤치마크 형식이다. 사내 위키 페이지의 근거 판정 같은 응용 평가를 위한 판정 워크플로가 아니다. **부적합.**

### 2.7 SaaS 또는 무거운 것 (메모만)

- Braintrust 0.37.0(MIT, 32 reqs), LangSmith 0.12.2(MIT, 45 reqs): SDK는 가볍지만 가치가 클라우드 대시보드에 있다. 에어갭에서는 목적이 사라진다.
- Arize Phoenix 20.8.0과 phoenix-evals 3.6.0: **Elastic-2.0**(OSI 비승인). 런타임 SBOM 정책(GPL 0건, LGPL 표시)과 별개로 검토가 필요하다. 자체 호스팅 서버가 전제라 무겁다.
- openevals 0.2.0(MIT, 5 reqs): LangSmith 팀의 판정 프롬프트 모음. 가볍지만 프롬프트를 패키지 안에 두는 구조라 KB 규칙(프롬프트 가시성, 판정자 변경 명시)에는 우리가 복사해 오는 편이 낫다 [unverified, 코드 미확인].

### 2.8 Anthropic 자체 가이드 [웹, `platform.claude.com/docs/en/docs/test-and-evaluate/develop-tests`]

- 원칙: 실제 과제 분포를 반영, 자동 채점이 되게 문항을 구조화, **"신호가 조금 낮아도 문항 수가 많은 자동 채점이 소수의 고품질 수작업 채점보다 낫다"**.
- LLM 채점 예시는 Likert(1에서 5), 이진(yes/no), 서열 척도이고 모두 `client.messages.create(model="claude-opus-5", ...)` 한 번 호출이다. 모든 예시에 "생성 모델과 다른 모델로 평가하는 것이 일반적 관행"이 붙어 있다.
- 우리에게 쓸 도구: structured outputs(`output_config.format` 또는 `client.messages.parse()`)로 rubric 결과를 스키마로 받고, Batches(`client.messages.batches.create`, 결과는 `custom_id`로 키잉, 50% 비용)로 판정 호출을 몰아 보낸다. PLAN §4가 Batches를 게이트웨이 경로에서만 지원한다고 했으므로 판정기도 같은 조건을 따른다. citations는 structured outputs와 함께 쓸 수 없다(400).
- 이 가이드에 별도 프레임워크 권장은 없다. Console의 평가 도구는 이 페이지에 없고 UI 기능이라 에어갭과 무관하다 [unverified].

## 3. 실측: 의존성 비용

`uv pip compile --python-version 3.12` 후 각 결과를 venv에 실제 설치해 `.dist-info` 수와 `.so` 파일을 셌다(macOS arm64, 2026-09-09). 파일: scratchpad `llm-eval/req-{A,B,C,D,E}.txt`.

| 세트 | 해석 패키지 수 | 네이티브 확장 패키지(.so 수) | 설치 크기 | 끌려오는 것 |
|---|---|---|---|---|
| A `deepeval` 4.2.2 | **66** | 10개(14): aiohttp, charset_normalizer, frozenlist, grpc, jiter, markupsafe, multidict, propcache, pydantic_core, yarl | 104MB | `openai` 3.8.0, `posthog` 7.47.3, `grpcio` 1.83.1, `opentelemetry-sdk` 1.44.0. langchain 없음, sentry 없음 |
| B `ragas` 0.4.3 | **92** | 26개(277): numpy, scipy, pandas, pyarrow, PIL, sknetwork, tiktoken, orjson, ormsgpack, regex, sqlalchemy, hf_xet, zstandard 등 | 396MB | `langchain` 1.4.0, `langchain-core` 1.6.2, `langchain-openai` 1.6.1, `openai` 2.54.0, `instructor` 1.16.0, `datasets` 5.0.1. posthog 없음(자체 엔드포인트), sentry 없음 |
| C `inspect-ai` 0.3.263 | **81** | 18개(43): numpy, tiktoken, debugpy, psutil, ijson, mmh3, regex, rpds, zstandard, yaml 등 | 149MB | `aioboto3` 15.5.0, `boto3` 1.40.61, fastapi, uvicorn, textual. openai, langchain, posthog, sentry 모두 없음. `anthropic`은 포함 안 됨 |
| D `anthropic` 1.4.0 (기준선, 이미 있음) | 15 | 2개(2): jiter, pydantic_core | 18MB | 없음 |
| E `anthropic[bedrock]` | 22 | 위와 같음 | [unverified, 미설치] | boto3 1.43.89, botocore |

읽는 법: repowiki에 이미 `anthropic`, `pydantic`, `httpx2`, `typer`, `rich`, `networkx`, `scikit-network`, `tiktoken`, `langchain-core`가 있으므로 실제 **순증**은 표보다 적다. 그래도 DeepEval의 `openai`, `posthog`, `grpcio`, `opentelemetry-sdk`, RAGAS의 `langchain-openai`, `openai`, `datasets`, `pandas`, `pyarrow`, Inspect의 `aioboto3`, `boto3`, `fastapi`, `uvicorn`, `textual`, `debugpy`는 어느 것도 repowiki 목적에 필요 없다. 휠하우스와 SBOM(Phase 5)에 그대로 실린다.

## 4. 권고

### 4.1 v1 PLAN에 적을 문장

PLAN §6 5항 "LLM 판정자는 쓰지 않는다"를 다음으로 바꾼다.

> LLM 판정자는 게이트, 완료 판정, `verified` 스탬프에 쓰지 않는다. 두 자리에서만 보조로 쓴다. (1) `repowiki write` 뒤 `evals/judge/grounding.py`가 명제 단위 근거 지지 여부를 판정해 `.report.json`의 `warnings[]`에 `judge_unsupported` 항목으로 남기고, 사람 검토 우선순위에만 쓴다. (2) `evals/regression`은 고정 픽스처 페이지에 대해 구버전과 신버전을 위치 교환 쌍으로 비교해 "신버전 선호율"과 "반복 간 뒤집힘률"만 보고한다. 판정 모델, 프롬프트 해시, effort, 반복 횟수, 실행일, 사람 표본 대비 kappa와 unsupported recall을 결과 파일에 함께 기록하고, kappa <0.6 또는 recall <0.8이면 판정기를 끄고 그 사실을 기록한다. 프레임워크는 넣지 않는다(리서치 16).

### 4.2 자작 판정기의 정확한 모양 (`evals/judge/`, 추가 의존성 0)

- 위치: 템플릿의 `evals/` 아래. `evals/run.sh`가 `evals/judge/grounding.py --report .report.json --facts facts/ --sample evals/human/<repo>.jsonl`을 호출한다. 골든셋과 사람 표본은 봉인 경로에 둔다(리서치 06 §2).
- 입력: 페이지의 각 명제와 그 명제가 인용한 span 텍스트(facts에서 결정적으로 꺼낸다). 판정기는 레포 전체를 보지 않는다. 인용 span 밖은 보여주지 않으므로 "다른 곳에 근거가 있다"는 판정이 불가능하고, 이것이 의도다.
- 호출: `client.messages.parse(model=JUDGE_MODEL, output_config={"effort": "medium", "format": <schema>}, messages=[...])`. 스키마는 명제당 `{claim_id, verdict: supported|unsupported|ambiguous, quote: str}`이고 `quote`는 span 안의 문자열이어야 하며 결정적으로 검증한다(포함 검사 실패면 verdict를 `ambiguous`로 강등). `fallbacks: "default"`는 판정기에서 끈다. 판정자 대체 모델이 섞이면 판정자 고정이 깨지기 때문이다. refusal은 `ambiguous`로 기록한다.
- 반복: 명제 묶음마다 3회 호출, 다수결. 3회가 모두 다르면 `ambiguous`. 반복 간 뒤집힘률을 결과에 적는다. Batches 가능 환경이면 3회 × N묶음을 한 배치로 보낸다.
- 위치 교환(회귀 전용): `evals/judge/pairwise.py`가 같은 페이지의 구버전 본문과 신버전 본문을 A/B, B/A 두 번 묻고, 스키마는 `{winner: A|B|tie, reason}`. 두 순서의 답이 일치할 때만 승패로 센다.
- 보정: `evals/judge/agreement.py`가 사람 표본 50명제의 라벨과 판정기 다수결을 받아 raw agreement, Cohen's kappa(κ = (p_o − p_e) / (1 − p_e), 약 15줄, 알려진 예제 하나로 단위 테스트), unsupported recall과 precision을 낸다. `sklearn.metrics.cohen_kappa_score`는 scikit-learn을 새로 넣어야 하므로 쓰지 않는다.
- 결과 파일 `evals/reports/<repo>.<date>.judge.json`: 리서치 06 §7 필수 필드 + `judge_id`, `repeats`, `flip_rate`, `kappa`, `unsupported_recall`, `enabled: bool`. PLAN이나 README에 숫자를 옮길 때는 이 필드와 함께만 옮긴다.
- 판정 모델: 기본 `claude-sonnet-5`(생성기 Opus 5와 다른 모델, KB의 "독립은 아니다" 주석을 결과 파일 `note`에 고정 문자열로 남긴다). 게이트웨이가 Sonnet 5를 안 주면 `claude-opus-5`로 두되 `judge_id`가 달라지므로 기준선을 따로 잰다.
- 하지 말 것: 게이트 실패로 연결하지 않는다, `verified`를 찍지 않는다, 텔레메트리와 외부 호출은 SDK의 게이트웨이 호출 하나뿐이다(`network_calls` 카운트에 포함), 판정 프롬프트를 코드 문자열로 숨기지 않는다(`evals/judge/prompts/*.md`), 판정자 변경을 조용히 하지 않는다(`judge_id` 불일치는 비교 거부).
- 예상 분량: grounding 약 80줄, pairwise 약 50줄, agreement 약 40줄, 프롬프트 2개. 합쳐 150에서 200줄.

### 4.3 C-LIB-1 대 C-LIB-3

C-LIB-1(표준 측정은 검증된 구현에 위임)은 측정 자체가 **표준**일 때 성립한다. MoJoFM, ARI, PageRank, Cohen's kappa는 정의가 하나이고 구현이 검증되어 있다. LLM 판정은 반대다. KB가 확인한 대로 faithfulness는 DeepEval에서 "모순 없음", RAGAS에서 "지지됨"이고, 이번 실측에서 그 차이가 문서 문면으로 그대로 나왔다. G-Eval은 토큰 확률에 기대는데 Anthropic 모델에서는 그 정규화가 빠진다. 즉 프레임워크가 주는 "검증된 구현"은 프롬프트 문자열과 점수 산식이고, 그 프롬프트는 패키지 버전과 함께 바뀐다. KB 규칙(프롬프트 가시성, 판정자 변경 시 기준선 재측정)을 지키려면 어차피 프롬프트를 저장소로 복사해 고정해야 하고, 그 순간 프레임워크의 남는 가치는 호출 루프, 재시도, 로그 형식, 뷰어인데 호출 루프와 재시도는 이미 있는 `anthropic` SDK가 하고 로그 형식은 리서치 06 §7이 정했으며 뷰어는 안 쓴다.

C-LIB-3(최소 의존성)은 숫자로 판정된다. 자작 판정기는 순증 0, DeepEval은 posthog와 openai를 포함해 최소 수십 패키지, Inspect는 boto3와 fastapi를 포함해 수십 패키지. Cohen's kappa 하나만은 C-LIB-1의 대상이지만 15줄 산식에 scikit-learn을 넣는 것은 C-LIB-3 위반이 더 크다. 단위 테스트로 대신한다.

결론: **자작 판정기가 총 복잡도가 낮다.** 프레임워크를 쓰면 "판정 프롬프트가 어디에 있는가"라는 질문에 "패키지 안 어딘가"라고 답하게 되고, 그것이 KB가 금지한 상태다.

### 4.4 프레임워크가 필요해지는 조건과 그때의 선택

다음 중 둘 이상이 오면 프레임워크를 다시 본다: 판정 rubric이 5종을 넘는다, 판정 로그를 사람이 브라우저로 훑어야 한다, 여러 판정 모델의 다수결 패널이 필요하다, Bedrock과 게이트웨이를 같은 코드로 오가야 한다. 그때 후보는 **Inspect AI 하나**다. 이유: MIT, 텔레메트리 코드 없음, `ANTHROPIC_BASE_URL`과 `anthropic/bedrock/` 둘 다 SDK 경로, `template=`로 우리 프롬프트를 그대로 넣을 수 있음, `.eval` 로그가 로컬, `multi_scorer` 다수결 내장. 비용은 81패키지 149MB이고 `aioboto3`, `fastapi`, `textual`, `debugpy`가 휠하우스에 실린다. DeepEval은 텔레메트리 기본 켜짐과 `openai` 강제 때문에, RAGAS는 LangChain 생태계 강제와 자체 수집 서버 때문에 어느 조건에서도 앞서지 않는다.

## 5. 검증하지 못한 것

- Anthropic API에 `seed`가 없다는 것과 Opus 5가 sampling 파라미터를 거부한다는 것은 claude-api 스킬의 캐시 표(2026-06-24)에 의존했다. 게이트웨이가 파라미터를 걸러 주는지는 P-B 환경에서 확인해야 한다 [unverified].
- promptfoo 967패키지는 잠금 파일 해석 수이고 설치 크기와 네이티브 모듈은 세지 않았다 [unverified].
- `anthropic[bedrock]`은 컴파일만 했고 설치하지 않았다 [unverified].
- lm-evaluation-harness와 openevals의 텔레메트리 코드는 열어 보지 않았다 [unverified].
- kappa ≥0.6, unsupported recall ≥0.8 기준값은 관례이지 이 과제 실측이 아니다. Phase 3 사람 표본이 나오면 값을 다시 정한다.

## 6. 출처

- PyPI JSON: deepeval, ragas, inspect-ai, anthropic, promptfoo(파이썬 동명 패키지는 무관), lm-eval, braintrust, langsmith, arize-phoenix, arize-phoenix-evals, openevals (2026-09-09)
- npm registry: promptfoo 0.122.2, 잠금 파일 로컬 해석
- DeepEval 소스(GitHub `confident-ai/deepeval` main): `deepeval/telemetry/client.py`, `deepeval/config/settings.py`, `deepeval/__init__.py`, `deepeval/evaluate/execute/_common.py`, `deepeval/models/llms/anthropic_model.py`, `deepeval/models/llms/amazon_bedrock_model.py`, `deepeval/models/llms/gateway_model.py`, `deepeval/metrics/faithfulness/templates/`; 문서 `deepeval.com/docs/data-privacy`, `metrics-faithfulness`, `metrics-llm-evals`, `metrics-dag`, `evaluation-datasets`, `evaluation-unit-testing-in-ci-cd`, `integrations/models/anthropic`
- RAGAS 소스(GitHub `vibrantlabsai/ragas` main): `src/ragas/_analytics.py`, `pyproject.toml`, `src/ragas/llms/base.py`, `src/ragas/llms/adapters/instructor.py`; 문서 `docs.ragas.io` faithfulness, customize_models
- Inspect AI 소스(GitHub `UKGovernmentBEIS/inspect_ai` main): `LICENSE`, `src/inspect_ai/hooks/_legacy.py`, `src/inspect_ai/hooks/_startup.py`, `src/inspect_ai/model/_providers/anthropic.py`, `src/inspect_ai/model/_generate_config.py`, `src/inspect_ai/scorer/_model.py`; 문서 `inspect.aisi.org.uk` providers, eval-logs, scorers
- promptfoo 문서: `promptfoo.dev/docs/configuration/telemetry`, `docs/faq`, `docs/providers/anthropic`
- Anthropic 문서: `platform.claude.com/docs/en/docs/test-and-evaluate/develop-tests`; claude-api 스킬(모델 표, structured outputs, Batches, sampling 파라미터 제거)
- repowiki: `PLAN.md` §3, §4, §5, §6; `docs/research/06-kb-findings.md` §2, §3, §7
