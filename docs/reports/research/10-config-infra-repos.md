---
status: 실측 완료 (2026-09-08) — ast-grep 0.45.1, Serena 1.7.1, python-hcl2 8.1.4, PyYAML 6.0.3, helm 3.17.3, terraform 1.15.5. 대상은 사용자 로컬 레포(읽기 전용, 값 미열람)
scope: 설정·인프라 전용 레포(Helm, Terraform, k8s, Dockerfile, Spring 설정, CI)에 Serena·ast-grep이 맞는가와 대체 파서
---

# Config/infra repos: are Serena and ast-grep the right tools?

**답: 핵심 작업에는 아니다.** Serena는 `.tf`·YAML에서 최상위 키 목록 이상을 주지 않고(terraform-ls는 `terraform init`을 요구), ast-grep은 plain YAML·JSON·HCL은 파싱하지만 Helm 템플릿은 99%가 ERROR 노드이며 Dockerfile·TOML·properties·Groovy 문법이 없다. 설정 레포의 스택은 `helm template` + PyYAML, `python-hcl2`, `dockerfile-parse`, `jproperties`/`tomllib`, Jenkinsfile 정규식이고, ast-grep은 Java 쪽(`@ConfigurationProperties`)과 plain YAML/HCL 단발 규칙에만 남긴다.

작업 디렉토리: scratchpad `config-analysis/` (`hcl_inventory.py`, `k8s_graph.py`, `serena_overview.py`, `rules/`, `out/`). Serena는 복사본에서 실행(`.serena/`를 대상에 쓰므로).

레포 실태: 탐지 인프라 레포의 YAML 68개 중 k8s 매니페스트는 11개(나머지 vendored), Dockerfile 104개 중 100개가 kaniko vendor/testdata; `.tf` 371개는 ~30개 스택 디렉토리. aws-infra `.tf` 73개 = 실제 16 + `.terraform/modules/` 캐시 57.

## 1. ast-grep on config formats
언어 id: `yaml`, `hcl`, `json`, `bash`, `java`… **거부**: `terraform`(→`hcl`), `dockerfile`, `toml`, `properties`, `groovy`, `kotlin`.

### plain k8s manifests (11파일)
`-l yaml -k block_mapping_pair` 200건; ERROR 1/11(정상 YAML의 문법 특이점); `kind:` 9 + `image:` 5, `metadata.name` 9 추출 성공. 규칙 형태: `kind: block_mapping_pair` + `has: {field: key, regex: '^kind$'}`, 중첩은 `inside: {…, stopBy: end}`. 판정: 되지만 PyYAML보다 못하다(문서 분할·다중 문서 인식 없음, 매치가 텍스트).

### Helm templates (bdp-eks-charts, 377파일)
ERROR 노드 파일 **373/377 = 98.9%**; `{{` 포함 377/377; `kind:` 규칙 44건 vs grep 397건(**recall 11%**). **판정: 렌더 전 템플릿에는 쓸 수 없다.** 대신 `helm template x <chart>`(오프라인, 9개 차트 values 불필요): argo-cd 53 객체, grafana 12, rollout-operator 13, redis-ha 11, grafana-agent-operator 10, minio 8, fluent-bit 7, namespaces 4, app-of-apps 1; loki·emr-on-eks는 필수 values 부재로 실패 → 차트별 최소 values 오버라이드가 필요. 렌더 결과 PyYAML `safe_load_all` 119 객체, 오류 0.

### HCL / Terraform (aws-infra 실제 16파일)
ast-grep `hcl-block` 규칙: variable 11, data 8, resource 7, terraform 6, output 3, locals 3, module 2, provider 1 (ERROR 0). module source 추출: `./module-spark-ec2`, `terraform-aws-modules/vpc/aws`. 함정: tree-sitter-hcl은 **field 이름을 노출하지 않아** `has: {field: type}`가 조용히 0건 → `has: {kind: identifier, regex: '^module$', nthChild: 1}`; 패턴 문법 `module "x" { $$$ }`는 파싱 실패 → kind 룰 필수.
python-hcl2: 16/16 파싱, 0.77 s, 같은 수치 + data source·backend(s3 ×3)·변수/출력. 함정: 8.x는 문자열 리터럴을 **따옴표 포함**으로 반환 → 분류 전 strip. **판정: python-hcl2 우선.**

### 기타 포맷
| 포맷 | ast-grep | 대체(검증) |
|---|---|---|
| Dockerfile | 문법 없음 | `dockerfile-parse` 2.x(checkov 채택): 104/104 파싱, FROM 153 stage; 레지스트리 docker.io 112, alias/ARG 32, gcr.io 4, public.ecr.aws 3. `DockerfileParser(); d.content=text` 형태만 동작 |
| `.properties` | 없음 | `jproperties` |
| `.toml` | 없음 | stdlib `tomllib` |
| Groovy `build.gradle`, Jenkinsfile | 없음 | 정규식(`stage('…')`, `agent {`, `dependencies {`, `include`) |
| `.gitlab-ci.yml` | yaml 가능 | PyYAML: 최상위 dict에 `script`/`trigger`/`extends` → job; `stages`, `include`, `trigger` |

## 2. Serena on config repos (3분 사용)
언어 id에 `terraform`, `yaml`, `json`, `toml`, `groovy`, `ansible` 있음(`hcl`, `helm` 없음). `serena project index --language terraform` 73파일 5.9 s, terraform-ls가 "Backend initialization required, run terraform init" 출력; `--language yaml` 10파일 2.7 s. `get_symbols_overview`: `.tf`는 블록 헤더의 평면 목록("Class"로 태깅, outputs 누락), YAML은 최상위 키 목록에 잘못된 kind. `module.*`/`var.*` 교차 참조는 init 없이는 불가(실증). **판정: 설정 레포에서 Serena의 역할은 없다.**

## 3. 설정 레포 위키가 담을 것과 파서 (검증)
### Helm (bdp-eks-charts, `k8s_graph.py`)
- `Chart.yaml`: 11개 차트(최상위 7 + vendored 4). 교차 차트 엣지: loki → minio 5.4.0 / grafana-agent-operator 0.5.2 / rollout-operator 0.38.2(각 `condition`), argo-cd → redis-ha 4.34.11. `helm dependency list` 오프라인 일치.
- `values.yaml` 평탄화: argo-cd 764키(image 12), loki 1126(image 23, ingress host 2), grafana 302, fluent-bit 108. 자격증명 유사 키 14(값 미열람, 마스킹).
- 렌더 객체 그래프: **119 노드**(ServiceAccount 15, Service 15, ConfigMap 14, Role/RoleBinding 11/11, Deployment 9, ClusterRole/Binding 8/8, Secret 4, StatefulSet 3, CRD 3, Job 2, DaemonSet 1…), **292 엣지/124 고유**(env←CM 164, mounts 26, image 20, grants 19, to 19, env←Secret 17, runsAs 15, selects 12). dangling 22 = 외부 제공 Secret(예: `argocd-repo-server-tls`) → "외부 입력" 목록으로 유용. 이미지 16, 레지스트리 quay.io 9, docker.io 3 등. 산출: `out/k8s/{nodes,edges,images}.csv`, `graph.mmd`.
- 스팟체크 5건 전부 렌더 YAML에서 확인(Service selector→Deployment 라벨, serviceAccountName, ConfigMap 볼륨, secretKeyRef, RoleBinding roleRef/subject).

### Terraform (aws-infra, `hcl_inventory.py` → `out/tf/module_graph.{csv,mmd}`)
스택 = 최상위 디렉토리(`sg/`, `vpc/`, `spark/`, `spark/module-spark-ec2/`); 모듈 엣지 spark→`./module-spark-ec2`(local), vpc→`terraform-aws-modules/vpc/aws`(registry); backend s3 ×3; remote_state 0. `terraform graph`는 **init 필수**(복사본에서 "Backend initialization required" 확인, `validate`도 실패). HashiCorp 문서: init이 provider·module 소스를 내려받음(미러/플러그인 캐시 없으면 네트워크). → 오프라인 그래프는 python-hcl2(또는 hcl2json).

### Raw manifests / kustomize
`kubectl kustomize` 로컬 base 오프라인 동작(2 객체); 그래프 = `kustomization.yaml`의 resources/bases/patches를 PyYAML로. 원격 base(git URL)는 네트워크 필요 [README 문면].

### Spring Boot 설정 (scratchpad `repos/dubbo`)
`application.yml` 6파일, 61키/25 distinct, 프로필 없음(`dubbo.application.name`, `dubbo.config-center.address`…). ast-grep java `@ConfigurationProperties($$$A)` 4건(`prefix = "endpoints.dubbo"`, 상수 참조 2건은 2차 조회 필요). 키↔클래스 매칭은 prefix 조인 — 여기가 ast-grep이 진짜 맞는 자리.

## 4. 도구 지형 (WebFetch 검증, 표기 없으면 검증)
| 도구 | 읽는 것 | init/네트워크 | 라이선스 | 상태 |
|---|---|---|---|---|
| `terraform graph` | config | **init 필수**(문서+실증) | BSL | — |
| rover | terraform plan + 바이너리 | 예 | MIT | v0.3.2 |
| blast-radius | init된 dir, PyHCL | 예 | MIT | 활동 불명 |
| inframap | HCL dir 또는 tfstate | init 불요(문면) | MIT | 커밋일 미확인 |
| hcl2json | HCL | 아니오 | Apache-2.0 | 단일 Go 바이너리 |
| checkov | TF/K8s/Helm/Kustomize/Dockerfile | init 불요; `bc-python-hcl2`, `pyyaml`, `dockerfile-parse` 사용 | Apache-2.0 | 활발 |
| tfsec | HCL | 아니오 | MIT | Trivy로 대체됨 |
| `helm dependency list` | Chart.yaml + charts/ | 오프라인(검증) | Apache-2.0 | — |
| kustomize / `kubectl kustomize` | 로컬 파일 | 로컬 base 오프라인(검증) | Apache-2.0 | — |
| kubeview, k8sviz, kubectl-graph | **라이브 클러스터만** | kubeconfig | MIT/Apache | 레포에 부적합 |
| datree | manifests | 오프라인 모드 | Apache-2.0 | **2024-06-06 아카이브** |
| helm-dependency-graph, kube-graph | — | — | — | **[unverified]** |

## 5. 권고
레포 종류 감지(파일 서명, 순서대로, 2개 이상이면 mixed): **helm** = `Chart.yaml` + `templates/`; **terraform** = `.terraform/` 밖 `*.tf` ≥1; **k8s/kustomize** = `kustomization.y*ml` 또는 `apiVersion`+`kind`가 있고 `{{` 없는 YAML; **code** = `pom.xml`/`build.gradle*`/`package.json`/`pyproject.toml`/`go.mod`; **ci-extras**(모든 종류) = `.gitlab-ci.yml`, `Jenkinsfile*`, `Dockerfile*`.

종류별 분석기: helm = PyYAML(Chart, values) → `helm template`(바이너리 있을 때, 차트별 최소 values 저장) → 객체 그래프; 없으면 values+Chart만 + "미렌더" 표기; 템플릿에 ast-grep 금지. terraform = python-hcl2(따옴표 strip); terraform 바이너리 의존 없음. k8s/kustomize = PyYAML + `kubectl kustomize`(있을 때). code = ast-grep + (PyYAML/jproperties로 `application*` + `@ConfigurationProperties` 조인). 전부 = dockerfile-parse(FROM → 레지스트리/베이스 인벤토리), PyYAML `.gitlab-ci.yml`, Jenkinsfile 정규식, `tomllib`.

위키 페이지: Helm = 차트 개요, 교차 차트 의존, 렌더 객체 그래프(Mermaid), values 레퍼런스(자격증명 유사 키 마스킹), 이미지/레지스트리 인벤토리, 외부 입력(dangling Secret/ConfigMap). Terraform = 스택 레이아웃(디렉토리+backend), 모듈 그래프(local/git/registry), 리소스·data 인벤토리, remote-state 엣지, 스택별 변수/출력 계약, provider/required_versions. K8s = 객체 그래프 + kustomize 오버레이 트리. Code = 기존 + 설정 레퍼런스(프로필, datasource/kafka/server.port, `@ConfigurationProperties`).

**Serena의 설정 레포 역할: 없음.** ast-grep 역할: Java 설정 애노테이션과 선택적 HCL/plain-YAML 규칙. Helm 템플릿·Dockerfile·TOML·properties·Groovy에는 쓰지 않는다.
