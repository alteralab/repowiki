// Mermaid 문법 게이트. 두 판(사이트 판과 GitLab 저장소 뷰 판)으로 같은 소스를 파싱한다.
// 입력은 stdin의 JSON `[{id, source}]`, 출력은 stdout의 JSON `[{id, ok, version, error}]`.
// Chromium을 쓰지 않는다 — jsdom에서 mermaid.parse만 부른다(PLAN §2.5).
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', { pretendToBeVisual: true });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.DOMPurify = (await import('dompurify')).default(dom.window);
for (const key of ['navigator', 'HTMLElement', 'SVGElement', 'Element', 'Node', 'getComputedStyle', 'DocumentFragment']) {
  if (!(key in globalThis)) globalThis[key] = dom.window[key];
}

const versions = [
  { name: 'site', module: 'mermaid' },
  { name: 'gitlab', module: 'mermaid-gitlab' },
];

const input = JSON.parse(await new Promise((resolve, reject) => {
  let buffer = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => { buffer += chunk; });
  process.stdin.on('end', () => resolve(buffer));
  process.stdin.on('error', reject);
}));

const results = [];
for (const { name, module } of versions) {
  const mermaid = (await import(module)).default;
  mermaid.initialize({ startOnLoad: false, securityLevel: 'loose', suppressErrorRendering: true });
  for (const { id, source } of input) {
    try {
      const parsed = await mermaid.parse(source, { suppressErrors: false });
      results.push({ id, version: name, ok: true, diagram_type: parsed.diagramType });
    } catch (error) {
      const message = String(error?.message ?? error).split('\n').slice(0, 3).join(' | ');
      results.push({ id, version: name, ok: false, error: message });
    }
  }
}
process.stdout.write(JSON.stringify(results));
