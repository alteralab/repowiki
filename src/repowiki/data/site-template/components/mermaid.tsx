'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { useTheme } from 'next-themes';

// Client-side Mermaid (bundled `mermaid` npm package; no CDN). Adds a click-to-open zoom/pan overlay
// (wheel = zoom, drag = pan, Esc/click outside = close). ~40 lines, no extra dependency.
//
// 색은 마크다운에 들어 있지 않다. 소스에는 `:::rwFocus` 같은 역할 표식만 있고, 이 컴포넌트가
// 현재 테마에 맞는 `classDef` 줄을 렌더 직전에 앞에 붙인다. 이유가 셋이다.
//  1. 다크와 라이트가 둘 다 맞는다. 고정 hex를 마크다운에 박으면 한쪽에서 읽히지 않는다.
//  2. 마크다운의 소스 문자 상한(다이어그램 게이트)을 색이 먹지 않는다.
//  3. classDef가 없어도 `:::표식`만으로 정상 렌더되므로, GitHub에서 원문을 봐도 안 깨진다.
// 셋 다 2026-09-09에 Chrome으로 실측했다. classDiagram은 mermaid가 id 스코프 `!important`
// 규칙을 내서 classDef도 외부 CSS도 이기지 못한다 — 그래서 역할 표식은 flowchart에만 붙인다.

// 역할별 색. flowchart 노드에만 쓴다. 뜻이 먼저이고 색은 그 뜻의 표현이다.
//   rwFocus = 이 쪽이 다루는 주인공, rwEntry = 진입점이 있는 자리, rwTest = 테스트
const CLASS_DEFS: Record<'light' | 'dark', string> = {
  light: [
    'classDef rwFocus fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a5f',
    'classDef rwEntry fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d',
    'classDef rwTest fill:#f1f5f9,stroke:#94a3b8,stroke-dasharray:4 3,color:#475569',
  ].join('\n'),
  dark: [
    'classDef rwFocus fill:#1e3a5f,stroke:#60a5fa,stroke-width:2px,color:#dbeafe',
    'classDef rwEntry fill:#14532d,stroke:#4ade80,stroke-width:2px,color:#dcfce7',
    'classDef rwTest fill:#1e293b,stroke:#64748b,stroke-dasharray:4 3,color:#94a3b8',
  ].join('\n'),
};

// 역할 표식이 쓰인 그림에만 정의를 붙인다. 안 쓰는 정의를 넣으면 소스만 길어진다.
function withRoles(chart: string, mode: 'light' | 'dark'): string {
  if (!/:::rw[A-Z]/.test(chart)) return chart;
  const lines = chart.split('\n');
  // 첫 줄은 `%%{init}%%` 지시문이거나 `flowchart ...` 머리다. 정의는 머리 바로 뒤에 온다.
  const head = lines[0]?.trimStart().startsWith('%%') ? 1 : 0;
  const defs = CLASS_DEFS[mode].split('\n').map((line) => '  ' + line);
  return [...lines.slice(0, head + 1), ...defs, ...lines.slice(head + 1)].join('\n');
}
export function Mermaid({ chart }: { chart: string }) {
  const id = useId();
  const [svg, setSvg] = useState('');
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    void (async () => {
      const { default: mermaid } = await import('mermaid');
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'loose',
        fontFamily: 'inherit',
        theme: resolvedTheme === 'dark' ? 'dark' : 'default',
        flowchart: { useMaxWidth: false },
        sequence: { useMaxWidth: false },
      });
      try {
        const source = withRoles(chart.replaceAll('\\n', '\n'), resolvedTheme === 'dark' ? 'dark' : 'light');
        const { svg, bindFunctions } = await mermaid.render(id.replaceAll(':', '_'), source);
        setSvg(svg);
        bindFunctions?.(container);
      } catch (e) {
        setSvg(`<pre class="text-red-500">Mermaid error: ${String(e)}</pre>`);
      }
    })();
  }, [chart, id, resolvedTheme]);

  return (
    <>
      <div
        ref={containerRef}
        data-mermaid=""
        title="클릭하면 확대/이동 보기"
        className="my-4 overflow-x-auto cursor-zoom-in rounded-lg border border-fd-border p-2"
        onClick={() => setOpen(true)}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      {open && <ZoomOverlay svg={svg} onClose={() => setOpen(false)} />}
    </>
  );
}

function ZoomOverlay({ svg, onClose }: { svg: string; onClose: () => void }) {
  const [t, setT] = useState({ x: 0, y: 0, k: 1 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div
      data-mermaid-zoom=""
      className="fixed inset-0 z-50 bg-fd-background/95 overflow-hidden cursor-grab"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      onWheel={(e) => { e.preventDefault(); const k = Math.min(8, Math.max(0.2, t.k * (e.deltaY < 0 ? 1.1 : 0.9))); setT({ ...t, k }); }}
      onPointerDown={(e) => { drag.current = { x: e.clientX - t.x, y: e.clientY - t.y }; }}
      onPointerMove={(e) => { if (drag.current) setT({ ...t, x: e.clientX - drag.current.x, y: e.clientY - drag.current.y }); }}
      onPointerUp={() => { drag.current = null; }}
    >
      <div className="absolute top-3 right-3 flex gap-2 text-sm">
        <span className="rounded bg-fd-muted px-2 py-1">{Math.round(t.k * 100)}% · 휠=확대 · 드래그=이동 · Esc=닫기</span>
        <button className="rounded bg-fd-primary px-2 py-1 text-fd-primary-foreground" onClick={onClose}>닫기</button>
      </div>
      <div style={{ transform: `translate(${t.x}px, ${t.y}px) scale(${t.k})`, transformOrigin: '0 0' }} className="p-8 inline-block" dangerouslySetInnerHTML={{ __html: svg }} />
    </div>
  );
}
