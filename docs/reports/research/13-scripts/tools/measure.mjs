import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import path from 'node:path';

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const ROOT = path.resolve('..');
const SHOTS = path.join(ROOT, 'shots');
const AXE = fs.readFileSync(path.join('node_modules/axe-core/axe.min.js'), 'utf8');

const SITES = {
  mkdocs:   { base: 'http://127.0.0.1:8001', prefix: '',      sidebar: '.md-sidebar--primary', toc: '.md-sidebar--secondary', current: '.md-nav__link--active', searchOpen: async p => { await p.click('.md-search__input'); }, searchInput: '.md-search__input', result: '.md-search-result__item', snippet: '.md-search-result__teaser', mobileMenu: '.md-header__button[for="__drawer"]', mermaid: '.mermaid svg, pre.mermaid svg, div.mermaid svg' },
  fuma:     { base: 'http://127.0.0.1:8002', prefix: '/docs', sidebar: '#nd-sidebar, #nd-sidebar-mobile', toc: '#nd-toc, [data-toc], nav[aria-label*="On this page"], nav[aria-label*="Table"]', current: 'a[data-active="true"], a[aria-current="page"]', searchOpen: async p => { await p.evaluate(() => { const b = [...document.querySelectorAll('button[data-search], button[data-search-full]')].find(e => e.getBoundingClientRect().width > 0); b.click(); }); }, searchInput: '[role="dialog"] input', result: '[role="dialog"] button[aria-selected]', snippet: '[role="dialog"] button[aria-selected]', mobileMenu: 'button[aria-label="Open Sidebar"]', mermaid: '[data-mermaid] svg' },
  starlight:{ base: 'http://127.0.0.1:8003', prefix: '',      sidebar: 'nav.sidebar', toc: 'starlight-toc, .right-sidebar', current: 'a[aria-current="page"]', searchOpen: async p => { await p.click('site-search button'); }, searchInput: 'site-search input, .pagefind-ui__search-input', result: '.pagefind-ui__result', snippet: '.pagefind-ui__result-excerpt', mobileMenu: 'button.sl-menu-button', mermaid: '.mermaid svg, pre.mermaid svg, [data-mermaid] svg' },
  zensical: { base: 'http://127.0.0.1:8004', prefix: '',      sidebar: '.md-sidebar--primary', toc: '.md-sidebar--secondary', current: '.md-nav__link--active', searchOpen: async p => { await p.click('.md-search__input'); }, searchInput: '.md-search__input', result: '.md-search-result__item', snippet: '.md-search-result__teaser', mobileMenu: '.md-header__button[for="__drawer"]', mermaid: '.mermaid svg, pre.mermaid svg, div.mermaid svg' },
};
const PAGES = { index: { path: '/', diagrams: 1 }, deep: { path: '/3-replication/3-2-b/3-2-4/', diagrams: null }, heavy: { path: '/2-broker/2-2-replicamanager/2-2-1/', diagrams: 3 } };
// diagrams count for deep page derived from markdown source
const deepSrc = fs.readFileSync(path.join(ROOT, 'mkdocs-test/docs/3-replication/3-2-b/3-2-4.md'), 'utf8');
PAGES.deep.diagrams = (deepSrc.match(/```mermaid/g) || []).length;

const only = process.argv[2] ? process.argv[2].split(',') : Object.keys(SITES);
const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars'] });
const report = {};

async function newPage(width, height, dark) {
  // fresh incognito context per load: Material persists the palette choice (and panzoom state) in localStorage,
  // which would otherwise leak the light choice into the dark run.
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  const origClose = page.close.bind(page);
  page.close = async () => { await origClose(); await ctx.close(); };
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: dark ? 'dark' : 'light' }]);
  await page.setCacheEnabled(false);
  // Material for MkDocs / Zensical render Mermaid into a CLOSED shadow root; force open so we can measure the SVG.
  await page.evaluateOnNewDocument(() => { const o = Element.prototype.attachShadow; Element.prototype.attachShadow = function (init) { return o.call(this, { ...init, mode: 'open' }); }; });
  return page;
}

async function loadWithMetrics(page, url, expectDiagrams, sel) {
  const cdp = await page.createCDPSession();
  await cdp.send('Network.enable');
  const res = {}; let transferred = 0, raw = 0; const byType = {};
  cdp.on('Network.responseReceived', e => { res[e.requestId] = { type: e.type, url: e.response.url, mime: e.response.mimeType }; });
  cdp.on('Network.loadingFinished', e => { const r = res[e.requestId]; if (!r) return; transferred += e.encodedDataLength; const t = r.type || 'Other'; byType[t] = byType[t] || { n: 0, bytes: 0 }; byType[t].n++; byType[t].bytes += e.encodedDataLength; });
  const t0 = Date.now();
  await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  const loadMs = Date.now() - t0;
  // poll for mermaid svgs
  let svgReadyMs = null, svgCount = 0;
  for (let i = 0; i < 300; i++) {
    svgCount = await page.evaluate((sel, G) => eval(G)(sel).length, sel, GETSVGS);
    if (svgCount >= expectDiagrams) { svgReadyMs = Date.now() - t0; break; }
    await new Promise(r => setTimeout(r, 100));
  }
  await new Promise(r => setTimeout(r, 800)); // settle
  const paint = await page.evaluate(() => { const o = {}; for (const e of performance.getEntriesByType('paint')) o[e.name] = Math.round(e.startTime); const n = performance.getEntriesByType('navigation')[0]; o.domContentLoaded = Math.round(n.domContentLoadedEventEnd); o.load = Math.round(n.loadEventEnd); o.htmlBytes = n.transferSize; return o; });
  // raw sizes: sum of response body sizes via resource timing
  raw = await page.evaluate(() => performance.getEntriesByType('resource').reduce((a, r) => a + (r.decodedBodySize || 0), 0) + (performance.getEntriesByType('navigation')[0].decodedBodySize || 0));
  await cdp.detach();
  return { loadMs, svgReadyMs, svgCount, expectDiagrams, paint, transferredBytes: transferred, rawBytes: raw, byType };
}

async function sidebarInfo(page, S) {
  return page.evaluate((sbSel, curSel) => {
    const sb = document.querySelector(sbSel);
    if (!sb) return { found: false };
    const links = [...sb.querySelectorAll('a')];
    const vis = links.filter(a => { const r = a.getBoundingClientRect(); return r.height > 0 && r.width > 0; });
    const depth = el => { let d = 0, p = el; while (p && p !== sb) { if (p.tagName === 'UL' || p.tagName === 'OL') d++; p = p.parentElement; } return d; };
    const maxDepth = Math.max(...links.map(depth));
    const curs = [...sb.querySelectorAll(curSel)]; const cur = curs.find(a => a.getBoundingClientRect().height > 0) || curs[0];
    let curInfo = null;
    if (cur) { const r = cur.getBoundingClientRect(); const sbr = sb.getBoundingClientRect(); curInfo = { text: cur.textContent.trim().slice(0, 40), visible: r.height > 0, inView: r.top >= sbr.top && r.bottom <= sbr.bottom, top: Math.round(r.top) }; }
    const firstTexts = vis.slice(0, 8).map(a => a.textContent.trim().replace(/\s+/g, ' ').slice(0, 30));
    return { found: true, totalLinks: links.length, visibleLinks: vis.length, maxDepth, current: curInfo, sample: firstTexts, sidebarWidth: Math.round(sb.getBoundingClientRect().width) };
  }, S.sidebar, S.current);
}

const GETSVGS = `(sel) => { const a = [...document.querySelectorAll(sel)]; for (const d of document.querySelectorAll('.mermaid')) if (d.shadowRoot) a.push(...d.shadowRoot.querySelectorAll('svg')); return a; }`;
async function diagramInfo(page, sel) {
  return page.evaluate((sel, G) => {
    const vw = window.innerWidth;
    const svgs = eval(G)(sel);
    return { viewport: vw, docScrollWidth: document.documentElement.scrollWidth, svgs: svgs.map(s => {
      const r = s.getBoundingClientRect(); const c = s.parentElement || s.getRootNode().host; const vb = s.getAttribute('viewBox'); const nodes = s.querySelectorAll('.node, g.node').length; const edges = s.querySelectorAll('.edgePath, path.flowchart-link, .messageLine0, .messageLine1').length;
      const cs = getComputedStyle(c);
      const txt = s.querySelector('text, foreignObject span, foreignObject div, .nodeLabel'); const fs = txt ? getComputedStyle(txt).fontSize : null;
      const rect = s.querySelector('rect.basic, .node rect, rect.actor, rect'); const fill = rect ? getComputedStyle(rect).fill : null; const tfill = txt ? getComputedStyle(txt).color || getComputedStyle(txt).fill : null;
      return { renderedW: Math.round(r.width), renderedH: Math.round(r.height), viewBox: vb, nativeW: vb ? Math.round(+vb.split(/[ ,]+/)[2]) : null, containerW: c.clientWidth, containerScrollW: c.scrollWidth, containerOverflowX: cs.overflowX, clipped: c.scrollWidth > c.clientWidth + 2 && cs.overflowX === 'hidden', hscroll: c.scrollWidth > c.clientWidth + 2 && (cs.overflowX === 'auto' || cs.overflowX === 'scroll'), nodes, edges, fontSize: fs, nodeFill: fill, textColor: tfill, styleMaxWidth: s.style.maxWidth, styleW: s.getAttribute('width') };
    }) };
  }, sel, GETSVGS);
}

async function tocInfo(page, S) {
  return page.evaluate((tocSel) => {
    const toc = document.querySelector(tocSel);
    if (!toc) return { found: false };
    const r = toc.getBoundingClientRect(); const links = toc.querySelectorAll('a');
    return { found: true, rightSide: r.left > window.innerWidth * 0.6, left: Math.round(r.left), links: links.length, visible: r.width > 0 && r.height > 0 };
  }, S.toc);
}

async function tocFollows(page, S) {
  // scroll to a late heading and see what's marked active
  const before = await page.evaluate((tocSel) => { const t = document.querySelector(tocSel); if (!t) return null; const a = t.querySelector('a[aria-current], a.md-nav__link--active, a[data-active="true"], a[aria-current="true"]'); return a ? a.textContent.trim() : null; }, S.toc);
  await page.evaluate(() => { const hs = document.querySelectorAll('article h2, main h2, .md-content h2'); const h = hs[hs.length - 1]; if (h) h.scrollIntoView(); });
  await new Promise(r => setTimeout(r, 900));
  const after = await page.evaluate((tocSel) => { const t = document.querySelector(tocSel); if (!t) return null; const a = t.querySelector('a[aria-current], a.md-nav__link--active, a[data-active="true"], a[aria-current="true"]'); return a ? a.textContent.trim() : null; }, S.toc);
  await page.evaluate(() => window.scrollTo(0, 0));
  return { before, after, follows: before !== after && after != null };
}

async function pageFeatures(page) {
  return page.evaluate(() => {
    const txt = document.body.innerText;
    const hasBreadcrumb = !!document.querySelector('nav[aria-label*="bread" i], .md-path, [class*="breadcrumb" i], .md-header__topic + .md-path') || !!document.querySelector('nav ol li a + svg');
    const btns = [...document.querySelectorAll('button, a')].map(b => (b.getAttribute('aria-label') || b.textContent || '').trim()).filter(Boolean);
    const copyMd = btns.filter(t => /copy markdown|markdown|open in|llm|chatgpt|claude|llms/i.test(t)).slice(0, 6);
    const callout = [...document.querySelectorAll('*')].find(e => e.children.length < 6 && /분석 커밋/.test(e.textContent) && e.getBoundingClientRect().height < 200);
    const h1 = document.querySelector('h1'); const calloutTop = callout ? Math.round(callout.getBoundingClientRect().top) : null;
    const hs = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(h => +h.tagName[1]);
    let skips = 0; for (let i = 1; i < hs.length; i++) if (hs[i] - hs[i - 1] > 1) skips++;
    const hasLastUpdated = /last updated|마지막 업데이트|최종 수정|업데이트/i.test(txt);
    const lang = document.documentElement.lang;
    const link = document.querySelector('article a[href*="github.com"], main a[href*="github.com"], .md-content a[href*="github.com"]');
    const cs = link ? getComputedStyle(link) : null; const bg = getComputedStyle(document.body).backgroundColor;
    return { hasBreadcrumb, copyMd, calloutTop, h1Top: h1 ? Math.round(h1.getBoundingClientRect().top) : null, headingLevels: hs.slice(0, 12), headingSkips: skips, h1Count: hs.filter(x => x === 1).length, hasLastUpdated, lang, linkColor: cs?.color, bodyBg: bg, pageBg: getComputedStyle(document.documentElement).backgroundColor };
  });
}

function lum(c) { const m = c && c.match(/\d+(\.\d+)?/g); if (!m) return null; const [r, g, b] = m.map(Number).slice(0, 3).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; }
function contrast(a, b) { const la = lum(a), lb = lum(b); if (la == null || lb == null) return null; const [h, l] = la > lb ? [la, lb] : [lb, la]; return +((h + 0.05) / (l + 0.05)).toFixed(2); }

async function axeRun(page) {
  await page.evaluate(AXE);
  const r = await page.evaluate(async () => { const res = await axe.run(document, { runOnly: ['wcag2a', 'wcag2aa'] }); return res.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })); });
  return r;
}

async function searchTest(page, S, base, prefix) {
  const out = { indexBytes: null, queries: {} };
  const idxFiles = { mkdocs: 'mkdocs-test/site/search/search_index.json', fuma: 'fuma-static/out/api/search', starlight: 'starlight-test/dist/pagefind', zensical: 'zensical-test/proj/site/search/search_index.json' };
  await page.goto(base + prefix + '/', { waitUntil: 'load' });
  for (const q of ['컴포넌트', '복제 관리자', '리더 에포크 캐시가 절단 지점을 결정한다', 'ReplicaManager', '퍼거토리']) {
    try {
      await page.goto(base + prefix + '/', { waitUntil: 'load' });
      await new Promise(r => setTimeout(r, 500));
      await S.searchOpen(page);
      await new Promise(r => setTimeout(r, 500));
      const input = await page.waitForSelector(S.searchInput, { visible: true, timeout: 5000 });
      await input.click({ clickCount: 3 });
      const t0 = Date.now();
      await input.type(q, { delay: 10 });
      let n = 0, ms = null;
      for (let i = 0; i < 100; i++) { n = await page.$$eval(S.result, els => els.filter(e => e.getBoundingClientRect().height > 0).length); if (n > 0) { ms = Date.now() - t0; break; } await new Promise(r => setTimeout(r, 100)); }
      await new Promise(r => setTimeout(r, 400));
      n = await page.$$eval(S.result, els => els.length);
      const first = await page.$$eval(S.result, els => els.slice(0, 3).map(e => e.innerText.replace(/\s+/g, ' ').slice(0, 160)));
      out.queries[q] = { hits: n, firstResultMs: ms, top3: first };
      if (q === '컴포넌트') { await page.screenshot({ path: path.join(SHOTS, `${S.name}-search.png`) }); }
    } catch (e) { out.queries[q] = { error: String(e).slice(0, 120) }; }
  }
  return out;
}

for (const name of only) {
  const S = SITES[name]; S.name = name;
  const prevFile = path.join(ROOT, `report-${name}.json`);
  const R = report[name] = process.env.SEARCH_ONLY && fs.existsSync(prevFile) ? JSON.parse(fs.readFileSync(prevFile, 'utf8')) : { pages: {} };
  for (const [pn, P] of Object.entries(PAGES)) {
    if (process.env.SEARCH_ONLY) break;
    const url = S.base + S.prefix + P.path;
    const PR = R.pages[pn] = { url };
    for (const [mode, dark] of [['light', false], ['dark', true]]) {
      for (const [vp, w, h] of [['1440', 1440, 900], ['1920', 1920, 1080]]) {
        if (mode === 'dark' && vp === '1920') continue;
        const page = await newPage(w, h, dark);
        const m = await loadWithMetrics(page, url, P.diagrams, S.mermaid);
        const d = await diagramInfo(page, S.mermaid);
        const rec = { load: m, diagrams: d };
        if (vp === '1440') {
          rec.sidebar = await sidebarInfo(page, S);
          rec.toc = await tocInfo(page, S);
          rec.features = await pageFeatures(page);
          rec.features.linkContrast = contrast(rec.features.linkColor, rec.features.bodyBg !== 'rgba(0, 0, 0, 0)' ? rec.features.bodyBg : rec.features.pageBg);
          await page.screenshot({ path: path.join(SHOTS, `${name}-${pn}-${mode}-desktop.png`) });
          if (mode === 'light') { rec.tocFollow = await tocFollows(page, S); try { rec.axe = await axeRun(page); } catch (e) { rec.axe = String(e).slice(0, 100); } }
        }
        PR[`${mode}-${vp}`] = rec;
        await page.close();
      }
    }
    // mobile
    const page = await newPage(390, 844, false);
    const m = await loadWithMetrics(page, url, P.diagrams, S.mermaid);
    const d = await diagramInfo(page, S.mermaid);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${pn}-light-mobile.png`) });
    let drawer = null;
    try { const btn = await page.$(S.mobileMenu); if (btn) { await btn.click(); await new Promise(r => setTimeout(r, 700)); await page.screenshot({ path: path.join(SHOTS, `${name}-${pn}-mobile-drawer.png`) }); drawer = await page.evaluate((sbSel) => { const cands = [...document.querySelectorAll(sbSel + ', #nd-sidebar-mobile, [role="dialog"], #starlight__sidebar, .md-sidebar--primary')]; const sb = cands.find(e => { const r = e.getBoundingClientRect(); return r.width > 100 && r.height > 200 && r.left > -5 && r.left < 200; }); if (!sb) return { found: false, cands: cands.length }; const r = sb.getBoundingClientRect(); return { found: true, id: sb.id || sb.className.slice(0, 40), width: Math.round(r.width), left: Math.round(r.left), links: sb.querySelectorAll('a').length }; }, S.sidebar); } } catch (e) { drawer = String(e).slice(0, 80); }
    PR.mobile = { load: m, diagrams: { docScrollWidth: d.docScrollWidth, viewport: d.viewport, svgs: d.svgs.map(s => ({ renderedW: s.renderedW, containerW: s.containerW, containerScrollW: s.containerScrollW, hscroll: s.hscroll, clipped: s.clipped })) }, drawer };
    await page.close();
    // dark mobile shot only
    const pd = await newPage(390, 844, true); await pd.goto(url, { waitUntil: 'load' }); await new Promise(r => setTimeout(r, 2500)); await pd.screenshot({ path: path.join(SHOTS, `${name}-${pn}-dark-mobile.png`) }); await pd.close();
  }
  const sp = await newPage(1440, 900, false);
  R.search = await searchTest(sp, S, S.base, S.prefix);
  await sp.close();
  fs.writeFileSync(path.join(ROOT, `report-${name}.json`), JSON.stringify(R, null, 1));
  console.log('done', name);
}
await browser.close();
