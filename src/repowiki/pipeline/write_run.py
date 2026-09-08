"""쓰기 실행: 작업 만들기, 세션에 넘기기, 제출 받기, 번들 만들기(PLAN §4).

경계 계약: 세션 드라이버는 파일로 오간다. `plan`이 작업을 만들어 `.repowiki/jobs/<id>/`에
두고, 세션이 `job next`로 하나를 받아 쓰고 `job submit`으로 낸다. 제출은 게이트를 지나야
받아들여지고, 실패하면 사유와 함께 같은 작업이 다시 대기로 돌아간다.

LLM이 사실 밖을 보지 못하게 하는 장치는 둘이다. 작업 디렉토리에 사실 조각만 두는 것과,
인용이 근거 id 밖이면 게이트가 거부하는 것이다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from repowiki.adapters.jobs import Job, JobError, JobStore
from repowiki.bundle.emit import Frontmatter, frontmatter_of, render_index, render_llms_full, render_llms_txt, render_page
from repowiki.gate.page import PageViolation, check_page
from repowiki.models import PageJob, PageOutput, RepoFacts
from repowiki.write.plan import build_jobs

JOBS_DIRNAME = ".repowiki"


class Workspace(BaseModel):
    """쓰기 작업장. 경로 계산만 한다."""

    root: str

    @property
    def base(self) -> Path:
        return Path(self.root) / JOBS_DIRNAME

    @property
    def store_path(self) -> Path:
        return self.base / "jobs.sqlite"

    def job_dir(self, job_id: str) -> Path:
        return self.base / "jobs" / job_id

    @property
    def pages_dir(self) -> Path:
        return self.base / "pages"


def prepare(out: Path, facts: RepoFacts) -> tuple[Workspace, int]:
    """사실에서 작업을 만들어 작업장에 둔다. 이미 있는 작업장은 지우고 다시 만든다."""
    workspace = Workspace(root=str(out))
    if workspace.base.exists():
        for path in sorted(workspace.base.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        workspace.base.rmdir()
    workspace.pages_dir.mkdir(parents=True, exist_ok=True)

    store = JobStore(workspace.store_path)
    jobs = build_jobs(facts)
    for job in jobs:
        directory = workspace.job_dir(job.id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "job.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")
        (directory / "brief.md").write_text(_brief(job), encoding="utf-8")
        store.add(job.id, job.path, str(directory), job.input_hash)
    return workspace, len(jobs)


def _brief(job: PageJob) -> str:
    """세션이 읽을 지시문. 사실은 `job.json`에 있고 여기에는 규약만 둔다."""
    evidence_lines = "\n".join(f"- `{item.id}` {item.note}: `{item.span.cite()}`" for item in job.evidence)
    diagram_note = (
        "이 작업의 `job.json`에 있는 `diagrams[].source`를 그대로 ```mermaid 블록에 넣어라."
        " 새로 그리거나 고치지 마라."
        if job.diagrams
        else "이 페이지에는 다이어그램이 없다."
    )
    return f"""# 작업 {job.id}

- 쓸 파일: `{job.path}`
- 종류: `{job.type.value}`
- 제목: {job.title}
- 목적: {job.purpose}

## 규칙

1. `job.json`의 `facts` 안에 있는 것만 쓴다. 저장소를 열어 보지 않는다.
2. 중요한 명제에는 근거를 각주로 단다. 형식은 `[^E3]`이고 아래 목록 밖의 id는 게이트가 거부한다.
3. 인용은 최소 세 건이다.
4. {diagram_note}
5. 문장은 서술어와 종결어미로 끝낸다. 엠대시와 가운뎃점과 이모지를 쓰지 않는다. 이중 피동을 쓰지 않는다.
6. 소스 트리를 나열하거나 메서드 목록을 반복하지 않는다. 책임, 경계면 계약, 핵심 흐름, 실패 모드를 쓴다.

## 근거 목록

{evidence_lines or "이 페이지에는 인용할 근거가 없다. 사실 요약만 쓴다."}

## 제출

`page.json`을 이 디렉토리에 쓰고 `repowiki job submit <이 디렉토리>/page.json`을 실행한다.
형식은 `{{"job_id", "title", "description", "tags", "body_markdown", "citations"}}`이다.
"""


def next_job(workspace: Workspace, worker: str) -> Job | None:
    """대기 중인 작업 하나를 빌린다."""
    store = JobStore(workspace.store_path)
    store.recover()
    return store.lease(worker)


def submit(workspace: Workspace, page_path: Path, worker: str) -> list[PageViolation]:
    """제출을 받아 게이트를 지난다. 위반이 없으면 페이지를 저장하고 작업을 끝낸다."""
    output = PageOutput.model_validate_json(page_path.read_text(encoding="utf-8"))
    job_file = workspace.job_dir(output.job_id) / "job.json"
    if not job_file.exists():
        raise FileNotFoundError(f"없는 작업이다: {output.job_id}")
    job = PageJob.model_validate_json(job_file.read_text(encoding="utf-8"))

    store = JobStore(workspace.store_path)
    state = store.state_of(job.id)
    if state == "done":
        raise JobError(f"이미 받은 작업이다: {job.id}. 다시 쓰려면 write를 다시 돌린다")
    if state == "pending":
        raise JobError(
            f"빌리지 않은 작업이다: {job.id}. `repowiki job next`로 먼저 받아야 한다"
            " (게이트가 거부하면 임대가 풀린다)"
        )
    violations = check_page(job, output)
    if violations:
        store.reject(job.id, violations[0].rule)
        return violations

    store.journal(job.id, store.generation_of(job.id), worker, output.model_dump_json())
    store.finish(job.id)
    target = workspace.pages_dir / job.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(output.body_markdown, encoding="utf-8")
    (workspace.job_dir(job.id) / "page.json").write_text(
        output.model_dump_json(indent=2), encoding="utf-8"
    )
    return []


def bundle(workspace: Workspace, out: Path, facts: RepoFacts) -> tuple[Path, int]:
    """제출된 페이지를 위키 디렉토리로 낸다. 머리말과 인덱스와 llms.txt를 함께 만든다."""
    wiki = out / "wiki"
    wiki.mkdir(parents=True, exist_ok=True)
    entries: list[tuple[str, Frontmatter]] = []
    bodies: list[tuple[str, str]] = []
    stamp = datetime.now(UTC).isoformat(timespec="seconds")

    store = JobStore(workspace.store_path)
    for job in build_jobs(facts):
        page_file = workspace.job_dir(job.id) / "page.json"
        # 게이트를 통과해 끝난 작업만 낸다. 거부된 제출이 디렉토리에 남아 있어도 싣지 않는다.
        if not page_file.exists() or store.state_of(job.id) != "done":
            continue
        output = PageOutput.model_validate_json(page_file.read_text(encoding="utf-8"))
        rendered = render_page(job, output, facts, stamp)
        target = wiki / job.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        entries.append((job.path, frontmatter_of(job, output, facts, stamp)))
        bodies.append((job.path, rendered))

    name = facts.profile.root_name
    (wiki / "index.md").write_text(render_index(entries, name), encoding="utf-8")
    (wiki / "llms.txt").write_text(render_llms_txt(entries, name), encoding="utf-8")
    (wiki / "llms-full.txt").write_text(render_llms_full(bodies), encoding="utf-8")
    schema = wiki / ".schema"
    schema.mkdir(exist_ok=True)
    (schema / "frontmatter.json").write_text(
        json.dumps(Frontmatter.model_json_schema(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return wiki, len(entries)


def status(workspace: Workspace) -> dict[str, int]:
    """작업 상태별 수. 진행의 정본은 이 표다."""
    return JobStore(workspace.store_path).counts()


def load_facts(out: Path) -> RepoFacts:
    """이전 분석의 사실을 읽는다."""
    return RepoFacts.model_validate_json((out / "facts.json").read_text(encoding="utf-8"))


def write_manifest(workspace: Workspace, facts: RepoFacts) -> Path:
    """페이지별 입력 해시를 남긴다. 증분 판정의 정본이다(PLAN §2.9)."""
    jobs = build_jobs(facts)
    manifest = {
        "analyzed_commit": facts.profile.head_sha,
        "pages": {job.path: {"job_id": job.id, "input_hash": job.input_hash} for job in jobs},
    }
    target = workspace.pages_dir / ".manifest.json"
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return target
