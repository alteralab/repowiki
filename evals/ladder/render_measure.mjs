// 가독성 사다리 측정. 실제 브라우저에서 렌더해 좌표를 뽑는다(PLAN §2.5, SPEC SC-1.6).
//
// 입력: stdin의 JSON `[{id, level, source}]`
// 출력: stdout의 JSON `[{id, level, ok, width, viewport_width, hscroll, nodes,
//        truncated_labels, edge_points}]`
//
// jsdom에는 레이아웃이 없어 `getBBox`가 없다. 그래서 텍스트 실측이 필요한 이 측정은
// 실제 Chrome을 쓴다. 시스템에 설치된 Chrome을 몰고 다운로드하지 않는다.
// 엣지 교차 수는 여기서 세지 않는다. 좌표만 내고 판정은 파이썬이 한다(C-DEPTH-3).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import puppeteer from 'puppeteer-core';

const HERE = dirname(fileURLToPath(import.meta.url));
const HOST = resolve(HERE, 'host.html');
const CHROME = process.env.REPOWIKI_CHROME
  || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const VIEWPORT = Number(process.env.REPOWIKI_VIEWPORT || 1440);
// 사이트의 본문 너비. 사다리는 다이어그램이 본문 안에서 읽히는지를 본다.
const CONTENT = Number(process.env.REPOWIKI_CONTENT || 1100);
const SAMPLES = 24;

const input = JSON.parse(readFileSync(0, 'utf8'));
// 레이아웃 엔진. 기본은 mermaid 내장 dagre이고, elk는 사다리의 두 번째 단이다.
const LAYOUT = process.env.REPOWIKI_LAYOUT || 'dagre';

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox', '--allow-file-access-from-files'],
});
const page = await browser.newPage();
await page.setViewport({ width: VIEWPORT, height: 1200, deviceScaleFactor: 1 });
await page.goto(`file://${HOST}`);
await page.waitForFunction(() => window.__ready === true, { timeout: 30000 });
await page.evaluate((content) => {
  document.getElementById('host').style.width = `${content}px`;
}, CONTENT);

const results = [];
for (const { id, level, source } of input) {
  const measured = await page.evaluate(
    async (source, samples, content, layout) => {
      const host = document.getElementById('host');
      host.innerHTML = '';
      try {
        const prepared = layout === 'dagre' ? source : `%%{init: {"layout": "${layout}"}}%%\n${source}`;
        const { svg } = await window.mermaid.render(`d${Date.now()}`, prepared);
        host.innerHTML = svg;
      } catch (error) {
        return { ok: false, error: String(error?.message ?? error).slice(0, 200) };
      }
      const root = host.querySelector('svg');
      if (!root) return { ok: false, error: 'svg 없음' };
      const box = root.getBoundingClientRect();

      // 라벨 잘림: 텍스트의 실제 폭이 담는 상자의 폭을 넘으면 잘린 것이다.
      let truncated = 0;
      const labels = [];
      for (const text of root.querySelectorAll('text, .nodeLabel, .edgeLabel')) {
        const rect = text.getBoundingClientRect();
        const parent = text.closest('.node, .edgeLabel, .label');
        const owner = parent ? parent.getBoundingClientRect() : null;
        const clipped = owner ? rect.width > owner.width + 1 : false;
        if (clipped) truncated += 1;
        labels.push({ width: Math.round(rect.width), owner: owner ? Math.round(owner.width) : null });
      }

      const nodes = root.querySelectorAll('.node, .nodes .node, g.node').length;

      // 엣지는 경로를 일정 간격으로 표본해 꺾은선으로 만든다. 교차 판정은 밖에서 한다.
      const edges = [];
      for (const path of root.querySelectorAll('path.flowchart-link, .edgePath path, path.relation')) {
        const total = path.getTotalLength();
        if (!total) continue;
        const points = [];
        for (let i = 0; i <= samples; i += 1) {
          const point = path.getPointAtLength((total * i) / samples);
          points.push([Math.round(point.x * 100) / 100, Math.round(point.y * 100) / 100]);
        }
        edges.push(points);
      }
      return {
        ok: true,
        width: Math.round(box.width),
        height: Math.round(box.height),
        content_width: content,
        hscroll: box.width > content + 1,
        nodes,
        truncated_labels: truncated,
        label_count: labels.length,
        edge_points: edges,
      };
    },
    source,
    SAMPLES,
    CONTENT,
    LAYOUT,
  );
  results.push({ id, level, layout: LAYOUT, viewport_width: VIEWPORT, ...measured });
}

await browser.close();
process.stdout.write(JSON.stringify(results));
