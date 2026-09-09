import defaultMdxComponents from 'fumadocs-ui/mdx';
import { Accordion, Accordions } from 'fumadocs-ui/components/accordion';
// 근거 파일 목록을 디렉토리 트리로 낸다. `bundle/site_emit.py`가 위키의 `<details>`를
// 이 컴포넌트로 바꾼다. 위키 원문은 GitHub 에서 보이도록 `<details>` 그대로 둔다.
import { File, Files, Folder } from 'fumadocs-ui/components/files';
import { Callout, CalloutContainer, CalloutTitle, CalloutDescription } from 'fumadocs-ui/components/callout';
import type { MDXComponents } from 'mdx/types';
import { Mermaid } from './mermaid';

export function getMDXComponents(components?: MDXComponents) {
  return {
    ...defaultMdxComponents,
    Mermaid,
    Accordion,
    Accordions,
    File,
    Files,
    Folder,
    Callout,
    CalloutContainer,
    CalloutTitle,
    CalloutDescription,
    ...components,
  } satisfies MDXComponents;
}

export const useMDXComponents = getMDXComponents;

declare global {
  type MDXProvidedComponents = ReturnType<typeof getMDXComponents>;
}
