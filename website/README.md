# Kumiki / Kigumi Website

A static [Astro](https://astro.build) site for Kumiki and the Kigumi VS Code extension.

## Local development

```bash
cd website
npm install
npm run dev
```

Then open the URL printed in the terminal (usually <http://localhost:4321/kumiki/>).

## Build

```bash
npm run build      # outputs to website/dist
npm run preview    # serves the built site
```

## Deployment

Pushes to `main` that touch `website/**` trigger
`.github/workflows/deploy-website.yml`, which builds the site and publishes
it to GitHub Pages.

To enable Pages on the repo:

1. Repo **Settings → Pages → Build and deployment → Source = GitHub Actions**.

The site is configured for a project page at
`https://minimapletinytools.github.io/kumiki/` (`base: '/kumiki'` in
`astro.config.mjs`).

### Custom domain

When pointing a custom domain at the site:

1. In `astro.config.mjs`, change `base` to `'/'` (or remove it).
2. Add a `public/CNAME` file containing the domain (e.g. `kumiki.dev`).
3. Configure the domain in **Settings → Pages → Custom domain**.

## Adding photos

Drop images into `public/photos/` and reference them as
`${import.meta.env.BASE_URL}/photos/<file>.png` from `.astro` files so the
links work in both local-dev and GitHub Pages project-page deployments.
