import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--no-sandbox'] });
for (const url of process.argv.slice(2)) {
  const p = await b.newPage(); await p.setViewport({ width: 1440, height: 900 });
  await p.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'dark' }]);
  await p.goto(url, { waitUntil: 'load' }); await new Promise(r => setTimeout(r, 1500));
  console.log(url, await p.evaluate(() => ({ mm: matchMedia('(prefers-color-scheme: dark)').matches, scheme: document.body.getAttribute('data-md-color-scheme'), htmlTheme: document.documentElement.getAttribute('data-theme') || document.documentElement.className, bg: getComputedStyle(document.body).backgroundColor, palette: [...document.querySelectorAll('input[data-md-color-media]')].map(i => [i.getAttribute('data-md-color-media'), i.getAttribute('data-md-color-scheme'), i.checked]) })));
  await p.close();
}
await b.close();
