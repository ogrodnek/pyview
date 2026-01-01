import { describe, it, expect } from 'vitest';
import { remarkStripFirstHeading, remarkRewriteMdLinks } from './remark-plugins.mjs';

describe('remarkStripFirstHeading', () => {
  it('removes first h1 heading', () => {
    const tree = {
      children: [
        { type: 'heading', depth: 1, children: [{ type: 'text', value: 'Title' }] },
        { type: 'paragraph', children: [{ type: 'text', value: 'Content' }] },
      ],
    };

    remarkStripFirstHeading()(tree);

    expect(tree.children).toHaveLength(1);
    expect(tree.children[0].type).toBe('paragraph');
  });

  it('does not remove h2 headings', () => {
    const tree = {
      children: [
        { type: 'heading', depth: 2, children: [{ type: 'text', value: 'Subtitle' }] },
        { type: 'paragraph', children: [{ type: 'text', value: 'Content' }] },
      ],
    };

    remarkStripFirstHeading()(tree);

    expect(tree.children).toHaveLength(2);
    expect(tree.children[0].type).toBe('heading');
  });

  it('handles empty tree', () => {
    const tree = { children: [] };

    remarkStripFirstHeading()(tree);

    expect(tree.children).toHaveLength(0);
  });

  it('does not remove h1 if not first element', () => {
    const tree = {
      children: [
        { type: 'paragraph', children: [{ type: 'text', value: 'Intro' }] },
        { type: 'heading', depth: 1, children: [{ type: 'text', value: 'Title' }] },
      ],
    };

    remarkStripFirstHeading()(tree);

    expect(tree.children).toHaveLength(2);
  });
});

describe('remarkRewriteMdLinks', () => {
  it('rewrites .md links to trailing slash', () => {
    const tree = {
      type: 'root',
      children: [
        {
          type: 'paragraph',
          children: [
            { type: 'link', url: 'getting-started.md', children: [] },
          ],
        },
      ],
    };

    remarkRewriteMdLinks()(tree);

    expect(tree.children[0].children[0].url).toBe('getting-started/');
  });

  it('preserves anchor links', () => {
    const tree = {
      type: 'root',
      children: [
        {
          type: 'paragraph',
          children: [
            { type: 'link', url: 'guide.md#section', children: [] },
          ],
        },
      ],
    };

    remarkRewriteMdLinks()(tree);

    expect(tree.children[0].children[0].url).toBe('guide/#section');
  });

  it('handles relative paths', () => {
    const tree = {
      type: 'root',
      children: [
        {
          type: 'paragraph',
          children: [
            { type: 'link', url: '../other/page.md', children: [] },
          ],
        },
      ],
    };

    remarkRewriteMdLinks()(tree);

    expect(tree.children[0].children[0].url).toBe('../other/page/');
  });

  it('does not modify http links', () => {
    const tree = {
      type: 'root',
      children: [
        {
          type: 'paragraph',
          children: [
            { type: 'link', url: 'https://example.com/file.md', children: [] },
          ],
        },
      ],
    };

    remarkRewriteMdLinks()(tree);

    expect(tree.children[0].children[0].url).toBe('https://example.com/file.md');
  });

  it('does not modify non-.md links', () => {
    const tree = {
      type: 'root',
      children: [
        {
          type: 'paragraph',
          children: [
            { type: 'link', url: '/about/', children: [] },
          ],
        },
      ],
    };

    remarkRewriteMdLinks()(tree);

    expect(tree.children[0].children[0].url).toBe('/about/');
  });
});
