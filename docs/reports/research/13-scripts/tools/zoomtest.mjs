import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--no-sandbox'] });
const P = '/2-broker/2-2-replicamanager/2-2-1/';
const tests = {
  mkdocs: { url: 'http://127.0.0.1:8001' + P, sel: '.panzoom-box .mermaid', kind: 'panzoom' },
  fuma: { url: 'http://127.0.0.1:8002/docs' + P, sel: '[data-mermaid]', kind: 'overlay', overlay: '[data-mermaid-zoom]' },
  starlight: { url: 'http://127.0.0.1:8003' + P, sel: 'pre.mermaid[data-processed]', kind: 'overlay', overlay: '#mermaid-zoom' },
};
for (const [name, t] of Object.entries(tests)) {
  const p = await b.newPage(); await p.setViewport({ width: 1440, height: 900 });
  await p.evaluateOnNewDocument(() => { const o = Element.prototype.attachShadow; Element.prototype.attachShadow = function (init) { return o.call(this, { ...init, mode: 'open' }); }; });
  await p.goto(t.url, { waitUntil: 'load' }); await new Promise(r => setTimeout(r, 2500));
  const el = await p.waitForSelector(t.sel, { timeout: 10000 });
  await el.scrollIntoView(); const box = await el.boundingBox();
  const cx = box.x + box.width / 2, cy = box.y + Math.min(box.height / 2, 200);
  if (t.kind === 'panzoom') {
    const before = await p.$eval(t.sel, e => e.style.transform);
    await p.mouse.move(cx, cy); await p.keyboard.down('Alt'); await p.mouse.wheel({ deltaY: -300 }); await p.keyboard.up('Alt'); await new Promise(r => setTimeout(r, 500));
    const after = await p.$eval(t.sel, e => e.style.transform);
    const fs = await p.$('.panzoom-box button[title*="ull"], .panzoom-box .panzoom-fullscreen, .panzoom-nav button');
    console.log(name, 'alt+wheel transform', before, '->', after, 'changed:', before !== after, '| nav buttons:', await p.$$eval('.panzoom-nav button, .panzoom-nav a', els => els.map(e => e.getAttribute('title') || e.getAttribute('aria-label') || e.className)));
    await p.screenshot({ path: `../shots/${name}-heavy-zoomed.png` });
  } else {
    await p.mouse.click(cx, cy); await new Promise(r => setTimeout(r, 500));
    const ov = await p.$(t.overlay);
    let scale = null;
    if (ov) { await p.mouse.move(700, 450); await p.mouse.wheel({ deltaY: -300 }); await p.mouse.wheel({ deltaY: -300 }); await new Promise(r => setTimeout(r, 300)); scale = await p.evaluate((s) => document.querySelector(s).innerText.match(/\d+%/)?.[0], t.overlay); }
    console.log(name, 'overlay opened:', !!ov, 'zoom after 2 wheel steps:', scale, '| svg width in overlay:', ov ? await p.evaluate((s) => Math.round(document.querySelector(s).querySelector('svg').getBoundingClientRect().width), t.overlay) : null);
    await p.screenshot({ path: `../shots/${name}-heavy-zoomed.png` });
    await p.keyboard.press('Escape'); await new Promise(r => setTimeout(r, 300));
    console.log('  closed with Esc:', !(await p.$(t.overlay)));
  }
  await p.close();
}
await b.close();
