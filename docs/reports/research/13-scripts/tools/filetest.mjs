import puppeteer from 'puppeteer-core';
import path from 'node:path';
const [name, indexPath, deepRel, sectionText, deepText, searchQ] = process.argv.slice(2);
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--no-sandbox', '--allow-file-access-from-files', '--disable-web-security'] });
const p = await b.newPage(); await p.setViewport({ width: 1440, height: 900 });
await p.evaluateOnNewDocument(() => { const o = Element.prototype.attachShadow; Element.prototype.attachShadow = function (init) { return o.call(this, { ...init, mode: 'open' }); }; });
const failed = new Set(); p.on('requestfailed', r => failed.add(r.url().replace(/^file:\/\/.*docs-site\//, '')));
p.on('response', r => { if (r.status() >= 400) failed.add(r.status() + ' ' + r.url().slice(-80)); });
const out = { name };
await p.goto('file://' + path.resolve(indexPath), { waitUntil: 'load' }); await new Promise(r => setTimeout(r, 2500));
out.indexCss = await p.evaluate(() => { let n = 0; for (const s of document.styleSheets) { try { n += s.cssRules.length > 0 ? 1 : 0; } catch {} } return { sheetsWithRules: n, bodyFont: getComputedStyle(document.body).fontFamily.slice(0, 30), sidebarLinks: document.querySelectorAll('nav a, aside a').length }; });
out.indexSvg = await p.evaluate(() => { const a = [...document.querySelectorAll('svg')].filter(s => (s.id || '').includes('mermaid') || s.closest('.mermaid, [data-mermaid], pre.mermaid')); for (const d of document.querySelectorAll('.mermaid')) if (d.shadowRoot) a.push(...d.shadowRoot.querySelectorAll('svg')); return a.length; });
// click section link
try {
  const before = p.url();
  await p.evaluate((t) => { const a = [...document.querySelectorAll('a')].find(a => a.textContent.trim().startsWith(t)); a.click(); }, sectionText);
  await new Promise(r => setTimeout(r, 2500));
  out.afterSectionClick = { url: p.url().replace(/^.*docs-site\//, ''), h1: await p.evaluate(() => document.querySelector('h1')?.textContent.trim().slice(0, 40)), title: await p.title() };
  await p.evaluate((t) => { const a = [...document.querySelectorAll('a')].find(a => a.textContent.trim().startsWith(t)); if (a) a.click(); else throw new Error('no link ' + t); }, deepText);
  await new Promise(r => setTimeout(r, 3000));
  out.afterDeepClick = { url: p.url().replace(/^.*docs-site\//, ''), h1: await p.evaluate(() => document.querySelector('h1')?.textContent.trim().slice(0, 40)) };
  out.deepSvg = await p.evaluate(() => { const a = [...document.querySelectorAll('svg')].filter(s => (s.id || '').includes('mermaid') || s.closest('.mermaid, [data-mermaid], pre.mermaid')); for (const d of document.querySelectorAll('.mermaid')) if (d.shadowRoot) a.push(...d.shadowRoot.querySelectorAll('svg')); return a.length; });
} catch (e) { out.navError = String(e).slice(0, 120); }
// direct deep load + dark toggle + search
await p.goto('file://' + path.resolve(deepRel), { waitUntil: 'load' }); await new Promise(r => setTimeout(r, 2500));
out.deepDirect = { css: await p.evaluate(() => { let n = 0; for (const s of document.styleSheets) { try { n += s.cssRules.length > 0 ? 1 : 0; } catch {} } return n; }), svg: await p.evaluate(() => { const a = [...document.querySelectorAll('svg')].filter(s => (s.id || '').includes('mermaid') || s.closest('.mermaid, [data-mermaid], pre.mermaid')); for (const d of document.querySelectorAll('.mermaid')) if (d.shadowRoot) a.push(...d.shadowRoot.querySelectorAll('svg')); return a.length; }) };
const bg0 = await p.evaluate(() => getComputedStyle(document.body).backgroundColor);
try {
  await p.evaluate(() => { const c = [...document.querySelectorAll('label[for^="__palette"], button[aria-label*="Theme" i], button[aria-label*="테마" i], starlight-theme-select select, button[data-theme-toggle], [data-md-color-media] + label')]; const el = c.find(e => e.getBoundingClientRect().width > 0); if (!el) throw new Error('no toggle'); if (el.tagName === 'SELECT') { el.value = 'dark'; el.dispatchEvent(new Event('change', { bubbles: true })); } else el.click(); });
  await new Promise(r => setTimeout(r, 1500));
  out.darkToggle = { before: bg0, after: await p.evaluate(() => getComputedStyle(document.body).backgroundColor) };
} catch (e) { out.darkToggle = String(e).slice(0, 80); }
try {
  await p.evaluate(() => { const c = [...document.querySelectorAll('.md-search__input, button[data-search], button[data-search-full], site-search button, label[for="__search"]')]; const el = c.find(e => e.getBoundingClientRect().width > 0); if (!el) throw new Error('no search'); el.click(); });
  await new Promise(r => setTimeout(r, 600));
  await p.keyboard.type(searchQ); await new Promise(r => setTimeout(r, 8000));
  out.search = await p.evaluate(() => { const t = document.body.innerText; const res = document.querySelectorAll('.md-search-result__item, [role="dialog"] button[aria-selected], .pagefind-ui__result').length; return { results: res, hasKeyword: /ReplicaManager|복제 관리자/.test(t), sample: (document.querySelector('.md-search-result__item, [role="dialog"] button[aria-selected], .pagefind-ui__result')?.innerText || '').replace(/\s+/g, ' ').slice(0, 80) }; });
} catch (e) { out.search = String(e).slice(0, 80); }
out.failedRequests = [...failed].filter(u => /pagefind|mermaid/.test(u)).slice(0, 8); out.failedCount = failed.size;
await p.screenshot({ path: `../shots/${name}-file-deep.png` });
console.log(JSON.stringify(out, null, 1));
await b.close();
