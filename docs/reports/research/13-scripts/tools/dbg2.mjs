import puppeteer from 'puppeteer-core';
const url = process.argv[2];
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--no-sandbox'] });
const p = await b.newPage(); await p.setViewport({ width: 1440, height: 900 });
p.on('console', m => console.log('console:', m.type(), m.text().slice(0, 300)));
p.on('pageerror', e => console.log('pageerror:', String(e).slice(0, 300)));
await p.setRequestInterception(false);
const html = await (await fetch(url)).text();
const m = html.match(/<pre class="mermaid"><code>([\s\S]*?)<\/code><\/pre>/);
const chart = m[1].replace(/&quot;/g, '"').replace(/&gt;/g, '>').replace(/&lt;/g, '<').replace(/&amp;/g, '&');
await p.goto(url, { waitUntil: 'networkidle0' });
await new Promise(r => setTimeout(r, 1500));
const r = await p.evaluate(async (chart) => {
  try { const { svg } = await mermaid.render('dbg1', chart); return { ok: true, len: svg.length, head: svg.slice(0, 120) }; } catch (e) { return { ok: false, err: String(e).slice(0, 400) }; }
}, chart);
console.log(r);
console.log(await p.evaluate(() => [...document.querySelectorAll('.mermaid')].map(d => ({ tag: d.tagName, html: d.innerHTML.length, parent: d.parentElement.className, prev: d.previousElementSibling?.className }))));
await b.close();
