import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import { remarkStripFirstHeading, remarkRewriteMdLinks } from './remark-plugins.mjs';

export default defineConfig({
  site: 'https://pyview.rocks',
  markdown: {
    remarkPlugins: [remarkStripFirstHeading, remarkRewriteMdLinks],
  },
  vite: {
    resolve: {
      preserveSymlinks: true,
    },
  },
  integrations: [
    starlight({
      title: 'PyView',
      logo: {
        src: './src/assets/pyview_logo_512.png',
      },
      social: {
        github: 'https://github.com/ogrodnek/pyview',
      },
      customCss: ['./src/styles/custom.css'],
      sidebar: [
        { label: 'Home', slug: '' },
        { label: 'Getting Started', slug: 'getting-started' },
        {
          label: 'Live Examples',
          link: 'https://examples.pyview.rocks',
          badge: 'Live',
          attrs: { target: '_blank' },
        },
        { label: 'Single-File Apps', slug: 'single-file-apps' },
        { label: 'Streams', slug: 'streams-usage' },
        {
          label: 'Core Concepts',
          autogenerate: { directory: 'core-concepts' },
        },
        {
          label: 'Templating',
          autogenerate: { directory: 'templating' },
        },
        {
          label: 'Features',
          items: [
            { label: 'Authentication', slug: 'features/authentication' },
            {
              label: 'File Uploads',
              items: [
                { label: 'Overview', slug: 'features/file-uploads' },
                { label: 'Direct Uploads', slug: 'features/file-uploads/direct' },
                { label: 'External Uploads', slug: 'features/file-uploads/external' },
              ],
            },
          ],
        },
      ],
    }),
  ],
});
