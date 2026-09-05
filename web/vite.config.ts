import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `public/` already holds the committed bundle (data/), derived renderings
// (media/) and geometry (geo/), all produced by the Python pipeline. Vite
// serves that directory verbatim at the site root, which is the whole reason
// the app needs no loader plumbing: every fetch is a plain path.
export default defineConfig({
  plugins: [react()],
  // A GitHub Pages PROJECT site is served from /<repo>/, not from the root, so
  // every asset URL needs that prefix. It is an env var rather than a constant
  // because the same build has to work three ways: the dev server at "/", the
  // project site, and a custom domain back at "/" again. The CI workflow sets
  // it; `npm run dev` and a root deploy both get the default.
  //
  // Paths INSIDE the committed data (media, geo) are site-absolute and are
  // resolved at render time by asset() in src/data/bundle.ts — Vite only
  // rewrites what it can see in the import graph, and the bundle is fetched.
  base: process.env.VITE_BASE || "/",
  server: { port: 5173, strictPort: false },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        // MapLibre and Plot/d3 are most of the bundle and change only when
        // their versions do. Splitting them means an app-code edit does not
        // invalidate ~1.4 MB of vendor JS in the reader's cache.
        //
        // Note this is chunking CODE, not data. The bundle under public/data is
        // still one eager load: it is 1.4 MB total, which is less than a single
        // map tile, and deferring it would add machinery for nothing.
        manualChunks: {
          maplibre: ["maplibre-gl"],
          plot: ["@observablehq/plot"],
        },
      },
    },
  },
});
