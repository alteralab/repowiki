"""Generate a ~20-page repowiki-style sample wiki into fuma-static/content/docs."""
import json, os, shutil, textwrap
root = "fuma-static/content/docs"
shutil.rmtree(root, ignore_errors=True); os.makedirs(root)
GL = "https://gitlab.example.com/platform/orderflow/-/blob/main"

def fm(title, desc, sources, extra=""):
    lines = ["---", 'title: "%s"' % title, 'description: "%s"' % desc, "generator: repowiki", "repo: platform/orderflow",
             "commit: 3f9c2a1", "generated_at: 2026-09-08T09:00:00+09:00", "sources:"] + ["  - " + x for x in sources]
    if extra: lines.append(extra.rstrip())
    return chr(10).join(lines) + chr(10) + "---" + chr(10)

def cite(path, a, b):
    return f"[`{path}:{a}-{b}`]({GL}/{path}#L{a}-{b})"

def sources_block(sources):
    items = "\n".join(f"- [{s}]({GL}/{s})" for s in sources)
    return f"""<Accordions type="single">
<Accordion title="Relevant source files ({len(sources)})">

{items}

</Accordion>
</Accordions>
"""

diagrams = {
 "flow": """```mermaid
flowchart LR
  API[REST API<br/>api/server.py] --> SVC[OrderService]
  SVC --> REPO[(PostgreSQL)]
  SVC --> MQ{{Kafka topic<br/>orders.v1}}
  MQ --> WK[Fulfilment worker]
  click SVC "../2-architecture/2-2-order-service" "Order service"
```""",
 "seq": """```mermaid
sequenceDiagram
  participant C as Client
  participant A as api/server.py
  participant S as OrderService
  participant K as Kafka
  C->>A: POST /orders (JSON)
  A->>S: create_order(dto)
  S->>K: produce orders.v1
  K-->>S: ack
  S-->>A: OrderCreated
  A-->>C: 201 {"id": "..."}
```""",
 "class": """```mermaid
classDiagram
  class OrderService {
    +create_order(dto) Order
    +cancel(id) None
    -_validate(dto) bool
  }
  class OrderRepository {
    +get(id) Order
    +save(order) None
  }
  OrderService --> OrderRepository : uses
  OrderService --> KafkaProducer : publishes
```""",
 "er": """```mermaid
erDiagram
  ORDER ||--o{ ORDER_LINE : contains
  ORDER {
    uuid id PK
    string status
    timestamp created_at
  }
  ORDER_LINE {
    uuid id PK
    uuid order_id FK
    int qty
  }
```""",
 "state": """```mermaid
stateDiagram-v2
  [*] --> Pending
  Pending --> Confirmed : payment ok
  Pending --> Cancelled : timeout
  Confirmed --> Shipped
  Shipped --> [*]
```""",
}
kinds = list(diagrams)

# Section plan: (folder, section title, [(slug, title, sources)])
plan = [
 ("1-overview", "1. Overview", [
   ("1-1-purpose", "1.1 Purpose and scope", ["README.md", "pyproject.toml"]),
   ("1-2-repository-layout", "1.2 Repository layout", ["src/orderflow/__init__.py", "Makefile"]),
   ("1-3-quick-start", "1.3 Quick start", ["docs/quickstart.md", "docker-compose.yml"]),
 ]),
 ("2-architecture", "2. Architecture", [
   ("2-1-system-context", "2.1 System context", ["src/orderflow/api/server.py", "src/orderflow/config.py"]),
   ("2-2-order-service", "2.2 Order service", ["src/orderflow/services/order.py", "src/orderflow/repo/order_repo.py"]),
   ("2-3-messaging", "2.3 Messaging (Kafka)", ["src/orderflow/mq/producer.py", "src/orderflow/mq/consumer.py"]),
   ("2-4-persistence", "2.4 Persistence", ["src/orderflow/repo/base.py", "migrations/0001_init.sql"]),
   ("2-5-order-lifecycle", "2.5 Order lifecycle", ["src/orderflow/domain/state.py"]),
 ]),
 ("3-modules", "3. Modules", [
   ("3-1-api", "3.1 api package", ["src/orderflow/api/server.py", "src/orderflow/api/routes/orders.py"]),
   ("3-2-services", "3.2 services package", ["src/orderflow/services/order.py", "src/orderflow/services/pricing.py"]),
   ("3-3-domain", "3.3 domain package", ["src/orderflow/domain/order.py", "src/orderflow/domain/state.py"]),
   ("3-4-repo", "3.4 repo package", ["src/orderflow/repo/order_repo.py"]),
   ("3-5-mq", "3.5 mq package", ["src/orderflow/mq/producer.py"]),
   ("3-6-cli", "3.6 cli package", ["src/orderflow/cli.py"]),
 ]),
 ("4-operations", "4. Operations", [
   ("4-1-configuration", "4.1 Configuration", ["src/orderflow/config.py", ".env.example"]),
   ("4-2-deployment", "4.2 Deployment", ["deploy/helm/values.yaml", ".gitlab-ci.yml"]),
   ("4-3-observability", "4.3 Observability", ["src/orderflow/telemetry.py"]),
   ("4-4-testing", "4.4 Testing strategy", ["tests/conftest.py", "tests/test_order_service.py"]),
 ]),
]

# root index + meta
with open(f"{root}/index.mdx", "w") as f:
    f.write(fm("orderflow wiki", "Auto-generated architecture wiki for platform/orderflow", ["README.md"]))
    f.write("""
<Callout title="Last indexed">Commit `3f9c2a1` · 2026-09-08 09:00 KST · 20 pages</Callout>

이 위키는 `platform/orderflow` 저장소의 아키텍처를 자동 생성한 문서입니다. (한글 렌더링 확인용 문장: 주문 서비스는 Kafka 토픽으로 이벤트를 발행합니다.)

## Contents

- [1. Overview](./1-overview/1-1-purpose.mdx)
- [2. Architecture](./2-architecture/2-1-system-context.mdx)
- [3. Modules](./3-modules/3-1-api.mdx)
- [4. Operations](./4-operations/4-1-configuration.mdx)

""" + diagrams["flow"] + "\n")
json.dump({"title": "orderflow", "pages": ["index", "---Wiki---", "1-overview", "2-architecture", "3-modules", "4-operations", "---Probes---", "probe-mdx-hostile", "probe-plain-md"]}, open(f"{root}/meta.json", "w"), indent=2)

n = 0
for folder, sec_title, pages in plan:
    os.makedirs(f"{root}/{folder}", exist_ok=True)
    json.dump({"title": sec_title, "defaultOpen": True, "pages": [p[0] for p in pages]}, open(f"{root}/{folder}/meta.json", "w"), indent=2)
    for i, (slug, title, sources) in enumerate(pages):
        kind = kinds[n % len(kinds)]; n += 1
        nxt = pages[(i + 1) % len(pages)][0]
        body = fm(title, f"{title} of orderflow — generated from {len(sources)} source files", sources)
        body += f"\n{sources_block(sources)}\n"
        body += f"## Summary\n\nThe **{title.split(' ',1)[1]}** is implemented in {cite(sources[0], 12, 48)} and wired from {cite(sources[-1], 1, 30)}. 한글 설명: 이 컴포넌트는 주문 생성 흐름의 핵심입니다.\n\n"
        body += f"## Diagram\n\n{diagrams[kind]}\n\n"
        body += "## Details\n\n"
        for h in ["Responsibilities", "Key functions", "Error handling", "Configuration"]:
            body += f"### {h}\n\nLorem ipsum dolor sit amet, see {cite(sources[0], 50, 90)} for details. Cross-ref: [{nxt}](./{nxt}.mdx) and [2.2 Order service](../2-architecture/2-2-order-service.mdx).\n\n"
        body += "```python\ndef create_order(dto: OrderDTO) -> Order:  # src/orderflow/services/order.py:12\n    order = Order.from_dto(dto)\n    repo.save(order)\n    producer.send('orders.v1', order.to_event())\n    return order\n```\n"
        open(f"{root}/{folder}/{slug}.mdx", "w").write(body)

# Probe 1: MDX-hostile plain prose (curly braces, generics) as .mdx
open(f"{root}/probe-mdx-hostile.mdx", "w").write(fm("Probe: MDX-hostile text", "Contains {braces} and <T> generics in prose", ["src/x.py"]) + "\nThis text has f-string style {name} and a generic List<T> and Map<K, V> in prose.\n")
# Probe 2: same content as plain .md (format md) with a mermaid fence and HTML details
open(f"{root}/probe-plain-md.md", "w").write(fm("Probe: plain .md", "Plain markdown with braces {x} <T> and mermaid", ["src/y.py"]) + "\nPlain markdown: {name} and List<T> here.\n\n<details><summary>Relevant source files</summary>\n\n- a.py\n\n</details>\n\n" + diagrams["state"] + "\n")
print("pages:", sum(len(f) for _, _, f in os.walk(root) for f in [f] if False) or sum(1 for d,_,fs in os.walk(root) for x in fs if x.endswith(('.md','.mdx'))))
