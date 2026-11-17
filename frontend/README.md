# Abarusura RFC website

The public site, built with SvelteKit as static files. The design is in `../docs/design.md`.

Use Node 24 (`nvm use` in this folder reads `.nvmrc`).

- `npm ci` installs the exact pinned versions.
- `npm run dev` starts the site on your machine.
- `npm run lint` type-checks the app, the configs and the e2e tests.
- `npx vitest run` runs the unit tests.
- `npx playwright test` runs the browser tests. It starts Directus from `../directus` first, so run `../directus/make-env.sh` once before.
- `npm run build` writes the site to `build/`.

The site reads Directus at `VITE_DIRECTUS_URL`, which defaults to `http://localhost:8065`.
