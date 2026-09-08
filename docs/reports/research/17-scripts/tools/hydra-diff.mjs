// Compare server HTML (JS off) vs hydrated DOM to hint where React #418 mismatches. Coarse: first differing element path.
import puppeteer from 'puppeteer-core';
const url = process.argv[2];
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--no-sandbox'] });
async function snap(js) {
  const p = await b.newPage(); await p.setViewport({ width: 1440, height: 900 }); await p.setJavaScriptEnabled(js);
  await p.goto(url, { waitUntil: js ? 'networkidle0' : 'load' }); if (js) await new Promise(r => setTimeout(r, 1500));
  const s = await p.evaluate(() => {
    const out = [];
    const walk = (el, path) => { if (el.nodeType !== 1) return; if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE' || el.tagName === 'NOSCRIPT' || el.tagName === 'SVG' || el.closest('[data-mermaid]')) return; const attrs = [...el.attributes].filter(a => !/^(style|data-state|aria-expanded|aria-controls|id|aria-labelledby|aria-describedby|tabindex|data-radix|data-orientation)/.test(a.name)).map(a => a.name + '=' + a.value.slice(0, 60)).sort().join(' '); out.push(path + ' <' + el.tagName.toLowerCase() + ' ' + attrs + '> ' + (el.childNodes.length && el.firstChild.nodeType === 3 ? el.firstChild.textContent.trim().slice(0, 40) : '')); let i = 0; for (const c of el.children) walk(c, path + '/' + el.tagName.toLowerCase() + '[' + (i++) + ']'); };
    walk(document.body, '');
    return out;
  });
  await p.close(); return s;
}
const a = await snap(false), h = await snap(true);
console.log('server nodes', a.length, 'hydrated nodes', h.length);
let n = 0;
for (let i = 0; i < Math.min(a.length, h.length) && n < 8; i++) { if (a[i] !== h[i]) { console.log('DIFF @', i, '\n  server:  ', a[i].slice(0, 300), '\n  client:  ', h[i].slice(0, 300)); n++; } }
await b.close();
