"""Generate ONE 300-page Kafka-style architecture wiki (Korean prose, numbered 3-level titles,
Mermaid diagrams, citations, '분석 커밋' callout) and emit it for 3 generators:
  mkdocs   -> mkdocs-test/docs + mkdocs-test/nav.yml
  fuma     -> fuma-static/content/docs (.md + meta.json)
  starlight-> starlight-test/src/content/docs (.md) + starlight-test/sidebar.json
Semantic content is identical; only frontmatter / callout / details / link syntax differ per generator.
"""
import json, os, random, shutil, sys
random.seed(42)
SHA = "e2b5f0c7d1a94c3b8f6e2d1c0b9a8f7e6d5c4b3a"
GH = f"https://github.com/apache/kafka/blob/{SHA}"
COMMIT = SHA[:7]
STAMP = "2026-09-08 09:00 KST"

# ---------- structure: 9 sections x 4 subsections x 7 leaves = 297 + index + 2 appendix = 300 ----------
SECTIONS = [
 ("overview", "개요", ["목적과 범위", "저장소 구조", "빌드와 실행", "용어"]),
 ("broker", "브로커 코어", ["KafkaApis 요청 처리", "ReplicaManager 복제 관리자", "LogManager", "SocketServer"]),
 ("replication", "복제와 리더 선출", ["ISR 관리", "리더 에포크", "페치 프로토콜", "복제 스로틀링"]),
 ("storage", "저장소 계층", ["세그먼트와 인덱스", "로그 컴팩션", "티어드 스토리지", "리텐션"]),
 ("clients", "클라이언트", ["프로듀서 파이프라인", "컨슈머 페처", "어드민 클라이언트", "직렬화"]),
 ("coordinator", "코디네이터", ["그룹 코디네이터", "트랜잭션 코디네이터", "오프셋 커밋", "리밸런스 프로토콜"]),
 ("kraft", "KRaft 메타데이터", ["QuorumController", "메타데이터 로그", "스냅샷", "컨트롤러 마이그레이션"]),
 ("network", "네트워크와 보안", ["요청 채널", "SASL 인증", "ACL 권한", "쿼터"]),
 ("operations", "운영", ["설정 항목", "메트릭", "장애 시나리오", "업그레이드"]),
]
LEAF_NAMES = ["책임과 경계", "핵심 자료구조", "요청 흐름", "오류 처리", "동시성 모델", "설정과 튜닝", "테스트 전략"]
FILES = [
 ("core/src/main/scala/kafka/server/ReplicaManager.scala", 120, 160),
 ("core/src/main/scala/kafka/server/KafkaApis.scala", 210, 265),
 ("core/src/main/scala/kafka/log/LogManager.scala", 88, 131),
 ("storage/src/main/java/org/apache/kafka/storage/internals/log/UnifiedLog.java", 402, 455),
 ("core/src/main/scala/kafka/cluster/Partition.scala", 640, 702),
 ("clients/src/main/java/org/apache/kafka/clients/producer/internals/Sender.java", 301, 347),
 ("clients/src/main/java/org/apache/kafka/clients/consumer/internals/Fetcher.java", 150, 199),
 ("group-coordinator/src/main/java/org/apache/kafka/coordinator/group/GroupCoordinatorService.java", 77, 118),
 ("metadata/src/main/java/org/apache/kafka/controller/QuorumController.java", 990, 1042),
 ("raft/src/main/java/org/apache/kafka/raft/KafkaRaftClient.java", 512, 570),
 ("core/src/main/scala/kafka/network/SocketServer.scala", 230, 288),
 ("core/src/main/scala/kafka/server/ReplicaFetcherThread.scala", 60, 104),
]
KO = [
 "이 컴포넌트는 브로커 기동 시 한 번 생성되며 파티션별 상태를 메모리에 유지한다.",
 "요청은 요청 채널을 거쳐 핸들러 스레드 풀로 전달되고, 응답은 같은 경로를 역순으로 돌아간다.",
 "리더 복제본만 쓰기를 받으며 팔로워는 페치 요청으로 리더의 로그를 따라간다.",
 "ISR 축소는 replica.lag.time.max.ms 기준으로 판단되고 컨트롤러에 전파된다.",
 "세그먼트 롤링은 크기와 시간 두 조건 중 먼저 도달하는 쪽이 트리거한다.",
 "하이 워터마크는 ISR 내 모든 복제본이 확인한 오프셋의 최소값으로 갱신된다.",
 "락 순서는 항상 파티션 락 다음에 로그 락이며, 역순 획득은 데드락을 유발한다.",
 "타임아웃이 지난 지연 연산은 퍼거토리에서 강제로 완료되어 오류 응답을 만든다.",
 "메타데이터 캐시는 컨트롤러가 발행한 레코드를 순서대로 적용해 만들어진다.",
 "이 모듈의 결합도는 복제 관리자와 로그 관리자 사이에서 가장 높다.",
 "설정 값은 동적 브로커 설정으로 재기동 없이 바꿀 수 있는 항목과 그렇지 않은 항목으로 나뉜다.",
 "테스트는 통합 테스트 하네스 위에서 단일 브로커 클러스터를 띄워 검증한다.",
]
random.shuffle(KO)

def pick_files(k):
    return random.sample(FILES, k)

def cite(f):
    p, a, b = f
    return f"[`{p}:{a}-{b}`]({GH}/{p}#L{a}-L{b})"

# ---------- diagrams ----------
def heavy_flow(seed):
    r = random.Random(seed)
    groups = [("api", "요청 계층", ["SocketServer", "RequestChannel", "KafkaApis", "ApiVersions", "Authorizer", "Quotas"]),
              ("rep", "복제 계층", ["ReplicaManager", "Partition", "ISR", "LeaderEpochCache", "ReplicaFetcher", "HighWatermark", "DelayedProduce"]),
              ("log", "저장 계층", ["LogManager", "UnifiedLog", "LogSegment", "OffsetIndex", "TimeIndex", "LogCleaner", "RemoteLogManager"]),
              ("meta", "메타데이터", ["MetadataCache", "KRaftClient", "QuorumController", "BrokerLifecycle", "ConfigRepository"])]
    nodes = []
    lines = ["flowchart LR"]
    for gid, label, names in groups:
        lines.append(f"  subgraph {gid}[\"{label}\"]")
        for n in names:
            nid = f"{gid}_{n}"
            nodes.append(nid)
            shape = r.choice(["[{}]", "({})", "[({})]", "{{{{{}}}}}", "[[{}]]"])
            lines.append(f"    {nid}{shape.format(n)}")
        lines.append("  end")
    assert len(nodes) == 25, len(nodes)
    edges = set()
    labels = ["produce", "fetch", "append", "ack", "read", "update", "lookup", "callback", "apply", "publish"]
    while len(edges) < 60:
        a, b = r.sample(nodes, 2)
        edges.add((a, b))
    for a, b in sorted(edges):
        lab = r.choice(labels)
        arrow = r.choice(["-->", "-.->", "==>"])
        lines.append(f"  {a} {arrow}|{lab}| {b}")
    lines.append("  click rep_ReplicaManager \"../../2-broker/2-2-replicamanager/\" \"ReplicaManager\"")
    return "```mermaid\n" + "\n".join(lines) + "\n```"

def heavy_seq(seed):
    r = random.Random(seed)
    parts = ["Producer", "SocketServer", "KafkaApis", "ReplicaManager", "UnifiedLog"]
    lines = ["sequenceDiagram", "  autonumber"] + [f"  participant {p}" for p in parts]
    msgs = ["Produce v9 요청", "요청 큐 적재", "handleProduceRequest", "appendRecords", "append(records)",
            "LEO 갱신 반환", "DelayedProduce 등록", "팔로워 페치로 HW 전진", "tryCompleteDelayedProduce", "ProduceResponse 생성", "응답 큐 적재", "응답 전송 (base offset 포함)"]
    hops = [(0,1),(1,2),(2,3),(3,4),(4,3),(3,2),(2,3),(3,4),(4,3),(3,2),(2,1),(1,0)]
    for (a, b), m in zip(hops, msgs):
        arrow = "-->>" if a > b else "->>"
        lines.append(f"  {parts[a]}{arrow}{parts[b]}: {m}")
    lines.insert(9, "  Note over ReplicaManager,UnifiedLog: 파티션 락 → 로그 락 순서 유지")
    return "```mermaid\n" + "\n".join(lines) + "\n```"

def small_flow(names):
    lines = ["flowchart TD"]
    for i, n in enumerate(names):
        lines.append(f"  N{i}[{n}]")
    for i in range(len(names) - 1):
        lines.append(f"  N{i} --> N{i+1}")
    lines.append(f"  N0 -.-> N{len(names)-1}")
    return "```mermaid\n" + "\n".join(lines) + "\n```"

def dep_graph(seed):
    r = random.Random(seed)
    mods = ["clients", "core", "storage", "metadata", "raft", "server-common", "group-coordinator", "transaction-coordinator", "connect", "streams"]
    lines = ["flowchart LR"]
    for m in mods:
        lines.append(f"  {m.replace('-', '_')}[{m}]")
    for _ in range(18):
        a, b = r.sample(mods, 2)
        lines.append(f"  {a.replace('-', '_')} --> {b.replace('-', '_')}")
    return "```mermaid\n" + "\n".join(lines) + "\n```"

def class_diag():
    return """```mermaid
classDiagram
  class ReplicaManager {
    +appendRecords(timeout, requiredAcks, entries) Unit
    +fetchMessages(params) Unit
    +becomeLeaderOrFollower(request) Response
    -allPartitions ConcurrentHashMap
  }
  class Partition {
    +makeLeader(state) Boolean
    +appendRecordsToLeader(records) LogAppendInfo
    +maybeShrinkIsr() Unit
  }
  class UnifiedLog {
    +appendAsLeader(records) LogAppendInfo
    +read(offset, maxLength) FetchDataInfo
  }
  ReplicaManager "1" --> "*" Partition : manages
  Partition --> UnifiedLog : owns
```"""

def state_diag():
    return """```mermaid
stateDiagram-v2
  [*] --> Follower
  Follower --> Leader : makeLeader
  Leader --> Follower : makeFollower
  Leader --> Offline : 로그 디렉터리 장애
  Follower --> Offline : 로그 디렉터리 장애
  Offline --> [*]
```"""

def er_diag():
    return """```mermaid
erDiagram
  TOPIC ||--o{ PARTITION : has
  PARTITION ||--o{ SEGMENT : stores
  PARTITION }o--|| BROKER : leader
  TOPIC { string name  uuid id  int partitions }
  PARTITION { int index  long hw  long leo }
  SEGMENT { long baseOffset  int size }
```"""

# ---------- page model ----------
class Page:
    def __init__(self, num, slug_parts, title, level, heavy=False, seed=0):
        self.num, self.slug_parts, self.title, self.level, self.heavy, self.seed = num, slug_parts, title, level, heavy, seed
        self.files = pick_files(3 if heavy else 2)
        self.keyphrase = None

pages = []
sec_pages = []
for si, (sslug, stitle, subs) in enumerate(SECTIONS, 1):
    sp = Page(f"{si}", [f"{si}-{sslug}"], f"{si}. {stitle}", 1, seed=si)
    pages.append(sp); sec_pages.append((sp, []))
    for ji, subt in enumerate(subs, 1):
        subslug = f"{si}-{ji}-" + subt.split()[0].lower().replace("kafkaapis", "kafkaapis")
        subslug = f"{si}-{ji}-{['a','b','c','d'][ji-1]}" if not subt[0].isascii() else f"{si}-{ji}-{subt.split()[0].lower()}"
        subp = Page(f"{si}.{ji}", [f"{si}-{sslug}", subslug], f"{si}.{ji} {subt}", 2, seed=si*10+ji)
        pages.append(subp); sec_pages[-1][1].append((subp, []))
        for ki, leaf in enumerate(LEAF_NAMES, 1):
            heavy = (ki == 1)  # 36 heavy pages
            lp = Page(f"{si}.{ji}.{ki}", [f"{si}-{sslug}", subslug, f"{si}-{ji}-{ki}"], f"{si}.{ji}.{ki} {leaf}", 3, heavy=heavy, seed=si*100+ji*10+ki)
            pages.append(lp); sec_pages[-1][1][-1][1].append(lp)
# 2 appendix leaf pages under 9-operations/9-4
app = sec_pages[-1][1][-1]
for ki, leaf in [(8, "부록 A. 설정 전체 목록"), (9, "부록 B. 메트릭 전체 목록")]:
    lp = Page(f"9.4.{ki}", ["9-operations", "9-4-d", f"9-4-{ki}"], f"9.4.{ki} {leaf}", 3, seed=9000+ki)
    pages.append(lp); app[1].append(lp)
DEEP = next(p for p in pages if p.num == "3.2.4")
DEEP.keyphrase = "리더 에포크 캐시가 절단 지점을 결정한다"
RM = next(p for p in pages if p.num == "2.2")
print("pages:", len(pages) + 1, "heavy:", sum(p.heavy for p in pages), file=sys.stderr)

# ---------- rendering ----------
def link(target, frm, page):
    """relative link between pages; mkdocs/fuma use .md relative paths, starlight uses absolute URL"""
    if target == "starlight":
        return "/" + "/".join(page.slug_parts) + "/"
    tpath = page.slug_parts[:] ; fpath = frm.slug_parts[:-1] if frm.level == 3 else frm.slug_parts[:]  # dir of frm
    # frm dir: level1/2 pages are index.md inside their dir; level3 is file inside its parent dir
    i = 0
    while i < len(tpath) and i < len(fpath) and tpath[i] == fpath[i]: i += 1
    ups = "../" * (len(fpath) - i)
    rest = tpath[i:]
    pre = ups if ups else ("./" if target == "fuma" else "")
    if page.level < 3:
        return pre + "/".join(rest + ["index.md"]) if rest else pre + "index.md"
    return pre + "/".join(rest) + ".md"

def rel_path(page):
    if page.level < 3: return "/".join(page.slug_parts) + "/index.md"
    return "/".join(page.slug_parts) + ".md"

def callout(target, title, body):
    if target == "mkdocs":
        return f'!!! info "{title}"\n\n    {body}\n'
    if target == "fuma":
        return f":::info[{title}]\n{body}\n:::\n"
    return f":::note[{title}]\n{body}\n:::\n"

def details(target, title, items):
    lis = "\n".join(f"- {x}" for x in items)
    if target == "mkdocs":
        return f'??? note "{title}"\n\n' + "\n".join("    " + l for l in lis.splitlines()) + "\n"
    if target == "fuma":
        return f":::details[{title}]\n{lis}\n:::\n"   # mapped to Accordion via custom directive handler
    return f"<details>\n<summary>{title}</summary>\n\n{lis}\n\n</details>\n"

def frontmatter(target, page, heavy):
    fm = {"title": page.title, "description": f"{page.title} — apache/kafka 자동 생성 아키텍처 문서"}
    if target == "fuma":
        if heavy: fm["full"] = True
    if target == "starlight":
        fm["sidebar"] = {"order": int(page.num.split(".")[-1]), "label": page.title}
        if heavy: fm["tableOfContents"] = False
        fm["lastUpdated"] = "__DATE__"
    out = ["---"]
    for k, v in fm.items():
        if isinstance(v, dict):
            out.append(f"{k}:")
            for kk, vv in v.items(): out.append(f"  {kk}: {json.dumps(vv, ensure_ascii=False)}")
        else:
            out.append(f"{k}: {json.dumps(v, ensure_ascii=False)}".replace('"__DATE__"', '2026-09-08'))
    out.append("---")
    return "\n".join(out) + "\n"

def render(target, page, children):
    r = random.Random(page.seed)
    s = frontmatter(target, page, page.heavy)
    s += f"\n# {page.title}\n\n" if target == "mkdocs" else "\n"
    s += callout(target, "분석 커밋", f"`{COMMIT}` · {STAMP} · 분석 대상 파일 {len(page.files)}개 · 생성기 repowiki 0.4") + "\n"
    s += details(target, f"관련 소스 파일 ({len(page.files)})", [f"[{f[0]}]({GH}/{f[0]})" for f in page.files]) + "\n"
    s += "## 요약\n\n"
    s += f"**{page.title.split(' ',1)[1]}**는 {cite(page.files[0])}에 구현되어 있고 {cite(page.files[-1])}에서 호출된다. "
    s += " ".join(r.sample(KO, 3)) + "\n\n"
    if page.keyphrase: s += f"핵심 규칙: {page.keyphrase}. 이 규칙은 팔로워가 리더와 로그를 맞출 때 적용된다.\n\n"
    if page.num == "2.2": s += "복제 관리자(ReplicaManager)는 브로커의 모든 파티션 복제본을 소유하며 리더/팔로워 전환을 조율한다.\n\n"
    if children:
        s += "## 하위 문서\n\n"
        for c in children: s += f"- [{c.title}]({link(target, page, c)})\n"
        s += "\n"
    s += "## 구조\n\n"
    if page.heavy:
        s += "다음 그래프는 이 컴포넌트가 참여하는 25개 노드, 60개 의존 간선의 모듈 의존 그래프이다.\n\n" + heavy_flow(page.seed) + "\n\n"
        s += "### 요청 시퀀스\n\n12단계 호출 흐름. 홀수 단계는 요청, 짝수 단계는 응답 경로이다.\n\n" + heavy_seq(page.seed) + "\n\n"
        s += "### 상태 전이\n\n" + state_diag() + "\n\n"
    else:
        kind = r.choice(["dep", "class", "state", "er", "small"])
        s += {"dep": dep_graph(page.seed), "class": class_diag(), "state": state_diag(), "er": er_diag(),
              "small": small_flow([f[0].split("/")[-1].split(".")[0] for f in page.files] + ["Purgatory"])}[kind] + "\n\n"
        if r.random() < 0.5: s += "### 모듈 의존\n\n" + dep_graph(page.seed + 1) + "\n\n"
    s += "## 세부 사항\n\n"
    for h in ["책임", "핵심 함수", "오류 처리", "동시성", "설정"]:
        s += f"### {h}\n\n" + " ".join(r.sample(KO, 2)) + f" 자세한 내용은 {cite(r.choice(page.files))} 참고. "
        other = r.choice(pages)
        s += f"관련 문서: [{other.title}]({link(target, page, other)}), [{RM.title}]({link(target, page, RM)}).\n\n"
    s += "## 설정 표\n\n| 설정 | 기본값 | 동적 변경 | 설명 |\n|---|---|---|---|\n"
    for i in range(5):
        s += f"| `replica.lag.time.max.ms.{i}` | {30000 + i*1000} | {'예' if i%2 else '아니오'} | 팔로워가 ISR에서 제외되기까지의 최대 지연 |\n"
    s += "\n## 코드\n\n```scala\n// " + page.files[0][0] + f":{page.files[0][1]}\ndef appendRecords(timeout: Long, requiredAcks: Short,\n                  entriesPerPartition: Map[TopicPartition, MemoryRecords]): Unit = {{\n  val localProduceResults = appendToLocalLog(entriesPerPartition, requiredAcks)\n  if (delayedProduceRequestRequired(requiredAcks, entriesPerPartition, localProduceResults)) {{\n    val delayedProduce = new DelayedProduce(timeout, produceMetadata, this, responseCallback)\n    delayedProducePurgatory.tryCompleteElseWatch(delayedProduce, producerRequestKeys)\n  }}\n}}\n```\n"
    return s

def write_tree(target, root):
    shutil.rmtree(root, ignore_errors=True); os.makedirs(root)
    # index
    idx = frontmatter(target, Page("0", [], "Apache Kafka 아키텍처 위키", 0), False)
    if target == "starlight": idx = idx.replace('sidebar:\n  order: 0\n  label: "Apache Kafka 아키텍처 위키"\n', 'sidebar:\n  order: 0\n  label: "홈"\n')
    idx += ("\n# Apache Kafka 아키텍처 위키\n\n" if target == "mkdocs" else "\n")
    idx += callout(target, "분석 커밋", f"`{COMMIT}` · {STAMP} · 300 페이지 · 저장소 apache/kafka") + "\n"
    idx += "이 위키는 `apache/kafka` 저장소를 정적 분석해 자동 생성한 아키텍처 문서이다. 브로커, 복제, 저장소, 클라이언트, 코디네이터, KRaft 컴포넌트를 다룬다.\n\n## 목차\n\n"
    for sp, subs in sec_pages:
        idx += f"- [{sp.title}]({'/' + sp.slug_parts[0] + '/' if target=='starlight' else sp.slug_parts[0] + '/index.md'})\n"
        for subp, leaves in subs:
            idx += f"    - [{subp.title}]({'/' + '/'.join(subp.slug_parts) + '/' if target=='starlight' else '/'.join(subp.slug_parts) + '/index.md'})\n"
    idx += "\n## 전체 모듈 의존 그래프\n\n" + heavy_flow(1) + "\n"
    open(f"{root}/index.md", "w").write(idx)
    for sp, subs in sec_pages:
        d = f"{root}/{sp.slug_parts[0]}"; os.makedirs(d, exist_ok=True)
        open(f"{d}/index.md", "w").write(render(target, sp, [s for s, _ in subs]))
        if target == "fuma":
            json.dump({"title": sp.title, "pages": ["index"] + [s.slug_parts[1] for s, _ in subs]}, open(f"{d}/meta.json", "w"), ensure_ascii=False, indent=1)
        for subp, leaves in subs:
            dd = f"{d}/{subp.slug_parts[1]}"; os.makedirs(dd, exist_ok=True)
            open(f"{dd}/index.md", "w").write(render(target, subp, leaves))
            if target == "fuma":
                json.dump({"title": subp.title, "pages": ["index"] + [l.slug_parts[2] for l in leaves]}, open(f"{dd}/meta.json", "w"), ensure_ascii=False, indent=1)
            for lp in leaves:
                open(f"{dd}/{lp.slug_parts[2]}.md", "w").write(render(target, lp, []))
    if target == "fuma":
        json.dump({"title": "Kafka 위키", "root": True, "pages": ["index"] + [sp.slug_parts[0] for sp, _ in sec_pages]}, open(f"{root}/meta.json", "w"), ensure_ascii=False, indent=1)
    if target == "mkdocs":
        nav = [{"홈": "index.md"}]
        for sp, subs in sec_pages:
            grp = [f"{sp.slug_parts[0]}/index.md"]
            for subp, leaves in subs:
                g2 = [f"{'/'.join(subp.slug_parts)}/index.md"] + [rel_path(l) for l in leaves]
                grp.append({subp.title: g2})
            nav.append({sp.title: grp})
        import yaml
        open(os.path.join(os.path.dirname(root), "nav.yml"), "w").write(yaml.safe_dump({"nav": nav}, allow_unicode=True, sort_keys=False))
    if target == "starlight":
        sb = [{"label": "홈", "link": "/"}]
        for sp, subs in sec_pages:
            items = [{"label": sp.title, "link": f"/{sp.slug_parts[0]}/"}]
            for subp, leaves in subs:
                items.append({"label": subp.title, "collapsed": True, "items": [{"label": subp.title, "link": "/" + "/".join(subp.slug_parts) + "/"}] + [{"label": l.title, "link": "/" + "/".join(l.slug_parts) + "/"} for l in leaves]})
            sb.append({"label": sp.title, "collapsed": True, "items": items})
        json.dump(sb, open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(root))), "sidebar.json"), "w"), ensure_ascii=False, indent=1)

targets = sys.argv[1:] or ["mkdocs", "fuma", "starlight"]
for t in targets:
    root = {"mkdocs": "mkdocs-test/docs", "fuma": "fuma-static/content/docs", "starlight": "starlight-test/src/content/docs"}[t]
    write_tree(t, root)
    n = sum(1 for _, _, fs in os.walk(root) for x in fs if x.endswith(".md"))
    print(t, root, "pages:", n, file=sys.stderr)
