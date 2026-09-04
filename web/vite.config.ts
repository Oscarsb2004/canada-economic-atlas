import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `public/` already holds the committed bundle (data/), derived renderings
// (media/) and geometry (geo/), all produced by the Python pipeline. Vite
// serves that directory verbatim at the site root, which is the whole reason
// the app needs no loader plumbing: every fetch is a plain path.
export default defineConfig({
  plugins: [react()],
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
