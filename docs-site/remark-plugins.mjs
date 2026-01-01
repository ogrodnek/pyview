import { visit } from 'unist-util-visit';

// Strips the first # heading if present (Starlight renders title from frontmatter)
export function remarkStripFirstHeading() {
  return (tree) => {
    const firstChild = tree.children[0];
    if (firstChild?.type === 'heading' && firstChild.depth === 1) {
      tree.children.shift();
    }
  };
}

// Rewrites .md links to work in Starlight (e.g., "foo.md" -> "/foo/", "foo.md#bar" -> "/foo/#bar")
export function remarkRewriteMdLinks() {
  return (tree) => {
    visit(tree, 'link', (node) => {
      if (node.url && node.url.includes('.md') && !node.url.startsWith('http')) {
        // Remove .md extension and add trailing slash, preserving anchors
        node.url = node.url.replace(/\.md(#|$)/, '/$1');
      }
    });
  };
}
