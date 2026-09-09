'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { useTheme } from 'next-themes';

// Client-side Mermaid (bundled `mermaid` npm package; no CDN). Adds a click-to-open zoom/pan overlay
// (wheel = zoom, drag = pan, Esc/click outside = close). ~40 lines, no extra dependency.
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
        const { svg, bindFunctions } = await mermaid.render(id.replaceAll(':', '_'), chart.replaceAll('\\n', '\n'));
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
