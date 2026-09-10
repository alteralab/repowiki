"""시스템 인덱스. 한 뿌리 아래 위키들을 찾아 `system/index.md` 와 `system/llms.txt` 를 낸다.

위키가 하나여도 만든다. 저장소가 늘면 같은 뿌리 아래 산출 디렉터리를 더 두고 이 명령을
다시 돌리면 줄이 더해진다 — 인덱스를 나중에 짓는 것이 아니라 처음부터 있는 자리다.

경계 계약: 입력은 뿌리 디렉터리이고 출력은 `system/` 아래 파일 둘이다. 구성원의 사실은 각
위키의 `.manifest.json` 에서만 읽는다. 저장소 사이의 관계(시스템 그래프)는 이 모듈이 아니다 —
이것은 라우팅이지 분석이 아니다.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from repowiki.bundle.emit import SYSTEM_MARK, render_system_index, render_system_llms
from repowiki.models import SystemMember

MANIFEST = ".manifest.json"
_FILES = ("index.md", "llms.txt")


class SystemIndexError(Exception):
    """뿌리 아래의 위키를 인덱스로 만들 수 없다. 메시지에 어느 자리인지가 있다."""


def discover(root: Path) -> list[SystemMember]:
    """뿌리 아래의 위키들. `<뿌리>/wiki` 와 `<뿌리>/*/wiki` 를 경로순으로 본다.

    더 깊이 뒤지지 않는다. 산출 디렉터리 하나가 `wiki/` 를 갖는 배치이고, 더 내려가면 사이트의
    복사본(`site/out/...`)이나 픽스처가 위키로 잡힌다.

    같은 이름이 둘이거나 같은 위키가 두 경로로 잡히면(링크) 거부한다. 이름으로 저장소를 고르는
    자리라 같은 이름 두 줄은 길을 잃게 한다.
    """
    candidates = [root / "wiki"] + sorted(p / "wiki" for p in root.iterdir() if p.is_dir())
    members: list[SystemMember] = []
    seen_names: dict[str, str] = {}
    seen_real: dict[Path, str] = {}
    for wiki in candidates:
        manifest = wiki / MANIFEST
        if not manifest.is_file():
            continue
        relative = wiki.relative_to(root).as_posix()
        try:
            member = SystemMember(path=relative, **json.loads(manifest.read_text(encoding="utf-8")))
        except (ValueError, ValidationError) as error:
            raise SystemIndexError(f"{manifest}: 읽을 수 없는 manifest 다: {error}") from error
        real = wiki.resolve()
        if real in seen_real:
            raise SystemIndexError(f"{relative} 는 {seen_real[real]} 와 같은 위키다(링크). 하나만 둔다")
        if member.name in seen_names:
            raise SystemIndexError(
                f"이름 {member.name!r} 이 {seen_names[member.name]} 와 {relative} 둘에 있다. 이름은 하나여야 한다"
            )
        seen_real[real] = relative
        seen_names[member.name] = relative
        members.append(member)
    return members


def _refuse_foreign(system: Path) -> None:
    """repowiki 가 만들지 않은 `system/index.md` 나 `llms.txt` 가 있으면 건드리지 않고 멈춘다."""
    for name in _FILES:
        target = system / name
        if target.is_file() and SYSTEM_MARK not in target.read_text(encoding="utf-8"):
            raise SystemIndexError(f"{target} 는 repowiki 가 만든 파일이 아니다. 옮기거나 지운 뒤 다시 돌린다")


def write_system(root: Path, root_name: str | None = None) -> tuple[Path, int]:
    """`system/` 을 쓴다. 구성원이 없으면 낡은 인덱스를 지우고 0 을 낸다 — 빈 인덱스도 낡은
    인덱스도 길을 잘못 안내한다."""
    members = discover(root)
    system = root / "system"
    _refuse_foreign(system)
    if not members:
        for name in _FILES:
            (system / name).unlink(missing_ok=True)
        return system, 0
    name = root_name or (members[0].name if len(members) == 1 else root.name)
    system.mkdir(parents=True, exist_ok=True)
    (system / "index.md").write_text(render_system_index(members, name), encoding="utf-8")
    (system / "llms.txt").write_text(render_system_llms(members, name), encoding="utf-8")
    return system, len(members)
