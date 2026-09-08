import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);
import puppeteer from 'puppeteer-core';
const [site, q] = process.argv.slice(2);
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--no-sandbox'] });
const p = await b.newPage(); await p.setViewport({ width: 1440, height: 900 });
p.on('console', m => { if (m.type() === 'error') console.log('console.error:', m.text().slice(0, 200)); });
p.on('requestfailed', r => console.log('reqfail', r.url()));
if (site === 'fuma') {
  await p.goto('http://127.0.0.1:8002/docs/', { waitUntil: 'load' }); await new Promise(r => setTimeout(r, 500));
  await p.evaluate(() => { const b=[...document.querySelectorAll('button[data-search], button[data-search-full]')].find(e=>e.getBoundingClientRect().width>0); b.click(); }); await new Promise(r => setTimeout(r, 500));
  const inp = await p.waitForSelector('[role="dialog"] input', { visible: true, timeout: 5000 });
  const t0 = Date.now(); await inp.type(q);
  let dump = '';
  for (let i = 0; i < 150; i++) { dump = await p.evaluate(() => document.querySelector('[role="dialog"]')?.innerText || ''); if (/\n.*\n.*\n/.test(dump) && !/loading|검색 중/i.test(dump) && dump.length > 60) break; await new Promise(r => setTimeout(r, 100)); }
  console.log('ms', Date.now() - t0); console.log(dump.slice(0, 900));
  require('node:fs').writeFileSync('fuma-dialog.html', await p.evaluate(() => document.querySelector('[role="dialog"]').outerHTML)); console.log(await p.evaluate(() => [...document.querySelectorAll('[role="dialog"] *')].filter(e => e.getAttribute('role') || e.hasAttribute('data-value') || e.tagName === 'A').slice(0, 10).map(e => e.tagName + ' role=' + e.getAttribute('role') + ' ' + (e.getAttribute('href') || '') + ' ' + e.className.toString().slice(0, 40))));
} else if (site === 'zensical') {
  await p.goto('http://127.0.0.1:8004/', { waitUntil: 'load' }); await new Promise(r => setTimeout(r, 500)); await p.keyboard.press('/'); await new Promise(r => setTimeout(r, 800)); console.log('active:', await p.evaluate(() => document.activeElement.tagName + '.' + document.activeElement.className + ' shadow=' + !!document.activeElement.shadowRoot)); await p.keyboard.type(q); await new Promise(r => setTimeout(r, 2000)); console.log(await p.evaluate(() => document.body.innerText.slice(0, 600))); await p.screenshot({ path: '../shots/zensical-search.png' }); await b.close(); process.exit(0);
  await p.goto('http://127.0.0.1:8004/', { waitUntil: 'load' }); await new Promise(r => setTimeout(r, 500));
  await p.evaluate(() => { const b=[...document.querySelectorAll('label[for="__search"], .md-search__button, [data-md-toggle=search]')].find(e=>e.getBoundingClientRect().width>0); (b||document.querySelector('label[for="__search"]')).click(); }); await new Promise(r => setTimeout(r, 800));
  console.log(await p.evaluate(() => [...document.querySelectorAll('input')].map(i => i.className + '|' + i.type + '|' + (i.placeholder || ''))));
  const inp = await p.waitForSelector('input[type="search"], input[type="text"], .md-search__input', { visible: true, timeout: 5000 });
  const t0 = Date.now(); await inp.type(q); await new Promise(r => setTimeout(r, 1500));
  const dump = await p.evaluate(() => (document.querySelector('.md-search__output, .md-search-result, [class*="search"] [class*="result"]')?.innerText || document.body.innerText.slice(0, 200)));
  console.log('ms', Date.now() - t0); console.log(dump.slice(0, 700));
  console.log(await p.evaluate(() => [...document.querySelectorAll('[class*="search-result"], [class*="search__"]')].slice(0, 8).map(e => e.tagName + '.' + e.className)));
}
await p.screenshot({ path: `../shots/${site}-search-dbg.png` });
await b.close();
