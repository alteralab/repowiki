import os, socket, sys, sqlite3, time
attempts = []
_orig_connect = socket.socket.connect
def blocked(self, addr):
    attempts.append(addr); raise OSError("blocked by probe")
socket.socket.connect = blocked
_orig_gai = socket.getaddrinfo
def gai(*a, **k):
    attempts.append(("getaddrinfo", a[0])); raise socket.gaierror("blocked by probe")
socket.getaddrinfo = gai
t = time.time()
import langgraph, langchain_core, langsmith
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt, Command
from typing import TypedDict
print(f"import ok in {time.time()-t:.2f}s, network attempts at import: {attempts}")
class S(TypedDict):
    n: int
    page: str
def plan(s): return {"n": s["n"] + 1}
def write(s):
    page = interrupt({"job": s["n"]})
    return {"page": page}
g = StateGraph(S).add_node("plan", plan).add_node("write", write)
g.add_edge(START, "plan"); g.add_edge("plan", "write"); g.add_edge("write", END)
with SqliteSaver.from_conn_string(":memory:") as saver:
    app = g.compile(checkpointer=saver)
    cfg = {"configurable": {"thread_id": "t1"}}
    r1 = app.invoke({"n": 0, "page": ""}, cfg)
    r2 = app.invoke(Command(resume="written"), cfg)
    time.sleep(1.5)  # give background tracing threads time to attempt
print("run ok:", r2, "| network attempts after run:", attempts)
print("env:", {k: os.environ.get(k) for k in ("LANGSMITH_TRACING","LANGCHAIN_TRACING_V2","LANGSMITH_API_KEY")})
