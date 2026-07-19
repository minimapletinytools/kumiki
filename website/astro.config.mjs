import { defineConfig } from 'astro/config';

// GitHub Pages project-page config. When a custom domain is attached later,
// drop `base` (or set it to '/') and add `public/CNAME` containing the domain.
export default defineConfig({
  site: 'https://kumiki.build',
  trailingSlash: 'ignore',
});
