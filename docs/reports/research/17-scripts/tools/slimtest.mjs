// Does client-side navigation survive when RSC .txt payloads are stripped from the export? (research 13: it silently falls back to full reloads)
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--no-sandbox'] });
for (const base of process.argv.slice(2)) {
  const p = await b.newPage(); await p.setViewport({ width: 1440, height: 900 });
  const f = [], errs = [];
  p.on('response', r => { if (r.status() >= 400) f.push(r.status() + ' ' + r.url().replace(base, '')); });
  p.on('pageerror', e => errs.push(String(e).slice(0, 100)));
  await p.goto(base + '/docs/', { waitUntil: 'networkidle0' });
  await p.evaluate(() => { window.__marker = 42; });
  const t0 = Date.now();
  await p.evaluate(() => { [...document.querySelectorAll('#nd-sidebar a')].find(a => a.textContent.trim().startsWith('2. 브로커 코어')).click(); });
  await p.waitForFunction(() => location.pathname.includes('2-broker') && document.querySelector('h1')?.textContent.includes('2.'), { timeout: 20000 }).catch(() => {});
  await p.waitForNetworkIdle({ idleTime: 500, timeout: 10000 }).catch(() => {});
  const soft = await p.evaluate(() => window.__marker === 42);
  console.log(base, '| nav ms', Date.now() - t0, '| soft(SPA) nav:', soft, '| url:', p.url().replace(base, ''), '| h1:', await p.$eval('h1', e => e.textContent).catch(() => null), '| svg:', await p.$$eval('[data-mermaid] svg', e => e.length), '| 4xx:', f.slice(0, 3), '| errors:', [...new Set(errs)].slice(0, 2));
  await p.close();
}
await b.close();
