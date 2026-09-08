import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--no-sandbox'] });
const p = await b.newPage(); await p.setViewport({ width: 1440, height: 900 }); await p.evaluateOnNewDocument(() => { const o = Element.prototype.attachShadow; Element.prototype.attachShadow = function (init) { return o.call(this, { ...init, mode: 'open' }); }; });
const GETSVGS = `(sel) => { const a = [...document.querySelectorAll(sel)]; for (const d of document.querySelectorAll('.mermaid')) if (d.shadowRoot) a.push(...d.shadowRoot.querySelectorAll('svg')); return a; }`;
const t0 = Date.now();
await p.goto(process.argv[2], { waitUntil: 'load' });
for (let i = 0; i < 100; i++) { const n = await p.evaluate((sel, G) => eval(G)(sel).length, '.mermaid svg', GETSVGS); if (n > 0) { console.log('svgs', n, 'at', Date.now() - t0, 'ms'); break; } await new Promise(r => setTimeout(r, 100)); }
console.log(await p.evaluate(() => [...document.querySelectorAll('.mermaid')].map(d => ({ shadow: !!d.shadowRoot, inner: d.innerHTML.length, shadowSvg: d.shadowRoot ? d.shadowRoot.querySelectorAll('svg').length : -1 }))));
await b.close();
