import puppeteer from 'puppeteer-core';
const bases = process.argv.slice(2);
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--no-sandbox'] });
for (const base of bases) {
  for (const u of (process.env.PAGES || '/docs/,/docs/2-broker/').split(',')) {
    const ctx = await b.createBrowserContext(); const p = await ctx.newPage(); await p.setViewport({ width: 1440, height: 900 });
    const errs = [], f = [];
    p.on('pageerror', e => errs.push(String(e).slice(0, 120))); p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text().slice(0, 120)); });
    p.on('response', r => { if (r.status() >= 400) f.push(r.status() + ' ' + r.url().replace(base, '')); });
    await p.goto(base + u, { waitUntil: 'networkidle0' }); await new Promise(r => setTimeout(r, 1000));
    const links = await p.evaluate(() => [...document.querySelectorAll('#nd-sidebar a')].filter(a => a.getBoundingClientRect().height > 0).map(a => a.textContent.trim().slice(0, 40) + ' -> ' + a.getAttribute('href')));
    const mdLinks = await p.evaluate(() => [...document.querySelectorAll('a[href*="index.md"]')].map(a => (a.textContent.trim().slice(0, 30) || a.getAttribute('aria-label')) + ' -> ' + a.getAttribute('href')));
    console.log(base + u, '| pageerrors:', errs, '| 4xx:', f.slice(0, 4), '| sidebar links:', links.slice(0, 12), '| index.md links:', mdLinks.slice(0, 5));
    await p.close(); await ctx.close();
  }
}
await b.close();
