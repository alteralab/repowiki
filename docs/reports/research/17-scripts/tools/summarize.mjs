import fs from 'node:fs';
const sites = process.argv.slice(2);
const kb = n => n == null ? '-' : (n / 1024).toFixed(0) + 'K';
for (const s of sites) {
  const f = `../report-${s}-loopback.json`; if (!fs.existsSync(f)) { console.log('missing', s); continue; }
  const r = JSON.parse(fs.readFileSync(f, 'utf8'));
  console.log(`\n===== ${s}`);
  for (const pn of ['index', 'deep', 'heavy']) {
    const P = r.pages[pn]; const L = P['light-1440'], W = P['light-1920'], D = P['dark-1440'], M = P.mobile;
    const bt = L.load.byType; const js = bt.Script?.bytes || 0, css = bt.Stylesheet?.bytes || 0, doc = bt.Document?.bytes || 0, xhr = (bt.XHR?.bytes || 0) + (bt.Fetch?.bytes || 0) + (bt.Other?.bytes || 0);
    console.log(`[${pn}] load=${L.load.loadMs}ms fcp=${L.load.paint['first-contentful-paint']}ms svgReady=${L.load.svgReadyMs}ms (${L.load.svgCount}/${L.load.expectDiagrams}) transferred=${kb(L.load.transferredBytes)} (doc ${kb(doc)} js ${kb(js)} css ${kb(css)} xhr ${kb(xhr)}) raw=${kb(L.load.rawBytes)}`);
    console.log(`  svg@1440: ` + L.diagrams.svgs.map(x => `${x.renderedW}/${x.nativeW}px(cont ${x.containerW}, scrollW ${x.containerScrollW}, ox ${x.containerOverflowX}${x.clipped ? ' CLIPPED' : ''}${x.hscroll ? ' HSCROLL' : ''}, n${x.nodes} e${x.edges}, fs ${x.fontSize})`).join(' | '));
    console.log(`  svg@1920: ` + W.diagrams.svgs.map(x => `${x.renderedW}/${x.nativeW}px(cont ${x.containerW})`).join(' | ') + `  docScrollW@1440=${L.diagrams.docScrollWidth}`);
    console.log(`  dark: bodyBg=${D.features.bodyBg} link=${D.features.linkColor} contrast=${D.features.linkContrast} mermaid nodeFill/text: ` + D.diagrams.svgs.slice(0, 2).map(x => `${x.nodeFill}/${x.textColor}`).join(' | '));
    console.log(`  light: link=${L.features.linkColor} contrast=${L.features.linkContrast}`);
    const sb = L.sidebar; console.log(`  sidebar: links=${sb.totalLinks} visible=${sb.visibleLinks} maxDepth=${sb.maxDepth} width=${sb.sidebarWidth} current=${JSON.stringify(sb.current)} first=${JSON.stringify(sb.sample.slice(0, 4))}`);
    console.log(`  toc: ${JSON.stringify(L.toc)} follow=${JSON.stringify(L.tocFollow)}`);
    const ft = L.features; console.log(`  features: breadcrumb=${ft.hasBreadcrumb} copyMd=${JSON.stringify(ft.copyMd)} calloutTop=${ft.calloutTop} h1Top=${ft.h1Top} h1Count=${ft.h1Count} headingSkips=${ft.headingSkips} levels=${ft.headingLevels.join('')} lastUpdated=${ft.hasLastUpdated} lang=${ft.lang}`);
    console.log(`  axe: ${JSON.stringify(L.axe)}`);
    console.log(`  mobile: docScrollW=${M.diagrams.docScrollWidth} svgs=${JSON.stringify(M.diagrams.svgs)} drawer=${JSON.stringify(M.drawer)} load=${M.load.loadMs}ms svgReady=${M.load.svgReadyMs}`);
  }
  console.log('  search:'); for (const [q, v] of Object.entries(r.search.queries)) console.log(`   ${q}: hits=${v.hits} ms=${v.firstResultMs} top=${JSON.stringify((v.top3 || []).map(t => t.slice(0, 70)))} ${v.error || ''}`);
}
