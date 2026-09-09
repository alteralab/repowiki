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
from repowiki.adapters.site import build, install, scaffold
from repowiki.bundle.emit import Frontmatter, frontmatter_of, render_index, render_llms_full, render_llms_txt, render_page
from repowiki.bundle.placeholders import expand, names
from repowiki.bundle.site_emit import meta_files, to_site_page
from repowiki.gate.page import PageViolation, check_page
from repowiki.models import PageJob, PageOutput, RepoFacts
from repowiki.write import source
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


def prepare(out: Path, facts: RepoFacts, repo: Path | None = None) -> tuple[Workspace, int]:
    """사실에서 작업을 만들어 작업장에 둔다. 이미 있는 작업장은 지우고 다시 만든다.

    `repo`를 주면 근거 자리의 원문을 함께 싣는다. 원문이 없으면 쓰는 층은 구조만 보고
    쓰게 되고, 구조에서 나올 수 있는 문장은 몇 가지로 닫힌다.
    """
    workspace = Workspace(root=str(out))
    if workspace.base.exists():
        for path in sorted(workspace.base.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        workspace.base.rmdir()
    workspace.pages_dir.mkdir(parents=True, exist_ok=True)

    store = JobStore(workspace.store_path)
    jobs = build_jobs(facts)
    if repo is not None:
        for job in jobs:
            source.fill(job.evidence, _evidence_texts(repo, job))
    for job in jobs:
        directory = workspace.job_dir(job.id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "job.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")
        (directory / "brief.md").write_text(_brief(job), encoding="utf-8")
        store.add(job.id, job.path, str(directory), job.input_hash)
    return workspace, len(jobs)


def _evidence_block(item) -> str:
    """근거 하나의 브리핑 조각. 자리와 설명과 원문을 한 덩어리로 둔다."""
    head = f"### `{item.id}` {item.note}\n\n`{item.span.cite()}`"
    if not item.text:
        return f"{head}\n\n(원문을 싣지 못했다. 이 자리를 근거로 쓰려면 자리만 인용한다.)"
    return f"{head}\n\n```\n{item.text}\n```"


def _evidence_texts(repo: Path, job: PageJob) -> dict[str, str]:
    """이 작업의 근거가 가리키는 파일만 읽는다. 읽지 못한 파일은 원문 없이 남는다."""
    texts: dict[str, str] = {}
    for item in job.evidence:
        path = item.span.path
        if path in texts:
            continue
        try:
            texts[path] = (repo / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return texts


def _brief(job: PageJob) -> str:
    """세션이 읽을 지시문. 사실은 `job.json`에 있고 여기에는 규약만 둔다."""
    evidence_lines = "\n\n".join(_evidence_block(item) for item in job.evidence)
    sibling_lines = "\n".join(
        f"- {item.get('title', '')}: `{item.get('path', '')}`" for item in job.siblings
    )
    slots = names(job.diagrams, job.tables)
    slot_lines = "\n".join(f"- `{slot}`" for slot in slots)
    diagram_note = (
        "도식과 표는 아래 자리표시자로 넣는다. 손으로 옮겨 적지 마라 — 제출할 때 도구가"
        " 사실의 소스로 바꾼다. 준 것은 하나도 빠뜨리지 말고, 주지 않은 도식이나 표를 만들지"
        " 마라."
        if slots
        else "이 페이지에는 도식과 표가 없다. 새로 만들지 마라."
    )
    table_note = (
        f"쓸 수 있는 자리표시자는 이것뿐이다.\n\n{slot_lines}"
        if slots
        else "표를 새로 만들면 게이트가 거부한다."
    )
    return f"""# 작업 {job.id}

- 쓸 파일: `{job.path}`
- 종류: `{job.type.value}`
- 제목: {job.title}
- 목적: {job.purpose}

## 규칙

1. `job.json`의 `facts`와 아래 근거의 원문에서 읽은 것만 쓴다. 저장소를 따로 열지 않는다.
2. 명제마다 근거를 각주로 단다. 형식은 `[^E3]`이고 아래 목록 밖의 id는 게이트가 거부한다.
3. 인용 밀도는 60단어에 한 건 이상이다. 분량은 700단어 이상을 목표로 한다.
4. {diagram_note}
5. {table_note}
6. 문장은 서술어와 종결어미로 끝낸다. 엠대시와 가운뎃점과 이모지를 쓰지 않는다. 이중 피동을 쓰지 않는다.
7. 소스 트리를 나열하지 않는다. 이 묶음이 무엇을 맡는지, 타입들이 서로 어떻게 일하는지,
   경계면 계약이 무엇인지, 무엇이 실패할 수 있는지를 쓴다. 원문에서 읽은 동작을 쓰되
   읽지 않은 것은 쓰지 않는다.
8. 형제 페이지를 가리킬 일이 있으면 상대 링크로 건다.

## 형제 페이지

{sibling_lines or "형제 페이지가 없다."}

## 근거

각 근거는 자리와 원문을 함께 준다. 원문에 없는 동작을 그 근거로 주장하지 않는다.

{evidence_lines or "이 페이지에는 인용할 근거가 없다. 사실 요약만 쓴다."}

## 제출

`page.json`을 이 디렉토리에 쓰고 `repowiki job submit <이 디렉토리>/page.json`을 실행한다.
형식은 `{{"job_id", "title", "description", "tags", "body_markdown", "citations"}}`이다.
"""


def describe(workspace: Workspace, job_id: str, evidence_ids: list[str]) -> str:
    """작업 하나를 사람이 읽을 형태로 낸다.

    `job.json`은 기계가 읽는 형태라 사람이 훑기에 나쁘다. 근거의 원문은 요청한 것만 싣는다 —
    전부 실으면 이 출력이 저장소가 된다.
    """
    job_file = workspace.job_dir(job_id) / "job.json"
    if not job_file.exists():
        raise FileNotFoundError(f"없는 작업이다: {job_id}")
    job = PageJob.model_validate_json(job_file.read_text(encoding="utf-8"))
    wanted = set(evidence_ids)

    lines = [
        f"# {job.id}",
        "",
        f"- 쓸 파일: `{job.path}`",
        f"- 종류: `{job.type.value}`  섹션: `{job.section}`",
        f"- 제목: {job.title}",
        f"- 목적: {job.purpose}",
        "",
        "## 자리표시자",
        "",
        *(f"- `{slot}`" for slot in names(job.diagrams, job.tables)),
        "",
        "## 형제 페이지",
        "",
        *(f"- {item.get('title', '')}: `{item.get('path', '')}`" for item in job.siblings),
        "",
        "## 사실",
        "",
        "```json",
        json.dumps(job.facts, ensure_ascii=False, indent=1),
        "```",
        "",
        f"## 근거 {len(job.evidence)}건",
        "",
    ]
    for item in job.evidence:
        lines.append(f"- `{item.id}` {item.note}: `{item.span.cite()}`")
    if wanted:
        lines += ["", "## 요청한 근거의 원문", ""]
        for item in job.evidence:
            if item.id not in wanted:
                continue
            lines += [f"### `{item.id}` {item.note}", "", f"`{item.span.cite()}`", ""]
            lines += ["```", item.text or "(원문을 싣지 못했다)", "```", ""]
    return "\n".join(lines)


def take(workspace: Workspace, job_id: str, worker: str) -> Job:
    """작업 하나를 이름으로 지정해 빌린다.

    `next`는 대기 순서대로 준다. 사람이 특정 쪽을 먼저 쓰고 싶을 때 그 순서에 매이지 않게
    한다. 이미 빌린 사람이 있으면 그 사실을 말하고 멈춘다.
    """
    store = JobStore(workspace.store_path)
    store.recover()
    job = store.lease_id(job_id, worker)
    if job is None:
        state = store.state_of(job_id)
        raise JobError(f"빌릴 수 없다: {job_id} 상태가 `{state}`다")
    return job


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
    # 자리표시자를 먼저 편다. 게이트가 보는 것은 편 뒤의 본문이다.
    output = output.model_copy(
        update={"body_markdown": expand(output.body_markdown, job.diagrams, job.tables)}
    )

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
        # 위키에 실리는 것은 게이트를 지나 저널에 확정된 내용이다. 작업 디렉토리의
        # `page.json`은 제출 뒤에도 고칠 수 있어서, 그것을 읽으면 게이트를 지나지 않은
        # 글이 위키에 실린다(C-GATE-1).
        if store.state_of(job.id) != "done":
            continue
        accepted = store.response_of(job.id)
        if accepted is None:
            continue
        output = PageOutput.model_validate_json(accepted)
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


def build_site(out: Path, repo_name: str, offline: bool) -> tuple[Path, int, float]:
    """위키를 Fumadocs 사이트로 만든다. 콘텐츠 변환은 순수 함수가 하고 여기서는 파일만 다룬다."""
    wiki = out / "wiki"
    if not wiki.exists():
        raise FileNotFoundError(f"위키가 없다: {wiki}. `repowiki bundle`을 먼저 돌린다")
    pages: dict[str, str] = {}
    for markdown in sorted(wiki.rglob("*.md")):
        relative = markdown.relative_to(wiki).as_posix()
        page = to_site_page(relative, markdown.read_text(encoding="utf-8"))
        pages[page.path] = page.content
    pages.update(meta_files(sorted(pages), repo_name))

    target = out / "site"
    scaffold(target, pages, app_name=f"{repo_name} 위키")
    install(target, offline)
    result = build(target)
    return Path(result.out), result.pages, result.seconds


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
