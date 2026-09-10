// 가독성 사다리 측정. 실제 브라우저에서 렌더해 좌표를 뽑는다(PLAN §2.5, SPEC SC-1.6).
//
// 입력: 첫 인자로 준 JSON 파일(없으면 stdin) `[{id, level, source}]`
// 출력: stdout의 JSON `[{id, level, ok, width, rendered_width, scroll_width, viewport_width,
//        hscroll, shrunk, nodes, truncated_labels, edge_points}]`
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
// 1,100이 아니다. Fumadocs 본문의 도식 컨테이너는 1440px 뷰포트에서 823px, 1920px 에서
// 834px 이다(2026-09-10 실측). 1,100으로 재던 동안 통과한 그림이 사이트에서는 넘쳤다.
const CONTENT = Number(process.env.REPOWIKI_CONTENT || 820);
const SAMPLES = 24;

// 입력은 인자로 준 파일이거나 stdin 이다. 파이프 stdin 은 macOS 에서 EAGAIN 을 내므로
// 파이썬 쪽은 파일을 준다.
const input = JSON.parse(readFileSync(process.argv[2] || 0, 'utf8'));
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
      // 폭은 그림의 원래 크기다. Mermaid는 기본으로 `max-width: 100%`를 걸어 그림을 본문에
      // 맞춰 줄이므로, 줄어든 뒤의 상자를 재면 어떤 그림도 본문을 넘지 못한다. kafka의
      // `TYPE-Admin`은 원본 5,187px이 1,100px로 줄어 글자가 21% 크기였는데 이 자는 통과로
      // 냈다(2026-09-10). 원본 폭은 viewBox 에 있다.
      const viewBox = (root.getAttribute('viewBox') || '').split(/\s+/).map(Number);
      const natural = viewBox.length === 4 && viewBox[2] > 0 ? viewBox[2] : box.width;
      const naturalHeight = viewBox.length === 4 && viewBox[3] > 0 ? viewBox[3] : box.height;
      // 둘을 따로 적는다. 원본이 본문보다 넓으면 사이트는 그림을 줄이거나(classDiagram 처럼
      // max-width 를 끌 수 없는 종류) 가로로 넘친다(flowchart, sequence). 어느 쪽이든 사람은
      // 못 읽으므로 둘 다 실패 사유이고, 어느 쪽인지는 기록에 남긴다.
      const scrollWidth = host.scrollWidth;

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

      // 상자 밖으로 삐져나온 글자. 시퀀스의 참가자는 `.node` 가 아니라 `<g><rect/><text/></g>`
      // 라 위의 검사가 못 본다. kafka `SEQ` 의 참가자 이름이 상자 90px 을 넘어 이웃과 겹쳤는데
      // 이 자는 잘림 0으로 냈다(2026-09-10). 같은 g 안의 rect 보다 넓은 text 는 넘친 것이다.
      for (const text of root.querySelectorAll('text')) {
        const group = text.closest('g');
        const rect = group ? group.querySelector(':scope > rect') : null;
        if (!rect) continue;
        if (text.getBoundingClientRect().width > rect.getBoundingClientRect().width + 2) truncated += 1;
      }

      const nodes = root.querySelectorAll('.node, .nodes .node, g.node, g[data-type="participant"]').length;

      // 엣지는 경로를 일정 간격으로 표본해 꺾은선으로 만든다. 교차 판정은 밖에서 한다.
      const edges = [];
      // 보이지 않는 선(`~~~`)은 관계가 아니다. Mermaid 11.17.2 는 그 선에 `flowchart-link` 를
      // 붙이지 않고 `edge-thickness-invisible` 만 붙인다(2026-09-10 실측). 혹시 붙어도 거른다.
      for (const path of root.querySelectorAll('path.flowchart-link:not(.edge-thickness-invisible), .edgePath path, path.relation')) {
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
        width: Math.round(natural),
        height: Math.round(naturalHeight),
        rendered_width: Math.round(box.width),
        scroll_width: Math.round(scrollWidth),
        content_width: content,
        hscroll: scrollWidth > content + 1,
        shrunk: natural > content + 1 && scrollWidth <= content + 1,
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
