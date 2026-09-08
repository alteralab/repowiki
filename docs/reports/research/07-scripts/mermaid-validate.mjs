// Headless Mermaid syntax validator: mermaid.parse() under jsdom, no Chromium.
// usage: node validate.mjs file1.mmd [file2.mmd ...]   (or pass a .md to check all ```mermaid fences)
import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';

const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', { pretendToBeVisual: true });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.DOMPurify = (await import('dompurify')).default(dom.window);
for (const k of ['navigator','HTMLElement','SVGElement','Element','Node','getComputedStyle','DocumentFragment'])
  if (!(k in globalThis)) globalThis[k] = dom.window[k];

const mermaid = (await import('mermaid')).default;
mermaid.initialize({ startOnLoad: false, securityLevel: 'loose', suppressErrorRendering: true });

function extract(path) {
  const src = readFileSync(path, 'utf8');
  if (!path.endsWith('.md')) return [{ name: path, code: src }];
  const out = []; const re = /```mermaid\s*\n([\s\S]*?)```/g; let m, i = 0;
  while ((m = re.exec(src))) out.push({ name: `${path}#${++i}`, code: m[1] });
  return out;
}

let bad = 0;
for (const f of process.argv.slice(2)) {
  for (const { name, code } of extract(f)) {
    try {
      const r = await mermaid.parse(code, { suppressErrors: false });
      console.log(`OK    ${name}  (${r.diagramType})`);
    } catch (e) {
      bad++;
      const msg = String(e.message ?? e).split('\n').slice(0, 3).join(' | ');
      console.log(`FAIL  ${name}: ${msg}`);
    }
  }
}
process.exit(bad ? 1 : 0);
