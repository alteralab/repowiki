// file:// diagnosis: per page, list failed requests (by kind), console errors, CSS applied, sidebar links, Mermaid SVGs, dark toggle, search, first-click target.
import puppeteer from 'puppeteer-core';
import path from 'node:path';
const [outDir, label] = process.argv.slice(2);
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--no-sandbox', '--allow-file-access-from-files'] });
const pages = ['index.html', 'docs/index.html', 'docs/3-replication/3-2-b/3-2-4/index.html'];
const out = { label, pages: {} };
for (const rel of pages) {
  const p = await b.newPage(); await p.setViewport({ width: 1440, height: 900 });
  const failed = [], errs = [];
  p.on('requestfailed', r => failed.push(r.failure()?.errorText + ' ' + r.url().replace('file://' + path.resolve(outDir), '<out>')));
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 160)); });
  p.on('pageerror', e => errs.push('pageerror: ' + String(e).slice(0, 160)));
  await p.goto('file://' + path.resolve(outDir, rel), { waitUntil: 'load' }); await new Promise(r => setTimeout(r, 3000));
  const info = await p.evaluate(() => ({
    css: [...document.styleSheets].filter(s => { try { return s.cssRules.length > 0; } catch { return false; } }).length,
    bodyBg: getComputedStyle(document.body).backgroundColor,
    scripts: [...document.scripts].map(s => s.src).filter(Boolean).length,
    hydrated: !!document.querySelector('[data-search], button[data-search-full]'),
    svg: document.querySelectorAll('[data-mermaid] svg').length,
    mermaidBlocks: document.querySelectorAll('[data-mermaid]').length,
    firstSidebarHref: document.querySelector('#nd-sidebar a[href*="2-broker"]')?.getAttribute('href') || null,
    themeToggle: !!document.querySelector('button[aria-label*="Theme" i]'),
  }));
  let toggle = null, search = null;
  try { const bg0 = info.bodyBg; await p.evaluate(() => document.querySelector('button[aria-label*="Theme" i]').click()); await new Promise(r => setTimeout(r, 800)); toggle = { before: bg0, after: await p.evaluate(() => getComputedStyle(document.body).backgroundColor) }; } catch (e) { toggle = 'no toggle (not hydrated)'; }
  try { await p.evaluate(() => { const el = [...document.querySelectorAll('button[data-search], button[data-search-full]')].find(e => e.getBoundingClientRect().width > 0); el.click(); }); await new Promise(r => setTimeout(r, 500)); await p.keyboard.type('ReplicaManager'); await new Promise(r => setTimeout(r, 4000)); search = { results: await p.$$eval('[role="dialog"] button[aria-selected]', e => e.length) }; } catch (e) { search = 'no search button (not hydrated)'; }
  const kinds = {}; for (const f of failed) { const k = /_next\/static/.test(f) ? 'asset(_next/static)' : /\.txt/.test(f) ? 'rsc(.txt)' : /api\/search/.test(f) ? 'search index' : 'other'; kinds[k] = (kinds[k] || 0) + 1; }
  out.pages[rel] = { ...info, darkToggle: toggle, search, failedRequests: failed.length, failedKinds: kinds, failedSample: failed.slice(0, 3), consoleErrors: [...new Set(errs)].slice(0, 5) };
  await p.close();
}
console.log(JSON.stringify(out, null, 1));
await b.close();
