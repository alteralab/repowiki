"""픽스처 모듈. 라우트 진입점과 인자 안의 호출을 함께 담는다."""

import os


class Service:
    def __init__(self, store: "Store") -> None:
        self.store = store


class Store:
    pass


@app.get("/items")  # noqa: F821
def read_items():
    return []


@click.option("--path", default=lambda: os.environ.get("PATH"))  # noqa: F821
def cli():
    return None
