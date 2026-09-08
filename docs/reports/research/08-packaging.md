---
status: 조사 완료 — 로컬 실측(uv 0.11.8, pip 26.2.1, Node 22.17, Docker amd64 에뮬레이션) + 문서 인용; **[unverified]** 표기 항목은 미확인
date: 2026-09-08
scope: 사내(오프라인) 반입용 의존성 벤더링·패키징 전략
---

# repowiki — air-gapped packaging & dependency strategy

## 0. Headline findings
| # | Finding | Impact |
|---|---|---|
| 1 | `--platform manylinux2014_x86_64`는 패키지를 **조용히 다운그레이드**한다(ast-grep-cli 0.36.3, pygit2 1.17.0, tree-sitter-language-pack 0.13.0). 현행 휠 태그: ast-grep-cli·pygit2·tiktoken = `manylinux_2_28`, tree-sitter-language-pack ≥1.0 = **`manylinux_2_34`** | 대상 Linux는 **glibc ≥ 2.34 (RHEL 9 / Ubuntu 22.04+)**. RHEL 8(2.28)은 컨테이너 경로 또는 0.13.0 핀만 가능. ast-grep 0.45.3 바이너리는 GLIBC_2.28 필요 |
| 2 | **tree-sitter-language-pack ≥1.0.0(2026-03-21)은 문법을 동봉하지 않는다** — 첫 사용 시 GitHub releases에서 `parsers.json` + `libtree_sitter_<lang>.so` 다운로드; `--network none`이면 `DownloadError`. 검증된 해결: `TREE_SITTER_LANGUAGE_PACK_CACHE_DIR` + `prefetch([...])`를 **대상 플랫폼에서** 실행해 캐시 동봉(20개 언어 68 MB, 7 s). 마지막 동봉 판 0.13.0(2025-11-26, 20 MB) | 플랫폼별 문법 캐시를 사전 시딩하거나 0.13.0 핀 |
| 3 | `uv sync --frozen --no-index --find-links wheelhouse`는 **wheelhouse에서 설치하지 않는다**(uv.lock의 pythonhosted URL을 시도, uv#15519). wheelhouse 대상 재락은 상대 경로가 lock에 박혀 이동 시 깨진다(검증) | 오프라인은 **`uv pip install --no-index --find-links … --require-hashes -r requirements.lock.txt`** (검증, `--network none` 컨테이너) 또는 시딩된 `UV_CACHE_DIR` |
| 4 | `ast-grep-cli` 휠 = Rust 바이너리 데이터 휠: `.data/scripts/ast-grep`(50.2 MB ELF x86-64) + `sg`(deprecated 안내). CycloneDX SBOM 동봉(205 components, `tree-sitter-java@0.23.5` 등) | `ast-grep-cli==0.45.3` 핀 = 문법 집합 핀 (출력 안정성) |
| 5 | `tiktoken`은 첫 `get_encoding()`에 BPE 파일 다운로드(`openaipublic.blob.core.windows.net`); `TIKTOKEN_CACHE_DIR` 시딩으로 오프라인 로드 검증(o200k_base 3.6 MB). Anthropic `count_tokens`는 네트워크 | 5 MB 캐시 동봉; tiktoken은 추정기로만 |
| 6 | Mermaid 오프라인 검증 = Node + `mermaid` + `jsdom` (`mermaid.parse()`), 0.6 s/실행, 브라우저 불요. 순수 Python 검증기 없음(`mermaid-syntax-parser`는 pythonmonkey 의존). `mermaid-cli`는 puppeteer/Chromium → 부적합. GitLab·MkDocs Material은 클라이언트 렌더 → SVG 렌더링 불필요 | `node`(31 MB) + `node_modules` tgz(38 MB) 또는 npm 캐시(43 MB) 동봉 |
| 7 | **PEX `--scie eager`** 동작: Linux x86_64 단일 실행 파일 153 MB(python-build-standalone 3.12.14 내장), Mac에서 빌드해 python 없는 `debian:bookworm-slim --network none`에서 실행. 단 `pygit2` import는 `/etc/ssl/certs/ca-certificates.crt` 없으면 `GitError: OpenSSL error` | 컨테이너 없는 서버용 단일 파일 대안 |
| 8 | amd64 이미지(python:3.12-slim + git + node 바이너리 + venv + mermaid node_modules + tiktoken 캐시): **722 MB 비압축, 290 MB `docker save | gzip`**; `--network none`에서 전 검사 통과 | 컨테이너가 가장 깨끗한 단일 산출물 |
| 9 | Serena Java 기본 모드는 ~500 MB 다운로드(vscode-java VSIX + Gradle 8.14.2). **Upstream-JDTLS 모드**(`jdtls_path`+`lombok_path`, JDK 21+)는 다운로드 0(serena#1414). JDTLS 1.61.0 51 MB, Temurin 21 JRE 52 MB. pyright/TS는 Node + `npm install`을 `~/.serena/language_servers/static/`에; gopls는 프리빌트 없음 | Serena = 선택 계층; 언어별 static 디렉토리 사전 시딩 |

## 1. Python vendoring (verified)
- `uv pip download`는 uv 0.11.8에 **없다**. `pip download` 사용. Homebrew Python 3.14의 pip은 truststore 버그로 크래시 → 빌드 호스트는 uv 관리 3.12 venv.
- 올바른 명령: `pip download ast-grep-cli "anthropic[bedrock]" tree-sitter tree-sitter-language-pack pygit2 networkx pyyaml jinja2 typer click python-gitlab tiktoken pydantic rich -d wheelhouse228 --platform manylinux_2_34_x86_64 --platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all:` → 47 wheels, 44 MB, 실패 0. 최대: botocore 15.8 MB, ast-grep-cli 8.0 MB, pygit2 5.8 MB(libgit2 1.9.6·OpenSSL 3·libssh2 동봉).
- 락 기반: `uv lock` → `uv export --format requirements-txt --no-emit-project --frozen -o requirements.lock.txt`(hash 721줄) → `pip download -r requirements.lock.txt --require-hashes …` → Linux 46 wheels/44 MB, macOS arm64 46/49 MB, 합집합 58/71 MB.

| Flow | Command (offline) | Result |
|---|---|---|
| **A. pip-style (권장)** | `UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python --no-index --find-links wheelhouse --require-hashes -r requirements.lock.txt` | OK (`--network none`) |
| B. Mac에서 크로스 벤더 | `uv pip install --target ./vendor-linux --python-platform x86_64-manylinux_2_34 --python-version 3.12 --no-index --find-links wh-linux --only-binary :all: --require-hashes -r …` | OK, 148 MB; `manylinux_2_28` 타깃은 language-pack 휠 거부 |
| C. `uv sync --frozen --no-index --find-links` | — | **실패** |
| D. wheelhouse 대상 재락 | `uv lock --no-index --find-links wh-all` + `uv sync --frozen --no-index … --no-install-project` | 조건부(모든 universal-lock 패키지·빌드 백엔드 필요, 상대 경로 고정) |
| E. 시딩된 uv 캐시 | `UV_CACHE_DIR=./uv-cache uv sync --frozen`(온라인) → 복사 → `uv sync --frozen --offline` | OK (191 MB, 플랫폼별) |

env: `UV_OFFLINE`, `UV_NO_INDEX`, `UV_FIND_LINKS`, `UV_DEFAULT_INDEX`, `UV_INDEX`, `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_MIRROR`(`file://` 허용), `UV_PYTHON_INSTALL_DIR`, `UV_PYTHON_DOWNLOADS`, `UV_REQUIRE_HASHES`, `UV_SYSTEM_CERTS`, `SSL_CERT_FILE`, `HTTP(S)_PROXY`. Nexus: `[[tool.uv.index]] name="nexus" url="https://nexus.corp/repository/pypi-all/simple" default=true`. `uv export --format cyclonedx1.5` 존재(preview, 48 components).

Python 인터프리터: `UV_PYTHON_INSTALL_MIRROR=file:///opt/repowiki/pbs-mirror UV_PYTHON_INSTALL_DIR=… UV_OFFLINE=1 uv python install 3.12` 검증; 레이아웃 `<mirror>/<PBS tag>/<asset>`, 태그는 uv 버전에 고정 → uv와 PBS 자산을 함께 벤더. Linux x86_64 3.12.14 `install_only_stripped` 34 MB.

단일 파일: PEX 2.101.5 `--complete-platform`(대상에서 `pex3 interpreter inspect --markers --tags`) 45 MB; `--scie eager` 153 MB 네이티브(검증). shiv/zipapp/PyInstaller 미검증. `uv build --wheel`은 빌드 백엔드 벤더 시 오프라인 가능 — 휠은 **외부에서 빌드**해 동봉.

## 2. Node / Mermaid (verified)
mermaid 11.17.2 MIT(84 MB unpacked); mermaid+jsdom 29.1.1 = 152 packages, 179 MB node_modules, 38 MB tgz. 오프라인 검증 스크립트 `pkg-test/npm-test/parse_test.mjs`(flowchart/sequence/class/er/state/C4 통과, 4건 malformed 거부, 0.6 s). 시딩 npm 캐시(43 MB) + `npm ci --offline --cache ./npm-cache` 검증. Node 런타임 `node-v22.23.2-linux-x64.tar.xz` 31 MB(이미지에는 `/usr/local/bin/node`만 복사). mermaid-cli는 puppeteer 25.x → 부적합. Python 전용 검증기 없음. 기성: `@zabaca/mermaid-validate`.

## 3. Serena offline
`~/.serena/language_servers/static/<Server>/…`(`SERENA_HOME` 오버라이드). `RuntimeDependency(url, …)` → SHA 검증 다운로드; npm 서버는 `npm install --prefix ./ [--registry]`(registry 사용자 설정 여부 **[unverified]**). Java upstream 모드: `ls_specific_settings.java: {jdtls_path, lombok_path, java_home}`, JDK 21+. pyright 1.1.413 npm 4.2 MB(Node 필요; pip 래퍼는 nodeenv 런타임 다운로드 → 부적합). gopls 프리빌트 없음(외부 빌드 [portability unverified]). **판정**: `--lsp` opt-in 계층, 같은 OS/arch에서 만든 static 스냅샷 + JDK 21 + JDTLS tar(+~110 MB) 있을 때만.

## 4. Container vs tarball
기본 이미지(amd64 압축): python:3.12-slim-bookworm 45 MB · astral-sh/uv:python3.12-bookworm-slim 68 MB · node:22-slim 80 MB · eclipse-temurin:21-jre-jammy 99 MB. 테스트 이미지 722 MB/290 MB gz(`pkg-test/imgbuild/Dockerfile`). +tree-sitter 캐시 68 MB, +Java 계층 ≈105 MB 압축.

| 기준 | OCI 이미지 | tarball | PEX scie |
|---|---|---|---|
| 전송 크기 | ~300 MB gz(+Java 400) | ~220–250 MB Linux; +70 Mac; +110 Java | 153 MB + node/캐시 별도 |
| 재현성 | 최상(glibc·CA·node·캐시 고정, digest) | 양호(hash+PBS) but host glibc ≥2.34·ca-certificates·git 의존 | 양호, 같은 호스트 조건 |
| 갱신 | 전체 재전송(레이어 dedupe) | 바뀐 휠·캐시만 | 전체 |
| root | rootless podman(RHEL ≥8.1) 불요 | 불요 | 불요 |
| Mac 개발 | Docker/Podman Desktop + amd64 에뮬 | 네이티브 | Linux 전용 |
| devcontainer | `"image": "repowiki:<tag>"` | n/a | n/a |

## 5. LLM access in enterprise (verified against anthropic 1.4.0 / httpx2 2.12.0)
- SDK는 **`httpx2`** 사용; `http_client`는 httpx2 클라이언트여야 함(`httpx.Client` → TypeError). `DefaultHttpxClient(proxy=…, verify=…)`.
- env: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, **`ANTHROPIC_BASE_URL`**, `ANTHROPIC_BEDROCK_MANTLE_BASE_URL`, `ANTHROPIC_CUSTOM_HEADERS`, `AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION`, `ANTHROPIC_LOG`.
- httpx2는 `SSL_CERT_FILE`/`SSL_CERT_DIR`·`HTTPS_PROXY`·`NO_PROXY`(trust_env) 존중; `REQUESTS_CA_BUNDLE`은 python-gitlab(requests)·boto3만. 둘 다 사내 PEM으로 설정; uv는 `SSL_CERT_FILE` 또는 `UV_SYSTEM_CERTS=1`.
- Bedrock: `anthropic[bedrock]`(+16 MB boto3); `AnthropicBedrockMantle(aws_region=…)` 권장.
- Gateway: LiteLLM `base_url="http://litellm:4000/anthropic"`; base_url은 prefix, SDK가 `/v1/messages`를 붙임; 커스텀 경로 게이트웨이는 rewrite 필요 **[unverified]**.
- Secrets: URL에 PAT 금지(셸 이력); `GIT_ASKPASS`, `.netrc`(`machine gitlab.corp login oauth2 password <PAT>`), CI `gitlab-ci-token:${CI_JOB_TOKEN}`; pygit2 `RemoteCallbacks(credentials=UserPass("oauth2", token))` [API 미실행]; pygit2 import에 시스템 CA 필요.

## 6. Reproducibility / SBOM / licenses
- 출력을 정하는 핀: `ast-grep-cli==0.45.3`, `tree-sitter==0.26.0`, `tree-sitter-language-pack==1.16.2` + 캐시(`<cache>/tree-sitter-language-pack/v1.16.2/{manifest.json, libs/*.so}`; SBOM 198 components 동봉).
- hash: `uv export --frozen`이 sha256 전부 emit; `pip download --require-hashes`·`uv pip install --require-hashes` 검증. find-links 소스는 hash 불가(uv#10987) → PyPI 대상으로 락, wheelhouse에서 설치만.
- SBOM: `uv export --format cyclonedx1.5`, `cyclonedx-py environment .venv`. 취약점: `pip-audit`은 네트워크 필요 → 외부에서 lock에 대해 실행; `osv-scanner --offline`. 라이선스: `pip-licenses --with-license-file`.

## 7. Per-dependency table (Python 3.12, Linux x86_64, 2026-09-08)
| Package | Pure Python? | Wheel / size | Offline gotcha | License |
|---|---|---|---|---|
| ast-grep-cli 0.45.3 | No (Rust binary) | manylinux_2_28 / 8.0 MB (50 MB unpacked) | glibc ≥2.28; `sg` deprecated → `ast-grep` | MIT |
| ast-grep-py 0.45.3 | No | cp312 manylinux_2_28 | 바인딩 쓸 때만 | MIT |
| tree-sitter 0.26.0 | No | 0.67 MB | — | MIT |
| tree-sitter-language-pack 1.16.2 | No | **manylinux_2_34** / 2.4 MB | **문법 lazy 다운로드** → `prefetch()` 캐시 68 MB; 0.13.0이 마지막 동봉판 | MIT |
| pygit2 1.20.0 | No (libgit2·OpenSSL·libssh2) | manylinux_2_26/2_28 / 5.8 MB | import에 시스템 CA 필요 | **GPLv2 + linking exception** (법무 검토) |
| anthropic 1.4.0 | Yes | 1.3 MB | `count_tokens` 네트워크; `[bedrock]` +16 MB | MIT |
| httpx2/httpcore2 2.12.0 | Yes | any | SSL_CERT_FILE·HTTPS_PROXY 존중 | [unverified] BSD-3 |
| pydantic 2.13.5 / pydantic-core / jiter | Yes / No | — | — | MIT |
| networkx 3.6.1 | Yes | 2.1 MB | — | BSD-3 |
| pyyaml 6.0.3 | C ext | manylinux2014 | — | MIT |
| jinja2 / markupsafe | Yes / C | — | — | BSD-3 |
| typer / click / rich / pygments | Yes | — | `colorama` win32 only | MIT/BSD-3/MIT/BSD-2 [unverified] |
| python-gitlab 8.5.0 (+requests) | Yes | — | `REQUESTS_CA_BUNDLE` | **LGPL-3.0-or-later** (법무 검토) |
| tiktoken 0.14.0 | No (Rust) | manylinux_2_28 / 1.2 MB | BPE 다운로드 → `TIKTOKEN_CACHE_DIR` 5 MB | MIT |
| boto3/botocore | Yes | 16 MB | Bedrock만 | Apache-2.0 [unverified] |
| mermaid 11.17.2, jsdom 29.1.1 | JS | 38 MB tgz | Node 22 (31 MB) | MIT |
| JDT.LS 1.61.0 / Temurin 21 JRE / Lombok | Java | 51 / 52 / 2 MB | JDK ≥21, Serena upstream | EPL-2.0 [unverified] / GPLv2+CE / MIT |
| pyright 1.1.413 (npm) | JS | 4.2 MB | node ≥14 | MIT |

## 8. Recommended deliverable layout
```
repowiki-bundle-<version>-linux-x86_64/          (~250 MB; +50 MB macOS)
├── README-INSTALL.md · install.sh · SHA256SUMS
├── sbom/ {repowiki.cdx.json, licenses.md, pip-audit.json}
├── python/ {uv, pbs-mirror/<tag>/cpython-3.12.x-…-install_only_stripped.tar.gz (34 MB)}
├── wheels/ {requirements.lock.txt (hashes), repowiki-<ver>-py3-none-any.whl (외부 빌드), *.whl (44 MB)}
├── caches/ {tiktoken/ (5 MB), tree-sitter-language-pack/v1.16.2/{manifest.json, libs/*.so} (68 MB, Linux에서 prefetch)}
├── node/ {node-v22.x-linux-x64.tar.xz (31 MB), mermaid-node_modules.tgz (38 MB)}
└── optional-lsp/ {jdt-language-server-1.61.0.tar.gz, lombok.jar, temurin-21-jre.tar.gz, pyright-1.1.413.tgz, gopls}
```
컨테이너 대안: `repowiki-<version>-amd64.oci.tar.gz`(~300 MB), `podman load -i`. 같은 lock에서 두 산출물을 만든다.

`install.sh` 핵심(검증):
```
tar -xf python/pbs-mirror/*/cpython-*.tar.gz -C /opt/repowiki
export UV_OFFLINE=1 UV_NO_INDEX=1 UV_PYTHON_DOWNLOADS=never
uv venv --python /opt/repowiki/python/bin/python3.12 /opt/repowiki/venv
uv pip install --python /opt/repowiki/venv/bin/python --no-index --find-links wheels --require-hashes -r wheels/requirements.lock.txt
uv pip install --python /opt/repowiki/venv/bin/python --no-index --find-links wheels wheels/repowiki-*.whl
tar -xf node/node-v22*.tar.xz -C /opt/repowiki && tar -xzf node/mermaid-node_modules.tgz -C /opt/repowiki/mermaid
cp -r caches/* /opt/repowiki/caches/
# /etc/repowiki.env: TIKTOKEN_CACHE_DIR, TREE_SITTER_LANGUAGE_PACK_CACHE_DIR, NODE_PATH, ANTHROPIC_BASE_URL | AWS_REGION, SSL_CERT_FILE, REQUESTS_CA_BUNDLE
```

## 9. Recommendation
1. **1차 산출물: OCI 이미지 하나**(python:3.12-slim 또는 astral uv 이미지 + git + ca-certificates + node 바이너리 + hash 검증 venv + tiktoken/tree-sitter 캐시 + mermaid node_modules), ~300 MB gz, rootless podman; glibc 2.34·CA 문제를 우회. devcontainer는 이미지 참조만.
2. **2차: 포터블 tarball**(Mac·컨테이너 없는 Linux). `uv venv` + `uv pip install --no-index --find-links --require-hashes`(`uv sync --no-index` 아님).
3. **금지**: 오프라인 `uv sync`, 내부 `uv build`, `pyright` pip 래퍼, `mermaid-cli`, 캐시 없는 `tree-sitter-language-pack`. 대상이 RHEL 8이면 컨테이너 전용 또는 언어별 `tree-sitter-<lang>` 휠/0.13.0 핀.
4. **LLM**: `Anthropic(base_url=…)` + env; `--provider bedrock` → `AnthropicBedrockMantle`; `count_tokens` 선택적 + 로컬 추정 폴백; `SSL_CERT_FILE`.
5. **LSP/Serena = 선택 계층**(`--lsp`).
6. **재현성**: `uv.lock` 커밋; 릴리스마다 `requirements.lock.txt`(hash)·`sbom.cdx.json`·`licenses.md`; ast-grep-cli·tree-sitter·language-pack(+캐시)·PBS 태그·node·mermaid 핀; pygit2(GPLv2+예외)·python-gitlab(LGPL-3) 법무 검토 표시.

Local artefacts: scratchpad `pkg-test/` (`wheelhouse/`, `wheelhouse228/`, `uvproj/`, `imgbuild/Dockerfile`, `npm-test/parse_test.mjs`, `tslp-cache/`, `tt-cache/`, `pbs-mirror/`).
