"""진입점 규칙의 픽스처. 라우트로 세어야 하는 것과 아닌 것을 한 파일에 둔다.

이 파일은 실행 대상이 아니라 룰의 기대값이다. 줄 번호가 검사의 일부다.
"""

import os


@app.get("/items")  # noqa: F821
def read_items():
    """라우트다."""


@router.post("/create")  # noqa: F821
def create_item():
    """라우트다."""


@click.option("--path", default=lambda: os.environ.get("PATH"))  # noqa: F821
def cli_command():
    """라우트가 아니다. 인자 안의 `.get(`이 잡히면 오검출이다."""


@task  # noqa: F821
def plain_task():
    """라우트가 아니다. 이름만 있는 데코레이터다."""
