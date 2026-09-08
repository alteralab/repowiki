// Extra checks for Fumadocs under a loopback http.server (research 17):
// breadcrumbs, prev/next, TOC, SPA navigation chain with failed requests + console errors,
// dark toggle, Korean search incl. particle-suffixed queries, llms.txt / content.md, Mermaid max-width CSS variant.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import path from 'node:path';

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const BASE = process.argv[2] || 'http://127.0.0.1:8002';
const OUT = process.argv[3] || '../report-fuma-extras.json';
const SHOTS = path.resolve('../shots');
const P = { index: '/docs/', section: '/docs/2-broker/', heavy: '/docs/2-broker/2-2-replicamanager/2-2-1/', deep: '/docs/3-replication/3-2-b/3-2-4/' };
const R = { base: BASE };
const sleep = ms => new Promise(r => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars'] });
async function fresh(width = 1440, height = 900, dark = false) {
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: dark ? 'dark' : 'light' }]);
  const failed = [], consoleErrors = [], requests = [];
  page.on('requestfailed', r => failed.push('FAILED ' + r.failure()?.errorText + ' ' + r.url()));
  page.on('response', r => { if (r.status() >= 400) failed.push(r.status() + ' ' + r.url()); });
  page.on('request', r => requests.push(r.url()));
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') consoleErrors.push(m.type() + ': ' + m.text().slice(0, 200)); });
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + String(e).slice(0, 200)));
  page.diag = { failed, consoleErrors, requests };
  page.closeAll = async () => { await page.close(); await ctx.close(); };
  return page;
}

// 1. Navigation affordances on the deep page
{
  const p = await fresh();
  await p.goto(BASE + P.deep, { waitUntil: 'networkidle0' });
  R.deepNav = await p.evaluate(() => {
    const txt = s => s ? s.textContent.replace(/\s+/g, ' ').trim() : null;
    const bc = document.querySelector('nav[aria-label*="bread" i], [class*="breadcrumb" i], nav ol');
    const bcItems = bc ? [...bc.querySelectorAll('a, li, span')].map(e => e.textContent.trim()).filter(t => t && t.length < 60) : [];
    const links = [...document.querySelectorAll('a')];
    const prev = links.find(a => /previous|이전|prev/i.test(a.getAttribute('aria-label') || '') || a.querySelector('svg.lucide-chevron-left, .lucide-chevron-left'));
    const next = links.find(a => /next|다음/i.test(a.getAttribute('aria-label') || '') || a.querySelector('svg.lucide-chevron-right, .lucide-chevron-right'));
    const footerLinks = [...document.querySelectorAll('article a, main a')].filter(a => { const r = a.getBoundingClientRect(); return r.top > 0; });
    const pn = footerLinks.filter(a => /2-broker|3-replication|3-2/.test(a.getAttribute('href') || '') && a.closest('[class*="footer" i], [data-pagination], nav')).map(a => ({ href: a.getAttribute('href'), text: txt(a).slice(0, 50) }));
    const toc = document.querySelector('#nd-toc, [data-toc], nav[aria-label*="On this page" i], nav[aria-label*="Table" i]');
    const sb = document.querySelector('#nd-sidebar');
    const sbLinks = sb ? [...sb.querySelectorAll('a')] : [];
    const depth = el => { let d = 0, q = el; while (q && q !== sb) { if (q.tagName === 'UL' || q.tagName === 'OL' || q.getAttribute?.('data-level')) d++; q = q.parentElement; } return d; };
    const active = sb ? sb.querySelector('a[data-active="true"], a[aria-current="page"]') : null;
    const folders = sb ? sb.querySelectorAll('[data-state], button[aria-expanded]').length : 0;
    const openFolders = sb ? sb.querySelectorAll('[data-state="open"], button[aria-expanded="true"]').length : 0;
    return {
      title: document.title, h1: txt(document.querySelector('h1')),
      breadcrumb: { found: !!bc, items: bcItems.slice(0, 8) },
      prev: prev ? { href: prev.getAttribute('href'), text: txt(prev).slice(0, 60) } : null,
      next: next ? { href: next.getAttribute('href'), text: txt(next).slice(0, 60) } : null,
      paginationCandidates: pn.slice(0, 4),
      toc: toc ? { links: toc.querySelectorAll('a').length, left: Math.round(toc.getBoundingClientRect().left), right: toc.getBoundingClientRect().left > innerWidth * 0.6 } : null,
      sidebar: { links: sbLinks.length, visible: sbLinks.filter(a => a.getBoundingClientRect().height > 0).length, maxDepth: Math.max(...sbLinks.map(depth)), folders, openFolders, active: active ? { text: txt(active).slice(0, 40), inView: (() => { const r = active.getBoundingClientRect(), s = sb.getBoundingClientRect(); return r.top >= s.top && r.bottom <= s.bottom; })() } : null },
      copyMd: [...document.querySelectorAll('button, a')].map(b => (b.getAttribute('aria-label') || b.textContent || '').trim()).filter(t => /copy markdown|open in|markdown/i.test(t)).slice(0, 5),
    };
  });
  await p.screenshot({ path: path.join(SHOTS, 'fuma-loopback-deep-desktop.png') });
  R.deepNav.failedRequests = p.diag.failed; R.deepNav.consoleErrors = p.diag.consoleErrors; R.deepNav.requestCount = p.diag.requests.length;
  await p.closeAll();
}

// 2. SPA navigation chain: index -> section -> heavy -> deep via sidebar clicks, then browser back
{
  const p = await fresh();
  await p.goto(BASE + P.index, { waitUntil: 'networkidle0' });
  await p.evaluate(() => { window.__marker = 42; });
  const chain = [];
  async function clickSidebar(text) {
    const t0 = Date.now();
    const before = p.diag.requests.length;
    const ok = await p.evaluate((t) => { const a = [...document.querySelectorAll('#nd-sidebar a')].find(a => a.textContent.trim().startsWith(t)); if (!a) return false; a.click(); return true; }, text);
    if (!ok) { chain.push({ text, error: 'link not found' }); return; }
    await p.waitForFunction((t) => document.querySelector('h1') && document.querySelector('h1').textContent.includes(t.split(' ')[0].replace(/\.$/, '')), { timeout: 15000 }, text).catch(() => {});
    await p.waitForNetworkIdle({ idleTime: 500, timeout: 15000 }).catch(() => {});
    const soft = await p.evaluate(() => window.__marker === 42);
    const newReqs = p.diag.requests.slice(before);
    chain.push({ text, ms: Date.now() - t0, softNav: soft, url: p.url().replace(BASE, ''), h1: await p.$eval('h1', e => e.textContent.trim().slice(0, 50)), newRequests: newReqs.length, rscTxt: newReqs.filter(u => /\.txt(\?|$)/.test(u)).length, svg: await p.$$eval('[data-mermaid] svg', e => e.length) });
  }
  await clickSidebar('2. 브로커 코어');
  await clickSidebar('2.2 ReplicaManager');
  await clickSidebar('2.2.1');
  await clickSidebar('3. 복제와 리더 선출');
  await p.goBack({ waitUntil: 'networkidle0' }).catch(() => {});
  await sleep(500);
  chain.push({ back: true, softNav: await p.evaluate(() => window.__marker === 42), url: p.url().replace(BASE, ''), h1: await p.$eval('h1', e => e.textContent.trim().slice(0, 50)).catch(() => null) });
  R.spaChain = { chain, failedRequests: p.diag.failed, consoleErrors: p.diag.consoleErrors, totalRequests: p.diag.requests.length };
  await p.closeAll();
}

// 3. Dark toggle on heavy page: click the theme toggle, check body bg and mermaid node fill re-render
{
  const p = await fresh(1440, 900, false);
  await p.goto(BASE + P.heavy, { waitUntil: 'networkidle0' });
  await p.waitForFunction(() => document.querySelectorAll('[data-mermaid] svg').length >= 3, { timeout: 20000 }).catch(() => {});
  const grab = () => p.evaluate(() => { const rect = document.querySelector('[data-mermaid] svg .node rect, [data-mermaid] svg rect'); return { bodyBg: getComputedStyle(document.body).backgroundColor, html: document.documentElement.className, nodeFill: rect ? getComputedStyle(rect).fill : null, svgs: document.querySelectorAll('[data-mermaid] svg').length }; });
  const before = await grab();
  const toggled = await p.evaluate(() => { const c = [...document.querySelectorAll('button[aria-label*="theme" i], button[data-theme-toggle], [data-theme-toggle] button, button[aria-label*="Toggle" i]')]; const el = c.find(e => e.getBoundingClientRect().width > 0); if (!el) return { found: false, candidates: c.length }; el.click(); return { found: true, label: el.getAttribute('aria-label') }; });
  await sleep(1500);
  const after = await grab();
  await p.screenshot({ path: path.join(SHOTS, 'fuma-loopback-heavy-toggled.png') });
  R.darkToggle = { toggled, before, after, changed: before.bodyBg !== after.bodyBg, mermaidRerendered: before.nodeFill !== after.nodeFill, consoleErrors: p.diag.consoleErrors, failedRequests: p.diag.failed };
  await p.closeAll();
}

// 4. Korean search incl. particle-suffixed queries (static Orama index over http.server)
{
  const p = await fresh();
  await p.goto(BASE + P.index, { waitUntil: 'networkidle0' });
  const qs = ['컴포넌트', '컴포넌트는', '퍼거토리', '퍼거토리에서', '복제 관리자', '복제 관리자가', 'ReplicaManager', '리더 에포크 캐시가 절단 지점을 결정한다', 'ㅋㅍ'];
  R.search = { queries: {} };
  for (const q of qs) {
    try {
      await p.goto(BASE + P.index, { waitUntil: 'networkidle0' });
      const before = p.diag.requests.length;
      await p.evaluate(() => { const b = [...document.querySelectorAll('button[data-search], button[data-search-full]')].find(e => e.getBoundingClientRect().width > 0); b.click(); });
      const input = await p.waitForSelector('[role="dialog"] input', { visible: true, timeout: 5000 });
      await input.click({ clickCount: 3 });
      const t0 = Date.now();
      await input.type(q, { delay: 10 });
      let n = 0, ms = null;
      for (let i = 0; i < 100; i++) { n = await p.$$eval('[role="dialog"] button[aria-selected]', els => els.filter(e => e.getBoundingClientRect().height > 0).length); if (n > 0) { ms = Date.now() - t0; break; } await sleep(100); }
      await sleep(400);
      n = await p.$$eval('[role="dialog"] button[aria-selected]', els => els.length);
      const top3 = await p.$$eval('[role="dialog"] button[aria-selected]', els => els.slice(0, 3).map(e => e.innerText.replace(/\s+/g, ' ').slice(0, 120)));
      const idx = p.diag.requests.slice(before).filter(u => /api\/search/.test(u));
      R.search.queries[q] = { hits: n, firstResultMs: ms, top3, indexFetches: idx.length };
      if (q === '컴포넌트는') await p.screenshot({ path: path.join(SHOTS, 'fuma-loopback-search-particle.png') });
      // Enter on first result: does it navigate to the page?
      if (n > 0 && q === '리더 에포크 캐시가 절단 지점을 결정한다') { await p.keyboard.press('Enter'); await sleep(1500); R.search.queries[q].enterNavigatedTo = p.url().replace(BASE, ''); }
    } catch (e) { R.search.queries[q] = { error: String(e).slice(0, 150) }; }
  }
  R.search.indexBytes = fs.statSync('../site/out/api/search').size;
  R.search.failedRequests = p.diag.failed; R.search.consoleErrors = p.diag.consoleErrors;
  await p.closeAll();
}

// 5. llms.txt, llms-full.txt, per-page content.md, .md rewrite, served by http.server
{
  const p = await fresh();
  const get = async (u) => { const r = await p.goto(BASE + u, { waitUntil: 'load' }).catch(e => null); if (!r) return { url: u, error: 'nav failed' }; const body = await r.text().catch(() => ''); return { url: u, status: r.status(), contentType: r.headers()['content-type'], bytes: body.length, head: body.slice(0, 160).replace(/\n/g, '\\n') }; };
  R.llms = [await get('/llms.txt'), await get('/llms-full.txt'), await get('/llms.mdx/docs/2-broker/2-2-replicamanager/2-2-1/content.md'), await get('/docs/2-broker/2-2-replicamanager/2-2-1.md'), await get('/docs/2-broker/2-2-replicamanager/2-2-1/index.md')];
  // does the per-page markdown still carry JSX from the directive transform?
  const md = await (await p.goto(BASE + '/llms.mdx/docs/2-broker/2-2-replicamanager/2-2-1/content.md')).text();
  R.llmsMdJsx = { hasCalloutJsx: /<Callout/.test(md), hasAccordionJsx: /<Accordion/.test(md), hasMermaidJsx: /<Mermaid/.test(md), mermaidFence: (md.match(/```mermaid/g) || []).length, sample: (md.match(/<[A-Z][A-Za-z]+[^>]*>/g) || []).slice(0, 5) };
  await p.closeAll();
}

// 6. Mermaid at 1440: native size vs CSS max-width:100% variant; zoom overlay
{
  for (const variant of ['native', 'maxwidth']) {
    const p = await fresh();
    if (variant === 'maxwidth') await p.evaluateOnNewDocument(() => { document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); s.textContent = '[data-mermaid] svg { max-width: 100%; height: auto; }'; document.head.appendChild(s); }); });
    await p.goto(BASE + P.heavy, { waitUntil: 'networkidle0' });
    await p.waitForFunction(() => document.querySelectorAll('[data-mermaid] svg').length >= 3, { timeout: 20000 }).catch(() => {});
    await sleep(300);
    const info = await p.evaluate(() => [...document.querySelectorAll('[data-mermaid] svg')].map(s => { const r = s.getBoundingClientRect(); const c = s.parentElement; const vb = s.getAttribute('viewBox'); const txt = s.querySelector('.nodeLabel, text'); const fs = txt ? getComputedStyle(txt).fontSize : null; const scale = vb ? r.width / (+vb.split(/[ ,]+/)[2]) : null; return { renderedW: Math.round(r.width), renderedH: Math.round(r.height), nativeW: vb ? Math.round(+vb.split(/[ ,]+/)[2]) : null, containerW: c.clientWidth, containerScrollW: c.scrollWidth, hscroll: c.scrollWidth > c.clientWidth + 2, scale: scale ? +scale.toFixed(2) : null, effectiveFontPx: fs && scale ? +(parseFloat(fs) * scale).toFixed(1) : null, nodes: s.querySelectorAll('.node, g.node').length }; }));
    const docScrollW = await p.evaluate(() => document.documentElement.scrollWidth);
    await p.evaluate(() => document.querySelector('[data-mermaid]').scrollIntoView());
    await p.screenshot({ path: path.join(SHOTS, `fuma-loopback-heavy-${variant}.png`) });
    R[`mermaid_${variant}`] = { svgs: info, docScrollWidth: docScrollW };
    if (variant === 'native') {
      const el = await p.$('[data-mermaid]'); const box = await el.boundingBox();
      await p.mouse.click(box.x + box.width / 2, box.y + Math.min(box.height / 2, 200)); await sleep(500);
      const ov = await p.$('[data-mermaid-zoom]');
      let zoom = null, w = null;
      if (ov) { await p.mouse.move(700, 450); await p.mouse.wheel({ deltaY: -300 }); await p.mouse.wheel({ deltaY: -300 }); await sleep(300); zoom = await p.evaluate(() => document.querySelector('[data-mermaid-zoom]').innerText.match(/\d+%/)?.[0]); w = await p.evaluate(() => Math.round(document.querySelector('[data-mermaid-zoom] svg').getBoundingClientRect().width)); await p.screenshot({ path: path.join(SHOTS, 'fuma-loopback-heavy-zoomed.png') }); await p.keyboard.press('Escape'); await sleep(300); }
      R.zoomOverlay = { opened: !!ov, zoomAfter2Wheel: zoom, svgWidthInOverlay: w, closedWithEsc: !(await p.$('[data-mermaid-zoom]')) };
    }
    await p.closeAll();
  }
}

// 7. Page weight without gzip (http.server sends identity encoding) on heavy page
{
  const p = await fresh();
  const cdp = await p.createCDPSession(); await cdp.send('Network.enable');
  let enc = 0, raw = 0; const byType = {};
  const res = {};
  cdp.on('Network.responseReceived', e => { res[e.requestId] = e.type; });
  cdp.on('Network.loadingFinished', e => { enc += e.encodedDataLength; const t = res[e.requestId] || 'Other'; byType[t] = byType[t] || { n: 0, bytes: 0 }; byType[t].n++; byType[t].bytes += e.encodedDataLength; });
  await p.goto(BASE + P.heavy, { waitUntil: 'networkidle0' });
  await p.waitForFunction(() => document.querySelectorAll('[data-mermaid] svg').length >= 3, { timeout: 20000 }).catch(() => {});
  R.heavyWeightNoGzip = { transferredBytes: enc, byType, requests: p.diag.requests.length, failed: p.diag.failed, consoleErrors: p.diag.consoleErrors };
  await p.closeAll();
}

await browser.close();
fs.writeFileSync(OUT, JSON.stringify(R, null, 1));
console.log(JSON.stringify(R, null, 1));
