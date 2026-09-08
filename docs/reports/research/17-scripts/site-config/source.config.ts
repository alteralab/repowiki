import { defineConfig } from 'fumadocs-mdx/config';
import { remarkMdxMermaid, remarkDirectiveAdmonition } from 'fumadocs-core/mdx-plugins';
import remarkDirective from 'remark-directive';
import { visit } from 'unist-util-visit';

// :::details[title] ... ::: -> <Accordions><Accordion title="..."> (collapsible source list, works in plain .md)
function remarkDetailsDirective() {
  return (tree: any) => {
    visit(tree, 'containerDirective', (node: any) => {
      if (node.name !== 'details') return;
      let title = 'Details';
      const body: any[] = [];
      for (const c of node.children) {
        if (c.type === 'paragraph' && c.data?.directiveLabel) title = c.children.map((x: any) => x.value ?? '').join('');
        else body.push(c);
      }
      Object.assign(node, {
        type: 'mdxJsxFlowElement', name: 'Accordions',
        attributes: [{ type: 'mdxJsxAttribute', name: 'type', value: 'single' }],
        children: [{ type: 'mdxJsxFlowElement', name: 'Accordion', attributes: [{ type: 'mdxJsxAttribute', name: 'title', value: title }], children: body }],
      });
    });
  };
}

export default defineConfig({
  mdxOptions: {
    remarkPlugins: (v) => [remarkDirective, remarkDetailsDirective, remarkDirectiveAdmonition, ...v, remarkMdxMermaid],
  },
});
