import { JSDOM } from "jsdom";
const dom = new JSDOM("<!doctype html><body></body>");
globalThis.window = dom.window; globalThis.document = dom.window.document;
globalThis.DOMPurify = undefined;
const { default: mermaid } = await import("mermaid");
const { default: mermaidGitlab } = await import("mermaid-gitlab");
mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
mermaidGitlab.initialize({ startOnLoad: false, securityLevel: "strict" });
const ok = "flowchart LR\n A[core] --> B[api]\n";
const bad = "flowchart LR\n A[core] --> \n";
for (const [name, m] of [["11.17.2", mermaid], ["11.13.0", mermaidGitlab]]) {
  console.log(name, "ok:", JSON.stringify(await m.parse(ok)));
  console.log(name, "bad:", JSON.stringify(await m.parse(bad, { suppressErrors: true })));
}
